"""
A9b (23/11/2026): từ ghép thông dụng mà một âm tiết cũng hay làm tên ("thanh toán", "gia đình", "trung thành"...) là CỤM dừng, không phải từ dừng đơn.

Trước A9b các âm tiết "thanh", "gia", "trung", "thành", "tài", "chính", "đại", "lý", "bảo", "thương", "tư", "nhân", "mai" nằm riêng trong `_TU_THONG_DUNG`, nên tên
khách viết thường chứa chúng ("công ty hoàng gia", "công ty thanh vân") làm vòng quét dừng và tên đi nguyên văn ra bộ tìm kiếm ngoài (R2). Lỗ có từ BR-26,
A9 (#245) chỉ ghi lại. Các ca dưới đây đo hai phía: tên không còn lọt, và câu công khai thật có chính các cụm đó vẫn đi nguyên văn.
"""
import itertools

import pytest

from src.core import retrieval_policy as rp
from src.core.retrieval_policy import _CUM_DUNG, _CUM_MO_TA, _TU_THONG_DUNG, loc_truy_van_web

AM_TIET_DA_NGHIA = ["thanh", "gia", "trung", "thành", "tài", "chính", "đại", "lý", "bảo", "thương", "tư", "nhân", "mai", "liên", "quan", "hiệu", "thường", "xuyên", "đình", "hữu"]


def _loc(q: str) -> str:
    try:
        return rp._xoa_ten_rieng(q)
    except rp._KhongLocSach:
        return ""


def test_am_tiet_hay_lam_ten_khong_con_la_tu_dung_don():
    assert not (set(AM_TIET_DA_NGHIA) & _TU_THONG_DUNG), sorted(set(AM_TIET_DA_NGHIA) & _TU_THONG_DUNG)
    assert len(_TU_THONG_DUNG) >= 150, "chống xanh suông: tập rỗng thì mọi câu bị chặn"


def test_moi_cum_dung_co_it_nhat_hai_tu_va_xep_dai_truoc():
    assert _CUM_DUNG and all(len(c) >= 2 for c in _CUM_DUNG)
    do_dai = [len(c) for c in _CUM_DUNG]
    assert do_dai == sorted(do_dai, reverse=True)


# Tên viết thường chứa âm tiết đa nghĩa: phải bị xoá, ở mọi từ đánh dấu.
TEN = ["hoàng gia", "thanh vân", "thanh hà", "gia hưng", "gia bảo", "trung kiên", "thành đạt", "tài lộc", "bảo ngọc", "đại phát", "mai linh", "lý hùng", "chính nghĩa",
       "nhân hoà", "tư thành", "liên hương", "hiệu minh", "xuyên lâm", "thường tín"]
DANH_DAU = ["công ty", "khách hàng", "nhà cung cấp", "đối tác", "nhà xe", "khách"]
DUOI = ["có bắt buộc không", "phải nộp thuế gì", "có phải xuất hoá đơn không"]


@pytest.mark.parametrize("danh_dau,ten,duoi", list(itertools.product(DANH_DAU, TEN, DUOI)))
def test_ten_chua_am_tiet_da_nghia_bi_xoa(danh_dau, ten, duoi):
    ra = _loc(f"{danh_dau} {ten} {duoi}")
    assert ra in ("", f"{danh_dau} {duoi}"), f"tên lọt hoặc xoá sai: {ra!r}"
    assert not any(t in ra.split() for t in ten.split()), ra


def test_ten_sau_cum_mo_ta_co_am_tiet_da_nghia_cung_bi_xoa():
    assert _loc("công ty vận tải thanh vân có bắt buộc không") == "công ty vận tải có bắt buộc không"
    assert _loc("công ty tài chính hoàng gia phải nộp thuế gì") == "công ty tài chính phải nộp thuế gì"
    assert _loc("công ty bảo hiểm minh long có phải xuất hoá đơn không") == "công ty bảo hiểm có phải xuất hoá đơn không"
    assert _loc("công ty gia công thanh vân có bắt buộc không") == "công ty gia công có bắt buộc không"


# Câu công khai thật có chính các cụm này: phải đi nguyên văn, không bị cắt hay chặn.
@pytest.mark.parametrize(
    "cau",
    [
        "khách thanh toán chậm thì có phải xuất hoá đơn không",
        "khách hàng thanh toán tiền mặt có được khấu trừ thuế không",
        "công ty thanh toán tiền cho nhà cung cấp thì có cần hoá đơn không",
        "hộ gia đình cho thuê nhà có phải nộp thuế không",
        "khách hàng gia đình có phải xuất hoá đơn không",
        "khách hàng trung thành được chiết khấu thì hạch toán thế nào",
        "công ty tài chính có phải nộp thuế môn bài không",
        "công ty bảo hiểm có phải xuất hoá đơn điện tử không",
        "nhà cung cấp đại lý xăng dầu có phải xuất hoá đơn không",
        "đối tác xử lý hoá đơn sai sót thì làm thế nào",
        "công ty mới thành lập có phải nộp thuế môn bài không",
        "công ty thành lập năm ngoái có phải khai thuế theo quý không",
        "công ty trách nhiệm hữu hạn một thành viên có phải nộp thuế TNDN không",
        "khách hàng liên quan có phải kê khai giao dịch liên kết không",
        "khách mua thường xuyên được chiết khấu thì hạch toán thế nào",
        "nhà xe kém hiệu quả có bị phạt hợp đồng không",
    ],
)
def test_cau_cong_khai_co_cum_dung_di_nguyen_van(cau):
    assert loc_truy_van_web(cau) == cau


def test_ten_sau_cum_thanh_lap_van_bi_xoa_khong_mat_chu_thanh_lap():
    """Ca có sẵn của A9: "thành" từng là từ dừng đơn, giờ phải đứng trong cụm "thành lập" để tên đứng trước nó vẫn được xoá mà "thành lập" không bị coi là tên."""
    assert _loc("công ty mới minh long thành lập") == "công ty mới thành lập"
    assert ("thành", "lập") in _CUM_DUNG
    assert ("thành",) not in _CUM_MO_TA


def test_hai_cum_dung_va_mo_ta_khong_chong_nhau():
    """Một cụm chỉ thuộc một loại: mô tả (giữ rồi quét tiếp) hoặc dừng (dừng quét). Chồng nhau thì luật nào thắng phụ thuộc thứ tự kiểm tra."""
    assert not (set(_CUM_DUNG) & set(_CUM_MO_TA)), set(_CUM_DUNG) & set(_CUM_MO_TA)
