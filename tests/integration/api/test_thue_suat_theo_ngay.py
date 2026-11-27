"""
tests/integration/api/test_thue_suat_theo_ngay.py — mức 8% chỉ áp theo NGÀY LẬP hoá đơn (A15, #200).

Hạn của mức giảm (31/12/2026) rơi giữa kế hoạch pilot; hoá đơn lập 31/12/2026 và 01/01/2027 phải ra hai mức khác nhau. Căn cứ
(`HIEU_LUC_TU/DEN`) là cách đọc của nhóm nghiên cứu, chưa kiểm bản chính, chờ kế toán xác nhận nhóm hàng: test khoá HÀNH VI của bảng, không khoá tính đúng đắn pháp lý.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core import vat_catalog as vc

client = TestClient(app)


def _vat(ngay, giam):
    than = {"items": [{"name": "Hàng A", "price": 1_000_000, "qty": 1, "is_reduced_vat": giam}],
            "prices_include_vat": False, "stated_total": 1_080_000 if giam else 1_100_000}
    if ngay is not None:
        than["invoice_date"] = ngay
    return client.post("/tools/vat", json=than)


@pytest.mark.parametrize("ngay,giam,ma", [
    ("2026-12-31", True, 200),     # ngày cuối còn hiệu lực
    ("2027-01-01", True, 422),     # sau hạn: không được 8%
    ("2025-06-30", True, 200),     # trước căn cứ này: chỉ cảnh báo (nghị quyết trước cũng từng cho 8%), không chặn oan kỳ cũ
    ("2025-07-01", True, 200),
    ("2027-01-01", False, 200),    # 10% luôn được
    ("2026-12-31", False, 200),
])
def test_8_phan_tram_theo_ngay_lap(ngay, giam, ma):
    r = _vat(ngay, giam)
    assert r.status_code == ma, r.text
    if ma == 422:
        assert "10%" in r.json()["detail"] and "Nghị quyết 204/2025/QH15" in r.json()["detail"]


def test_truoc_hieu_luc_co_canh_bao_chu_khong_chan():
    j = _vat("2025-06-30", True).json()
    assert j["is_valid"] is True and j["warnings"] and "kế toán xác nhận" in j["warnings"][0]


def test_ket_qua_ghi_ngay_va_can_cu():
    j = _vat("2026-12-31", True).json()
    assert j["effective_date"] == "2026-12-31" and "204/2025" in j["vat_basis"] and j["is_valid"] is True


def test_thieu_ngay_thi_canh_bao_khi_co_dong_8_va_khong_doan():
    j = _vat(None, True).json()
    assert j["effective_date"] is None and j["warnings"] and "ngày lập" in j["warnings"][0]
    assert "warnings" not in _vat(None, False).json()


@pytest.mark.parametrize("ngay", ["31/12/2026", "2026-13-01", "2026-02-30", "26-12-31", ""])
def test_ngay_sai_khuon_la_422(ngay):
    assert _vat(ngay, False).status_code == 422


def test_ham_thuan():
    assert vc.kiem_hieu_luc_giam_thue("2026-12-31", True) == (None, [])
    assert vc.kiem_hieu_luc_giam_thue("2027-01-01", False) == (None, [])
    assert vc.kiem_hieu_luc_giam_thue("2027-01-01", True)[0]
    loi, canh_bao = vc.kiem_hieu_luc_giam_thue("2025-06-30", True)
    assert loi is None and canh_bao


# Đường hoá đơn cước (VLM đọc ảnh): 8% sau hạn thì phải bị bắt
def _cuoc(ngay, vat):
    from src.core.freight_invoice import FreightCharge, FreightInvoice, verify
    hd = FreightInvoice(carrier_name="Nhà xe A", invoice_date=ngay, charges=[FreightCharge(kind="cước", description="cước", unit_price=1_000_000)],
                        vat_rate=vat, subtotal=1_000_000, vat_amount=1_000_000 * vat / 100, total=1_000_000 * (1 + vat / 100))
    return verify(hd)


def test_hoa_don_cuoc_8_phan_tram_sau_han_bi_bat():
    r = _cuoc("2027-01-05", 8.0)
    assert r["ok"] is False and any("8% hết hiệu lực" in i for i in r["issues"]) and "hiệu_lực_thuế_8%" in r["checks_performed"]


def test_hoa_don_cuoc_trong_han_hoac_10_phan_tram_hoac_ngay_la_khong_bi_bat_oan():
    assert _cuoc("2026-12-31", 8.0)["ok"] is True
    assert _cuoc("2027-01-05", 10.0)["ok"] is True
    assert _cuoc("2025-03-01", 8.0)["ok"] is True       # trước căn cứ: không nói gì ở đường này
    assert _cuoc("05/01/2027", 8.0)["ok"] is True       # ngày không phải ISO: không đoán
