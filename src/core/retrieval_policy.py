"""
src/core/retrieval_policy.py — được phép lấy câu trả lời từ đâu.

VÌ SAO CÓ FILE NÀY
------------------
Nhánh RETRIEVAL trước đây làm một việc rất đơn giản và rất sai: tra kho tài liệu
nội bộ, không thấy gì thì **tra web rồi trả lời như thường**. Với câu "nghị định
72 quy định thuế suất bao nhiêu" thì đúng. Với câu "chính sách công nợ bên mình
thế nào" thì đó là lấy một bài viết bất kỳ trên mạng và trình bày như thể đó là
quy định của công ty khách.

Loại sai này tệ hơn hẳn "không trả lời được": nó nghe rất hợp lý, không có dấu
hiệu gì để nghi ngờ, và người đọc là chủ doanh nghiệp đang cần ra quyết định.

Nên quyết định 05/08/2026: **tách câu hỏi kiến thức công khai khỏi câu hỏi tài
liệu nội bộ**, và chỉ cho tra web ở loại thứ nhất.

VÌ SAO LÀ HÀM THUẦN Ở `core/`
-----------------------------
Không phụ thuộc HTTP, không phụ thuộc model, không trạng thái — nên test được
từng luật một. Đây là chỗ quyết định "có được nói ra ngoài phạm vi tài liệu
khách hay không", loại luật cần đọc được bằng mắt và kiểm được bằng test.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Dấu hiệu người hỏi đang nói về CHÍNH DOANH NGHIỆP MÌNH. Có bất kỳ dấu hiệu nào
# thì web bị loại thẳng, kể cả khi câu có nhắc tới thuế hay nghị định — "bên mình
# đang áp thuế suất mấy phần trăm" là câu hỏi về hồ sơ của họ, không phải về luật.
#
# "nhà" KHÔNG nằm trong danh sách sở hữu, chỉ có "nhà mình": "luật thuế của nhà
# nước" khớp phải "của nhà" và bị đánh dấu là câu hỏi nội bộ — đúng câu mà tra
# web là việc nên làm.
_INTERNAL_MARKERS = re.compile(
    r"\b(của|bên|chỗ|phía)\s+(mình|em|tôi|anh|chị|công ty|cty|nhà mình|bọn mình|chúng tôi)"
    r"|công ty (tôi|mình|em|chúng tôi)"
    r"|nội bộ"
    # "bảng giá CƯỚC áp dụng cho khách sỉ" — có chữ chen giữa, nên cho khoảng hở.
    # Nhưng "quy định CỦA NHÀ NƯỚC" thì tuyệt đối không phải tài liệu nội bộ,
    # nên chặn bằng lookahead ngay sau giới từ sở hữu.
    r"|(hợp đồng|bảng giá|báo giá|chính sách|quy định|quy trình|biểu phí|phụ lục)"
    r".{0,20}\b(của|với|ký với|áp dụng cho)\s+"
    r"(?!nhà nước|pháp luật|chính phủ|bộ |cơ quan|nhà cung cấp nào)"
    r"|(khách|nhà xe|đối tác|nhà cung cấp)\s+(của|bên)\s*(mình|tôi|em|công ty)",
    re.IGNORECASE,
)

# Kiến thức CÔNG KHAI: luật, thuế, thủ tục hành chính. Tra web ở đây là đúng
# việc — văn bản pháp quy nằm ngoài công ty và thay đổi theo thời gian, model
# học tới đâu thì biết tới đó.
_PUBLIC_KNOWLEDGE = re.compile(
    r"nghị định|thông tư|quyết định số|luật\b|bộ luật"
    r"|thuế|vat|gtgt|tncn|tndn|hoá đơn đỏ|hóa đơn đỏ|hoá đơn điện tử|hóa đơn điện tử"
    r"|tổng cục thuế|bộ tài chính|cơ quan thuế"
    r"|thủ tục|đăng ký (kinh doanh|hộ kinh doanh|doanh nghiệp)"
    r"|bảo hiểm xã hội|bhxh|hải quan|giấy phép"
    r"|quy định (của )?(nhà nước|pháp luật)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WebDecision:
    """Có được tra web không, và VÌ SAO — lý do đi vào log để soi lại được."""

    allow: bool
    reason: str


def is_internal_question(query: str) -> bool:
    """Câu hỏi về hồ sơ/quy định của chính doanh nghiệp khách."""
    return bool(_INTERNAL_MARKERS.search(query or ""))


def is_public_knowledge_question(query: str) -> bool:
    """Câu hỏi về luật, thuế, thủ tục — thứ nằm ngoài công ty."""
    return bool(_PUBLIC_KNOWLEDGE.search(query or ""))


# ---------------------------------------------------------------------------
# Lọc trước khi truy vấn RỜI KHỎI HỆ THỐNG (R2)
# ---------------------------------------------------------------------------
# `decide_web_fallback` quyết định CÓ TRA WEB KHÔNG. Nó không nói gì về thứ
# được gửi đi — và thứ được gửi đi là NGUYÊN TIN NHẮN người dùng.
#
# AGENTS.md R2 cho đúng một ngoại lệ: "nguồn công khai, CHỈ ĐỌC, KHÔNG KÈM
# THAM SỐ CHỨA DỮ LIỆU KHÁCH". Cổng chủ đề không đủ để thoả vế thứ hai.
#
# Đo 04/11/2026 — năm trên bảy câu thử mang dữ liệu khách lọt qua cổng:
#
#   "thuế suất VAT bao nhiêu nếu doanh thu 4,2 tỷ một năm"          -> cho qua
#   "thuế GTGT áp cho cước 18.500.000đ tuyến Hà Nội Hải Phòng"      -> cho qua
#   "thuế TNDN tính thế nào khi biên lợi nhuận 23%"                 -> cho qua
#   "thủ tục kiện đòi nợ khách đang nợ 340 triệu"                   -> cho qua
#
# Doanh thu, bảng giá cước, tỷ lệ biên lợi nhuận, công nợ — R2 liệt kê đích
# danh cả bốn. Chúng đang đi tới DuckDuckGo.
# Số hiệu văn bản pháp quy PHẢI GIỮ LẠI: "72/2024/NĐ-CP", "123/2020/TT-BTC".
# Đó là thứ công khai, và là thứ làm cho truy vấn tìm đúng văn bản. Bỏ nó đi là
# đổi một lỗi R2 lấy một câu trả lời sai.
_SO_VAN_BAN = re.compile(r"\b\d+\s*/\s*\d{4}\s*(?:/\s*[A-ZĐ][\w-]*)?", re.IGNORECASE)

# Thứ tự các nhánh có ý nghĩa: nhánh DÀI đặt trước. Để "4,2" ở nhánh số trần
# lên trước thì nó ăn mất phần số, bỏ lại chữ "tỷ" trơ ra — đã thấy khi đo.
#
# Và nhánh số trần KHÔNG kết thúc bằng `\b`: với "18.500.000đ", "0" và "đ" đều
# là ký tự chữ nên không có ranh giới, regex lùi dần và chỉ bắt được "18.500.",
# bỏ lại "000đ". Đúng cái bẫy đã sập một lần ở `src/core/grounding.py`.
_SO_TIEN = re.compile(
    # 1. Số kèm thang bậc: "4,2 tỷ", "340 triệu", "25 nghìn", "2tr", và cả khi
    #    gõ KHÔNG DẤU ("3 ty", "5 trieu", "2 nghin") hay nói tắt "12tr5".
    #    Bản trước chỉ có dạng có dấu, nên "cong no 5 trieu qua han" đi nguyên
    #    văn tới DuckDuckGo; gõ điện thoại không dấu là chuyện thường.
    r"\d[\d.,]*\s*(?:nghìn|ngàn|nghin|ngan|triệu|trieu|tỷ|tỉ|ty|ti|tr|k)\d*(?![^\W\d_])"
    # 2. Phần trăm: "23%", "23 phần trăm"
    r"|\d[\d.,]*\s*(?:%|phần trăm)"
    # 3. Số kèm đơn vị tiền: "18.500.000đ", "500000 VNĐ"
    r"|\d[\d.,]*\d\s*(?:đ|vnd|vnđ|đồng)(?![^\W\d_])"
    # 4. Số trần từ 4 chữ số trở lên (sau khi đã bỏ dấu phân tách)
    r"|\d[\d.,]*\d|\d{4,}",
    re.IGNORECASE,
)


# Từ đánh dấu một ĐỐI TÁC CỤ THỂ. Chuỗi từ viết hoa ngay sau chúng gần như
# chắc chắn là tên riêng — tên khách, tên nhà xe, tên người.
#
# Chỉ xoá SAU những từ này, không xoá mọi từ viết hoa trong câu. "Sở Kế hoạch
# Đầu tư", "Bộ Tài chính", "Tổng cục Thuế" là cơ quan nhà nước, công khai, và
# là thứ làm truy vấn tìm đúng văn bản — xoá chúng là đổi một lỗi R2 lấy một
# câu trả lời sai.
_DANH_DAU_DOI_TAC = re.compile(
    r"\A(công ty|cty|khách hàng|khách|nhà xe|đối tác|nhà cung cấp)\Z",
    re.IGNORECASE,
)

# Hình thức pháp nhân: viết hoa nhưng KHÔNG phải tên riêng — nên vòng quét BỎ
# QUA chúng rồi đi tiếp, chứ không dừng lại ở chúng.
#
# CỐ Ý KHÔNG có "VIỆT"/"NAM" ở đây. Bản đầu có, và nó làm lọt một tên người:
# "khách Trần Văn Nam" -> "khách Nam", vì vòng lặp dừng ngay ở "Nam". Giữa
# nguy cơ bỏ sót một cái tên và nguy cơ xoá nhầm chữ "Việt Nam" trong một câu
# hỏi luật, chọn cái thứ hai — R2 là ràng buộc bất biến, một truy vấn kém hơn
# một chút thì không.
_HINH_THUC_PHAP_NHAN = {"TNHH", "CP", "CTCP", "MTV", "TM", "DV", "XNK", "SX"}


def _xoa_ten_rieng(query: str) -> str:
    """Bỏ chuỗi từ viết hoa đứng ngay sau một từ đánh dấu đối tác."""
    tu = (query or "").split()
    ra: list[str] = []
    i = 0
    while i < len(tu):
        ra.append(tu[i])
        # Từ đánh dấu dài một hoặc hai từ: "khách" / "khách hàng", "nhà xe".
        dai = 0
        if i + 1 < len(tu) and _DANH_DAU_DOI_TAC.match(" ".join(tu[i : i + 2])):
            dai = 2
        elif _DANH_DAU_DOI_TAC.match(tu[i]):
            dai = 1
        if not dai:
            i += 1
            continue
        if dai == 2:
            ra.append(tu[i + 1])
        j = i + dai
        while j < len(tu):
            w = tu[j].strip(".,;:!?")
            if not w:
                break
            # Hình thức pháp nhân: GIỮ LẠI rồi đi tiếp, không dừng và không xoá.
            #
            # Bản 517d232 để nó ở nhánh `break`, và đó là một lỗ R2 ở đúng cách
            # viết thường gặp nhất: "công ty TNHH Minh Long" dừng ngay ở "TNHH"
            # nên "Minh Long" — tên khách — đi nguyên ra bộ tìm kiếm. Tên riêng
            # đứng SAU hình thức pháp nhân, nên dừng ở đó là dừng trước đúng thứ
            # cần xoá.
            #
            # Giữ lại chứ không xoá: "công ty TNHH" là hình thức pháp nhân, một
            # câu hỏi thuế có thể cần biết nó. Nó công khai, không phải tên ai.
            if w.upper() in _HINH_THUC_PHAP_NHAN:
                ra.append(tu[j])
                j += 1
                continue
            if not w[0].isupper():
                break
            j += 1
        i = j
    return " ".join(ra)


def loc_truy_van_web(query: str) -> str:
    """
    Bỏ con số khỏi truy vấn trước khi gửi ra ngoài. Giữ nguyên phần chủ đề.

    "thuế GTGT áp cho cước 18.500.000đ tuyến Hà Nội Hải Phòng"
      -> "thuế GTGT áp cho cước tuyến Hà Nội Hải Phòng"

    Tra cứu luật thuế cần BIẾT HỎI VỀ GÌ, không cần biết khách thu bao nhiêu.
    Bỏ con số đi thì kết quả tìm kiếm không kém đi, mà dữ liệu thì ở lại.

    CÒN HỞ GÌ — đọc tiếp
    --------------------
    Hàm này bỏ con số, VÀ bỏ tên riêng viết hoa đứng sau một từ đánh dấu đối
    tác (`_xoa_ten_rieng`, thêm 03/11/2026):

        "hoá đơn điện tử cho công ty Minh Long có bắt buộc không"
          -> "hoá đơn điện tử cho công ty có bắt buộc không"

    Chỉ xoá SAU từ đánh dấu, nên `Bộ Tài chính` / `Tổng cục Thuế` ở lại — đó là
    cơ quan nhà nước, công khai, và là thứ làm truy vấn tìm đúng văn bản.

    CÒN SÓT, cố ý, một chỗ: **tên viết thường**.

        "công ty minh long có bắt buộc không"   -> KHÔNG đổi

    Quy tắc dựa vào chữ viết hoa. Xoá N từ sau từ đánh dấu bất kể hoa thường thì
    `"công ty của tôi"` và `"công ty vận tải"` cũng bị cắt — đổi một lỗi R2 lấy
    một truy vấn hỏng. Cần chủ dự án cân, xem việc trên bảng kanzo.

    Ghi ra đây vì một lớp lọc im lặng bỏ sót còn nguy hơn không có lớp nào:
    người đọc sẽ tưởng đã an toàn. Bản trước của chính đoạn này nói ngược lại —
    nó ghi "KHÔNG bỏ được TÊN RIÊNG" và "chưa xử" trong khi `_xoa_ten_rieng` đã
    chạy — tức là nói lớp lọc yếu hơn thực tế. Lệch theo chiều nào cũng sai.
    """
    goc = query or ""

    # Giữ số hiệu văn bản pháp quy: thay bằng chỗ giữ chỗ trước khi lọc, trả
    # lại sau. Không làm thế thì nhánh "số trần" ăn mất "72/2024".
    giu: list[str] = []

    def _cat(m: "re.Match[str]") -> str:
        giu.append(m.group(0))
        return f"\x00{len(giu) - 1}\x00"

    sach = _SO_VAN_BAN.sub(_cat, goc)
    # Nhánh 3 của `_SO_TIEN` đã nuốt cả đơn vị tiền đi kèm số, nên KHÔNG cần
    # thêm một bước dọn đơn vị riêng.
    #
    # Bản trước có bước đó — `re.sub(r"\s+(đ|vnd|đồng)", …)` — và nó ăn nhầm từ
    # thường: "hợp đồng với đối tác" thành "hợp với đối tác". Chữ "đồng" trong
    # "hợp đồng" không phải đơn vị tiền. Xoá một bước lọc thừa an toàn hơn là
    # thêm ngoại lệ cho từng từ ghép.
    sach = _SO_TIEN.sub(" ", sach)
    sach = re.sub(r"\x00(\d+)\x00", lambda m: giu[int(m.group(1))], sach)
    ra = _xoa_ten_rieng(" ".join(sach.split()))

    # Chốt chặn cuối, FAIL-CLOSED. Regex ở trên chỉ biết những HÌNH DẠNG ta đã
    # nghĩ ra; `doc_so_tien` là bộ đọc số tiền của cổng đầu vào và biết thêm
    # chữ ("ba tỷ rưỡi", "hai trăm nghìn"). Hai bộ đọc lệch nhau thì phần lệch là
    # chỗ dữ liệu khách đi qua. Còn đọc ra được số tiền SAU khi đã lọc nghĩa là
    # không lọc sạch được -> KHÔNG gửi gì. Một lần tra web hụt rẻ hơn một con
    # số công nợ nằm lại trong log của bên thứ ba (R2).
    from src.core.doc_dau_vao import doc_so_tien  # nạp muộn: tránh vòng import

    con_lai = doc_so_tien(ra)
    if con_lai:
        logger.warning(
            "Truy vấn web còn số tiền sau khi lọc — không gửi (R2)",
            extra={"so_khoan": len(con_lai)},
        )
        return ""
    return ra


def decide_web_fallback(query: str) -> WebDecision:
    """
    Kho tài liệu không trả về gì — có được tra web thay thế không?

    Thứ tự có ý nghĩa: dấu hiệu nội bộ THẮNG dấu hiệu luật. "Bên mình đang áp
    thuế suất mấy phần trăm" khớp cả hai mẫu, và câu trả lời đúng là "chưa có
    trong tài liệu", chứ không phải một trang blog về thuế suất.
    """
    q = (query or "").strip()
    if not q:
        return WebDecision(False, "câu hỏi rỗng")
    if is_internal_question(q):
        return WebDecision(False, "hỏi về tài liệu nội bộ — không lấy nguồn ngoài")
    if is_public_knowledge_question(q):
        return WebDecision(True, "hỏi về luật/thuế — nguồn công khai")
    return WebDecision(False, "không phải câu kiến thức công khai")


# Câu trả lời khi kho trống VÀ không được tra web. Cố tình là hằng số tất định,
# không nhờ model diễn đạt: đây là lúc hệ thống thú nhận mình không biết, và câu
# thú nhận đó không được phép biến tướng thành một câu nghe như đang biết.
KHONG_CO_TAI_LIEU = (
    "Tôi chưa tìm thấy tài liệu nội bộ nào nói về việc này, nên tôi không trả lời "
    "để tránh nói sai. Bạn tải văn bản liên quan lên mục Tài liệu giúp tôi "
    "(hợp đồng, bảng giá, quy định nội bộ) rồi hỏi lại — khi đó tôi trả lời kèm "
    "trích dẫn đúng đoạn."
)


__all__ = [
    "WebDecision",
    "decide_web_fallback",
    "loc_truy_van_web",
    "is_internal_question",
    "is_public_knowledge_question",
    "KHONG_CO_TAI_LIEU",
]
