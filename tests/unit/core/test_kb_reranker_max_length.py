"""
tests/test_kb_reranker_max_length.py — `KB_RERANKER_MAX_LENGTH` (#214): cắt cặp (câu hỏi, đoạn) ở N token trước khi vào reranker để hạ độ trễ trên CPU.

Thành đo 24/11/2026 (Colab L4, CPU): 384 hạ p95 từ 12,7 xuống 7,3 giây, 20/20 câu hỏi trả về đúng tập đoạn như cũ. Mặc định vẫn là "không đặt" cho tới khi có recall/MRR (#34).
`sentence_transformers` KHÔNG được import thật ở đây (kéo torch, xem requirements-dev.txt): module giả ghi lại tham số dựng `CrossEncoder`.
"""

from __future__ import annotations

import sys
import types

import pytest

from src.core import config
from src.core.knowledge import KnowledgeBase


@pytest.fixture
def cross_encoder_gia(monkeypatch):
    ghi: list[dict] = []

    class CrossEncoder:
        def __init__(self, ten, **kwargs):
            ghi.append({"ten": ten, **kwargs})

    mod = types.ModuleType("sentence_transformers")
    mod.CrossEncoder = CrossEncoder  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", mod)
    return ghi


def test_khong_dat_bien_thi_khong_truyen_max_length(monkeypatch, cross_encoder_gia):
    monkeypatch.delenv("KB_RERANKER_MAX_LENGTH", raising=False)
    kb = KnowledgeBase(collection=object())
    _ = kb.reranker
    assert len(cross_encoder_gia) == 1 and "max_length" not in cross_encoder_gia[0], "không đặt thì hành vi như cũ, không thêm tham số nào"


@pytest.mark.parametrize("tho", ["", "  ", "0"])
def test_rong_hoac_0_la_mac_dinh_cua_model(monkeypatch, cross_encoder_gia, tho):
    monkeypatch.setenv("KB_RERANKER_MAX_LENGTH", tho)
    assert config.kb_reranker_max_length() == 0
    _ = KnowledgeBase(collection=object()).reranker
    assert "max_length" not in cross_encoder_gia[0]


def test_dat_384_thi_truyen_dung_cho_cross_encoder(monkeypatch, cross_encoder_gia):
    monkeypatch.setenv("KB_RERANKER_MAX_LENGTH", "384")
    kb = KnowledgeBase(collection=object(), device="cpu")
    _ = kb.reranker
    assert cross_encoder_gia[0]["max_length"] == 384 and cross_encoder_gia[0]["device"] == "cpu"


@pytest.mark.parametrize("tho", ["abc", "3.5", "-1", "63", "8193", "1e3"])
def test_gia_tri_hong_la_loi_to_ngay_luc_dung_kho_khong_doi_toi_lan_tim(monkeypatch, tho):
    monkeypatch.setenv("KB_RERANKER_MAX_LENGTH", tho)
    with pytest.raises(ValueError, match="KB_RERANKER_MAX_LENGTH"):
        KnowledgeBase(collection=object())


@pytest.mark.parametrize("tho,ky_vong", [("64", 64), ("384", 384), ("512", 512), ("8192", 8192), (" 256 ", 256)])
def test_bien_hop_le(monkeypatch, tho, ky_vong):
    monkeypatch.setenv("KB_RERANKER_MAX_LENGTH", tho)
    assert config.kb_reranker_max_length() == ky_vong
