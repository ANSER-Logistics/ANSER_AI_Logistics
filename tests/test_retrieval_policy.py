"""
tests/test_retrieval_policy.py — được phép lấy câu trả lời từ đâu.

Luật ở đây quyết định một chuyện rất cụ thể: có được lấy một trang bất kỳ trên
mạng và trình bày như thể đó là quy định của công ty khách hay không. Sai theo
hướng "chặn nhầm" thì mất một câu trả lời; sai theo hướng "cho qua nhầm" thì
chủ doanh nghiệp ra quyết định dựa trên thông tin của công ty khác.
"""

import pytest

from src.core.retrieval_policy import (
    KHONG_CO_TAI_LIEU,
    decide_web_fallback,
    is_internal_question,
    is_public_knowledge_question,
    loc_truy_van_web,
)

# --------------------------------------------------------------------------
# Câu hỏi nội bộ — TUYỆT ĐỐI không lấy nguồn ngoài
# --------------------------------------------------------------------------

def test_hoi_ve_tai_lieu_cua_minh_khong_tra_web():
    for cau in [
        "chính sách công nợ bên mình thế nào",
        "quy định giao nhận của công ty là gì",
        "hợp đồng với Minh Long có điều khoản phạt không",
        "bảng giá cước áp dụng cho khách sỉ ra sao",
        "quy trình nội bộ khi hàng về trễ",
    ]:
        assert not decide_web_fallback(cau).allow, cau
        assert is_internal_question(cau), cau


def test_dau_hieu_noi_bo_thang_dau_hieu_luat():
    """
    "Bên mình đang áp thuế suất mấy phần trăm" khớp CẢ HAI mẫu. Câu trả lời đúng
    là "chưa có trong tài liệu", không phải một bài viết về thuế suất.
    """
    cau = "bên mình đang áp thuế suất mấy phần trăm"
    assert is_internal_question(cau) and is_public_knowledge_question(cau)
    quyet = decide_web_fallback(cau)
    assert not quyet.allow
    assert "nội bộ" in quyet.reason


# --------------------------------------------------------------------------
# Kiến thức công khai — tra web là đúng việc
# --------------------------------------------------------------------------

def test_hoi_luat_thue_duoc_tra_web():
    for cau in [
        "nghị định 72 quy định thuế suất bao nhiêu",
        "thủ tục đăng ký hộ kinh doanh gồm những gì",
        "hoá đơn điện tử bắt buộc từ khi nào",
        "mức đóng bảo hiểm xã hội năm nay là bao nhiêu",
    ]:
        assert decide_web_fallback(cau).allow, cau


def test_cua_nha_nuoc_khong_bi_nham_la_noi_bo():
    """
    "Luật thuế của nhà nước" từng khớp phải mẫu sở hữu ở cụm "của nhà" — đúng
    câu mà tra web là việc nên làm.
    """
    cau = "quy định của nhà nước về thuế khoán hộ kinh doanh"
    assert not is_internal_question(cau)
    assert decide_web_fallback(cau).allow


# --------------------------------------------------------------------------
# Không thuộc loại nào -> không tra web
# --------------------------------------------------------------------------

def test_cau_khong_phai_kien_thuc_cong_khai_thi_khong_tra_web():
    for cau in ["hôm nay thời tiết thế nào", "bạn làm được những gì", ""]:
        assert not decide_web_fallback(cau).allow, cau


def test_moi_quyet_dinh_deu_co_ly_do():
    """Lý do đi vào log — không có nó thì không soi lại được vì sao chặn."""
    for cau in ["", "bên mình thu bao nhiêu", "nghị định 72 nói gì", "xin chào"]:
        assert decide_web_fallback(cau).reason


def test_cau_thu_nhan_khong_biet_la_hang_so():
    """
    Đây là lúc hệ thống nói mình không biết. Nhờ model diễn đạt lại thì câu đó
    có cơ hội biến thành một câu nghe như đang biết.
    """
    assert "chưa tìm thấy" in KHONG_CO_TAI_LIEU
    assert "Tài liệu" in KHONG_CO_TAI_LIEU      # chỉ đúng chỗ cần tải lên


# ===========================================================================
# R2 — truy vấn rời khỏi hệ thống không được mang dữ liệu khách
#
# `decide_web_fallback` xét CHỦ ĐỀ, không xét thứ gửi đi. Đo 04/11/2026: năm
# trên bảy câu thử mang dữ liệu khách lọt qua cổng, trong đó có doanh thu,
# bảng giá cước, tỷ lệ biên lợi nhuận và công nợ — R2 liệt kê đích danh cả bốn.
#
# `loc_truy_van_web` là lớp thứ hai: bỏ con số trước khi gửi.
# ===========================================================================



@pytest.mark.parametrize(
    "cau, phai_biet_mat",
    [
        ("thuế suất VAT bao nhiêu nếu doanh thu 4,2 tỷ một năm", "4,2"),
        ("thuế GTGT áp cho cước 18.500.000đ tuyến Hà Nội Hải Phòng", "18.500.000"),
        ("thuế TNDN tính thế nào khi biên lợi nhuận 23%", "23"),
        ("thủ tục kiện đòi nợ khách đang nợ 340 triệu", "340"),
        ("hoá đơn điện tử khi doanh thu 500000 VNĐ mỗi ngày", "500000"),
    ],
)
def test_con_so_khong_roi_khoi_he_thong(cau, phai_biet_mat):
    """Doanh thu, giá cước, biên lợi nhuận, công nợ — R2 gọi tên cả bốn."""
    ra = loc_truy_van_web(cau)
    assert phai_biet_mat not in ra, f"còn sót {phai_biet_mat!r} trong {ra!r}"


@pytest.mark.parametrize(
    "cau",
    [
        # Số hiệu văn bản pháp quy: công khai, VÀ là thứ làm truy vấn tìm đúng
        # văn bản. Lọc nó đi là đổi một lỗi R2 lấy một câu trả lời sai.
        "thuế suất VAT theo nghị định 72/2024/NĐ-CP là bao nhiêu",
        "thông tư 123/2020/TT-BTC quy định gì về hoá đơn điện tử",
        # Không có số thì không có gì để lọc.
        "thuế suất VAT cho dầu nhờn là bao nhiêu",
        "thủ tục đăng ký hộ kinh doanh gồm những gì",
    ],
)
def test_khong_loc_qua_tay(cau):
    """Lọc quá tay thì kết quả tìm kiếm kém đi — đổi lỗi này lấy lỗi khác."""
    assert loc_truy_van_web(cau) == cau


def test_don_sach_don_vi_tien_con_tro_lai():
    """Bỏ số mà để lại chữ 'đồng' thì câu truy vấn thành vô nghĩa."""
    ra = loc_truy_van_web("thuế GTGT cho khoản 5.000.000 đồng")
    assert "5.000.000" not in ra
    assert "đồng" not in ra
    assert "thuế GTGT" in ra


def test_chuoi_rong_khong_no():
    assert loc_truy_van_web("") == ""
    assert loc_truy_van_web(None) == ""


def test_duong_gui_that_dung_bo_loc():
    """
    Lọc phải nằm TRONG `web_search_fallback`, không nằm ở chỗ gọi.

    Đặt ở chỗ gọi thì chỗ gọi thứ hai thêm vào sau này sẽ quên — và quên ở đây
    nghĩa là dữ liệu khách rời khỏi hệ thống, im lặng.
    """
    import inspect

    from src.api.dependencies import web_search_fallback

    nguon = inspect.getsource(web_search_fallback)
    assert "loc_truy_van_web" in nguon, "web_search_fallback phải tự lọc"
    assert "ddgs.text(truy_van" in nguon, "phải gửi bản ĐÃ LỌC, không phải bản gốc"


# ---------------------------------------------------------------------------
# Tên riêng — R2 liệt kê "danh sách khách" là dữ liệu khách hàng
#
# Chỉ xoá chuỗi từ viết hoa đứng NGAY SAU một từ đánh dấu đối tác. Không xoá
# mọi từ viết hoa: "Sở Kế hoạch Đầu tư", "Bộ Tài chính", "Tổng cục Thuế" là cơ
# quan nhà nước, công khai, và là thứ làm truy vấn tìm đúng văn bản.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cau, ten_phai_biet_mat",
    [
        ("hoá đơn điện tử cho công ty Minh Long có bắt buộc không", "Minh"),
        ("thuế suất cho nhà xe Hoàng Phát Logistics", "Hoàng"),
        ("hợp đồng với đối tác Phúc Thịnh cần giấy tờ gì", "Phúc"),
        # Ca này bắt được một lỗi thật: bản đầu để "VIỆT"/"NAM" vào danh sách
        # từ chung (nghĩ tới "Việt Nam"), nên vòng lặp dừng ngay ở "Nam" và
        # TÊN NGƯỜI ĐI LỌT. Phép thử "câu có đổi không" vẫn xanh — chỉ khi đòi
        # chính cái tên biến mất mới lộ ra.
        ("thủ tục kiện khách Trần Văn Nam đòi nợ 340 triệu", "Nam"),
    ],
)
def test_ten_rieng_khong_roi_khoi_he_thong(cau, ten_phai_biet_mat):
    ra = loc_truy_van_web(cau)
    assert ten_phai_biet_mat not in ra, f"còn sót tên trong {ra!r}"


@pytest.mark.parametrize(
    "cau",
    [
        # Cơ quan nhà nước — công khai, và cần cho truy vấn.
        "thủ tục đăng ký với Sở Kế hoạch Đầu tư",
        "nghị định của Bộ Tài chính về hoá đơn",
        "quy định của Tổng cục Thuế về hoá đơn điện tử",
        # Hình thức pháp nhân, không phải tên riêng.
        "công ty TNHH có phải nộp thuế môn bài không",
        # Từ chung sau từ đánh dấu.
        "khách hàng cá nhân có được xuất hoá đơn không",
    ],
)
def test_khong_xoa_ten_co_quan_nha_nuoc(cau):
    """Xoá nhầm cơ quan nhà nước là đổi một lỗi R2 lấy một câu trả lời sai."""
    assert loc_truy_van_web(cau) == cau


def test_khong_an_nham_tu_thuong_chua_don_vi_tien():
    """
    "hợp đồng" có chữ "đồng" nhưng không phải đơn vị tiền.

    Bản đầu có một bước dọn đơn vị tiền riêng và nó biến "hợp đồng với đối tác"
    thành "hợp với đối tác". Đã bỏ bước đó — nhánh số của `_SO_TIEN` vốn đã
    nuốt cả đơn vị đi kèm số.
    """
    ra = loc_truy_van_web("hợp đồng với đối tác Phúc Thịnh cần giấy tờ gì")
    assert "hợp đồng" in ra
    assert "Phúc" not in ra

    # Đơn vị tiền ĐI KÈM SỐ thì vẫn phải biến mất.
    ra2 = loc_truy_van_web("thuế GTGT cho khoản 5.000.000 đồng")
    assert "5.000.000" not in ra2 and "đồng" not in ra2

