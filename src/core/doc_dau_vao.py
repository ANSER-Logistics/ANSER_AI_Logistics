"""
src/core/doc_dau_vao.py — đọc ĐẦU VÀO của tool từ chính câu người dùng, bằng mã.

VÌ SAO (BR-04 §5.2, BR-05; chủ dự án chốt 28/10/2026)
-----------------------------------------------------
Chốt neo số liệu (`guard_answer`) soi CÂU TRẢ LỜI so với KẾT QUẢ tool. Nó mù
trước lỗi ở chiều ngược lại: model CHÉP SAI ĐẦU VÀO rồi tool tính đúng trên số
sai. Đo được trên vLLM thật: hoá đơn hai dòng 5.000.000 + 500.000, model gửi
cho `vat` đúng MỘT dòng, Brain trả lời "tổng thực tế 5.500.000đ" kèm "kết quả
từ công cụ VAT" — sai mà trông có nguồn.

Hai cách, áp TUỲ TRƯỜNG HỢP:

  B — mã bóc thay model, khi câu có cấu trúc đọc được:
      `tach_hoa_don`  hoá đơn dán (JSON, hoặc các dòng "tên: số")  -> `vat`
      `tach_loi_chao` nhiều lời chào giá trong câu                -> `carrier_selection`
  A — lưới cho mọi trường hợp còn lại (`so_tien_bi_bo_sot`): mọi số tiền người
      dùng đưa ra phải có mặt trong tham số gửi cho tool. Thiếu thì KHÔNG chạy
      tool, hỏi lại đích danh số bị bỏ sót.

Mọi hàm ở đây là mã tất định, không gọi model, không đụng mạng — chỉ thư viện
chuẩn, để test được ở mọi máy.

A soát HAI CHIỀU (bổ sung 28/10 sau lần chạy thật):
  - `so_tien_bi_bo_sot`          số trong câu không có trong tham số -> chép THIẾU
  - `so_tien_khong_co_trong_cau` số tiền trong tham số không có trong câu -> BỊA
Số đọc được cả viết bằng chữ ("năm triệu rưỡi", "hai trăm nghìn") lẫn kiểu nói
tắt ("5 triệu rưỡi", "12tr5", "5 triệu 200 nghìn").

`co_so_thue` đọc câu nói giá ĐÃ GỒM hay CHƯA GỒM VAT. Không nói rõ thì `vat`
hỏi lại (chủ dự án chốt 28/10): hiểu sai chỗ này là lệch nguyên khoản thuế.

GIỚI HẠN, CÓ CHỦ ĐÍCH
---------------------
- Số chữ chỉ được coi là TIỀN khi có đơn vị nghìn/triệu/tỷ ("năm trăm" trơn,
  "năm 2026" không phải tiền).
- `tach_*` chỉ nhận dạng câu có cấu trúc rõ. Không nhận ra thì trả None/[] và
  tầng trên giữ nguyên tham số của model — không đoán.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any, TypeGuard

from src.core.so_bang_chu import so_bang_chu
from src.core.vat_catalog import DUOC_GIAM, KHONG_GIAM, phan_loai_thue_suat

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Đọc số tiền
# ---------------------------------------------------------------------------

# Đơn vị nhân. "tr" phải đứng riêng (\b) để không nuốt chữ "trả", "trong".
_HE_SO = {
    "tỷ": 1_000_000_000, "ty": 1_000_000_000,
    "triệu": 1_000_000, "trieu": 1_000_000, "tr": 1_000_000,
    "nghìn": 1_000, "ngàn": 1_000, "nghin": 1_000, "ngan": 1_000, "k": 1_000,
}
_DON_VI_TIEN = r"đồng|dong|vnđ|vnd|đ|d"

_SO = re.compile(
    r"(?<![\w.,/])"                                   # không dính vào số/chữ phía trước
    r"(?P<so>\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"
    r"(?![\d/])"                                      # không phải mảnh ngày "20/12"
    r"(?:\s*(?P<dv>tỷ|ty|triệu|trieu|tr|nghìn|ngàn|nghin|ngan|k|" + _DON_VI_TIEN + r")"
    # Nói tắt sau đơn vị: "5 triệu rưỡi", "12tr5", "5 triệu 2." — chữ số lẻ chỉ
    # nhận khi đứng cuối cụm, nên "5 triệu 2 chuyến" không thành 5.200.000.
    r"(?:\s*(?P<ruoi>rưỡi|ruoi)"
    r"|\s*(?P<le>\d{1,3})(?=\s*(?:$|[,;!?)\n]|\.(?!\d)|đồng|dong|đ(?!\w))))?"
    r")?"
    r"(?![\wđ%])",                                    # đơn vị là trọn từ; loại "8%"
    re.IGNORECASE,
)


def _thanh_so(chuoi: str, dv: str | None) -> int | None:
    nhom_nghin = re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", chuoi)
    he_so = _HE_SO.get((dv or "").lower())
    if he_so:
        # Có nhóm nghìn thì dấu là dấu NGĂN NGHÌN: "1.500 nghìn" = 1.500.000.
        # Không có thì là dấu thập phân: "5,4 triệu", "1.5 tỷ".
        gia_tri = (float(re.sub(r"[.,]", "", chuoi)) if nhom_nghin
                   else float(chuoi.replace(",", ".")))
        return round(gia_tri * he_so)
    if nhom_nghin:
        return int(re.sub(r"[.,]", "", chuoi))                  # "12.500.000"
    if dv:                                                       # "500000đ"
        return int(float(chuoi.replace(",", "."))) if "." not in chuoi and "," not in chuoi else None
    if chuoi.isdigit() and len(chuoi) >= 5 and not chuoi.startswith("0"):
        return int(chuoi)                                        # số trần trong JSON dán kèm
    return None                                                  # "3 cái", "2026", "40 feet"


def _gia_tri(m: re.Match) -> int | None:
    v = _thanh_so(m.group("so"), m.group("dv"))
    he_so = _HE_SO.get((m.group("dv") or "").lower())
    if v is None or not he_so:
        return v
    if m.group("ruoi"):
        return v + he_so // 2                                     # "5 triệu rưỡi"
    if m.group("le"):
        le = m.group("le")
        return v + int(le) * he_so // 10 ** len(le)               # "12tr5", "5 triệu 200"
    return v


def doc_so_tien(cau: str) -> list[int]:
    """
    Mọi số tiền trong câu, theo thứ tự xuất hiện (VND, số nguyên).

    Nhận: "12.500.000 đồng", "7.450.000đ", "5 triệu", "5,4 triệu", "15tr", "500k",
    "28.500 đồng/lít", số trần >= 5 chữ số (JSON dán kèm); nói tắt "5 triệu
    rưỡi", "12tr5", "5 triệu 200 nghìn"; chữ "năm triệu rưỡi", "hai trăm nghìn".
    Bỏ: phần trăm ("8%"), ngày ("20/12", "26/10/2026"), năm, số lượng ("3 cái"),
    số bắt đầu bằng 0 (điện thoại, mã).
    """
    q = unicodedata.normalize("NFC", cau or "")
    ra: list[tuple[int, int]] = []
    truoc: re.Match | None = None
    for m in _SO.finditer(q):
        v = _gia_tri(m)
        if not v or v <= 0:
            truoc = None
            continue
        # "5 triệu 200 nghìn" là MỘT khoản: gộp khi chỉ cách nhau khoảng trắng và
        # đơn vị sau nhỏ hơn đơn vị trước.
        hs = _HE_SO.get((m.group("dv") or "").lower())
        hs_truoc = (
            _HE_SO.get((truoc.group("dv") or "").lower())
            if truoc is not None else None
        )
        # `truoc is not None` nhắc lại ở điều kiện dưới: `hs_truoc` đã hàm ý nó,
        # nhưng bộ kiểm kiểu không suy được, mà `truoc.end()` thì cần biết chắc.
        if (hs and hs_truoc and truoc is not None
                and hs < hs_truoc and v < hs_truoc
                and not q[truoc.end():m.start()].strip()):
            ra[-1] = (ra[-1][0], ra[-1][1] + v)
            truoc = None
            continue
        ra.append((m.start(), v))
        truoc = m
    ra.extend(so_bang_chu(q))
    return [v for _, v in sorted(ra, key=lambda x: x[0])]


# ---------------------------------------------------------------------------
# A — chốt neo đầu vào
# ---------------------------------------------------------------------------

def _so_trong_tham_so(args: Any) -> set[int]:
    """Mọi con số trong tham số, cộng tích đơn giá × số lượng của từng dòng hàng."""
    gom: set[int] = set()

    def di(x: Any) -> None:
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            gom.add(round(x))
        elif isinstance(x, dict):
            gia = x.get("price")
            sl = x.get("qty")
            if isinstance(gia, (int, float)) and isinstance(sl, (int, float)) \
                    and not isinstance(gia, bool) and not isinstance(sl, bool):
                gom.add(round(gia * sl))     # người dùng hay viết thành tiền của dòng
            for v in x.values():
                di(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                di(v)

    di(args)
    return gom


def so_tien_bi_bo_sot(cau: str, args: dict) -> list[int]:
    """
    Số tiền có trong câu người dùng mà KHÔNG có mặt trong tham số gửi cho tool.

    Rỗng = tham số phủ đủ mọi số người dùng đưa ra. Không rỗng = model chép
    thiếu hoặc chép sai — chạy tool lúc này là tính đúng trên đầu vào sai.
    """
    co = _so_trong_tham_so(args)
    thieu: list[int] = []
    for v in doc_so_tien(cau):
        if v not in co and v not in thieu:
            thieu.append(v)
    return thieu


# Khoá mang SỐ TIỀN trong tham số của `vat` / `quote`. Chiều "bịa" chỉ soi các
# khoá này: `qty`, `%`, `fuel_sensitivity` không phải tiền và người dùng hay
# nói theo đơn vị khác ("5 tấn" -> 5000 kg).
_KHOA_TIEN = {
    "price", "stated_total", "carrier_cost", "current_fuel_price",
    "fuel_baseline_price", "min_margin_amount", "amount",
}


def so_tien_khong_co_trong_cau(cau: str, args: dict, bo_qua: tuple[str, ...] = ()) -> list[int]:
    """
    Số tiền model ĐIỀN vào tham số mà người dùng KHÔNG hề đưa — chiều ngược của
    `so_tien_bi_bo_sot`. Không rỗng = model bịa hoặc chép sai chữ số; chạy tool
    lúc này là tính đúng trên một con số không có nguồn.

    Đơn giá của dòng hàng được chấp nhận khi chính nó HOẶC thành tiền
    (đơn giá × số lượng) có trong câu. `bo_qua`: khoá cấp cao do MÃ điền (ví dụ
    `items` sau khi cách B bóc), không phải model.
    """
    trong_cau = set(doc_so_tien(cau))
    bia: list[int] = []

    def la_so(x: Any) -> TypeGuard[float]:
        """`TypeGuard` chứ không phải `bool`: hàm này là cổng thu hẹp kiểu duy
        nhất trước khi `gia * sl` và `ghi(gia)` chạy. Khai `bool` thì bộ kiểm
        kiểu không biết `gia` đã là số, nên không bắt được nếu có ai bỏ cổng.

        `not isinstance(x, bool)` vì `True` là `int` trong Python — `price: true`
        trong JSON hoá đơn bẩn sẽ thành 1 đồng chứ không phải lỗi.
        """
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    def ghi(v: float) -> None:
        v = round(v)
        if v > 0 and v not in trong_cau and v not in bia:
            bia.append(v)

    def di(x: Any) -> None:
        if isinstance(x, dict):
            gia, sl = x.get("price"), x.get("qty")
            if la_so(gia) and not (la_so(sl) and round(gia * sl) in trong_cau):
                ghi(gia)
            for k, v in x.items():
                if k in _KHOA_TIEN and k != "price" and la_so(v):
                    ghi(v)
                elif isinstance(v, (dict, list, tuple)):
                    di(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                di(v)

    di({k: v for k, v in (args or {}).items() if k not in bo_qua})
    return bia


# ---------------------------------------------------------------------------
# Giá đã gồm VAT hay chưa — câu hỏi nghiệp vụ, mã KHÔNG đoán
# ---------------------------------------------------------------------------

_DA_GOM_VAT = re.compile(
    r"(?:đã|da)\s+(?:bao\s+)?(?:gồm|gom|có|co|tính|tinh)\s+(?:cả\s+|ca\s+)?(?:thuế|thue|vat|gtgt)"
    r"|(?:bao\s+gồm|bao\s+gom|gồm|gom)\s+(?:cả\s+|ca\s+)?(?:thuế|thue|vat|gtgt)"
    r"|sau\s+(?:thuế|thue|vat)|incl\.?\s*vat|giá\s+có\s+vat",
    re.IGNORECASE,
)
_CHUA_GOM_VAT = re.compile(
    r"(?:chưa|chua|không|khong)\s+(?:bao\s+)?(?:gồm\s+|gom\s+|có\s+|co\s+|tính\s+|tinh\s+)?"
    r"(?:cả\s+|ca\s+)?(?:thuế|thue|vat|gtgt)"
    r"|trước\s+(?:thuế|vat)|truoc\s+(?:thue|vat)|excl\.?\s*vat",
    re.IGNORECASE,
)
# Hoá đơn GTGT ghi riêng một dòng tiền thuế ("VAT: 650.000", khoá JSON "vat")
# -> các dòng hàng là giá trước thuế.
_DONG_THUE_RIENG = re.compile(
    r"(?:^|[\n;{,\"'])\s*(?:tiền\s+)?(?:thuế|thue|vat|gtgt|tax)[^:\n\"'=%]{0,20}[\"']?\s*[:=]\s*\d[\d.,]*(?!\s*%)\s*(?:$|[\n;,}đdv])",
    re.IGNORECASE,
)

# Câu hỏi lại — cũng là MỐC để nhận ra câu trả lời ở lượt sau.
MOC_HOI_THUE = "là giá chưa gồm VAT hay đã gồm VAT"
CAU_HOI_THUE = (
    f"Các số tiền trên hoá đơn {MOC_HOI_THUE}? Bạn trả lời \"chưa gồm VAT\" "
    "hoặc \"đã gồm VAT\" là tôi tính tiếp ngay — hiểu sai chỗ này là lệch "
    "nguyên khoản thuế."
)


def co_so_thue(cau: str) -> str | None:
    """
    "chua_gom" | "da_gom" | None. None = câu không nói, hoặc nói cả hai chiều
    (mâu thuẫn) — tầng trên hỏi lại, không đoán.
    """
    q = unicodedata.normalize("NFC", cau or "")
    # "chưa gồm VAT" chứa "gồm VAT": soát chiều phủ định trước rồi xoá nó đi.
    chua = bool(_CHUA_GOM_VAT.search(q) or _DONG_THUE_RIENG.search(q))
    da = bool(_DA_GOM_VAT.search(_CHUA_GOM_VAT.sub(" ", q)))
    if chua == da:
        return None
    return "chua_gom" if chua else "da_gom"


def noi_tra_loi_hoi_thue(cau: str, history: list[dict] | None) -> str | None:
    """
    Lượt trước Brain hỏi `CAU_HOI_THUE` (giá đã gồm VAT chưa) hoặc câu hỏi thuế suất (8% hay 10%), lượt
    này người dùng trả lời -> ghép với tin nhắn hoá đơn của lượt trước (và mọi câu trả lời trước đó
    trong cùng chuỗi hỏi), để `vat` chạy lại trên ĐỦ dữ liệu. None khi không phải câu trả lời cho
    câu hỏi đó: trả lời "8%" cho câu hỏi "đã gồm VAT chưa" không phải là trả lời.
    """
    if not history:
        return None
    ds = [m for m in history if isinstance(m, dict)]
    for i in range(len(ds) - 1, -1, -1):
        if ds[i].get("role") != "assistant":
            continue
        noi = str(ds[i].get("content") or "")
        if MOC_HOI_THUE in noi:
            tra_loi_dung = co_so_thue(cau) is not None
        elif MOC_HOI_THUE_SUAT in noi:
            tra_loi_dung = noi_thue_suat(cau) is not None
        else:
            return None
        if not tra_loi_dung:
            return None
        # Đi ngược qua các cặp (người dùng, câu hỏi lại) liền nhau để tới tin nhắn hoá đơn gốc.
        phan: list[str] = [cau]
        j = i - 1
        while j >= 0:
            if ds[j].get("role") == "user":
                phan.append(str(ds[j].get("content") or ""))
                truoc = ds[j - 1] if j >= 1 else None
                noi_truoc = str(truoc.get("content") or "") if truoc and truoc.get("role") == "assistant" else ""
                if MOC_HOI_THUE in noi_truoc or MOC_HOI_THUE_SUAT in noi_truoc:
                    j -= 2
                    continue
                return "\n".join(reversed(phan))
            j -= 1
        return None
    return None


TOOL_DOC_TU_CAU = ("vat", "quote", "carrier_selection")

# ---------------------------------------------------------------------------
# Ngày lập hoá đơn của `vat` (A15 / BR-43; mức 8% chỉ áp tới 31/12/2026)
# ---------------------------------------------------------------------------
# `invoice_date` của `/tools/vat` là NGUỒN của việc kiểm hiệu lực mức 8%, nên phải đến từ câu người dùng, không bao giờ từ model (cùng lý do `fuel_price_as_of`): lược đồ tool phơi
# trường này cho model, và một ngày model điền cho đủ khuôn ("2026-12-01" cho một hoá đơn lập 05/01/2027) làm phép kiểm hết hiệu lực trôi qua im lặng, đúng loại lỗi không có
# triệu chứng. Trước đó chỗ này chỉ có đường REST (`invoice_date` tuỳ chọn); đường `/chat` không bao giờ truyền ngày.
#
# Chỉ nhận ngày đi KÈM một từ nói tới việc lập hoá đơn ("hoá đơn lập ngày 05/01/2027", "xuất hoá đơn ngày..."), vì một câu hỏi thuế còn nhắc nhiều ngày khác ("áp dụng từ ngày 01/07/2025").
# Có đúng MỘT ngày như vậy thì dùng; không có, hoặc hai ngày khác nhau, thì để trống: `/tools/vat` sẽ cảnh báo "chưa có ngày lập" thay vì mã đoán.
_NGAY_THANG_NAM = re.compile(r"(?<![\d/.\-])(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})(?![\d/])")
_NGAY_THANG_NAM_CHU = re.compile(r"ngày\s*(\d{1,2})\s*tháng\s*(\d{1,2})\s*năm\s*(\d{4})", re.IGNORECASE)
_NGAY_ISO = re.compile(r"(?<![\d\-])(\d{4})-(\d{2})-(\d{2})(?![\d\-])")
_TU_NOI_LAP_HOA_DON = ("hoá đơn", "hóa đơn", "hoa don", "hđ", "lập", "lap ngay", "xuất hoá", "xuất hóa", "xuat hoa")


def ngay_lap_tu_cau(cau: str) -> str | None:
    """
    Ngày lập hoá đơn (`YYYY-MM-DD`) người dùng nói trong câu, hoặc None khi không có đúng một ngày chắc chắn.

        "hoá đơn lập ngày 05/01/2027, dầu 1.000.000đ"  -> "2027-01-05"
        "xuất hoá đơn ngày 5 tháng 1 năm 2027"         -> "2027-01-05"
        "thuế 8% áp từ ngày 01/07/2025, hoá đơn 10tr"   -> None   (ngày đó là của luật, không đi kèm từ lập hoá đơn)
        "hoá đơn ngày 01/12/2026 và hoá đơn ngày 05/01/2027" -> None (hai ngày: không đoán)
    Ngày không có thật (31/02) bị bỏ. Thứ tự ngày/tháng/năm theo cách viết Việt Nam.
    """
    import datetime as _dt

    ra: set[str] = set()
    tho = cau or ""
    thap = tho.lower()
    for mau, thu_tu in ((_NGAY_THANG_NAM, "dmy"), (_NGAY_THANG_NAM_CHU, "dmy"), (_NGAY_ISO, "ymd")):
        for m in mau.finditer(tho):
            a, b, c = (int(g) for g in m.groups())
            d, mo, y = (a, b, c) if thu_tu == "dmy" else (c, b, a)
            try:
                iso = _dt.date(y, mo, d).isoformat()
            except ValueError:
                continue
            truoc = thap[max(0, m.start() - 40): m.start()]
            if any(t in truoc for t in _TU_NOI_LAP_HOA_DON):
                ra.add(iso)
    return next(iter(ra)) if len(ra) == 1 else None

# Tham số CHÍNH SÁCH GIÁ của `quote` — của công ty, không phải của câu hỏi. BR-05
# chạy lại 28/10: model điền `fuel_sensitivity: 0.05` ở cả hai câu đủ dữ kiện
# (mặc định đã hiệu chỉnh 0,35 — phần điều chỉnh giá dầu nhỏ đi 7 lần) và bịa
# `min_margin_amount: 1000000`. Chủ dự án chốt: câu không nói tới thì MÃ XOÁ để
# tool dùng mặc định, vẫn tính ngay — không hỏi lại.
_CHINH_SACH_TIEN = ("min_margin_amount", "fuel_baseline_price")
_NOI_DO_NHAY_DAU = re.compile(
    r"(?:độ\s+nhạy|do\s+nhay|hệ\s+số|he\s+so)[^.;\n]{0,25}(?:dầu|dau|nhiên\s+liệu|nhien\s+lieu)",
    re.IGNORECASE,
)
_PHAN_TRAM = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")


def bo_chinh_sach_khong_noi_toi(cau: str, args: dict) -> tuple[dict, list[str]]:
    """
    Xoá tham số chính sách giá trong `pricing_rule` mà câu không nói tới.
    Trả (args mới, tên các trường đã xoá).
    """
    luat = args.get("pricing_rule")
    if not isinstance(luat, dict):
        return args, []
    luat = dict(luat)
    bo: list[str] = []
    if "fuel_sensitivity" in luat and not _NOI_DO_NHAY_DAU.search(cau):
        luat.pop("fuel_sensitivity")
        bo.append("fuel_sensitivity")
    tien = set(doc_so_tien(cau))
    for k in _CHINH_SACH_TIEN:
        v = luat.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and round(v) not in tien:
            luat.pop(k)
            bo.append(k)
    return ({**args, "pricing_rule": luat}, bo) if bo else (args, [])


def bien_khong_co_trong_cau(cau: str, args: dict) -> float | None:
    """`base_margin_pct` model điền mà câu không có "N%" nào bằng nó -> trả số
    đó (bịa). Trường bắt buộc, không có mặc định nên không xoá được — hỏi lại."""
    luat = args.get("pricing_rule")
    bien = luat.get("base_margin_pct") if isinstance(luat, dict) else None
    if not isinstance(bien, (int, float)) or isinstance(bien, bool):
        return None
    co = {float(m.group(1).replace(",", ".")) for m in _PHAN_TRAM.finditer(cau)}
    return None if float(bien) in co else float(bien)


# ---------------------------------------------------------------------------
# `vat`: thuế suất do BẢNG TRA quyết, số lượng phải có trong câu (BR-30, 15/11/2026)
# ---------------------------------------------------------------------------
# Khi gọi `vat`, model tự điền `is_reduced_vat` (8% hay 10%) và `qty`. Câu người dùng thường
# không nói cả hai. Thuế suất là một quy tắc pháp lý, không phải thứ đoán từ ngữ cảnh: model
# đọc sai "10 -> 100" hoặc chọn 8% cho một mặt hàng loại trừ thì `vat` vẫn tính ĐÚNG trên đầu
# vào sai, và kết quả trông có nguồn. Số lượng model bịa thì nhân vào mọi dòng.
#
# THUẾ SUẤT: người dùng chọn, mã không tự quyết (chủ dự án chỉ đạo 15/11/2026)
#   Khi bảng tra `vat_catalog` nói một mặt hàng "được giảm" còn 8% (dầu nhớt, cước vận tải...), mã
#   KHÔNG tự đặt 8% và model cũng không được chọn: bảng tra do team tự viết, chưa có kế toán thật
#   soát, và đổi mặc định 10% -> 8% là đổi MỌI con số `vat` trả ra. Nên để người dùng chọn.
#   Bốn luật, theo thứ tự cho từng dòng hàng:
#     1. Bảng tra kết luận KHÔNG được giảm (kim loại, rượu bia, viễn thông, tài chính...) -> mã ép
#        `is_reduced_vat = False` (10%), kể cả khi người dùng nói 8%. Có căn cứ pháp lý, chiều an toàn.
#     2. Người dùng NÓI thuế suất ("giảm 8%", "VAT 10%", hoặc trả lời "8%" / "10%" cho câu hỏi dưới)
#        -> MÃ đặt cờ theo lời đó cho mọi dòng chưa bị luật 1 ép. Không để model đọc: model đọc sai
#        "10" thành "100" hay quên đặt cờ thì `vat` vẫn tính đúng trên đầu vào sai.
#     3. Người dùng KHÔNG nói, và có dòng bảng tra nói "được giảm" -> HỎI LẠI ("áp 8% hay 10%?"),
#        không chạy `vat`. Câu hỏi nói rõ căn cứ và cái giá của hai chiều sai.
#     4. Người dùng không nói, bảng tra không có dòng nào "được giảm" (kể cả "chưa xác định") ->
#        gỡ giá trị model điền, tool dùng mặc định 10%. Mức đã dùng luôn hiện ở `tax_rate` từng dòng.
#   Trả lời câu hỏi ở luật 3 ở lượt sau được ghép với hoá đơn (`noi_tra_loi_hoi_thue`), như câu hỏi
#   "đã gồm VAT chưa". CHƯA làm, cần Body: mặc định theo từng cửa hàng ("cửa hàng này luôn 8%"), vì
#   Brain không lưu thiết lập; Body gửi kèm một trường là đủ, xem đề xuất ở docs/de-xuat-body/.
#
# SỐ LƯỢNG: `qty` khác 1 mà không có số nào đó trong câu (số hoặc chữ) -> hỏi lại, không chạy.
# `qty` bắt buộc ở lược đồ nên không gỡ được như `is_reduced_vat`.
_TU_THUE = r"(?:thuế|thue|vat|gtgt)"
_THUE_8 = re.compile(
    rf"(?:{_TU_THUE}[^.\n]{{0,20}}\b8\s*%|\b8\s*%[^.\n]{{0,20}}{_TU_THUE}"
    rf"|giảm\s+(?:thuế|vat|gtgt)|giam\s+(?:thue|vat)|thuế\s+suất\s+(?:giảm|8\b))",
    re.IGNORECASE,
)
_THUE_10 = re.compile(
    rf"(?:{_TU_THUE}[^.\n]{{0,20}}\b10\s*%|\b10\s*%[^.\n]{{0,20}}{_TU_THUE}|thuế\s+suất\s+10\b)",
    re.IGNORECASE,
)
# Cả một dòng chỉ là câu trả lời ngắn: "8%", "giảm 8%", "tính 10%", "thuế suất 8".
_TRA_LOI_NGAN = re.compile(
    r"\s*(?:(?:thuế\s*suất|thue\s*suat|vat|tính|tinh|áp|ap|theo|giảm|giam|là|la)\s*)*(8|10)\s*(?:%|phần\s*trăm)?\s*[.!]?\s*",
    re.IGNORECASE,
)

# Câu hỏi lại về thuế suất — cũng là MỐC để nhận ra câu trả lời ở lượt sau.
MOC_HOI_THUE_SUAT = "áp thuế GTGT 8% hay 10%"


def noi_thue_suat(cau: str) -> str | None:
    """
    "8" | "10" | None. None = câu không nói thuế suất, hoặc nói cả hai (mâu thuẫn): tầng trên hỏi lại.

    Chỉ nhận "8%"/"10%" khi đứng cạnh chữ thuế/VAT/GTGT, hoặc khi CẢ MỘT DÒNG là câu trả lời ngắn:
    "chiết khấu 10%" trong một hoá đơn không phải thuế suất.
    """
    q = unicodedata.normalize("NFC", cau or "")
    co8 = bool(_THUE_8.search(q))
    co10 = bool(_THUE_10.search(q))
    for dong in re.split(r"[\n;]", q):
        m = _TRA_LOI_NGAN.fullmatch(dong)
        if m:
            co8 = co8 or m.group(1) == "8"
            co10 = co10 or m.group(1) == "10"
    if co8 == co10:
        return None
    return "8" if co8 else "10"


def hang_duoc_giam(args: dict) -> list[tuple[str, str]]:
    """[(tên hàng, căn cứ)] các dòng của `vat` mà bảng tra kết luận "được giảm" (không tự đặt 8%)."""
    ra: list[tuple[str, str]] = []
    for it in args.get("items") or []:
        if isinstance(it, dict):
            kl = phan_loai_thue_suat(str(it.get("name") or ""))
            if kl.ket_luan == DUOC_GIAM:
                ra.append((str(it.get("name") or "")[:50], kl.can_cu))
    return ra


def cau_hoi_thue_suat(duoc_giam: list[tuple[str, str]]) -> str:
    ten = ", ".join(f"\"{t}\"" for t, _ in duoc_giam[:3]) + ("…" if len(duoc_giam) > 3 else "")
    return (
        f"Hàng {ten} thuộc diện được giảm thuế GTGT còn 8% theo bảng tra của hệ thống "
        f"({duoc_giam[0][1]}), nên tôi chưa dám chọn thay bạn: bạn muốn {MOC_HOI_THUE_SUAT}? "
        "Bạn trả lời \"8%\" hoặc \"10%\" là tôi tính tiếp ngay. Bảng tra này do đội dự án soạn, chưa "
        "có kế toán soát: tính 8% sai thì bị truy thu cộng tiền chậm nộp, tính 10% thừa thì chỉ "
        "phải điều chỉnh hoá đơn."
    )
_SO_DEM_CHU = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8,
               "chín": 9, "mười": 10, "mốt": 1}
_SO_TRONG_CAU = re.compile(r"\d+(?:[.,]\d+)*")


def thue_suat_nguoi_dung_da_noi(history: list[dict] | None) -> str | None:
    """
    Thuế suất người dùng đã nói ở một lượt TRƯỚC trong cùng cuộc hội thoại (lần gần nhất, trong 12 tin).

    Hỏi "8% hay 10%?" ở mọi hoá đơn là làm phiền: đã chọn một lần thì giữ trong hội thoại. Lượt hiện
    tại nói khác thì lời ở lượt hiện tại thắng (`noi_thue_suat(cau) or ...`). Chỉ đọc tin của NGƯỜI DÙNG.
    """
    for m in reversed([m for m in (history or []) if isinstance(m, dict)][-12:]):
        if m.get("role") == "user":
            muc = noi_thue_suat(str(m.get("content") or ""))
            if muc is not None:
                return muc
    return None


def ap_thue_suat_tu_bang_tra(
    cau: str, args: dict, muc_da_chon: str | None = None
) -> tuple[dict, list[str]]:
    """
    Áp luật 1, 2 và 4 ở khối chú thích trên cho từng dòng của `vat` (luật 3, hỏi lại, nằm ở
    `chot_dau_vao` vì nó trả câu hỏi). Trả (args mới, mô tả các thay đổi).
    """
    items = args.get("items")
    if not isinstance(items, list):
        return args, []
    muc = noi_thue_suat(cau) or muc_da_chon
    doi: list[str] = []
    moi: list[Any] = []
    for it in items:
        if not isinstance(it, dict):
            moi.append(it)
            continue
        it = dict(it)
        truoc = it.get("is_reduced_vat")
        if phan_loai_thue_suat(str(it.get("name") or "")).ket_luan == KHONG_GIAM:
            it["is_reduced_vat"] = False                       # luật 1
        elif muc is not None:
            it["is_reduced_vat"] = muc == "8"                  # luật 2
        else:
            it.pop("is_reduced_vat", None)                     # luật 3/4: gỡ lời model
        if it.get("is_reduced_vat") != truoc:
            doi.append(f"{it.get('name')!s:.40}: {truoc!r} -> {it.get('is_reduced_vat')!r}")
        moi.append(it)
    ra = {**args, "items": moi}
    if "default_is_reduced" in ra:
        ra.pop("default_is_reduced")
        doi.append("default_is_reduced: gỡ")
    return ra, doi


def _so_trong_cau(cau: str) -> set[float]:
    """Mọi số đếm trong câu, đọc cả hai nghĩa của dấu chấm/phẩy, cộng số viết bằng chữ nhỏ."""
    ra: set[float] = set()
    for m in _SO_TRONG_CAU.finditer(cau or ""):
        tho = m.group(0)
        chi_so = tho.replace(".", "").replace(",", "")
        if chi_so.isdigit():
            ra.add(float(chi_so))
        if tho.count(".") + tho.count(",") == 1:
            try:
                ra.add(float(tho.replace(",", ".")))
            except ValueError:
                # Chuỗi không đọc được thành số thì cách đọc thập phân đó không tồn tại: bình
                # thường, không phải lỗi cần ghi.
                pass
    low = unicodedata.normalize("NFC", (cau or "").lower())
    for tu, gia_tri in _SO_DEM_CHU.items():
        if re.search(rf"(?<!\w){tu}(?!\w)", low):
            ra.add(float(gia_tri))
    return ra


def so_luong_khong_co_trong_cau(cau: str, args: dict, bo_qua: tuple[str, ...] = ()) -> list[float]:
    """
    `qty` model điền (khác 1) mà câu không có số nào bằng nó -> trả các giá trị đó (bịa).
    1 là nghĩa "không ghi số lượng" (xem `calculate_vat`), nên luôn hợp lệ.
    """
    if "items" in bo_qua:
        return []
    items = args.get("items")
    if not isinstance(items, list):
        return []
    co = _so_trong_cau(cau)
    ra: list[float] = []
    for it in items:
        q = it.get("qty") if isinstance(it, dict) else None
        if isinstance(q, bool) or not isinstance(q, (int, float)) or q == 1:
            continue
        if float(q) not in co and float(q) not in ra:
            ra.append(float(q))
    return ra


def chot_dau_vao(
    ten: str, args: dict, cau: str, history: list[dict] | None = None
) -> tuple[dict, str | None, str]:
    """
    MỘT chỗ duy nhất quyết định đầu vào tool lấy từ câu người dùng — `chat.py`
    gọi lúc phục vụ, `benchmark_v3.py` gọi lúc đo (R4: đo đúng thứ chạy thật).

    Trả (args, câu_hỏi_lại | None, lý_do). `lý_do`:
      ""               không áp dụng (tool khác, câu rỗng, hoặc bóc không được)
      "boc_loi_chao"   carrier_selection: mã dựng carriers/offers từ câu
      "ok"             vat/quote: đầu vào khớp câu, chạy tool được
      "bo_sot"         có số tiền trong câu mà tham số thiếu
      "bia"            tham số có số tiền không có trong câu
      "so_luong"       vat: `qty` model điền không có trong câu
      "thue_suat"      vat: bảng tra nói "được giảm" mà câu không nói 8% hay 10% -> hỏi người dùng
      "thue"           vat: câu không nói giá đã gồm VAT hay chưa
    """
    args = dict(args or {})
    if ten == "quote" and "fuel_price_as_of" in args:
        # `fuel_price_as_of` là NGUỒN GỐC của giá dầu (báo giá ghi lại "dựa trên giá ngày
        # nào"): phải đến từ nơi lấy giá, không bao giờ từ model. Lược đồ tool phơi trường
        # này cho model; một ngày model bịa vào đây được lưu như bằng chứng thật (review
        # độc lập 12/11/2026). Gỡ TRƯỚC mọi lối thoát sớm, kể cả khi câu rỗng.
        args.pop("fuel_price_as_of")
        logger.info("quote: gỡ fuel_price_as_of do model tự điền")
    if ten == "vat" and "invoice_date" in args:
        # Cùng lý do: ngày lập là nguồn của phép kiểm hiệu lực mức 8%, chỉ được đến từ câu người dùng (xem `ngay_lap_tu_cau`). Gỡ TRƯỚC mọi lối thoát sớm.
        args.pop("invoice_date")
        logger.info("vat: gỡ invoice_date do model tự điền")
    if not cau or ten not in TOOL_DOC_TU_CAU:
        return args, None, ""

    if ten == "carrier_selection":
        tu_cau = tham_so_chon_nha_xe(cau)
        return ({**args, **tu_cau}, None, "boc_loi_chao") if tu_cau else (args, None, "")

    ma_dien: tuple[str, ...] = ()
    if ten == "vat":
        ngay_lap = ngay_lap_tu_cau(cau)
        if ngay_lap:
            args = {**args, "invoice_date": ngay_lap}
        dong = tach_hoa_don(cau)
        if dong:
            args, ma_dien = {**args, "items": dong}, ("items",)
        muc_da_chon = thue_suat_nguoi_dung_da_noi(history)
        args, doi_thue = ap_thue_suat_tu_bang_tra(cau, args, muc_da_chon)
        if doi_thue:
            logger.info("vat: thuế suất chỉnh theo luật bảng tra/câu, không theo model: %s", "; ".join(doi_thue))
        sai_sl = so_luong_khong_co_trong_cau(cau, args, bo_qua=ma_dien)
        if sai_sl:
            ds = ", ".join(f"{v:g}" for v in sai_sl)
            return args, (
                f"Tôi không thấy số lượng {ds} trong tin nhắn của bạn, nên chưa dùng nó để "
                "tính — tôi không tự thêm số. Bạn cho tôi biết số lượng từng mặt hàng nhé."
            ), "so_luong"
    if ten == "quote":
        args, bo = bo_chinh_sach_khong_noi_toi(cau, args)
        if bo:
            logger.info("quote: xoá tham số chính sách câu không nói tới: %s", ", ".join(bo))
        bien = bien_khong_co_trong_cau(cau, args)
        if bien is not None:
            return args, (
                f"Tôi không thấy biên lợi nhuận {bien:g}% trong tin nhắn của bạn. "
                "Bạn cho tôi biết biên lợi nhuận muốn áp cho chuyến này nhé."
            ), "bia"

    bo_sot = so_tien_bi_bo_sot(cau, args)
    if bo_sot:
        ds = ", ".join(dinh_dang_vnd(v) for v in bo_sot)
        cach_viet = (
            "Bạn liệt kê lại giúp tôi từng khoản (tên: số tiền), mỗi khoản một "
            "dòng, kèm tổng ghi trên hoá đơn nếu có nhé."
            if ten == "vat" else
            "Bạn cho tôi biết rõ khoản đó là giá nhà xe chào, giá dầu hiện tại, "
            "giá dầu lúc chốt bảng giá, hay một phụ phí nhé."
        )
        return args, (
            f"Tôi chưa đưa được khoản {ds} đồng trong tin nhắn của bạn vào phép "
            "tính, nên chưa dám trả lời — tính thiếu một khoản là ra con số sai. "
            + cach_viet
        ), "bo_sot"

    bia = so_tien_khong_co_trong_cau(cau, args, bo_qua=ma_dien)
    if bia:
        ds = ", ".join(dinh_dang_vnd(v) for v in bia)
        return args, (
            f"Tôi không thấy khoản {ds} đồng trong tin nhắn của bạn, nên không "
            "dùng nó để tính — tôi không tự thêm số. Bạn gửi lại đủ các khoản "
            "(tên: số tiền) giúp tôi nhé."
        ), "bia"

    if ten == "vat":
        co_so = co_so_thue(cau)
        if co_so is None:
            return args, CAU_HOI_THUE, "thue"
        args = {**args, "prices_include_vat": co_so == "da_gom"}
        duoc_giam = hang_duoc_giam(args)
        if duoc_giam and (noi_thue_suat(cau) or muc_da_chon) is None:
            return args, cau_hoi_thue_suat(duoc_giam), "thue_suat"
    return args, None, "ok"


def dinh_dang_vnd(v: int) -> str:
    return f"{v:,}".replace(",", ".")


# ---------------------------------------------------------------------------
# B — hoá đơn dán kèm -> dòng hàng cho `vat`
# ---------------------------------------------------------------------------

# Nhãn KHÔNG phải dòng hàng: tổng, thuế, chiết khấu… Bóc nhầm "Tổng cộng" thành
# một dòng hàng là cộng tổng vào chính nó.
_KHONG_PHAI_DONG_HANG = re.compile(
    r"tổng|tong|total|thuế|thue|vat|gtgt|chiết khấu|chiet khau|giảm giá|giam gia"
    r"|discount|tax|subtotal|cộng|cong tien",
    re.IGNORECASE,
)
_KHOA_TEN = ("name", "ten", "tên", "description", "item")
_KHOA_GIA = ("price", "unit_price", "don_gia", "đơn_giá", "gia")
_KHOA_SL = ("qty", "quantity", "so_luong", "số_lượng", "sl")


def _lay(d: dict, khoa: tuple[str, ...]) -> Any:
    for k in khoa:
        if k in d:
            return d[k]
    return None


def _dong_tu_json(obj: Any) -> list[dict] | None:
    # {"items": [...], ...}
    if isinstance(obj, dict) and isinstance(obj.get("items"), list):
        obj = obj["items"]
    # [{"name":…, "unit_price":…, "quantity":…}, …]
    if isinstance(obj, list):
        ra = []
        for d in obj:
            if not isinstance(d, dict):
                return None
            gia, sl = _lay(d, _KHOA_GIA), _lay(d, _KHOA_SL)
            if isinstance(gia, bool) or not isinstance(gia, (int, float)):
                return None
            if sl is None:
                sl = 1
            if isinstance(sl, bool) or not isinstance(sl, (int, float)):
                return None
            ra.append({"name": str(_lay(d, _KHOA_TEN) or "Unknown"), "price": gia, "qty": sl})
        return ra or None
    # {"Cước vận chuyển HN-HP": 5000000, "Phụ phí xăng dầu": 500000}
    if isinstance(obj, dict):
        ra = []
        for ten, gia in obj.items():
            if _KHONG_PHAI_DONG_HANG.search(str(ten)):
                continue
            if isinstance(gia, bool) or not isinstance(gia, (int, float)):
                return None
            ra.append({"name": str(ten), "price": gia, "qty": 1})
        return ra or None
    return None


_DONG_TEN_SO = re.compile(r"^\s*[-•*+]?\s*(?P<ten>[^:\n]{1,60}?)\s*[:=]\s*(?P<so>.+?)\s*$")


def tach_hoa_don(cau: str) -> list[dict] | None:
    """
    Dòng hàng của MỘT tờ hoá đơn dán trong câu, dạng `VatItem` (`name`, `price`,
    `qty`). None = không nhận ra cấu trúc nào — tầng trên giữ nguyên `items` của
    model, không đoán.

    Nhận hai dạng:
      1. JSON: object `{"tên": số}`, mảng dòng hàng, hoặc `{"items": [...]}`
      2. Từ HAI dòng trở lên dạng "tên: số tiền" (mỗi dòng một khoản)
    """
    q = cau or ""
    # 1. JSON — thử từ khối ngoặc lớn nhất trở xuống
    for m in re.finditer(r"[\[{]", q):
        for vi_tri_dong in (q.rfind("}"), q.rfind("]")):
            if vi_tri_dong > m.start():
                try:
                    ra = _dong_tu_json(json.loads(q[m.start():vi_tri_dong + 1]))
                except (ValueError, TypeError):
                    continue
                if ra:
                    return ra
    # 2. Các dòng "tên: số"
    ra = []
    # `khop` chứ không dùng lại tên `m` của vòng trên: ở đó `m` luôn là một
    # Match, ở đây có thể là None. Một tên cho hai kiểu làm mất khả năng
    # kiểm kiểu trên cả hai vòng.
    for dong in re.split(r"[\n;]", q):
        khop = _DONG_TEN_SO.match(dong)
        if not khop or _KHONG_PHAI_DONG_HANG.search(khop.group("ten")):
            continue
        so = doc_so_tien(khop.group("so"))
        if len(so) == 1:
            ra.append({"name": khop.group("ten").strip(), "price": so[0], "qty": 1})
    return ra if len(ra) >= 2 else None


# ---------------------------------------------------------------------------
# B — nhiều lời chào giá -> carriers/offers cho `carrier_selection`
# ---------------------------------------------------------------------------

# Chỉ gỡ động từ CÓ DẤU (cộng "chao"/"bao gia" không dấu, ít khi là tên riêng).
# "gia", "la" không dấu thì không gỡ: nhà xe "Phú Gia" phải giữ nguyên tên.
_DUOI_DONG_TU = re.compile(
    r"(?:\s*(?:vừa\s+)?(?:chào\s+giá|chào|chao|báo\s+giá|bao\s+gia|báo|chốt|giá|là|[=:-]))+\s*$",
    re.IGNORECASE,
)
# Không gỡ "bên": "Bên A chào …" thì "Bên A" là tên.
_DAU_THUA = re.compile(r"^\s*(?:còn|và|với|rồi)\s+", re.IGNORECASE)
_CHIET_KHAU = re.compile(r"(?:chiết khấu|chiet khau|ck)\s*(\d+(?:[.,]\d+)?)\s*%", re.IGNORECASE)
_CONG_NO = re.compile(r"(?:công nợ|cong no)\s*(\d+)\s*(?:ngày|ngay)", re.IGNORECASE)


def tach_loi_chao(cau: str) -> list[dict]:
    """
    Các lời chào giá trong câu: `[{"ten", "gia", "chiet_khau_pct", "cong_no_ngay"}]`.

    Tên nhà xe = đoạn chữ ngay trước số tiền, tính từ dấu ngăn gần nhất (, ; :
    xuống dòng), bỏ động từ "chào/báo/chốt" và từ nối "còn/và". Điều khoản đọc
    trong đoạn từ sau số tiền tới số tiền kế tiếp. Lời chào không có tên thì bỏ.
    """
    q = cau or ""
    so = [(m, _gia_tri(m)) for m in _SO.finditer(q)]
    so = [(m, v) for m, v in so if v]
    ra: list[dict] = []
    for i, (m, gia) in enumerate(so):
        dau = max(q.rfind(c, 0, m.start()) for c in ",;:\n")
        if i > 0:
            dau = max(dau, so[i - 1][0].end())
        ten = _DAU_THUA.sub("", _DUOI_DONG_TU.sub("", q[dau + 1:m.start()])).strip(" ,.;:-")
        if not ten or len(ten) > 40 or not re.search(r"[^\W\d_]", ten):
            continue
        het = so[i + 1][0].start() if i + 1 < len(so) else len(q)
        duoi = q[m.end():het]
        ck, cn = _CHIET_KHAU.search(duoi), _CONG_NO.search(duoi)
        if any(r["ten"].lower() == ten.lower() for r in ra):
            continue
        ra.append({
            "ten": ten,
            "gia": gia,
            "chiet_khau_pct": float(ck.group(1).replace(",", ".")) if ck else None,
            "cong_no_ngay": int(cn.group(1)) if cn else None,
        })
    return ra


def tham_so_chon_nha_xe(cau: str) -> dict | None:
    """
    `carriers` + `offers` cho `/tools/carrier-selection` dựng từ câu. None khi
    bóc được dưới hai lời chào — không có gì để so.

    `vehicle_types` để rỗng: câu không nói nhà xe nào có xe gì, và lọc cứng của
    tool bỏ qua kiểm loại xe khi danh sách rỗng — không đoán.
    """
    loi_chao = tach_loi_chao(cau)
    if len(loi_chao) < 2:
        return None
    carriers, offers = [], []
    for i, lc in enumerate(loi_chao, 1):
        ma = f"C{i}"
        carriers.append({"id": ma, "name": lc["ten"], "vehicle_types": [],
                         "discount_pct": lc["chiet_khau_pct"],
                         "credit_days": lc["cong_no_ngay"]})
        offers.append({"carrier_id": ma, "price": lc["gia"]})
    return {"carriers": carriers, "offers": offers}


__all__ = [
    "CAU_HOI_THUE",
    "MOC_HOI_THUE",
    "MOC_HOI_THUE_SUAT",
    "TOOL_DOC_TU_CAU",
    "bien_khong_co_trong_cau",
    "bo_chinh_sach_khong_noi_toi",
    "chot_dau_vao",
    "co_so_thue",
    "dinh_dang_vnd",
    "doc_so_tien",
    "cau_hoi_thue_suat",
    "hang_duoc_giam",
    "noi_thue_suat",
    "thue_suat_nguoi_dung_da_noi",
    "noi_tra_loi_hoi_thue",
    "so_tien_bi_bo_sot",
    "so_tien_khong_co_trong_cau",
    "tach_hoa_don",
    "tach_loi_chao",
    "tham_so_chon_nha_xe",
]
