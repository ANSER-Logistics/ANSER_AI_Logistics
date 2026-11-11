"""
src/core/grounding.py — chốt chặn NEO SỐ LIỆU. Code thuần, không LLM (P1).

VÌ SAO CÓ FILE NÀY
------------------
Phép kiểm "mọi con số trong câu trả lời phải có trong dữ liệu" đã tồn tại từ lâu
ở `offline_training/dgen_common.py`, và nó chạy ở HAI chỗ:

  - lọc dữ liệu huấn luyện (`make_narration_pairs.verify_answer`)
  - chấm điểm benchmark (`benchmark_v3.score_narration`)

Nhưng KHÔNG chạy ở chỗ thứ ba, chỗ quan trọng nhất: **lúc phục vụ người dùng**.
Nghĩa là ta biết rõ model bịa số bao nhiêu phần trăm, và vẫn để nguyên con số bịa
đó đi thẳng ra màn hình chủ doanh nghiệp (05/08/2026).

Buổi đo cho thấy bản fine-tune bịa số ở 8-10 ca trên 27. Nhưng model không cần
giỏi hơn để dùng được: **hệ thống chỉ cần an toàn khi model sai.** Câu trả lời
chứa con số không có trong dữ liệu thì bị TỪ CHỐI, không phải sửa.

Đặt ở `src/core/` vì đây là tầng nghiệp vụ thuần — `offline_training/` giờ import
ngược vào đây, để phép kiểm lúc đo và phép kiểm lúc chạy là MỘT (P4). Hai bản
chép tay sẽ trôi khỏi nhau, và khi đó điểm benchmark không còn nói gì về thực tế.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger("projecta.grounding")


# Từ CẤM trong nội dung soạn cho KHÁCH CUỐI (P2: biên là bí mật kinh doanh).
# So word-boundary CÓ DẤU — bỏ dấu sẽ khiến "lãi" khớp nhầm "lại".
_CUSTOMER_FORBIDDEN_RE = re.compile(
    r"\b(biên|margin|lãi|giá gốc|giá nhà xe|carrier_cost|internal)\b",
    re.IGNORECASE,
)

# Số ngắn (<4 chữ số) bỏ qua: phần trăm, số chuyến, ngày trong tháng, số tấn.
# Loại chúng đi sẽ chặn oan gần hết câu trả lời bình thường.
MIN_DIGITS = 4

# Hậu tố thang bậc tiếng Việt.
#
# VÌ SAO CÓ KHỐI NÀY
# ------------------
# Bản trước bỏ dấu phân tách rồi so CHUỖI. Nên context ghi `10250000`, model
# viết "10,25 triệu đồng" — cùng một con số — mà phép kiểm thấy "1025" ≠
# "10250000" và CHẶN OAN câu trả lời đúng, thay bằng câu từ chối. Đây là lỗi
# gây hại trực tiếp: khách hỏi, hệ thống có số đúng, rồi tự bịt miệng mình.
# (BAO_CAO_BR05 §3.3 xếp nó là "mã khung đo"; docstring đầu file này nói ngược
#  lại — offline_training import ngược vào đây nên lỗi sống trong production.)
_THANG = {
    "nghìn": 1_000,
    "ngàn": 1_000,
    "k": 1_000,
    "triệu": 1_000_000,
    "tr": 1_000_000,
    "tỷ": 1_000_000_000,
    "tỉ": 1_000_000_000,
}
# Bắt mọi con số, kèm hậu tố thang bậc nếu có. Hậu tố đứng SAU số, cách bằng
# khoảng trắng hoặc dính liền ("2tr", "2 triệu").
#
# `(?![^\W\d_])` = hậu tố không được dính thêm chữ cái. Nếu không có nó thì
# "tr" trong "trieu" (viết không dấu) cũng khớp. KHÔNG dùng `\b` ở cuối toàn
# biểu thức: với "3.450.000đ", "0" và "đ" đều là ký tự chữ nên không có ranh
# giới, regex lùi dần và chỉ bắt được "3.450" -> "3450". Đã làm hỏng
# `test_bo_dau_phan_tach_nghin` đúng một lần.
_SO_KEM_THANG = re.compile(
    r"(\d[\d.,]*\d|\d)(?:\s*(nghìn|ngàn|triệu|tỷ|tỉ|tr|k)(?![^\W\d_]))?",
    re.IGNORECASE,
)


# Số thực NGUYÊN GIÁ TRỊ: "12500000.0", "1000.00", "12.500.000,00".
#
# JSON của tool in số tiền kiểu float, nên `12500000.0` là hình dạng thường gặp
# trong context — và bộ đọc cũ bỏ dấu chấm rồi dính phần "0" vào: 12500000.0 ->
# "125000000", GẤP MƯỜI. Lỗi đó đi hai chiều:
#
#   - câu đúng "12.500.000" bị chặn oan (context chỉ còn "125000000");
#   - câu SAI "125.000.000" qua được, vì nó khớp đúng cái số đã bị nhân mười.
#
# Phần thập phân CHỈ là 1–2 chữ số 0. Ba chữ số 0 là dấu phân tách nghìn của tiếng
# Việt ("1.000" = một nghìn), nên tuyệt đối không được ăn chúng.
_SO_THUC_NGUYEN = re.compile(r"(\d[\d.,]*?)[.,]0{1,2}")


def _bo_khong_thap_phan(tho: str) -> str:
    """'12500000.0' -> '12500000'; '1.000' giữ nguyên (đó là một nghìn)."""
    m = _SO_THUC_NGUYEN.fullmatch(tho)
    return m.group(1) if m else tho


def _hai_cach_doc(tho: str) -> set[float]:
    """
    '10.25' đọc được HAI cách và tiếng Việt dùng lẫn lộn cả hai.

    - dấu phân tách nghìn  -> 1025
    - dấu thập phân        -> 10.25

    Trả cả hai. Phép kiểm chỉ cần MỘT cách khớp context là cho qua — nới lỏng
    có chủ ý, vì chặn oan tốn hơn lọt một con số trùng hình dạng.
    """
    ra: set[float] = set()
    chi_so = tho.replace(".", "").replace(",", "")
    if chi_so.isdigit():
        ra.add(float(chi_so))
    if tho.count(".") + tho.count(",") == 1:
        try:
            ra.add(float(tho.replace(",", ".")))
        except ValueError:
            # Im lặng ở đây là ĐÚNG, không phải nuốt lỗi: cả hàm này là phép
            # "thử đọc theo cách thứ hai". Chuỗi không đọc được thành số thì
            # cách đọc đó không tồn tại, và đó là kết quả bình thường — log ở
            # đây sẽ nổ trên mọi đầu vào thường gặp rồi che mất log thật.
            pass
    return ra


def _nhan_thang(tho: str, hau_to: str | None) -> set[str]:
    """{'10.25', 'triệu'} -> {'10250000', '1025000000'}. Không hậu tố -> rỗng."""
    if not hau_to:
        return set()
    nhan = _THANG[hau_to.lower()]
    ra: set[str] = set()
    for gia_tri in _hai_cach_doc(tho):
        tong = gia_tri * nhan
        if tong == int(tong):
            ra.add(str(int(tong)))
    return ra


def numbers_in(text: str) -> set[str]:
    """
    Tập con số đã chuẩn hoá: '3.450.000đ' -> '3450000'.

    Kèm cả giá trị đã nhân thang bậc, nên '10,25 triệu' sinh thêm '10250000'.
    Context và answer cùng đi qua hàm này ⇒ khớp được theo cả hai chiều.
    """
    ra: set[str] = set()
    for m in _SO_KEM_THANG.finditer(text or ""):
        tho, hau_to = _bo_khong_thap_phan(m.group(1)), m.group(2)
        ra.add(tho.replace(".", "").replace(",", ""))
        ra |= _nhan_thang(tho, hau_to)
    return ra


# ---------------------------------------------------------------------------
# HÌNH DẠNG TIỀN (04/11/2026, brain#42) — CHƯA BẬT MẶC ĐỊNH
# ---------------------------------------------------------------------------
# `narration_numbers_ok` phân loại con số bằng ĐỘ DÀI (>= 4 chữ số). Ngưỡng đó
# gộp ba thứ khác hẳn nhau vào một rổ:
#
#   "11.500.000 đồng"      — tiền. Phải có trong dữ liệu.
#   "năm 2026"             — năm. Không phải đại lượng đo được.
#   "Nghị định 72/2024"    — số hiệu văn bản. Càng không phải.
#
# Và nó BỎ SÓT theo chiều ngược lại: "45 triệu" chuẩn hoá ra "45" — hai chữ số,
# dưới ngưỡng — nên bốn mươi lăm triệu đồng đi lọt chỉ vì nó được VIẾT ngắn. Đó
# là chỗ hở thâm nhất, và `derived_ratios_ok` không bắt được vì câu không có từ
# so sánh nào.
#
# Phép phân biệt dưới đây sắc hơn ngưỡng độ dài ở CẢ HAI chiều. Nó KHÔNG tái sử
# dụng `retrieval_policy._SO_TIEN` dù hàm đó trông như làm đúng việc này: hàm
# đó viết cho R2 — xoá bớt đi cho an toàn — nên nhánh cuối của nó bắt "mọi số
# từ 4 chữ số", kể cả năm. Lệch pha không nằm ở biểu thức mà ở HƯỚNG THIÊN
# LỆCH: R2 thà bắt quá, còn chốt neo số liệu thì bắt quá = chặn oan câu trả lời
# đúng ngay trước mặt khách.
#
# Một số được coi là MANG HÌNH DẠNG TIỀN khi có ít nhất một trong bốn dấu hiệu:
#
#   1. Có hậu tố thang bậc       "45 triệu", "2tr", "4,2 tỷ"
#   2. Có đơn vị tiền ngay sau   "18.500.000đ", "500000 VNĐ"
#   3. Nhóm nghìn bằng dấu chấm  "3.450.000", "5.000"
#   4. Số trần từ 5 chữ số       "50000000"   (năm chỉ có 4)
#
# Số trần đúng 4 chữ số thì KHÔNG: đó là vùng của năm, số hiệu văn bản, mã sản
# phẩm. Một khoản tiền thật gần như luôn kèm đơn vị hoặc dấu nhóm nghìn — "3450000"
# viết trần không dấu là cách không ai viết.
#
# CÒN SÓT, đã đo: `32k` bị đánh dấu là tiền vì `k` là hậu tố thang bậc, trong khi
# trong tài liệu của dự án nó luôn là độ dài ngữ cảnh ("ctx 32k"). Giữ `k` lại vì
# "25k" = 25.000đ là cách viết rất thường gặp của người Việt; 29 lượt trong tài
# liệu kỹ thuật không đại diện cho câu trả lời gửi khách.
_DON_VI_TIEN = re.compile(r"\s*(?:đ|vnd|vnđ|đồng)(?![^\W\d_])", re.IGNORECASE)

# Dấu hiệu 3 phải là NHÓM NGHÌN thật: một đến ba chữ số, rồi một hoặc nhiều nhóm
# đúng ba chữ số sau dấu chấm. "3.450.000" và "5.000" khớp; "5.1.", "2.5", "1.0",
# "15,8" KHÔNG khớp.
#
# Bản đầu tôi viết dấu hiệu này là "có dấu chấm hoặc dấu phẩy". Đo trên 27 file
# .md tiếng Việt của dự án cho thấy nó đánh dấu thêm 747 con số mà luật cũ tha —
# phần lớn KHÔNG phải tiền: số mục (`5.1.`), số phiên bản (`2.5`, `1.0`), phần
# trăm (`15,8%`), dung lượng (`12,4 GB`). Tiếng Việt dùng dấu chấm làm dấu nghìn
# VÀ dấu phẩy làm dấu thập phân, nên "có dấu" không phân biệt được gì. Bảng 14 ca
# tôi tự soạn KHÔNG bắt được lỗi này — chỉ văn bản thật bắt được.
_NHOM_NGHIN = re.compile(r"^\d{1,3}(?:\.\d{3})+$")


def la_hinh_dang_tien(tho: str, hau_to: str | None, sau: str = "") -> bool:
    """
    Con số này có mang hình dạng MỘT KHOẢN TIỀN không?

    `tho` = chuỗi số như đã viết, `hau_to` = thang bậc nếu có, `sau` = văn bản
    ngay sau con số (để thấy đơn vị tiền). Xem khối chú thích bên trên.
    """
    if hau_to:
        return True
    if _DON_VI_TIEN.match(sau or ""):
        return True
    if _NHOM_NGHIN.match(tho):
        return True
    # Đếm CHỮ SỐ, không đếm ký tự: `len("3.3.1")` là 5 nhưng đó là ba chữ số
    # (một số phiên bản), không phải một khoản tiền năm chữ số.
    return len(re.sub(r"\D", "", tho)) >= 5

def narration_numbers_ok(
    answer: str,
    context: str,
    min_digits: int = MIN_DIGITS,
    *,
    chi_kiem_so_tien: bool = False,
):
    """
    Mọi con số >= `min_digits` chữ số trong `answer` PHẢI có trong `context`.

    Một con số được cho qua nếu BẤT KỲ cách đọc nào của nó có trong context —
    dạng thô, hoặc dạng đã nhân thang bậc. Tập cách đọc luôn chứa dạng thô, nên
    phép kiểm này chỉ NỚI so với bản trước, không bao giờ siết thêm: không có
    câu nào đang qua mà sau thay đổi lại bị chặn.

    `chi_kiem_so_tien=True` thay nguong do dai bang phep phan biet hinh dang
    tien (`la_hinh_dang_tien`). Sac hon o ca hai chieu — xem khoi chu thich cua
    ham do. MAC DINH TAT: day la lop an toan huong ra khach, bat len la doi
    hanh vi va can chu du an duyet (brain#42).

    Trả `(ok, con_số_vi_phạm | None)`.
    """
    ctx_numbers = numbers_in(context)
    for m in _SO_KEM_THANG.finditer(answer or ""):
        tho, hau_to = _bo_khong_thap_phan(m.group(1)), m.group(2)
        chinh = tho.replace(".", "").replace(",", "")
        if chi_kiem_so_tien:
            if not la_hinh_dang_tien(tho, hau_to, (answer or "")[m.end():]):
                continue
        elif len(chinh) < min_digits:
            continue
        if not ({chinh} | _nhan_thang(tho, hau_to)) & ctx_numbers:
            return False, chinh
    return True, None


# ---------------------------------------------------------------------------
# Chốt SỐ TỰ SUY RA (03/11/2026, R1)
# ---------------------------------------------------------------------------
# `narration_numbers_ok` bỏ qua số dưới 4 chữ số, vì chặn hết thì "có 3 chuyến"
# hay "ngày 15" cũng bị chặn oan. Cái giá của ngưỡng đó: **"gấp khoảng 1,2 lần"
# đi lọt** — model tự chia hai con số rồi tuyên bố kết quả. Đúng thứ R1 cấm:
# LLM không bao giờ tính toán.
#
# Ngưỡng độ dài là công cụ cùn vì nó gộp hai thứ khác hẳn nhau:
#
#   "có 3 chuyến"        — đếm, trích thẳng từ dữ liệu. Hợp lệ.
#   "gấp 1,2 lần"        — tỷ lệ, suy ra bằng phép chia. Phải do tool tính.
#
# Mẫu so sánh phân biệt được hai thứ đó, nên nó SẮC HƠN ngưỡng, không phải
# nghiêm hơn. Để khớp, câu phải có ĐỒNG THỜI một từ so sánh VÀ một đơn vị tỷ lệ
# (`%` hoặc `lần`). "tăng 3 chuyến" không khớp; "ngày 15" không khớp.
#
# Và nó chỉ chặn khi con số KHÔNG có trong context. Nếu tool đã tính ra 12% và
# đặt vào dữ liệu thì model được phép nhắc lại — đó là diễn giải, không phải
# tính toán.
_SO_SUY_RA = re.compile(
    r"(gấp|bằng|cao hơn|thấp hơn|nhiều hơn|ít hơn|tăng|giảm|chiếm|tương đương)"
    r"\s*(?:khoảng|gần|hơn|chừng|tầm|độ)?\s*"
    r"(\d[\d.,]*\d|\d)\s*(%|phần trăm|lần)",
    re.IGNORECASE,
)

LOI_TU_CHOI_SUY_RA = (
    "Tôi chưa trả lời được câu này một cách chắc chắn.\n\n"
    "Bản nháp vừa tạo có cụm \"{cum}\" — một tỷ lệ không có trong dữ liệu, nghĩa "
    "là nó do model tự tính chứ không phải do hệ thống tính ra. Tôi chặn lại "
    "thay vì đưa ra một tỷ lệ nghe hợp lý mà có thể sai. "
    "Bạn xem số liệu gốc bên dưới, hoặc hỏi lại cụ thể hơn."
)


def derived_ratios_ok(answer: str, context: str):
    """
    Mọi tỷ lệ so sánh trong `answer` PHẢI có sẵn trong `context`.

    Bắt loại câu mà model tự làm phép chia rồi tuyên bố kết quả — thứ
    `narration_numbers_ok` bỏ sót vì tỷ lệ thường ngắn hơn 4 chữ số.

    Trả `(ok, cụm_vi_phạm | None)`.
    """
    ctx_numbers = numbers_in(context)
    for m in _SO_SUY_RA.finditer(answer or ""):
        tho = m.group(2)
        if not ({tho.replace(".", "").replace(",", "")} | _nhan_thang(tho, None)) & ctx_numbers:
            return False, " ".join(m.group(0).split())
    return True, None


def customer_leak(answer: str) -> list[str]:
    """Các từ lộ thông tin nội bộ tìm thấy trong nội dung gửi khách cuối."""
    return _CUSTOMER_FORBIDDEN_RE.findall(answer or "")


@dataclass
class GuardVerdict:
    """
    Kết quả soát một câu trả lời trước khi cho ra ngoài.

    `safe_answer` LUÔN dùng được: bằng chính câu model viết khi sạch, hoặc bằng
    lời từ chối khi bẩn. Chỗ gọi không phải nhớ kiểm `ok` mới biết dùng gì —
    quên kiểm là đúng cái lỗi lớp này sinh ra để chặn.
    """
    ok: bool
    safe_answer: str
    reason: str = ""
    offending: str = ""

    @property
    def blocked(self) -> bool:
        return not self.ok


_LOI_TU_CHOI_SO = (
    "Tôi chưa trả lời được câu này một cách chắc chắn.\n\n"
    "Bản nháp vừa tạo có con số {so} không tìm thấy trong dữ liệu, nên tôi đã "
    "chặn lại thay vì đưa ra một câu trả lời nghe hợp lý mà sai. "
    "Bạn xem số liệu gốc bên dưới, hoặc hỏi lại cụ thể hơn."
)

_LOI_TU_CHOI_LO = (
    "Nội dung này gửi cho khách hàng nên tôi đã chặn lại: bản nháp có nhắc tới "
    "{tu} — đó là thông tin nội bộ."
)


# ---------------------------------------------------------------------------
# Chốt SUY BIẾN (29/10/2026, BR-05 yêu cầu 9)
# ---------------------------------------------------------------------------
# Bản fine-tune ở 6–13/27 câu diễn giải hết ý thì không dừng: trôi sang tiếng
# Trung/Anh, kê từ không dứt, rồi lặp một cụm tới trần 2048 token ("无所不能
# 无所不能…", "pull drag haul yank…"). Hạ repetition_penalty không chữa được
# (đo 1.25/1.1/1.0) — gốc ở dữ liệu huấn luyện. Chốt số liệu không bắt được loại
# này vì rác không chứa số; khách sẽ nhận nguyên đoạn rác.
#
# Hai dấu hiệu tất định, cố ý hẹp để không chặn oan câu tiếng Việt bình thường:
#   - có chữ Hán: Brain trả lời tiếng Việt, không có lý do nào để có chữ Hán
#   - đuôi lặp: 100 ký tự cuối đã xuất hiện nguyên văn ở phía trước — văn bình
#     thường không bao giờ lặp nguyên một đoạn dài như vậy
_CHU_HAN = re.compile(r"[㐀-䶿一-鿿]")
_DO_DAI_DUOI = 100

LOI_SUY_BIEN = (
    "Tôi chưa soạn được câu trả lời trọn vẹn cho câu này — bản nháp bị hỏng giữa "
    "chừng nên tôi đã chặn lại. Bạn hỏi lại giúp tôi, hoặc hỏi ngắn và cụ thể hơn."
)


def kiem_suy_bien(answer: str) -> str | None:
    """Lý do suy biến ("chữ Hán" / "lặp đuôi"), hoặc None khi câu trả lời sạch."""
    q = answer or ""
    if _CHU_HAN.search(q):
        return "chữ Hán"
    duoi = q.rstrip()[-_DO_DAI_DUOI:]
    if len(duoi) == _DO_DAI_DUOI and q.count(duoi) >= 2:
        return "lặp đuôi"
    return None


def guard_answer(answer: str, context: str, *, for_customer: bool = False) -> GuardVerdict:
    """
    Soát câu trả lời do model viết TRƯỚC KHI cho ra ngoài.

    Hai phép kiểm, cùng một nguyên tắc: thà không trả lời còn hơn trả lời sai mà
    nghe xuôi tai. Con số bịa trong một báo cáo tài chính không lộ ra cho tới
    lúc quyết toán.

    `for_customer=True` bật thêm lớp chặn lộ biên lợi nhuận — dùng cho nội dung
    soạn để gửi thẳng khách hàng cuối.
    """
    if not (answer or "").strip():
        return GuardVerdict(False, "Tôi chưa tạo được câu trả lời cho câu này.",
                            reason="rỗng")

    ok, bad = narration_numbers_ok(answer, context)
    if not ok:
        logger.warning("Chặn câu trả lời: bịa số %s", bad)
        return GuardVerdict(False, _LOI_TU_CHOI_SO.format(so=bad),
                            reason="bịa số", offending=str(bad))

    ok, cum = derived_ratios_ok(answer, context)
    if not ok:
        logger.warning("Chặn câu trả lời: tỷ lệ model tự suy ra %r", cum)
        return GuardVerdict(False, LOI_TU_CHOI_SUY_RA.format(cum=cum),
                            reason="tự suy ra tỷ lệ", offending=str(cum))

    if for_customer and (leaks := customer_leak(answer)):
        logger.warning("Chặn câu trả lời gửi khách: lộ %s", leaks)
        return GuardVerdict(False, _LOI_TU_CHOI_LO.format(tu=", ".join(sorted(set(leaks)))),
                            reason="lộ nội bộ", offending=", ".join(sorted(set(leaks))))

    return GuardVerdict(True, answer)


__all__ = [
    "LOI_SUY_BIEN",
    "LOI_TU_CHOI_SUY_RA",
    "GuardVerdict",
    "customer_leak",
    "la_hinh_dang_tien",
    "derived_ratios_ok",
    "guard_answer",
    "kiem_suy_bien",
    "narration_numbers_ok",
    "numbers_in",
]
