"""
tests/test_hoa_don_so_luong_le.py — `/ocr` phải nhận hoá đơn có số lượng LẺ (R4).

Hai định nghĩa cho cùng một khái niệm "số lượng của một dòng hàng":

  - `MCPServer.validate_invoice_total` (và `/tools/vat`) cố ý nhận số lẻ và bằng 0.
    Chú thích trong mã nêu đúng ca: `int(2.5) = 2` cắt cụt dầu nhờn bán theo lít, tính
    THIẾU tiền mà không bên nào kêu; `qty = 0` là dòng huỷ trên hoá đơn nhà xe.
  - `schemas.InvoiceItem` (cổng vào của `/ocr`) khai `qty: int` và chặn `< 1`.

Cổng vào chặn trước nên định nghĩa tử tế phía sau không bao giờ được dùng: một hoá
đơn có "2,5 lít" ra `schema_invalid` và cả `/ocr` hỏng. Khách pilot chuyên bán dầu —
đơn vị lít, số lẻ là chuyện hằng ngày, không phải ca hiếm.
"""

from __future__ import annotations

import math
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.main import app
from src.core.mcp_server import MCPServer
from src.core.schemas import InvoiceItem, InvoicePayload

client = TestClient(app)
PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "hoa_don.png", "image/png")


def _dong(**kw) -> dict:
    return {"name": "Dầu diesel", "price": 28_000} | kw


# ---------------------------------------------------------------------------
# Lược đồ
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("qty", [2.5, 0.125, 0, 0.0, 1, 1000, 1e9])
def test_so_luong_le_va_bang_0_duoc_nhan(qty):
    assert InvoiceItem(**_dong(qty=qty)).qty == pytest.approx(qty)


def test_khong_ghi_so_luong_thi_mac_dinh_1():
    """"Không ghi" khác "ghi 0" — đúng như MCPServer."""
    assert InvoiceItem(**_dong()).qty == 1.0


@pytest.mark.parametrize("qty", [-1, -0.5, math.inf, -math.inf, math.nan, 1e9 + 1])
def test_so_luong_vo_ly_van_bi_tu_choi(qty):
    """Chưa nhận số âm (đa phần là VLM đọc nhầm dấu), NaN/Inf, hay vượt trần chống tràn."""
    with pytest.raises(ValidationError):
        InvoiceItem(**_dong(qty=qty))


def test_gia_van_khong_duoc_am():
    """Chỉ sửa số lượng — quy tắc về đơn giá không đổi trong PR này."""
    with pytest.raises(ValidationError):
        InvoiceItem(**_dong(price=-1, qty=1))


# ---------------------------------------------------------------------------
# Hai nửa khớp nhau: cái cổng vào nhận thì phép tính phía sau tính ĐÚNG
# ---------------------------------------------------------------------------

def test_2_5_lit_duoc_tinh_du_khong_bi_cat_cut_thanh_2():
    inv = InvoicePayload(items=[_dong(qty=2.5)], total=77_000)     # 28.000 × 2,5 × 1,1
    kq = MCPServer.validate_invoice_total([i.model_dump() for i in inv.items], inv.total)
    assert kq["calculated_total"] == 77_000 and kq["is_valid"] is True
    # Nếu qty bị cắt cụt thành 2 thì tổng là 61.600 và hoá đơn ĐÚNG bị báo lệch.


def test_dong_huy_qty_0_khong_tinh_tien():
    inv = InvoicePayload(
        items=[_dong(qty=1), _dong(name="Dòng huỷ", qty=0)], total=30_800,
    )
    kq = MCPServer.validate_invoice_total([i.model_dump() for i in inv.items], inv.total)
    assert kq["calculated_total"] == 30_800 and kq["is_valid"] is True


# ---------------------------------------------------------------------------
# Đường HTTP: /ocr không còn bác hoá đơn bán theo lít
# ---------------------------------------------------------------------------

@pytest.fixture
def gia_lap_vision(monkeypatch):
    from src.api import dependencies as deps

    class FakeVision:
        result: dict = {}

        async def extract_invoice(self, path):
            return dict(self.result)

    fake = FakeVision()

    async def _ensure():
        deps.runtime.vision = fake

    monkeypatch.setattr(deps.runtime, "ensure_vision_runtime", _ensure)
    monkeypatch.setattr(deps.runtime, "vision", fake, raising=False)
    return fake


def _post_ocr():
    data, name, mime = PNG
    return client.post("/ocr", files={"file": (name, BytesIO(data), mime)}).json()


def test_ocr_nhan_hoa_don_ban_theo_lit(gia_lap_vision):
    gia_lap_vision.result = {"items": [_dong(qty=2.5)], "total": 77_000}
    body = _post_ocr()
    assert body["success"] is True, body
    assert body["validation"]["calculated_total"] == 77_000
    assert body["needs_manual_review"] is False
    assert body["invoice"]["items"][0]["qty"] == 2.5


def test_ocr_van_bao_lech_that_khi_tong_ghi_sai(gia_lap_vision):
    """Sửa cổng vào không được làm mất khả năng bắt hoá đơn ghi sai tổng."""
    gia_lap_vision.result = {"items": [_dong(qty=2.5)], "total": 61_600}   # tổng của qty bị cắt cụt
    body = _post_ocr()
    assert body["success"] is True and body["needs_manual_review"] is True


def test_ocr_van_tu_choi_so_luong_am_va_noi_ro(gia_lap_vision):
    gia_lap_vision.result = {"items": [_dong(qty=-3)], "total": 1}
    body = _post_ocr()
    assert body["success"] is False and body["error"].startswith("schema_invalid")
