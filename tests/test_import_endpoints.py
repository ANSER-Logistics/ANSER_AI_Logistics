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

PHÁT HIỆN (13/11/2026)
---------------------
File hỏng, file rỗng và tên sheet không tồn tại đều làm cả hai endpoint trả
**500**. Endpoint chỉ bắt ValueError (-> 422) và RuntimeError (-> 503), còn
`_rows_from_workbook` / `_rows` gọi thẳng `openpyxl.load_workbook`, nên
BadZipFile, KeyError... rơi ra ngoài. /tools/inventory-import KHÔNG bị: lớp đọc
của nó gom mọi lỗi openpyxl về ValueError (src/core/inventory_import.py, khối
chú thích "openpyxl ném đủ loại ngoại lệ...").

Theo issue #36, PR này KHÔNG sửa src/. Các ca đó để `xfail(strict=True)`: hôm
nay chúng hỏng như dự kiến; ngày ai sửa xong, chúng thành XPASS và strict làm
bộ test đỏ — buộc người sửa gỡ dấu xfail, thay vì để nó nằm đó mãi.
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

BUG_500 = (
    "Phát hiện #36: lớp đọc .xlsx của endpoint này không gom lỗi openpyxl về "
    "ValueError như inventory_import, nên file hỏng ra 500 thay vì 422."
)


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


@pytest.mark.xfail(strict=True, reason=BUG_500)
@pytest.mark.parametrize("url", [URL_DOI_TAC, URL_HANG_HOA])
@pytest.mark.parametrize("content,form", FILE_HONG)
def test_file_hong_tra_loi_co_cau_truc_khong_phai_500(url, content, form):
    resp = _post(url, content, **form)
    assert resp.status_code == 422, f"{url}: {resp.status_code} {resp.text[:200]}"
    assert resp.json()["detail"]


@pytest.mark.xfail(strict=True, reason=BUG_500)
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


def test_chot_chong_xanh_suong_cac_ca_xfail_dang_hong_THAT_vi_500():
    """xfail chỉ nói "có hỏng", không nói hỏng VÌ SAO. Nếu các ca trên hỏng vì
    một lý do khác (sai URL -> 404, đổi tên trường -> 422 khác) thì xfail vẫn
    "đạt" mà không kiểm gì. Ca này khẳng định thẳng: hôm nay là 500.

    Ngày bug được sửa, ca này đỏ cùng lúc với các ca xfail thành XPASS — xoá cả
    ca này lẫn dấu xfail trong cùng PR sửa.
    """
    for url in (URL_DOI_TAC, URL_HANG_HOA):
        assert _post(url, b"day khong phai file excel").status_code == 500
