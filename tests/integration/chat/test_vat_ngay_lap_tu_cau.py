"""
tests/integration/chat/test_vat_ngay_lap_tu_cau.py — ngày lập hoá đơn của `vat` chỉ đến từ câu người dùng, không từ model (A15, #200; BR-43 phần "đường /chat chưa truyền ngày").

VÌ SAO CÓ FILE NÀY
------------------
Mức 8% hết hiệu lực sau 31/12/2026, rơi ngay sau cửa sổ pilot. `/tools/vat` đã kiểm theo `invoice_date`, nhưng qua `/chat` không chỗ nào đưa ngày vào: lược đồ tool phơi `invoice_date` cho model, nên
(1) người dùng nói "hoá đơn lập ngày 05/01/2027" mà ngày không tới được tool, phép kiểm chỉ cảnh báo mềm "chưa có ngày"; (2) model tự điền một ngày cho đủ khuôn ("2026-12-01") thì phép kiểm
hết hiệu lực trôi qua im lặng. Cùng loại lỗi với `fuel_price_as_of` đã chặn ở PR #50: nguồn của một ngày phải là nơi có ngày thật.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core.doc_dau_vao import chot_dau_vao, ngay_lap_tu_cau

client = TestClient(app)


@pytest.mark.parametrize("cau,ngay", [
    ("hoá đơn lập ngày 05/01/2027, dầu 1.000.000đ", "2027-01-05"),
    ("hóa đơn ngày 5/1/2027 gồm dầu 1.000.000đ", "2027-01-05"),
    ("xuất hoá đơn ngày 31-12-2026 cho khách", "2026-12-31"),
    ("hoá đơn lập 01.07.2025", "2025-07-01"),
    ("xuất hoá đơn ngày 5 tháng 1 năm 2027", "2027-01-05"),
    ("Hoá đơn lập ngày 2027-01-05", "2027-01-05"),
    ("HOÁ ĐƠN LẬP NGÀY 05/01/2027", "2027-01-05"),
    ("hoá đơn ngày 05 / 01 / 2027", "2027-01-05"),
    ("hoá đơn số 12 lập ngày 05/01/2027 và 05/01/2027", "2027-01-05"),     # cùng một ngày nhắc hai lần
])
def test_doc_duoc_ngay_lap_di_kem_tu_noi_hoa_don(cau, ngay):
    assert ngay_lap_tu_cau(cau) == ngay


@pytest.mark.parametrize("cau", [
    "",
    "tính VAT cho hoá đơn 1.000.000đ",                                          # không có ngày
    "thuế 8% áp từ ngày 01/07/2025, tính cho hoá đơn 10 triệu",                 # ngày của luật, không kèm từ lập hoá đơn
    "hoá đơn ngày 01/12/2026 và hoá đơn ngày 05/01/2027",                       # hai ngày khác nhau: không đoán
    "hoá đơn lập ngày 31/02/2026",                                              # ngày không có thật
    "hoá đơn lập ngày 13/13/2026",
    "hoá đơn lập ngày 05/01/27",                                                # năm hai chữ số: không đoán thế kỷ
    "theo Nghị định 72/2024/NĐ-CP, hoá đơn 1.000.000đ",                         # số văn bản, không phải ngày
    "Thông tư 78/2021/TT-BTC hoá đơn điện tử",
    "hoá đơn lập tháng 1/2027",                                                 # thiếu ngày
    "hoá đơn mã 2027-0105-XYZ",
])
def test_khong_co_dung_mot_ngay_chac_chan_thi_de_trong(cau):
    assert ngay_lap_tu_cau(cau) is None


def test_chi_nhan_ngay_trong_vong_40_ky_tu_sau_tu_noi_hoa_don():
    xa = "hoá đơn " + "x" * 60 + " 05/01/2027"
    assert ngay_lap_tu_cau(xa) is None


# ---------------------------------------------------------------------------
# chot_dau_vao
# ---------------------------------------------------------------------------

ARGS = {"items": [{"name": "Dầu", "price": 1_000_000, "qty": 1, "is_reduced_vat": True}], "stated_total": 1_080_000}


def test_ngay_model_tu_dien_bi_go_ke_ca_khi_cau_rong():
    args, hoi, _ = chot_dau_vao("vat", {**ARGS, "invoice_date": "2026-12-01"}, "")
    assert "invoice_date" not in args and hoi is None


def test_ngay_model_tu_dien_bi_go_khi_cau_khong_noi_ngay():
    args, _, _ = chot_dau_vao("vat", {**ARGS, "invoice_date": "2026-12-01"}, "tính VAT dầu 1.000.000đ chưa gồm VAT, thuế suất 8%, tổng 1.080.000đ")
    assert "invoice_date" not in args, "câu không nói ngày thì không có ngày: để tool cảnh báo, không để model bịa"


def test_ngay_trong_cau_ghi_de_ngay_model_dien():
    cau = "tính VAT hoá đơn lập ngày 05/01/2027: Dầu 1.000.000đ chưa gồm VAT, thuế suất 8%, tổng ghi trên hoá đơn 1.080.000đ"
    args, _, _ = chot_dau_vao("vat", {**ARGS, "invoice_date": "2026-12-01"}, cau)
    assert args["invoice_date"] == "2027-01-05"


def test_ngay_trong_cau_duoc_dua_vao_args_du_model_khong_dien():
    cau = "tính VAT hoá đơn lập ngày 05/01/2027: Dầu 1.000.000đ chưa gồm VAT, thuế suất 8%, tổng ghi trên hoá đơn 1.080.000đ"
    args, _, _ = chot_dau_vao("vat", dict(ARGS), cau)
    assert args["invoice_date"] == "2027-01-05"


@pytest.mark.parametrize("ten", ["quote", "carrier_selection"])
def test_cac_tool_khac_khong_bi_dung_toi(ten):
    args, _, _ = chot_dau_vao(ten, {"invoice_date": "2026-12-01"}, "hoá đơn lập ngày 05/01/2027")
    assert args.get("invoice_date") == "2026-12-01"


def test_doi_dau_cuoi_hoa_don_2027_co_dong_8_bi_chan_qua_dung_duong_chat():
    """Đường chạy thật: `chot_dau_vao` rồi `/tools/vat`. Trước thay đổi này ngày không tới tool và kết quả chỉ kèm cảnh báo mềm."""
    cau = "tính VAT hoá đơn lập ngày 05/01/2027: Dầu 1.000.000đ chưa gồm VAT, thuế suất 8%, tổng ghi trên hoá đơn 1.080.000đ"
    args, hoi, _ = chot_dau_vao("vat", {**ARGS, "invoice_date": "2026-12-01"}, cau)
    assert hoi is None
    r = client.post("/tools/vat", json={**args, "prices_include_vat": False})
    assert r.status_code == 422 and "10%" in r.json()["detail"]


def test_hoa_don_trong_cua_so_van_qua_va_ghi_ngay():
    cau = "tính VAT hoá đơn lập ngày 15/12/2026: Dầu 1.000.000đ chưa gồm VAT, thuế suất 8%, tổng ghi trên hoá đơn 1.080.000đ"
    args, hoi, _ = chot_dau_vao("vat", dict(ARGS), cau)
    assert hoi is None
    r = client.post("/tools/vat", json={**args, "prices_include_vat": False})
    assert r.status_code == 200 and r.json()["effective_date"] == "2026-12-15"


def test_khong_co_ngay_thi_tool_canh_bao_khong_chan():
    args, _, _ = chot_dau_vao("vat", {**ARGS, "invoice_date": "2026-12-01"}, "tính VAT Dầu 1.000.000đ chưa gồm VAT, thuế suất 8%, tổng ghi trên hoá đơn 1.080.000đ")
    r = client.post("/tools/vat", json={**args, "prices_include_vat": False})
    assert r.status_code == 200 and r.json()["effective_date"] is None and "ngày lập" in r.json()["warnings"][0]
