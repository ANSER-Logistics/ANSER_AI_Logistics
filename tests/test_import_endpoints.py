"""
tests/test_import_endpoints.py — POST /tools/partner-import và /tools/product-import
(issue #36).

VÌ SAO CÓ FILE NÀY
------------------
Phần ĐỌC BẢNG đã có test (`parse_partner_table` trong test_partner_import.py,
`parse_product_table` trong test_vat_catalog.py). Phần chưa ai kiểm là hai lớp
bọc ngoài: mở file .xlsx (`load_*_xlsx_bytes`) và endpoint HTTP. Test ở đây dựng
file .xlsx THẬT bằng openpyxl rồi bắn qua HTTP, cùng cách
test_inventory_import_api.py làm.

Ca KHÔNG TOKEN -> 401 không viết lại ở đây: tests/test_auth_bao_phu.py quét
toàn bộ bảng route và đã kiểm cả hai endpoint này, với token thiếu lẫn token
sai (grep theo tên không thấy vì ca được sinh tự động):

    pytest tests/test_auth_bao_phu.py --collect-only -q | grep import

ĐÃ SỬA (15/11/2026)
-------------------
Bản đầu của file này (PR #60) ghi lại một lỗi bằng `xfail(strict=True)`: file hỏng, file rỗng
và tên sheet không tồn tại làm cả hai endpoint trả **500**, vì `partner_import` và
`vat_catalog` gọi thẳng `openpyxl.load_workbook` còn tầng HTTP chỉ bắt ValueError/RuntimeError.
Nay cả ba loader dùng chung `doc_xlsx.doc_dong_xlsx` (một chỗ, R4), gom lỗi về ValueError ->
422 như `/tools/inventory-import` vẫn làm. Dấu xfail đã gỡ đúng như strict buộc phải làm.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

openpyxl = pytest.importorskip("openpyxl")

# raise_server_exceptions=False: để lỗi 500 hiện thành MÃ TRẠNG THÁI như Body
# sẽ thấy, thay vì ném exception ra giữa test.
client = TestClient(app, raise_server_exceptions=False)

URL_DOI_TAC = "/tools/partner-import"
URL_HANG_HOA = "/tools/product-import"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# ---------------------------------------------------------------------------
# Dựng file .xlsx đúng hình dạng MISA xuất ra
# ---------------------------------------------------------------------------

def _xlsx(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _bang_doi_tac(*dong: list) -> bytes:
    return _xlsx([
        ["Danh sách khách hàng"],
        [None],
        ["STT", "Mã khách hàng", "Tên khách hàng", "Địa chỉ", "Công nợ",
         "Mã số thuế", "Điện thoại"],
        *dong,
    ])


def _bang_hang_hoa(*dong: list) -> bytes:
    return _xlsx([
        ["DANH SÁCH HÀNG HÓA, DỊCH VỤ"],
        [None],
        ["STT", "Mã", "Tên", "Giảm 2% thuế suất thuế GTGT", "Nhóm VTHH",
         "Đơn vị tính chính", "Số lượng tồn", "Giá trị tồn"],
        *dong,
    ])


def _post(url: str, content: bytes, name: str = "file.xlsx", **form):
    return client.post(url, files={"file": (name, content, MIME_XLSX)}, data=form)


# ---------------------------------------------------------------------------
# /tools/partner-import — đường thuận
# ---------------------------------------------------------------------------

def test_doi_tac_file_dung_tra_200_va_du_lieu_dung():
    resp = _post(URL_DOI_TAC, _bang_doi_tac(
        [1, "KH01", "Công ty A", "Hà Nội", 5_000_000, "0101234567", "0901"],
        [2, "KH02", "Công ty B", "Hải Phòng", 3_000_000, "0201234567", "0902"],
    ), name="khach_hang.xlsx")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    imp = body["import"]
    assert imp["ok"] is True
    assert imp["file_name"] == "khach_hang.xlsx"
    assert imp["role"] == "khách hàng"          # đoán từ tiêu đề file
    assert imp["rows_parsed"] == 2
    assert [p["code"] for p in imp["partners"]] == ["KH01", "KH02"]
    # Chỗ hay lệch nhất: hai cột cùng bắt đầu bằng 'Mã'.
    assert imp["partners"][0]["tax_id"] == "0101234567"
    assert imp["partners"][0]["balance"] == 5_000_000
    # Đọc chắc chắn thì PHẢI soi công nợ luôn.
    assert body["audit"] is not None
    assert body["audit_skipped_reason"] is None


def test_doi_tac_vai_tro_truyen_vao_duoc_ap_dung():
    resp = _post(URL_DOI_TAC, _bang_doi_tac(
        [1, "NCC01", "Nhà cung cấp X", "HN", 1_000_000, "0301234567", ""],
    ), role="nhà cung cấp")
    assert resp.status_code == 200, resp.text
    assert resp.json()["import"]["role"] == "nhà cung cấp"


def test_doi_tac_thieu_cot_bat_buoc_thi_KHONG_soi():
    """Đọc không chắc thì không soi — soi trên dữ liệu thiếu cho ra số sai mà
    vẫn trông hợp lý. Trả 200 kèm lý do, không phải lỗi HTTP."""
    resp = _post(URL_DOI_TAC, _xlsx([["STT", "Địa chỉ"], [1, "Hà Nội"]]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["import"]["ok"] is False
    assert body["import"]["rows_parsed"] == 0
    assert body["audit"] is None
    assert body["audit_skipped_reason"]


# ---------------------------------------------------------------------------
# /tools/product-import — đường thuận
# ---------------------------------------------------------------------------

def test_hang_hoa_file_dung_tra_200_va_du_lieu_dung():
    resp = _post(URL_HANG_HOA, _bang_hang_hoa(
        [1, "VT01", "Dầu nhớt SJ-40", "Chưa xác định", "HH", "Lít", 4, 7_360_000],
        [2, "VT02", "Mỡ Litium L3", "Chưa xác định", "HH", "Kg", 10, 1_200_000],
    ), name="hang_hoa.xlsx")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    imp = body["import"]
    assert imp["ok"] is True
    assert imp["file_name"] == "hang_hoa.xlsx"
    assert imp["rows_parsed"] == 2
    assert [p["code"] for p in imp["products"]] == ["VT01", "VT02"]
    assert imp["products"][0]["name"] == "Dầu nhớt SJ-40"
    assert body["audit"] is not None
    assert body["audit_skipped_reason"] is None


def test_hang_hoa_thieu_cot_bat_buoc_thi_KHONG_doi_chieu():
    resp = _post(URL_HANG_HOA, _xlsx([["STT", "Địa chỉ"], [1, "Hà Nội"]]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["import"]["ok"] is False
    assert body["audit"] is None
    assert body["audit_skipped_reason"]


# ---------------------------------------------------------------------------
# File hỏng — phải là lỗi có cấu trúc (4xx kèm `detail`), không phải 500
# ---------------------------------------------------------------------------

FILE_HONG = [
    pytest.param(b"day khong phai file excel", {}, id="byte-rac"),
    pytest.param(b"", {}, id="file-rong"),
    pytest.param(b"PK\x03\x04" + b"\x00" * 64, {}, id="zip-gia"),
]


@pytest.mark.parametrize("url", [URL_DOI_TAC, URL_HANG_HOA])
@pytest.mark.parametrize("content,form", FILE_HONG)
def test_file_hong_tra_loi_co_cau_truc_khong_phai_500(url, content, form):
    resp = _post(url, content, **form)
    assert resp.status_code == 422, f"{url}: {resp.status_code} {resp.text[:200]}"
    assert resp.json()["detail"]


@pytest.mark.parametrize("url,file_dung", [
    pytest.param(URL_DOI_TAC,
                 lambda: _bang_doi_tac([1, "KH01", "A", "HN", 1, "0101234567", ""]),
                 id="doi-tac"),
    pytest.param(URL_HANG_HOA,
                 lambda: _bang_hang_hoa([1, "VT01", "A", "Chưa xác định", "HH", "L", 1, 1]),
                 id="hang-hoa"),
])
def test_ten_sheet_khong_ton_tai_tra_422(url, file_dung):
    resp = _post(url, file_dung(), sheet="khong_co_sheet_nay")
    assert resp.status_code == 422, f"{url}: {resp.status_code} {resp.text[:200]}"
    assert resp.json()["detail"]


def test_loi_file_noi_ro_nguyen_nhan_cho_nguoi_dung():
    """422 phải kèm lời khuyên dùng được, không phải stack trace hay chuỗi rỗng."""
    for url in (URL_DOI_TAC, URL_HANG_HOA):
        r = _post(url, b"day khong phai file excel")
        assert r.status_code == 422
        assert "Không mở được file Excel" in r.json()["detail"]
    r = _post(URL_DOI_TAC, _bang_doi_tac([1, "KH01", "A", "HN", 1, "0101234567", ""]), sheet="khong_co")
    assert "Không có sheet" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Một bộ đọc dùng chung (R4): ba loader cùng hành vi khi file hỏng
# ---------------------------------------------------------------------------

def test_ba_loader_cung_nem_valueerror_khi_file_hong():
    from src.core import inventory_import, partner_import, vat_catalog

    for ham in (inventory_import.load_xlsx_bytes, partner_import.load_partners_xlsx_bytes,
                vat_catalog.load_products_xlsx_bytes):
        with pytest.raises(ValueError):          # không phải BadZipFile/KeyError... rơi ra ngoài
            ham(b"khong phai excel")


def test_tran_dong_la_loi_khong_phai_cat_bot():
    from io import BytesIO

    from src.core.doc_xlsx import doc_dong_xlsx

    data = _xlsx([[i] for i in range(10)])
    assert len(doc_dong_xlsx(BytesIO(data), None)) == 10                 # không trần: đọc hết
    assert len(doc_dong_xlsx(BytesIO(data), None, max_rows=10)) == 10    # đúng trần: được
    with pytest.raises(ValueError, match="quá 9 dòng"):
        doc_dong_xlsx(BytesIO(data), None, max_rows=9)
