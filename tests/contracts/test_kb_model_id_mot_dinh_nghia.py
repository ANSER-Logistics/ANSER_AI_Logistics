"""
tests/contracts/test_kb_model_id_mot_dinh_nghia.py — model của kho tri thức chỉ được định nghĩa MỘT lần (R4).

Trước 17/11/2026 `KB_EMBEDDER_ID` và `KB_RERANKER_ID` được đọc ở HAI nơi (`core/config.py` và `core/knowledge.py`),
mỗi nơi viết cứng một bản mặc định. Chỉ `knowledge.py` thật sự nạp model; `Config` chỉ dùng cho báo cáo đo
(`offline_training/do_ngan_sach_ctx.py`). Đổi mặc định ở một nơi thì báo cáo đo ghi sai model mà không có gì đỏ.
Phát hiện khi Sơn soát 19 biến môi trường (PR #130, #38), ghi là "cần người quyết"; chủ dự án uỷ quyền quyết.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core import config, knowledge

GOC = Path(__file__).resolve().parents[2] / "src"


def _dem(chuoi: str) -> int:
    return sum(p.read_text(encoding="utf-8").count(chuoi) for p in GOC.rglob("*.py"))


@pytest.mark.parametrize("bien", ["KB_EMBEDDER_ID", "KB_RERANKER_ID"])
def test_moi_bien_chi_duoc_doc_tu_env_o_mot_noi(bien):
    assert _dem(f'getenv("{bien}"') == 1, f"{bien} được đọc từ env ở nhiều hơn một nơi trong src/"


@pytest.mark.parametrize("mac_dinh", [config.KB_EMBEDDER_MAC_DINH, config.KB_RERANKER_MAC_DINH])
def test_mac_dinh_chi_viet_cung_o_mot_noi(mac_dinh):
    assert _dem(f'"{mac_dinh}"') == 1, f"mặc định {mac_dinh!r} được viết cứng ở nhiều hơn một nơi trong src/"


def test_config_va_kho_nhat_tri_khi_dat_env(monkeypatch):
    monkeypatch.setenv("KB_EMBEDDER_ID", "x/embedder-thu")
    monkeypatch.setenv("KB_RERANKER_ID", "x/reranker-thu")
    c = config.Config()
    assert (c.embedding_model_id, c.reranker_model_id) == ("x/embedder-thu", "x/reranker-thu")
    assert (config.kb_embedder_id(), config.kb_reranker_id()) == ("x/embedder-thu", "x/reranker-thu")


def test_khong_dat_env_thi_dung_mac_dinh(monkeypatch):
    monkeypatch.delenv("KB_EMBEDDER_ID", raising=False)
    monkeypatch.delenv("KB_RERANKER_ID", raising=False)
    c = config.Config()
    assert (c.embedding_model_id, c.reranker_model_id) == (config.KB_EMBEDDER_MAC_DINH, config.KB_RERANKER_MAC_DINH)


def test_kho_nap_dung_model_theo_env_luc_nap_khong_luc_import(monkeypatch):
    """
    Mặc định cũ là hằng số lúc import: đặt env SAU khi import thì kho vẫn nạp model cũ. Giờ là hàm, nên
    kho nạp đúng model của env tại thời điểm nạp. Dùng SentenceTransformer/CrossEncoder giả, không nạp model thật.
    """
    import sys
    import types

    da_goi: dict[str, str] = {}

    class _ST:
        def __init__(self, ten, device=None):
            da_goi["embedder"] = ten

    class _CE:
        def __init__(self, ten, device=None):
            da_goi["reranker"] = ten

    gia = types.ModuleType("sentence_transformers")
    gia.SentenceTransformer = _ST  # type: ignore[attr-defined]
    gia.CrossEncoder = _CE  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", gia)
    monkeypatch.setenv("KB_EMBEDDER_ID", "x/embedder-sau-import")
    monkeypatch.setenv("KB_RERANKER_ID", "x/reranker-sau-import")

    kb = knowledge.KnowledgeBase("./data/vector_db")
    _ = kb.embedder
    _ = kb.reranker
    assert da_goi == {"embedder": "x/embedder-sau-import", "reranker": "x/reranker-sau-import"}
