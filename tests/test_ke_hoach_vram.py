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
    assert k.max_model_len == 18432          # tính tay: 2 x (5,3 + 2,5 + KV 2,53 GiB) = 20,66 <= 0,92 x 22,5 = 20,7


@pytest.mark.parametrize("gpu", [16.0, 22.5, 24.0, 40.0, 80.0])
@pytest.mark.parametrize("trong_so", [3.0, 5.3, 5.7, 7.0])
@pytest.mark.parametrize("so_server", [1, 2, 3])
def test_bat_bien_moi_server_du_bo_nho_va_tong_khong_vuot_tran(gpu, trong_so, so_server):
    """Hai chiều của cùng một lỗi làm tròn: server thiếu bộ nhớ, hoặc tổng vượt trần."""
    try:
        k = lap_ke_hoach([_dt(trong_so)] * so_server, gpu)
    except KeHoachLoi:
        return                                # không vừa thì từ chối là đúng; chỉ kiểm khi có kế hoạch
    assert k.tong_phan <= 0.92 + 1e-9
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
