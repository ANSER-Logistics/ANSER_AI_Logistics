"""
tests/test_so_thuc_va_loc_web.py — hai chỗ một con số đi lọt vì hai bộ đọc số
tiền trong repo nhìn cùng một chuỗi theo hai cách khác nhau.

1. `grounding.numbers_in` đọc `12500000.0` thành `125000000` (gấp mười).
2. `retrieval_policy.loc_truy_van_web` chỉ biết dạng có dấu, nên số tiền gõ
   không dấu đi nguyên văn tới DuckDuckGo (R2).

Cả hai đều do một nguyên nhân: có ba bộ đọc số tiền (`grounding`,
`doc_dau_vao`, `retrieval_policy`), mỗi bộ biết một tập hình dạng riêng. Phần
chênh giữa các tập đó là chỗ dữ liệu đi qua mà không ai thấy.
"""

from __future__ import annotations

import pytest

from src.core.grounding import narration_numbers_ok, numbers_in
from src.core.retrieval_policy import loc_truy_van_web

# ---------------------------------------------------------------------------
# 1. Số thực nguyên giá trị trong JSON của tool
# ---------------------------------------------------------------------------

CTX = '{"calculated_total": 12500000.0}'


def test_so_thuc_nguyen_khong_bi_nhan_muoi():
    assert numbers_in(CTX) == {"12500000"}


def test_cau_dung_qua_duoc_voi_context_dang_float():
    """Trước đây chặn OAN: context chỉ còn '125000000' nên '12.500.000' không khớp."""
    ok, vi_pham = narration_numbers_ok("Tổng cộng 12.500.000 đồng.", CTX)
    assert ok, f"câu đúng bị chặn: {vi_pham}"


def test_cau_lech_muoi_lan_bi_chan():
    """Trước đây LỌT: '125.000.000' khớp đúng cái số đã bị nhân mười."""
    ok, vi_pham = narration_numbers_ok("Tổng cộng 125.000.000 đồng.", CTX)
    assert not ok
    assert vi_pham == "125000000"


@pytest.mark.parametrize(
    "tho, phai_co",
    [
        ("1000.00", "1000"),         # hai chữ số 0 thập phân
        ("12.500.000,00", "12500000"),  # kiểu Việt: nghìn bằng chấm, thập phân bằng phẩy
        ("2500000.0", "2500000"),
    ],
)
def test_cac_dang_so_thuc_nguyen(tho, phai_co):
    assert phai_co in numbers_in(tho)


@pytest.mark.parametrize("tho, gia_tri", [("1.000", "1000"), ("10.000", "10000"), ("3.450.000", "3450000")])
def test_ba_chu_so_khong_van_la_dau_phan_tach_nghin(tho, gia_tri):
    """Phần thập phân CHỈ là 1–2 chữ số 0. Ba chữ số 0 là một nghìn, không phải số thực."""
    kq = numbers_in(tho)
    assert gia_tri in kq
    # Không được bị rút gọn thành '1' / '10' / '3450'
    assert tho.split(".")[0] not in kq or len(tho.split(".")[0]) >= 4


# ---------------------------------------------------------------------------
# 2. Lọc truy vấn trước khi rời hệ thống (R2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cau, khong_duoc_con",
    [
        ("doanh thu nam nay 3 ty co phai nop thue khong", "3 ty"),
        ("cong no 5 trieu qua han", "5 trieu"),
        ("gia cuoc 12tr5 co hop ly", "12tr5"),
        ("gia cuoc 12tr5 co hop ly", " 5 "),      # bản cũ để lại chữ số 5 trơ ra
        ("khach no 2 nghin 500 dong", "nghin"),
    ],
)
def test_so_tien_khong_dau_cung_bi_loc(cau, khong_duoc_con):
    ra = loc_truy_van_web(cau)
    assert khong_duoc_con not in ra, f"còn sót {khong_duoc_con!r} trong {ra!r}"


@pytest.mark.parametrize(
    "cau",
    [
        "doanh thu ba tỷ rưỡi thì thuế bao nhiêu",
        "khách đang nợ hai trăm nghìn",
    ],
)
def test_so_tien_bang_chu_khong_loc_sach_duoc_thi_khong_gui(cau):
    """
    Regex không biết chữ, nhưng `doc_so_tien` biết. Còn đọc ra được số tiền SAU
    khi lọc thì lọc chưa sạch -> trả rỗng, và `web_search_fallback` không gọi ra
    ngoài. Fail-closed: một lần tra web hụt rẻ hơn một con số công nợ nằm lại
    trong log của bên thứ ba.
    """
    assert loc_truy_van_web(cau) == ""


@pytest.mark.parametrize(
    "cau",
    [
        "thuế suất VAT theo nghị định 72/2024/NĐ-CP là bao nhiêu",
        "thông tư 123/2020/TT-BTC quy định gì về hoá đơn điện tử",
        "hoá đơn điện tử có bắt buộc với hộ kinh doanh không",
        "thủ tục đăng ký hộ kinh doanh gồm những gì",
    ],
)
def test_chot_chan_khong_chan_oan_cau_hoi_cong_khai(cau):
    """Câu hỏi luật không mang số tiền thì phải đi nguyên vẹn, kể cả số hiệu văn bản."""
    assert loc_truy_van_web(cau) == cau


def test_web_search_fallback_khong_goi_ra_ngoai_khi_loc_khong_sach(monkeypatch):
    """Lối ra duy nhất: truy vấn không lọc sạch được thì KHÔNG có lời gọi mạng nào."""
    import sys
    import types

    import src.api.dependencies as deps

    da_goi = []

    class _KhongDuocGoi:
        def __enter__(self):
            da_goi.append("DDGS")
            return self

        def __exit__(self, *a):
            return False

        def text(self, *a, **k):
            da_goi.append("text")
            return []

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=_KhongDuocGoi))

    assert deps.web_search_fallback("doanh thu ba tỷ rưỡi thì thuế bao nhiêu") == ""
    assert da_goi == [], "truy vấn còn số tiền mà vẫn gọi ra DuckDuckGo"
