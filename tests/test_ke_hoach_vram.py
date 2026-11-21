"""
tests/test_ke_hoach_vram.py — chia VRAM cho hai server vLLM trên một GPU (#91, đo v3 và v4 song song).

VÌ SAO ĐÁNG VIẾT
----------------
Con số sai ở đây không làm sai phép đo: nó làm phiên Colab tính giờ chết lúc khởi động server thứ hai. Ba chỗ dễ sai,
mỗi chỗ một nhóm test:

  1. Làm tròn. `--gpu-memory-utilization` nhận hai chữ số; làm tròn XUỐNG cho server ít bộ nhớ hơn mức nó cần.
  2. Đọc đặc tả từ file model chứ không từ trí nhớ: KV cache một token phụ thuộc số lớp, số đầu KV, head_dim.
  3. Lệch khỏi cờ production: lệnh in ra phải dùng đúng cờ của `deploy/docker-compose.yml`.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from offline_training import ke_hoach_vram as kh
from offline_training.ke_hoach_vram import (
    TRAN_TONG_MAC_DINH,
    DacTaMoHinh,
    KeHoachLoi,
    doc_dac_ta,
    dung_luong_gpu_gib,
    kv_can_gib,
    lap_ke_hoach,
    lenh_serve,
    nhu_cau_gib,
)

ROOT = Path(__file__).resolve().parent.parent
# Dạng Qwen3-8B: 36 lớp, 8 đầu KV, head_dim 128 -> 2 x 36 x 8 x 128 x 2 = 147.456 byte mỗi token.
KV_8B = 2 * 36 * 8 * 128 * 2


def _model(tmp_path: Path, ten: str = "m", cfg: dict | None = None, kich_co: tuple[int, ...] = (1024,)) -> Path:
    d = tmp_path / ten
    d.mkdir()
    cfg = cfg if cfg is not None else {
        "num_hidden_layers": 36, "num_attention_heads": 32, "num_key_value_heads": 8,
        "head_dim": 128, "hidden_size": 4096,
    }
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    for i, n in enumerate(kich_co):
        (d / f"model-{i}.safetensors").write_bytes(b"x" * n)
    (d / "README.txt").write_bytes(b"x" * 99999)      # không phải trọng số: không được cộng vào
    return d


# ---------------------------------------------------------------------------
# 1. Đọc đặc tả
# ---------------------------------------------------------------------------

def test_kv_moi_token_theo_config_va_trong_so_cong_cac_file_weights(tmp_path):
    d = doc_dac_ta(_model(tmp_path, kich_co=(1024, 2048)))
    assert d.kv_byte_moi_token == KV_8B
    assert d.trong_so_gib == pytest.approx(3072 / 1024 ** 3), "chỉ *.safetensors, không cộng README"


def test_khong_co_head_dim_thi_chia_hidden_cho_so_dau(tmp_path):
    cfg = {"num_hidden_layers": 10, "num_attention_heads": 16, "hidden_size": 2048}
    d = doc_dac_ta(_model(tmp_path, cfg=cfg))
    # không có num_key_value_heads: coi bằng số đầu attention; head_dim = 2048/16 = 128
    assert d.kv_byte_moi_token == 2 * 10 * 16 * 128 * 2


def test_cau_hinh_nam_trong_text_config(tmp_path):
    cfg = {"text_config": {"num_hidden_layers": 4, "num_attention_heads": 8, "num_key_value_heads": 2,
                           "head_dim": 64, "hidden_size": 512}}
    assert doc_dac_ta(_model(tmp_path, cfg=cfg)).kv_byte_moi_token == 2 * 4 * 2 * 64 * 2


def test_thieu_config_thieu_weights_thieu_khoa_deu_bao_ro(tmp_path):
    rong = tmp_path / "rong"
    rong.mkdir()
    with pytest.raises(KeHoachLoi, match="config.json"):
        doc_dac_ta(rong)

    khong_weights = tmp_path / "kw"
    khong_weights.mkdir()
    (khong_weights / "config.json").write_text(json.dumps({
        "num_hidden_layers": 1, "num_attention_heads": 1, "hidden_size": 8}), encoding="utf-8")
    with pytest.raises(KeHoachLoi, match="safetensors"):
        doc_dac_ta(khong_weights)

    with pytest.raises(KeHoachLoi, match="num_hidden_layers"):
        doc_dac_ta(_model(tmp_path, ten="t", cfg={"hidden_size": 8}))


# ---------------------------------------------------------------------------
# 2. Xếp chỗ
# ---------------------------------------------------------------------------

def _dt(trong_so: float, kv: int = KV_8B, ten: str = "m") -> DacTaMoHinh:
    return DacTaMoHinh(Path(ten), trong_so, kv)


def test_mot_model_vua_ngu_canh_production():
    k = lap_ke_hoach([_dt(5.3)], 22.5)
    assert k.max_model_len == 32768


def test_hai_model_tren_gpu_22_5_gib_phai_ha_ngu_canh_xuong_duoi_32768():
    """Chép cờ production (32768) sang hai server là hết bộ nhớ ngay lúc khởi động; kế hoạch phải thấy điều đó."""
    k = lap_ke_hoach([_dt(5.3), _dt(5.3)], 22.5)
    assert 12288 <= k.max_model_len < 32768
    assert k.max_model_len == 14336          # tính tay: 2 x (5,3 + 2,5 + KV 1,74 GiB) = 19,08 <= 0,88 x 22,5 = 19,8; trùng cấu hình Thành đã đo ở #124


@pytest.mark.parametrize("gpu", [16.0, 22.5, 24.0, 40.0, 80.0])
@pytest.mark.parametrize("trong_so", [3.0, 5.3, 5.7, 7.0])
@pytest.mark.parametrize("so_server", [1, 2, 3])
def test_bat_bien_moi_server_du_bo_nho_va_tong_khong_vuot_tran(gpu, trong_so, so_server):
    """Hai chiều của cùng một lỗi làm tròn: server thiếu bộ nhớ, hoặc tổng vượt trần."""
    try:
        k = lap_ke_hoach([_dt(trong_so)] * so_server, gpu)
    except KeHoachLoi:
        return                                # không vừa thì từ chối là đúng; chỉ kiểm khi có kế hoạch
    assert k.tong_phan <= TRAN_TONG_MAC_DINH + 1e-9
    for s in k.servers:
        assert s.phan_gpu * gpu >= s.nhu_cau_gib - 1e-9, "server được cấp ÍT hơn mức nó cần"
    assert [s.cong for s in k.servers] == list(range(8001, 8001 + so_server))


def test_khong_vua_thi_tu_choi_va_noi_cach_chay_lan_luot():
    with pytest.raises(KeHoachLoi, match="LẦN LƯỢT"):
        lap_ke_hoach([_dt(9.0), _dt(9.0)], 22.5)


def test_san_ngu_canh_khong_bi_ha_xuong_duoi():
    """Hạ ngữ cảnh dưới mức prompt dài nhất là cắt prompt: thà từ chối."""
    with pytest.raises(KeHoachLoi):
        lap_ke_hoach([_dt(5.3), _dt(5.3)], 22.5, ctx_can_thiet=24576)


def test_tham_so_vo_ly_bi_chan():
    with pytest.raises(KeHoachLoi):
        lap_ke_hoach([], 22.5)
    with pytest.raises(KeHoachLoi):
        lap_ke_hoach([_dt(5.3)], 0)
    with pytest.raises(KeHoachLoi, match="ctx-can-thiet"):
        lap_ke_hoach([_dt(5.3)], 22.5, ctx_toi_da=4096, ctx_can_thiet=8192)
    with pytest.raises(KeHoachLoi, match="--ten"):
        lap_ke_hoach([_dt(5.3), _dt(5.3)], 22.5, ten=["chi-mot"])


def test_nhu_cau_bang_trong_so_cong_overhead_cong_kv():
    d = _dt(5.0)
    assert kv_can_gib(d, 1024 ** 3 // KV_8B) == pytest.approx(1.0, rel=1e-3)
    assert nhu_cau_gib(d, 0, 2.5) == pytest.approx(7.5)


def test_dau_do_bat_duoc_lam_tron_xuong():
    """Chứng minh nhóm test bất biến không câm: cấp đúng phần làm tròn XUỐNG thì ít nhất một ca thiếu bộ nhớ."""
    k = lap_ke_hoach([_dt(5.3), _dt(5.3)], 22.5)
    s = k.servers[0]
    xuong = int(s.nhu_cau_gib / 22.5 * 100) / 100
    assert xuong * 22.5 < s.nhu_cau_gib, "ca này phải là ca làm tròn xuống thì thiếu"


# ---------------------------------------------------------------------------
# 3. Lệnh in ra bám cờ production
# ---------------------------------------------------------------------------

def test_lenh_serve_dung_co_cua_compose_production():
    k = lap_ke_hoach([_dt(5.3), _dt(5.3)], 22.5, ten=["anser-v3", "anser-v4"])
    cmd = lenh_serve(k.servers[1], k.max_model_len)
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    khoi = compose.split("vllm-text:", 1)[1].split("vllm-vision:", 1)[0]
    for co in re.findall(r"--[a-z-]+", cmd):
        assert co in khoi, f"{co} có trong lệnh in ra mà không có ở service vllm-text của compose"
    assert "--served-model-name=anser-v4" in cmd and "--port=8002" in cmd
    assert f"--max-model-len={k.max_model_len}" in cmd


# ---------------------------------------------------------------------------
# 4. Dung lượng GPU: hỏi máy, không ghim
# ---------------------------------------------------------------------------

def _gia_smi(monkeypatch, stdout: str):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout, ""))


def test_dung_luong_gpu_doc_tu_nvidia_smi_doi_mib_sang_gib(monkeypatch):
    _gia_smi(monkeypatch, "23034\n")
    assert dung_luong_gpu_gib() == pytest.approx(22.49, abs=0.01)


def test_nhieu_gpu_thi_tu_choi_chu_khong_doan(monkeypatch):
    _gia_smi(monkeypatch, "23034\n23034\n")
    with pytest.raises(KeHoachLoi, match="2 GPU"):
        dung_luong_gpu_gib()


def test_khong_co_nvidia_smi_thi_chi_cach_dua_tay(monkeypatch):
    def hong(*a, **k):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(subprocess, "run", hong)
    with pytest.raises(KeHoachLoi, match="--gpu-gib"):
        dung_luong_gpu_gib()


# ---------------------------------------------------------------------------
# 5. Dòng lệnh
# ---------------------------------------------------------------------------

def test_main_in_ke_hoach_va_thoat_0(tmp_path, capsys):
    a, b = _model(tmp_path, "a"), _model(tmp_path, "b")
    assert kh.main(["--model", str(a), "--model", str(b), "--gpu-gib", "22.5", "--ten", "v3", "--ten", "v4"]) == 0
    out = capsys.readouterr().out
    assert "vllm serve" in out and "--served-model-name=v3" in out and "--served-model-name=v4" in out
    assert "ƯỚC TÍNH" in out, "con số overhead là đoán: phải nói ra"


def test_main_khong_vua_thi_thoat_2_va_noi_tren_stderr(tmp_path, capsys):
    a = _model(tmp_path, "a", kich_co=(1,))
    b = _model(tmp_path, "b", kich_co=(1,))
    # GPU 1 GiB: không thể vừa hai server
    assert kh.main(["--model", str(a), "--model", str(b), "--gpu-gib", "1"]) == 2
    assert "KHÔNG LẬP ĐƯỢC KẾ HOẠCH" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Ghép model text với model thị giác (#124): ngữ cảnh cố định và overhead riêng cho từng server
# ---------------------------------------------------------------------------

# Số thật lấy từ API công khai của Hugging Face ngày 19/11/2026 (kích thước tệp trọng số và config.json).
TEXT_AWQ = DacTaMoHinh(Path("text"), 5.68, 147456)            # Qwen3-8B AWQ: 36 lớp, 8 đầu KV, head_dim 128
VISION_7B_AWQ = DacTaMoHinh(Path("v7"), 6.45, 57344)          # Qwen2.5-VL-7B AWQ: 28 lớp, 4 đầu KV
VISION_4B_FP8 = DacTaMoHinh(Path("v4"), 5.61, 147456)
VISION_4B_BF16 = DacTaMoHinh(Path("v4b"), 8.27, 147456)
VISION_7B_BF16 = DacTaMoHinh(Path("v7b"), 15.45, 57344)
L4 = 22.49
RTX_3090 = 24.0


def _ghep(vision, gpu, oh=2.8, ctx_v=8192):   # 2,8 GiB: overhead vision ĐO THẬT (#124, 20/11/2026), thay cho 3,5 là con số đoán
    return lap_ke_hoach([TEXT_AWQ, vision], gpu, ctx_toi_da=32768, ctx_can_thiet=4096,
                        ctx_co_dinh={1: ctx_v}, overhead_rieng={1: oh})


def test_ctx_co_dinh_giu_nguyen_o_server_vision_va_chi_ha_server_text():
    k = _ghep(VISION_7B_AWQ, L4)
    assert k.servers[1].ngu_canh == 8192, "vision phải giữ đúng ngữ cảnh cố định"
    assert 4096 <= k.servers[0].ngu_canh < 32768, "chỉ server text bị hạ"
    assert k.max_model_len == k.servers[0].ngu_canh
    assert k.tong_phan <= TRAN_TONG_MAC_DINH + 1e-9


def test_overhead_rieng_lam_vision_can_nhieu_bo_nho_hon_va_text_phai_nhuong():
    nhe = _ghep(VISION_7B_AWQ, L4, oh=2.5)
    nang = _ghep(VISION_7B_AWQ, L4, oh=3.5)
    assert nang.servers[1].nhu_cau_gib > nhe.servers[1].nhu_cau_gib
    assert nang.servers[0].ngu_canh < nhe.servers[0].ngu_canh


def test_model_nang_khong_vua_cung_server_text_tren_l4():
    """Số tính ngày 19/11/2026: bản bf16 của 7B (15,45 GiB) không có chỗ cạnh server text trên L4 ở bất kỳ overhead nào."""
    with pytest.raises(KeHoachLoi, match="LẦN LƯỢT"):
        _ghep(VISION_7B_BF16, L4, oh=2.5)


def test_4b_bf16_khong_du_cho_text_tren_l4_voi_overhead_vua_phai():
    with pytest.raises(KeHoachLoi):
        _ghep(VISION_4B_BF16, L4, oh=3.5)


def test_hai_ung_vien_luong_tu_hoa_dong_host_duoc_tren_ca_l4_va_3090():
    for v in (VISION_7B_AWQ, VISION_4B_FP8):
        k_l4 = _ghep(v, L4)
        k_3090 = _ghep(v, RTX_3090)
        assert k_3090.servers[0].ngu_canh >= k_l4.servers[0].ngu_canh, "GPU lớn hơn thì text không được kém đi"


def test_tat_ca_server_deu_co_dinh_thi_chi_kiem_vua_hay_khong():
    k = lap_ke_hoach([TEXT_AWQ, VISION_7B_AWQ], L4, ctx_co_dinh={0: 8192, 1: 8192})
    assert k.max_model_len == 0 and [s.ngu_canh for s in k.servers] == [8192, 8192]
    with pytest.raises(KeHoachLoi):
        lap_ke_hoach([TEXT_AWQ, VISION_7B_BF16], L4, ctx_co_dinh={0: 32768, 1: 32768})


def test_chi_so_sai_bi_chan():
    with pytest.raises(KeHoachLoi, match="chỉ số server"):
        lap_ke_hoach([TEXT_AWQ], L4, ctx_co_dinh={3: 8192})
    with pytest.raises(KeHoachLoi, match="chỉ số server"):
        lap_ke_hoach([TEXT_AWQ], L4, overhead_rieng={-1: 1.0})


def test_overhead_va_ngu_canh_cua_tung_server_vao_lenh_serve():
    k = _ghep(VISION_7B_AWQ, L4)
    assert f"--max-model-len={k.servers[0].ngu_canh}" in lenh_serve(k.servers[0])
    assert "--max-model-len=8192" in lenh_serve(k.servers[1])


def test_doc_dac_ta_hieu_llm_config_cua_ho_internvl(tmp_path):
    cfg = {"architectures": ["InternVLChatModel"],
           "llm_config": {"num_hidden_layers": 24, "num_attention_heads": 14, "num_key_value_heads": 2, "hidden_size": 896},
           "vision_config": {"num_hidden_layers": 24}}
    d = doc_dac_ta(_model(tmp_path, ten="vintern", cfg=cfg))
    assert d.kv_byte_moi_token == 2 * 24 * 2 * 64 * 2, "head_dim = 896/14 = 64"


def test_ghi_de_trong_so_khi_tep_luu_fp32_ma_nap_bf16(tmp_path):
    thu_muc = _model(tmp_path, ten="m", kich_co=(1024,))
    assert doc_dac_ta(thu_muc).trong_so_gib == pytest.approx(1024 / 1024 ** 3)
    assert doc_dac_ta(thu_muc, trong_so_gib=1.8).trong_so_gib == 1.8


def test_main_nhan_ctx_co_dinh_overhead_rieng_va_trong_so(tmp_path, capsys):
    a, b = _model(tmp_path, "a", kich_co=(10,)), _model(tmp_path, "b", kich_co=(10,))   # tệp nhỏ; trọng số thật ghi đè bên dưới
    ma = kh.main(["--model", str(a), "--ten", "anser-v3", "--model", str(b), "--ten", "anser-vision",
                  "--gpu-gib", "22.49", "--ctx-co-dinh", "anser-vision=8192", "--overhead-rieng", "anser-vision=2.8",
                  "--trong-so-gib", "anser-v3=5.68", "--trong-so-gib", "anser-vision=6.45", "--ctx-can-thiet", "4096"])
    out = capsys.readouterr().out
    assert ma == 0
    assert "--served-model-name=anser-vision" in out and "--max-model-len=8192" in out
    assert "overhead 2.8" in out and "trọng số 6.45 GiB" in out


def test_main_ten_khong_co_hoac_gia_tri_sai_thoat_2(tmp_path, capsys):
    a, b = _model(tmp_path, "a"), _model(tmp_path, "b")
    base = ["--model", str(a), "--ten", "x", "--model", str(b), "--ten", "y", "--gpu-gib", "22.49"]
    assert kh.main(base + ["--ctx-co-dinh", "khong_co=8192"]) == 2
    assert "không có server tên" in capsys.readouterr().err
    assert kh.main(base + ["--overhead-rieng", "y=abc"]) == 2
    assert kh.main(base + ["--ctx-co-dinh", "thieu_dau_bang"]) == 2
