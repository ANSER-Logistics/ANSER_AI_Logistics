"""
tests/test_retrieval_policy.py — được phép lấy câu trả lời từ đâu.

Luật ở đây quyết định một chuyện rất cụ thể: có được lấy một trang bất kỳ trên
mạng và trình bày như thể đó là quy định của công ty khách hay không. Sai theo
hướng "chặn nhầm" thì mất một câu trả lời; sai theo hướng "cho qua nhầm" thì
chủ doanh nghiệp ra quyết định dựa trên thông tin của công ty khác.
"""

import json
import logging
from pathlib import Path

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
        ("thuế suất cho nhà xe Vạn Tín Logistics", "Vạn"),
        ("hợp đồng với đối tác Phúc Thịnh cần giấy tờ gì", "Phúc"),
        # Ca này bắt được một lỗi thật: bản đầu để "VIỆT"/"NAM" vào danh sách
        # từ chung (nghĩ tới "Việt Nam"), nên vòng lặp dừng ngay ở "Nam" và
        # TÊN NGƯỜI ĐI LỌT. Phép thử "câu có đổi không" vẫn xanh — chỉ khi đòi
        # chính cái tên biến mất mới lộ ra.
        ("thủ tục kiện khách Trần Văn Nam đòi nợ 340 triệu", "Nam"),
        # Ba ca dưới bắt một lỗ R2 ở ĐÚNG cách viết tên doanh nghiệp thường
        # gặp nhất. Bản 517d232 để hình thức pháp nhân ở nhánh `break`, nên
        # vòng quét dừng ngay ở "TNHH" và tên khách đứng sau đi nguyên ra bộ
        # tìm kiếm. Mười ca cũ không có ca nào viết hình thức pháp nhân, nên
        # cả bộ test vẫn xanh trong khi lớp lọc hở ở cách viết phổ biến nhất.
        ("công ty TNHH Minh Long phải làm gì", "Minh"),
        ("công ty TNHH Minh Long phải làm gì", "Long"),
        ("công ty CP XNK Đại Việt xuất hoá đơn thế nào", "Đại"),
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


def test_giu_hinh_thuc_phap_nhan_nhung_xoa_ten():
    """Hình thức pháp nhân Ở LẠI, tên riêng sau nó thì KHÔNG.

    Hai yêu cầu ngược nhau trong cùng một câu. "TNHH" là thông tin công khai và
    một câu hỏi thuế có thể cần biết nó; "Minh Long" là tên khách, mà R2 liệt kê
    danh sách khách là dữ liệu khách hàng.
    """
    ra = loc_truy_van_web("công ty TNHH Minh Long phải làm gì")
    assert "TNHH" in ra
    assert "Minh" not in ra and "Long" not in ra

    # Hình thức pháp nhân đứng SAU tên cũng phải ở lại.
    ra = loc_truy_van_web("công ty Minh Long TNHH phải làm gì")
    assert "TNHH" in ra
    assert "Minh" not in ra and "Long" not in ra

    # Nhiều hình thức pháp nhân liền nhau.
    ra = loc_truy_van_web("công ty CP XNK Đại Việt xuất hoá đơn thế nào")
    assert "CP" in ra and "XNK" in ra
    assert "Đại" not in ra and "Việt" not in ra


# ---------------------------------------------------------------------------
# Tên viết THƯỜNG sau từ đánh dấu (BR-26)
#
# "công ty minh long có bắt buộc không" từng đi nguyên văn tới bộ tìm kiếm vì
# không có chữ hoa nào để bám vào. Luật mới: xoá tới ba từ thường lạ sau từ đánh
# dấu, dừng ở từ thông dụng, và từ lạ thứ tư thì không gửi gì.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cau, ten_phai_biet_mat, phai_con",
    [
        ("công ty minh long có bắt buộc xuất hoá đơn không", ["minh", "long"], "công ty có bắt buộc"),
        ("nhà xe vạn tín thu cước thế nào", ["vạn", "tín"], "nhà xe thu cước"),
        ("thủ tục kiện khách trần văn nam đòi nợ", ["trần", "văn", "nam"], "khách đòi nợ"),
        # Chữ hoa vẫn được lo như cũ, kể cả khi từ đánh dấu gõ không dấu.
        ("cong ty Minh Long có bắt buộc không", ["Minh", "Long"], "cong ty có bắt buộc"),
        # "nhà cung cấp" dài ba từ: bản trước không bao giờ nhận ra nó là từ đánh dấu.
        ("nhà cung cấp Minh Long có phải xuất hoá đơn không", ["Minh", "Long"], "nhà cung cấp có phải"),
        ("nhà cung cấp minh long có phải xuất hoá đơn không", ["minh", "long"], "nhà cung cấp có phải"),
        # Sau dấu hai chấm là một danh sách tên.
        ("nhà cung cấp: Minh Long, Hưng Phát có phải nộp thuế không", ["Minh", "Hưng"], "nhà cung cấp:"),
    ],
)
def test_ten_viet_thuong_khong_roi_khoi_he_thong(cau, ten_phai_biet_mat, phai_con):
    ra = loc_truy_van_web(cau)
    for ten in ten_phai_biet_mat:
        assert ten not in ra, f"còn sót {ten!r} trong {ra!r}"
    assert phai_con in ra, f"xoá quá tay: {ra!r}"


def test_tu_danh_dau_nhan_ca_dang_khong_dau():
    """Gõ không dấu là chuyện thường; bản trước chỉ nhận dạng có dấu."""
    for cau in ["cong ty Minh Long", "khach hang Minh Long", "nha xe Minh Long", "doi tac Minh Long"]:
        ra = loc_truy_van_web(cau + " có phải nộp thuế không")
        assert "Minh" not in ra and "Long" not in ra, ra


def test_tu_la_thu_tu_thi_khong_gui_gi():
    """Chuỗi quá dài những từ lạ sau từ đánh dấu: không chắc xoá sạch được thì KHÔNG GỬI (R2)."""
    assert loc_truy_van_web("công ty minh long hưng phát có bắt buộc không") == ""
    # Đúng ngưỡng: ba từ lạ vẫn xoá được và vẫn gửi.
    ra = loc_truy_van_web("công ty minh long hưng có bắt buộc không")
    assert ra == "công ty có bắt buộc không"
    # Câu gõ KHÔNG DẤU hoàn toàn: không phân biệt được "mình" với "minh" nên bị chặn.
    assert loc_truy_van_web("cong ty minh long co bat buoc khong") == ""


def test_khop_dau_chinh_xac_minh_khong_phai_minh():
    """"mình" (đại từ, thông dụng) khác "minh" (tên riêng). Bỏ dấu rồi so thì hai từ này khớp nhau."""
    assert loc_truy_van_web("công ty mình có phải nộp thuế không") == "công ty mình có phải nộp thuế không"
    assert loc_truy_van_web("công ty minh có phải nộp thuế không") == "công ty có phải nộp thuế không"


def test_danh_sach_tu_thong_dung_khong_chua_tu_co_the_la_ten():
    """Thêm một từ vào danh sách là nới lỏng một lớp R2; những từ này không được vào."""
    from src.core.retrieval_policy import _TU_THONG_DUNG

    co_the_la_ten = {"minh", "long", "hà", "hải", "nam", "phát", "thịnh", "hưng", "anh", "chị", "em",
                     "lan", "hoa", "tâm", "đức", "dũng"}
    assert not (co_the_la_ten & _TU_THONG_DUNG), sorted(co_the_la_ten & _TU_THONG_DUNG)
    # Khớp theo dấu chính xác nên mọi mục phải là chữ thường có dấu đúng, không khoảng trắng.
    assert all(t == t.lower() and t.isalpha() for t in _TU_THONG_DUNG)
    assert len(_TU_THONG_DUNG) >= 150  # chống xanh suông: đọc nhầm thì tập rỗng và mọi câu bị chặn


def test_het_cau_thi_het_ten_khong_xoa_sang_cau_sau():
    """"cho khách. Dịch vụ gia công" — chữ sau dấu chấm là câu khác, không phải tên khách."""
    cau = "Cửa hàng nhận gia công cho khách. Dịch vụ gia công và nguyên liệu tách riêng hay gộp chung?"
    assert loc_truy_van_web(cau) == cau


# Câu hỏi công khai kiểu thật, có từ đánh dấu: phải đi nguyên văn. Mỗi câu là một ca có thật
# mà luật tên-viết-thường có thể cắt nhầm; từ nào phải vào `_TU_THONG_DUNG` để câu thoát đều có
# ở đây. Không có số trong câu: lọc số là việc của lớp khác.
@pytest.mark.parametrize(
    "cau",
    [
        "khách hàng nước ngoài có được hoàn thuế GTGT không",
        "công ty vận tải có phải nộp thuế môn bài không",
        "công ty tôi có phải xuất hoá đơn điện tử không",
        "công ty của tôi mới mở thì khai thuế theo quý hay tháng",
        "nhà cung cấp nước ngoài có chịu thuế nhà thầu không",
        "khách hàng không lấy hoá đơn thì xử lý thế nào",
        "công ty cổ phần có phải nộp thuế TNDN không",
        "đối tác nước ngoài ký hợp đồng bằng tiếng Anh thì thuế thế nào",
        "nhà xe cho thuê xe có phải xuất hoá đơn không",
        "khách mua hàng xong đòi trả lại thì hoá đơn xử lý sao",
        "công ty con có được khấu trừ thuế đầu vào của công ty mẹ không",
        "khách vãng lai không lấy hoá đơn có phải lập hoá đơn bán lẻ không",
        "công ty nợ thuế quá hạn bị phạt chậm nộp bao nhiêu",
        "nhà cung cấp dịch vụ vận chuyển quốc tế có chịu thuế GTGT không",
        "công ty logistics có phải đăng ký giấy phép kinh doanh vận tải không",
        "khách đặt cọc trước thì xuất hoá đơn lúc nào",
        "công ty bảo hiểm có phải xuất hoá đơn điện tử không",
        "công ty tư nhân và công ty TNHH khác nhau thế nào về thuế",
        "nhà xe chậm giao hàng thì phạt hợp đồng theo luật nào",
        "khách hàng trả chậm có được tính vào doanh thu tính thuế không",
        "khách sạn có phải nộp thuế GTGT không",
        "đối tác nào được miễn thuế nhập khẩu theo nghị định 134/2016/NĐ-CP",
    ],
)
def test_cau_cong_khai_that_co_tu_danh_dau_di_nguyen_van(cau):
    assert loc_truy_van_web(cau) == cau


def test_log_khong_chua_noi_dung_truy_van(caplog):
    """Log là chỗ thứ hai tên khách rời hệ thống: dòng cảnh báo không được kèm truy vấn."""
    cau = "công ty zxqv ptrk wmnb hhjd có bắt buộc không"
    with caplog.at_level(logging.DEBUG, logger="src.core.retrieval_policy"):
        assert loc_truy_van_web(cau) == ""
    assert caplog.records, "chặn truy vấn mà không ghi log nào thì không ai biết"
    for r in caplog.records:
        dau_van_tay = " ".join([r.getMessage(), str(r.__dict__)])
        for tu in ("zxqv", "ptrk", "wmnb", "hhjd"):
            assert tu not in dau_van_tay, f"log chứa nội dung truy vấn: {dau_van_tay!r}"


# ---------------------------------------------------------------------------
# Nghiệm thu BR-26: tỷ lệ câu công khai thật bị lớp này cắt hoặc chặn nhầm ≤ 1%
# trên các câu hỏi có sẵn trong repo (đo ngày 15/11/2026: 0 trên 108 câu duy nhất).
# 108 mẫu chưa đủ để khẳng định ≤ 1% bằng thống kê (0/108 có cận trên 95% khoảng 3,4%):
# con số này canh việc KHÔNG TỆ ĐI, không chứng minh mức tuyệt đối.
# ---------------------------------------------------------------------------

_GOC = Path(__file__).resolve().parent.parent


def _cau_hoi_co_san() -> list[str]:
    nguon = [_GOC / "offline_training" / "seed_prompts.jsonl",
             *sorted((_GOC / "offline_training" / "v2_sources").glob("*.jsonl"))]
    cau: list[str] = []
    for p in nguon:
        for dong in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                o = json.loads(dong)
            except ValueError:
                continue
            if not isinstance(o, dict):
                continue
            if "messages" in o:
                cau += [m.get("content", "") for m in o["messages"] if m.get("role") == "user"]
            else:
                cau += [o[k] for k in ("prompt", "question", "user", "message", "text", "input",
                                       "query", "instruction") if isinstance(o.get(k), str)]
    return sorted({c for c in cau if c})


def test_ty_le_chan_nham_tren_cau_hoi_cong_khai_co_san(monkeypatch):
    from src.core import retrieval_policy as rp

    cong_khai = [c for c in _cau_hoi_co_san() if decide_web_fallback(c).allow]
    assert len(cong_khai) >= 100, f"chỉ thấy {len(cong_khai)} câu công khai — đổi định dạng file nguồn?"

    thuc = {c: loc_truy_van_web(c) for c in cong_khai}
    # Đường cơ sở: cùng bộ lọc số nhưng KHÔNG có lớp tên riêng.
    monkeypatch.setattr(rp, "_xoa_ten_rieng", lambda q: q)
    co_so = {c: loc_truy_van_web(c) for c in cong_khai}

    khac = [(c, co_so[c], thuc[c]) for c in cong_khai if thuc[c] != co_so[c]]
    chan = [c for c, _, moi in khac if moi == ""]
    assert len(khac) <= max(1, len(cong_khai) // 100), (
        f"{len(khac)}/{len(cong_khai)} câu công khai bị lớp tên riêng đổi, {len(chan)} bị chặn: "
        + "; ".join(f"{c[:70]!r} -> {m[:70]!r}" for c, _, m in khac[:5])
    )
