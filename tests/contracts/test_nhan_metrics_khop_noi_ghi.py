"""
tests/contracts/test_nhan_metrics_khop_noi_ghi.py — tập nhãn hợp lệ của báo cáo metrics phải KHỚP với những nơi SINH ra nhãn.

`offline_training/bao_cao_metrics.py` chỉ in nhãn thuộc `src.core.metrics.*_HOP_LE` (R2: một nhãn đúng khuôn vẫn có thể là tên khách). Các tập đó là bản chép từ router, tool và chốt
chặn. Bản chép lệch thì nhãn thật bị gộp vào "(khác)" mà không ai hay, nên test này đọc chính nơi sinh nhãn và đòi khớp: thêm nhánh hay tool mới mà quên tập, test đỏ.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.core import metrics

GOC = Path(__file__).resolve().parents[2]


def _gia_tri_theo_khoa(duong: str, khoa: str) -> set[str]:
    """Mọi hằng chuỗi làm GIÁ TRỊ của khoá `khoa` trong các dict literal của một tệp nguồn."""
    cay = ast.parse((GOC / duong).read_text(encoding="utf-8"))
    ra: set[str] = set()
    for nut in ast.walk(cay):
        if isinstance(nut, ast.Dict):
            for k, v in zip(nut.keys, nut.values):
                if isinstance(k, ast.Constant) and k.value == khoa and isinstance(v, ast.Constant) and isinstance(v.value, str):
                    ra.add(v.value)
    return ra


def _doi_so_reason(duong: str) -> set[str]:
    cay = ast.parse((GOC / duong).read_text(encoding="utf-8"))
    return {kw.value.value for nut in ast.walk(cay) if isinstance(nut, ast.Call) for kw in nut.keywords
            if kw.arg == "reason" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)}


def test_nhanh_hop_le_la_cac_nhanh_cua_router(monkeypatch):
    monkeypatch.setenv("ENV", "LOCAL")
    from src.agents.manager import SemanticRouter

    assert set(SemanticRouter(tu_nap_embedder=False).routes) == set(metrics.NHANH_HOP_LE)


def test_moi_nhanh_router_tra_ve_deu_thuoc_tap_hop_le():
    tra_ve = _gia_tri_theo_khoa("src/agents/manager.py", "route")
    assert tra_ve and tra_ve <= set(metrics.NHANH_HOP_LE), tra_ve - set(metrics.NHANH_HOP_LE)


def test_cach_dinh_tuyen_hop_le_la_dung_cac_gia_tri_method_cua_router():
    assert _gia_tri_theo_khoa("src/agents/manager.py", "method") == set(metrics.CACH_DINH_TUYEN_HOP_LE)


def test_ten_tool_hop_le_la_dung_cac_tool_dang_ky():
    pytest.importorskip("fastapi")
    from src.api.routes.tools import _TOOL_IMPL

    assert set(_TOOL_IMPL) == set(metrics.TEN_TOOL_HOP_LE)


def test_ly_do_chan_hop_le_la_cac_ly_do_cua_chot_chan_va_suy_bien():
    ly_do_chot_chan = _doi_so_reason("src/core/grounding.py")
    assert ly_do_chot_chan, "không đọc được lý do nào từ grounding.py: đổi cách viết thì sửa test này"
    assert ly_do_chot_chan | {"suy biến"} == set(metrics.LY_DO_CHAN_HOP_LE)
