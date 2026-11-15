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


# Dạng số tiền mà `doc_so_tien` chưa đọc, chỉ dùng làm chốt chặn fail-closed ở
# `loc_truy_van_web`:
#   - chữ số + "trăm" ("5 trăm nghìn" = 500.000; `_SO_TIEN` đòi đơn vị dính liền chữ số);
#   - từ chỉ số viết KHÔNG DẤU + đơn vị lớn ("hai ty ruoi", "ba ty", "mot trieu ruoi") —
#     bộ đọc chữ chỉ nhận "tỷ" có dấu dù "trieu"/"nghin" không dấu thì nhận.
_NUM_WORD = (r"(?:một|mot|hai|ba|bốn|bon|tư|năm|nam|sáu|sau|bảy|bay|tám|tam|chín|chin|"
             r"mười|muoi|mươi|chục|chuc)")
_SO_CHU_CON_SOT = re.compile(
    r"\d[\d.,]*\s*(?:trăm|tram)(?![^\W\d_])"
    rf"|(?<![^\W\d_]){_NUM_WORD}\s+(?:tỷ|tỉ|ty|ti|triệu|trieu|trăm|tram|nghìn|nghin|ngàn|ngan)(?![^\W\d_])",
    re.IGNORECASE,
)


# Từ đánh dấu một ĐỐI TÁC CỤ THỂ. Chuỗi từ viết hoa ngay sau chúng gần như
# chắc chắn là tên riêng — tên khách, tên nhà xe, tên người.
#
# Chỉ xoá SAU những từ này, không xoá mọi từ viết hoa trong câu. "Sở Kế hoạch
# Đầu tư", "Bộ Tài chính", "Tổng cục Thuế" là cơ quan nhà nước, công khai, và
# là thứ làm truy vấn tìm đúng văn bản — xoá chúng là đổi một lỗi R2 lấy một
# câu trả lời sai.
#
# Có cả dạng KHÔNG DẤU ("cong ty", "khach hang"): gõ điện thoại không dấu là chuyện thường,
# và bản trước chỉ nhận dạng có dấu nên "cong ty Minh Long" đi nguyên ra ngoài.
#
# "nhà cung cấp" dài BA từ. Bản trước chỉ thử khớp một và hai từ nên mẫu này không bao giờ
# khớp: "nhà cung cấp Minh Long" đi nguyên văn tới bộ tìm kiếm.
_DANH_DAU_DOI_TAC = re.compile(
    r"\A(công ty|cty|khách hàng|khách|nhà xe|đối tác|nhà cung cấp"
    r"|cong ty|khach hang|khach|nha xe|doi tac|nha cung cap)\Z",
    re.IGNORECASE,
)
_DO_DAI_DANH_DAU_TOI_DA = 3  # số từ của từ đánh dấu dài nhất ("nhà cung cấp")

# Hình thức pháp nhân: viết hoa nhưng KHÔNG phải tên riêng — nên vòng quét BỎ
# QUA chúng rồi đi tiếp, chứ không dừng lại ở chúng.
#
# CỐ Ý KHÔNG có "VIỆT"/"NAM" ở đây. Bản đầu có, và nó làm lọt một tên người:
# "khách Trần Văn Nam" -> "khách Nam", vì vòng lặp dừng ngay ở "Nam". Giữa
# nguy cơ bỏ sót một cái tên và nguy cơ xoá nhầm chữ "Việt Nam" trong một câu
# hỏi luật, chọn cái thứ hai — R2 là ràng buộc bất biến, một truy vấn kém hơn
# một chút thì không.
_HINH_THUC_PHAP_NHAN = {"TNHH", "CP", "CTCP", "MTV", "TM", "DV", "XNK", "SX"}

# ---------------------------------------------------------------------------
# Tên viết THƯỜNG sau từ đánh dấu (BR-26)
# ---------------------------------------------------------------------------
# "công ty minh long có bắt buộc không" — không có chữ hoa nào để bám vào, nên
# `_xoa_ten_rieng` bỏ qua và tên khách đi nguyên văn tới bộ tìm kiếm. Gõ điện thoại,
# gõ nhanh, không viết hoa là chuyện thường.
#
# Luật: sau từ đánh dấu, mỗi từ viết thường KHÔNG nằm trong `_TU_THONG_DUNG` là một ứng
# viên tên riêng và bị xoá, tối đa `_SO_TU_TEN_TOI_DA`. Gặp từ thông dụng thì dừng. Gặp
# từ lạ thứ tư liền nhau thì KHÔNG GỬI truy vấn đi (fail-closed): một chuỗi dài những từ
# lạ sau "khách" nhiều khả năng không còn là một cái tên mà là một đoạn mô tả khách, và
# một lần tra web hụt rẻ hơn một tên khách rò ra ngoài (R2).
#
# KHỚP THEO DẤU CHÍNH XÁC, không bỏ dấu rồi so. Bỏ dấu thì "mình" (đại từ) khớp "minh"
# (tên riêng) và "đang" khớp "Đặng": đúng hai từ mà luật này sinh ra để phân biệt. Hệ quả:
# câu gõ không dấu có từ đánh dấu thì hầu như luôn bị chặn — chấp nhận, vì không có cách
# nào tách "mình" khỏi "minh" khi đã mất dấu.
#
# KHÔNG đưa vào đây những từ có thể là tên: "minh", "long", "hà", "hải", "nam", "anh",
# "chị", "em" (đại từ nhưng cũng là tên), "thịnh", "hưng", "phát" (tên riêng thường gặp, nhưng cũng
# "phát hành": "công ty phát hành hoá đơn" thành "công ty hoá đơn", chấp nhận mất chữ đó).
# Thêm một từ vào đây là nới lỏng một lớp R2: phải kèm một câu trong
# `test_cau_cong_khai_that_co_tu_danh_dau_di_nguyen_van` cho thấy câu đó có thật và đang
# bị cắt nhầm.
#
# KHÔNG chữa được ở đây, và cố ý nói ra: tên đứng SAU một từ thông dụng
# ("công ty vận tải minh long", vì "vận" dừng vòng quét) hoặc không đứng sau từ đánh dấu
# ("minh long có phải nộp thuế không") vẫn lọt.
_SO_TU_TEN_TOI_DA = 3

_TU_THONG_DUNG = frozenset(
    """
    của là có không và với cho để thì mà hay hoặc nếu khi nào gì sao thế này kia đó ấy
    những các một mọi mỗi từng cả đã đang sẽ vừa mới còn cũng chỉ rất quá lắm hơn nhất
    được bị phải nên cần muốn định bắt buộc nữa lại luôn ngay thật khá hơi
    tôi mình ta chúng họ bên phía chỗ nhà ở tại trong ngoài trên dưới sau trước giữa
    theo về đến tới từ qua sang vào ra lên xuống do bởi vì như
    mua bán nhập xuất trả nợ đòi thu chi nộp kê khai ký gửi nhận đặt giao hủy huỷ hoàn
    đổi xin yêu cầu cung cấp dùng sử dụng làm tính lập ghi thanh toán chuyển lưu
    xử lý thực hiện áp tìm hiểu quay đăng điền đưa thối trừ cộng
    hàng hoá hóa đơn tiền giá thuế doanh nghiệp vận tải cước phí xe kho tài chính cá nhân
    tổ chức cổ phần trách nhiệm hữu hạn thương mại dịch vụ sản khẩu đại lý nước nội địa
    lẻ sỉ mẹ con công ty cty phụ thuộc liên quan nghiệp vụ hộ kinh gia đình
    mới cũ thân thiết thường xuyên tiềm năng mục tiêu hài lòng khó tính trung thành vip
    tháng năm ngày tuần quý kỳ lần lúc hôm nay mai qua cuối đầu
    nợ công đã hết quá hạn còn thiếu dư số lượng tổng đủ
    gì nào sao đâu bao nhiêu mấy
    sạn vãng lai quen du lịch cọc chậm tư nhân bảo hiểm luật kiểm toán cửa người lớn nhỏ
    xác rồi lo ngại logistics online offline startup freight forwarder khác nhau giống
    kém hiệu quả phân phối cạnh tranh trẻ
    """.split()
)


class _KhongLocSach(Exception):
    """Tên viết thường dài quá ngưỡng: không xoá chắc được thì không gửi (R2)."""


def _do_dai_danh_dau(tu: list[str], i: int) -> int:
    """Từ đánh dấu bắt đầu ở `tu[i]` dài mấy từ (0 nếu không phải): thử dài trước."""
    for dai in range(min(_DO_DAI_DANH_DAU_TOI_DA, len(tu) - i), 0, -1):
        cum = " ".join(w.strip(".,;:!?") for w in tu[i : i + dai])
        if _DANH_DAU_DOI_TAC.match(cum):
            return dai
    return 0


def _tu_la_ten_thuong(w: str) -> bool:
    """Từ viết thường, toàn chữ, không thuộc `_TU_THONG_DUNG`: ứng viên tên riêng."""
    return bool(w) and w.isalpha() and w.islower() and w not in _TU_THONG_DUNG


def _xoa_ten_rieng(query: str) -> str:
    """Bỏ tên riêng đứng ngay sau một từ đánh dấu đối tác: chuỗi từ viết hoa, rồi tới
    `_SO_TU_TEN_TOI_DA` từ thường lạ. Ném `_KhongLocSach` nếu còn từ lạ thứ tư."""
    tu = (query or "").split()
    ra: list[str] = []
    i = 0
    while i < len(tu):
        ra.append(tu[i])
        # Từ đánh dấu dài một tới ba từ: "khách", "khách hàng", "nhà cung cấp".
        dai = _do_dai_danh_dau(tu, i)
        if not dai:
            i += 1
            continue
        ra.extend(tu[i + 1 : i + dai])
        # Từ đánh dấu kết thúc bằng dấu hết câu/mệnh đề ("...cho khách. Dịch vụ gia công"):
        # chữ đứng sau là câu khác, không phải tên khách. (Dấu hai chấm thì không dừng:
        # "nhà cung cấp: Minh Long" là một danh sách tên.)
        if tu[i + dai - 1][-1] in ".!?;,":
            i += dai
            continue
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
        # Tên viết thường: xoá tới `_SO_TU_TEN_TOI_DA` từ lạ, dừng ở từ thông dụng, ở từ
        # có dấu câu theo sau (hết mệnh đề), và ở bất kỳ thứ gì không phải chữ thường.
        so_tu = 0
        while j < len(tu):
            w = tu[j].strip(".,;:!?")
            if not _tu_la_ten_thuong(w):
                break
            so_tu += 1
            if so_tu > _SO_TU_TEN_TOI_DA:
                raise _KhongLocSach(so_tu)
            ket_thuc = tu[j][-1] in ".,;:!?"
            j += 1
            if ket_thuc:
                break
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

    TÊN VIẾT THƯỜNG (BR-26, thêm 15/11/2026): sau từ đánh dấu, từ viết thường không
    thuộc `_TU_THONG_DUNG` bị xoá, tối đa ba từ; từ lạ thứ tư thì trả chuỗi rỗng.

        "công ty minh long có bắt buộc không"   -> "công ty có bắt buộc không"
        "công ty của tôi", "công ty vận tải"    -> không đổi

    CÒN SÓT, cố ý, hai chỗ — đọc kỹ vì một lớp lọc im lặng bỏ sót còn nguy hơn không
    có lớp nào, người đọc sẽ tưởng đã an toàn:

      1. Tên KHÔNG đứng ngay sau từ đánh dấu: "minh long có phải nộp thuế không".
      2. Tên đứng sau một từ thông dụng: "công ty vận tải minh long", vì "vận" dừng vòng
         quét. Chữa cả hai thì phải xoá bất kể từ đánh dấu, và lúc đó "công ty vận tải"
         cũng bị cắt.

    Câu gõ KHÔNG DẤU mà có từ đánh dấu thì hầu như luôn trả chuỗi rỗng: danh sách từ
    thông dụng khớp theo dấu chính xác (lý do ở `_TU_THONG_DUNG`).
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
    try:
        ra = _xoa_ten_rieng(" ".join(sach.split()))
    except _KhongLocSach:
        # KHÔNG ghi truy vấn vào log: log là chỗ thứ hai tên khách rời hệ thống.
        logger.warning(
            "Truy vấn web có chuỗi từ thường lạ sau từ đánh dấu đối tác — không gửi (R2)",
            extra={"so_tu_toi_da": _SO_TU_TEN_TOI_DA},
        )
        return ""

    # Chốt chặn cuối, FAIL-CLOSED. Regex ở trên chỉ biết những HÌNH DẠNG ta đã
    # nghĩ ra; `doc_so_tien` là bộ đọc số tiền của cổng đầu vào và biết thêm
    # chữ ("ba tỷ rưỡi", "hai trăm nghìn"). Hai bộ đọc lệch nhau thì phần lệch là
    # chỗ dữ liệu khách đi qua. Còn đọc ra được số tiền SAU khi đã lọc nghĩa là
    # không lọc sạch được -> KHÔNG gửi gì. Một lần tra web hụt rẻ hơn một con
    # số công nợ nằm lại trong log của bên thứ ba (R2).
    from src.core.doc_dau_vao import doc_so_tien  # nạp muộn: tránh vòng import

    con_lai = doc_so_tien(ra)
    # `doc_so_tien` KHÔNG biết hai họ dạng sau, nên chốt chặn phải tự biết thêm (đo 12/11/2026:
    # cả hai đều đi nguyên văn tới DuckDuckGo). Gộp chúng vào bộ đọc chung là việc của #222 —
    # nó đổi cách cổng ĐẦU VÀO hỏi lại khách nên cần đo trên câu thật; ở đây chỉ làm bộ lọc
    # CHẶT hơn, mà chặt hơn nghĩa là bỏ một lần tra web, không bao giờ là sai số liệu.
    if con_lai or _SO_CHU_CON_SOT.search(ra):
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
