"""
tests/contracts/test_giay_phep_model.py — mặc định model của Brain phải có giấy phép dùng thương mại được.

VÌ SAO CÓ FILE NÀY
------------------
Ngày 17/11/2026 mới phát hiện: model thị giác mặc định `Qwen/Qwen2.5-VL-3B-Instruct` mang giấy phép
`qwen-research` — chỉ cho nghiên cứu và đánh giá phi thương mại, dùng thương mại phải xin Alibaba Cloud.
Không tài liệu nào trong hai repo nhắc đến điều đó, trong khi `knowledge.py` đã loại jina-reranker-v2
chỉ vì CC-BY-NC. Một quy tắc đúng với reranker mà không áp cho VLM là quy tắc nằm trong trí nhớ của
một người, không nằm trong mã. Chủ dự án không xin được giấy phép, nên đổi model; file này giữ cho
việc đó không quay lại.

CÁCH HOẠT ĐỘNG
--------------
Mọi model mà `Config`, `deploy/.env.example` và `deploy/docker-compose.yml` đặt làm MẶC ĐỊNH phải nằm
trong `DUOC_PHEP` bên dưới, mỗi dòng kèm giấy phép và ngày kiểm trên thẻ model (API Hugging Face).
Thêm một model mới làm mặc định = mở thẻ model, đọc giấy phép, rồi thêm một dòng ở đây. `CAM` là các
model đã biết là phi thương mại; một model ở `CAM` không bao giờ được là mặc định.

GIỚI HẠN: test này không gọi mạng nên không biết thẻ model đổi giấy phép sau ngày kiểm. Nó chặn
việc vô ý, không thay cho việc đọc giấy phép.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]

# model -> (giấy phép, ngày kiểm trên thẻ model qua API Hugging Face)
DUOC_PHEP: dict[str, tuple[str, str]] = {
    "Qwen/Qwen3-VL-2B-Instruct": ("apache-2.0", "2026-11-17"),
    "Qwen/Qwen3-VL-4B-Instruct": ("apache-2.0", "2026-11-17"),
    "Qwen/Qwen3-VL-8B-Instruct": ("apache-2.0", "2026-11-17"),
    "Qwen/Qwen2.5-VL-7B-Instruct": ("apache-2.0", "2026-11-17"),
    "Qwen/Qwen2-VL-2B-Instruct": ("apache-2.0", "2026-11-17"),
    "5CD-AI/Vintern-1B-v3_5": ("mit", "2026-11-17"),
    "Qwen/Qwen3-8B": ("apache-2.0", "2026-11-17"),
    "BAAI/bge-m3": ("mit", "2026-11-17"),
    "namdp-ptit/ViRanker": ("apache-2.0", "2026-11-17"),
}

# model đã biết là phi thương mại: không bao giờ được là mặc định
CAM: dict[str, str] = {
    "Qwen/Qwen2.5-VL-3B-Instruct": "qwen-research: chỉ nghiên cứu và đánh giá, dùng thương mại phải xin Alibaba",
    "Qwen/Qwen2.5-3B-Instruct": "qwen-research",
    "jinaai/jina-reranker-v2-base-multilingual": "CC-BY-NC-4.0",
    "jinaai/jina-embeddings-v3": "CC-BY-NC-4.0",
    "jinaai/jina-embeddings-v4": "phi thương mại",
    "jinaai/jina-colbert-v2": "CC-BY-NC-4.0",
}

# biến môi trường nào mang HF id của một model mà Brain tự tải
_BIEN = ("VISION_MODEL_ID", "TEXT_MODEL_ID", "KB_EMBEDDER_ID", "KB_RERANKER_ID")


def _la_duong_dan(gia_tri: str) -> bool:
    return gia_tri.startswith(("/", "./", "../", "~")) or ":" in gia_tri or "\\" in gia_tri


def _mac_dinh_trong_env_example() -> dict[str, str]:
    ra: dict[str, str] = {}
    for dong in (ROOT / "deploy" / ".env.example").read_text(encoding="utf-8").splitlines():
        m = re.match(rf"^({'|'.join(_BIEN)})=(\S+)", dong)
        if m:
            ra[m.group(1)] = m.group(2)
    return ra


def _mac_dinh_trong_compose() -> list[tuple[str, str]]:
    s = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")
    return re.findall(rf"\$\{{({'|'.join(_BIEN)}):-([^}}]+)\}}", s)


def _mac_dinh_trong_config(monkeypatch) -> dict[str, str]:
    from src.core.config import Config

    for b in _BIEN:
        monkeypatch.delenv(b, raising=False)
    c = Config()
    return {
        "VISION_MODEL_ID": c.vision_model_id,
        "KB_EMBEDDER_ID": c.embedding_model_id,
        "KB_RERANKER_ID": c.reranker_model_id,
    }


def _kiem(nguon: str, bien: str, gia_tri: str) -> list[str]:
    if not gia_tri or _la_duong_dan(gia_tri):
        return []
    loi = []
    if gia_tri in CAM:
        loi.append(f"{nguon}: {bien}={gia_tri} là model phi thương mại ({CAM[gia_tri]}) — không được làm mặc định")
    elif gia_tri not in DUOC_PHEP:
        loi.append(
            f"{nguon}: {bien}={gia_tri} chưa nằm trong DUOC_PHEP. Mở thẻ model, đọc giấy phép; "
            "chỉ khi dùng thương mại được thì thêm một dòng (giấy phép, ngày kiểm) vào tests/contracts/test_giay_phep_model.py"
        )
    return loi


def test_danh_sach_cho_phep_va_cam_khong_giao_nhau():
    assert not (set(DUOC_PHEP) & set(CAM)), set(DUOC_PHEP) & set(CAM)


def test_giay_phep_trong_danh_sach_cho_phep_la_loai_dung_thuong_mai_duoc():
    thoai_mai = {"apache-2.0", "mit", "bsd-3-clause", "bsd-2-clause"}
    xau = {m: gp for m, (gp, _) in DUOC_PHEP.items() if gp not in thoai_mai}
    assert not xau, xau


def test_mac_dinh_trong_config_deu_dung_thuong_mai_duoc(monkeypatch):
    mac_dinh = _mac_dinh_trong_config(monkeypatch)
    assert len(mac_dinh) == 3
    loi = [e for b, v in mac_dinh.items() for e in _kiem("config.py", b, v)]
    assert not loi, "\n".join(loi)


def test_mac_dinh_trong_env_example_deu_dung_thuong_mai_duoc():
    mac_dinh = _mac_dinh_trong_env_example()
    assert "VISION_MODEL_ID" in mac_dinh, "không đọc được VISION_MODEL_ID từ deploy/.env.example"
    loi = [e for b, v in mac_dinh.items() for e in _kiem("deploy/.env.example", b, v)]
    assert not loi, "\n".join(loi)


def test_mac_dinh_trong_compose_deu_dung_thuong_mai_duoc():
    cap = _mac_dinh_trong_compose()
    assert any(b == "VISION_MODEL_ID" for b, _ in cap), "không đọc được VISION_MODEL_ID từ docker-compose.yml"
    loi = [e for b, v in cap for e in _kiem("deploy/docker-compose.yml", b, v)]
    assert not loi, "\n".join(loi)


def test_ba_nguon_mac_dinh_vision_khop_nhau(monkeypatch):
    """config, .env.example và compose phải cùng một model vision — lệch là ba chỗ ba câu chuyện."""
    cfg = _mac_dinh_trong_config(monkeypatch)["VISION_MODEL_ID"]
    env = _mac_dinh_trong_env_example()["VISION_MODEL_ID"]
    comp = {v for b, v in _mac_dinh_trong_compose() if b == "VISION_MODEL_ID"}
    assert comp == {cfg} and env == cfg, (cfg, env, comp)


def test_dau_do_bat_duoc_model_phi_thuong_mai():
    """Chứng minh phép kiểm không câm: đưa đúng mặc định cũ vào thì phải đỏ."""
    assert _kiem("x", "VISION_MODEL_ID", "Qwen/Qwen2.5-VL-3B-Instruct")
    assert _kiem("x", "VISION_MODEL_ID", "mot-to-chuc/model-la-chua-kiem")
    assert not _kiem("x", "VISION_MODEL_ID", "Qwen/Qwen3-VL-2B-Instruct")
    assert not _kiem("x", "TEXT_MODEL_ID", "/models/anser-v3-awq")   # đường dẫn cục bộ thì bỏ qua


# ---------------------------------------------------------------------------
# Lớp nạp model thị giác: không còn đóng đinh một lớp, và không lặng lẽ trả None
# ---------------------------------------------------------------------------

def test_chon_lop_nap_vision_uu_tien_image_text_to_text():
    from src.core.engine import chon_lop_nap_vision

    moi, cu = object(), object()
    tf = SimpleNamespace(AutoModelForImageTextToText=moi, AutoModelForVision2Seq=cu)
    assert chon_lop_nap_vision(tf) is moi


def test_chon_lop_nap_vision_lui_ve_vision2seq_cho_transformers_cu():
    from src.core.engine import chon_lop_nap_vision

    cu = object()
    assert chon_lop_nap_vision(SimpleNamespace(AutoModelForVision2Seq=cu)) is cu


def test_chon_lop_nap_vision_khong_co_lop_nao_thi_bao_ro():
    from src.core.engine import chon_lop_nap_vision

    with pytest.raises(ImportError, match="4.57"):
        chon_lop_nap_vision(SimpleNamespace())
