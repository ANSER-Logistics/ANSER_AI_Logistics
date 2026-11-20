"""
tests/test_tool_input_chan_inf_nan.py — mọi trường số của mọi schema đầu vào `/tools` từ chối vô cực và NaN (R1).

Phát hiện bởi property-based test của `receivables` (20/11/2026): `/tools/partner-audit` nhận JSON `Infinity` cho `balance`, `finding()` ném
`OverflowError` (`round(inf)`), route chỉ bắt `ValueError`, nên HTTP 500; `NaN` ra 422 lời lẽ khó hiểu. Gốc: chỉ vài trường có `allow_inf_nan=False`
viết tay. Nay đặt ở `_ToolIn`. Test lặp trên MỌI lớp con để thêm một schema hay một trường số mới không mở lại lỗ này.
"""

from __future__ import annotations

import inspect
import typing

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.main import app
from src.api.routes import tools as tools_mod

client = TestClient(app)
AI = {"X-Store-Id": "1", "X-User-Id": "1"}


def _lop_tool_in():
    return [c for _, c in inspect.getmembers(tools_mod, inspect.isclass)
            if issubclass(c, tools_mod._ToolIn) and c is not tools_mod._ToolIn]


def _truong_float(lop) -> list[str]:
    ra = []
    for ten, f in lop.model_fields.items():
        ann = f.annotation
        phan = typing.get_args(ann) or (ann,)
        if float in phan:
            ra.append(ten)
    return ra


CA = [(lop, ten) for lop in _lop_tool_in() for ten in _truong_float(lop)]


def test_tim_duoc_nhieu_truong_float_de_kiem():
    """Chốt chống xanh suông: parametrize trên danh sách rỗng là một ca SKIP."""
    assert len(CA) >= 25, [(c.__name__, t) for c, t in CA]
    assert any(c.__name__ == "PartnerIn" and t == "balance" for c, t in CA)


@pytest.mark.parametrize("lop, truong", CA, ids=[f"{c.__name__}.{t}" for c, t in CA])
@pytest.mark.parametrize("gia_tri", [float("inf"), float("-inf"), float("nan")], ids=["inf", "-inf", "nan"])
def test_truong_so_tu_choi_vo_cuc_va_nan(lop, truong, gia_tri):
    """Dựng schema với đủ trường bắt buộc rồi ép MỘT trường số thành vô cực/NaN: phải là ValidationError, không phải lọt qua."""
    kwargs = {}
    for ten, f in lop.model_fields.items():
        if f.is_required():
            kwargs[ten] = _mau_bat_buoc(f.annotation)
    kwargs[truong] = gia_tri
    with pytest.raises(ValidationError):
        lop(**kwargs)


def _mau_bat_buoc(ann):
    phan = typing.get_args(ann) or (ann,)
    if float in phan or int in phan:
        return 1.0 if float in phan else 1
    if str in phan:
        return "x"
    if bool in phan:
        return True
    return None


def test_partner_audit_http_infinity_la_422_khong_phai_500():
    """Đúng ca đã gây 500. `json.dumps` của thư viện chuẩn ghi `Infinity` như JavaScript không bao giờ ghi."""
    import json

    than = json.dumps({"customers": [{"code": "KH01", "name": "Khách mẫu", "balance": float("inf")}]})
    r = client.post("/tools/partner-audit", content=than, headers={**AI, "Content-Type": "application/json"})
    assert r.status_code == 422, r.text


def test_partner_audit_http_so_huu_han_van_qua():
    r = client.post("/tools/partner-audit", json={"customers": [{"code": "KH01", "name": "Khách mẫu", "balance": 1_500_000}]}, headers=AI)
    assert r.status_code == 200, r.text
