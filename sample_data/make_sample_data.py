"""
sample_data/make_sample_data.py — dựng bảng tồn kho MẪU để chạy thử nội bộ.

VÌ SAO CÓ FILE NÀY
------------------
Dữ liệu thật của khách pilot còn vài ngày nữa mới về, nhưng buổi chạy thử nội bộ
không đợi được. Vấn đề của mọi dữ liệu giả là nó dễ dãi: dựng đại một bảng đẹp
thì bộ soi lỗi không tìm ra gì, và ta kết luận nhầm rằng "chạy tốt".

Nên bảng này GIEO LỖI CÓ CHỦ ĐÍCH — mỗi lỗi ứng với đúng một phép kiểm trong
`core/inventory.py`. Danh sách lỗi gieo nằm ở `LOI_GIEO` ngay dưới, và
`tests/contracts/test_sample_data.py` chạy bộ soi lên chính file này rồi đối chiếu: thiếu
một lỗi là bộ soi hỏng, thừa một lỗi là bộ soi báo oan. Bảng mẫu vì vậy vừa là
dữ liệu chạy thử vừa là đề bài có đáp án.

ĐỊNH DẠNG
---------
Bắt chước bản xuất "Tổng hợp Nhập - Xuất - Tồn" của MISA kiểu A: tên nhóm (Đầu
kỳ / Nhập kho / Xuất kho / Cuối kỳ) nằm CÙNG dòng với "Mã hàng", tên cột con ở
dòng kế tiếp, và ô gộp để trống các cột sau. Đúng thứ `inventory_import.py`
phải xử lý, chứ không phải một bảng phẳng cho dễ.

Hàng hoá lấy theo ngành của khách: dầu nhờn, mỡ bò, dung dịch làm mát.

CHẠY
----
    python sample_data/make_sample_data.py
-> sample_data/ton_kho_mau.xlsx           bản xuất đến 30/06/2026 (bảy mã gieo lỗi sổ sách)
-> sample_data/ton_kho_mau_ban_sau.xlsx   bản xuất MUỘN hơn của CÙNG kỳ, đến 15/07/2026, có ba chỗ bị sửa hồi tố (phép so hai bản, `core/period_diff.py`)
-> sample_data/khach_hang_mau.xlsx         danh sách khách hàng kiểu MISA kèm công nợ, gieo lỗi (soi công nợ, `core/receivables.py`)
-> sample_data/nha_cung_cap_mau.xlsx       danh sách nhà cung cấp kiểu MISA, một số dư phải trả âm
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

KY_TU = "01/01/2026"
KY_DEN = "30/06/2026"      # 181 ngày — vượt ngưỡng 90 ngày của phép kiểm hàng chết
KHO = "Kho Hà Nội"


@dataclass
class Dong:
    code: str
    name: str
    unit: str
    opening_qty: float
    opening_value: float
    in_qty: float
    in_value: float
    out_qty: float
    out_value: float
    # Chỉ điền khi CỐ Ý phá cân đối; bỏ trống thì tự tính ĐK + N − X.
    closing_qty: float | None = None
    closing_value: float | None = None
    # Ghi số dạng chuỗi kiểu Việt Nam ("1.234.567") thay vì số — bản xuất thật
    # đôi khi ra như vậy, và đó là lúc `parse_vn_number` phải làm việc.
    chuoi_viet: bool = False
    loi_gieo: tuple[str, ...] = field(default_factory=tuple)

    def ck_qty(self) -> float:
        if self.closing_qty is not None:
            return self.closing_qty
        return self.opening_qty + self.in_qty - self.out_qty

    def ck_value(self) -> float:
        if self.closing_value is not None:
            return self.closing_value
        return self.opening_value + self.in_value - self.out_value


def _dv(qty: float, value: float) -> float:
    return value / qty if qty else 0.0


# ---------------------------------------------------------------------------
# Các dòng SẠCH — phải không sinh phát hiện nào
# ---------------------------------------------------------------------------

_SACH = [
    Dong("DN-CF4-200", "Dầu động cơ Diesel CF-4 15W40 phuy 200L", "phuy",
         20, 84_000_000, 40, 172_000_000, 45, 191_250_000),
    Dong("DN-SG-18", "Dầu động cơ xăng SG 20W50 can 18L", "can",
         60, 21_600_000, 120, 44_400_000, 140, 51_100_000),
    Dong("DN-TL-46", "Dầu thuỷ lực AW46 can 18L", "can",
         80, 24_000_000, 150, 45_750_000, 170, 51_425_000,
         chuoi_viet=True),
    Dong("DN-PHANH-1", "Dầu phanh DOT4 chai 1L", "chai",
         300, 21_000_000, 600, 43_200_000, 700, 49_700_000),
]

# ---------------------------------------------------------------------------
# Các dòng GIEO LỖI — mỗi dòng nhắm đúng một phép kiểm
# ---------------------------------------------------------------------------

_GIEO = [
    # Xuất 18 trong khi chỉ có 15 -> tồn cuối âm. Ngoài đời thường do thiếu
    # phiếu nhập chưa vào sổ, hoặc sai quy đổi phuy <-> lít.
    Dong("DN-TL-200", "Dầu thuỷ lực AW46 phuy 200L", "phuy",
         5, 16_500_000, 10, 33_500_000, 18, 59_400_000,
         loi_gieo=("negative_stock",)),

    # Hàng khuyến mại nhà cung cấp giao kèm: có số lượng, không ghi đồng nào.
    # Xuất 120/200 để tồn còn đủ bán ~4 tháng — nếu để tồn đủ bán quá 1 năm thì
    # dòng này dính THÊM cờ "bán chậm", và đề bài mất tính một-lỗi-một-dòng.
    Dong("KM-4T-08", "Nhớt xe máy 4T 0.8L (hàng khuyến mại)", "chai",
         0, 0, 200, 0, 120, 0,
         loi_gieo=("zero_valued_stock",)),

    # Giá nhập nhảy 20% so với giá tồn đầu kỳ.
    # Giá trị xuất tính theo BÌNH QUÂN GIA QUYỀN (40.800.000 / 42 xô) để đơn giá
    # tồn cuối bằng đơn giá đã bán — nếu không, dòng này dính thêm cờ "giá vốn
    # hàng tồn cao hơn hàng đã bán", vốn là hệ quả của cách tính chứ không phải
    # của giá nhập tăng.
    Dong("MO-EP2-15", "Mỡ bò chịu nhiệt EP2 xô 15kg", "xô",
         12, 10_200_000, 30, 30_600_000, 25, 24_285_714,
         loi_gieo=("price_jump",)),

    # Nhập một lần rồi nằm im suốt kỳ.
    Dong("DN-CAT-20", "Dầu cắt gọt kim loại can 20L", "can",
         30, 19_500_000, 0, 0, 0, 0,
         loi_gieo=("dead_stock",)),

    # Bán nhỏ giọt trong khi tồn đủ dùng nhiều năm.
    Dong("LC-COOL-200", "Dung dịch làm mát phuy 200L", "phuy",
         320, 128_000_000, 0, 0, 20, 8_000_000,
         loi_gieo=("slow_moving",)),

    # Hàng còn trong kho đắt hơn hàng vừa bán -> biên kỳ sau hẹp lại.
    # KHÔNG phải lỗi sổ sách; là cảnh báo cho kỳ sau.
    Dong("DN-GL5-18", "Dầu hộp số GL-5 90 can 18L", "can",
         10, 10_000_000, 20, 21_600_000, 15, 15_000_000,
         loi_gieo=("rising_cost_basis",)),

    # Tồn cuối ghi 20 trong khi 10 + 25 − 23 = 12. Bản xuất bị sửa tay.
    # Giá trị ghi theo ĐÚNG đơn giá đã bán (20 × 900.000) để lệch chỉ nằm ở chỗ
    # cân đối. Nếu để giá trị tự tính thì đơn giá tồn cuối tụt còn 565.000 và
    # dòng này dính thêm cờ "giá vốn hàng tồn giảm" — một hệ quả của con số bịa,
    # không phải một lỗi thứ hai.
    Dong("DN-BR-18", "Dầu bánh răng công nghiệp can 18L", "can",
         10, 9_000_000, 25, 23_000_000, 23, 20_700_000,
         closing_qty=20, closing_value=18_000_000,
         loi_gieo=("balance_mismatch",)),
]

DONG = _SACH + _GIEO

# Đáp án. `tests/contracts/test_sample_data.py` đối chiếu với kết quả soi thật.
LOI_GIEO: dict[str, tuple[str, ...]] = {d.code: d.loi_gieo for d in DONG if d.loi_gieo}


# ---------------------------------------------------------------------------
# Bản xuất MUỘN hơn của CÙNG kỳ — đề bài cho phép so hai bản (`core/period_diff.py`)
# ---------------------------------------------------------------------------
# Cùng ngày bắt đầu 01/01/2026, bản sau dài hơn 15 ngày. Bản nào cũng tự nhất quán (không lỗi cân đối); chỉ khi đặt cạnh nhau mới thấy ba chứng từ đã bị sửa
# SAU khi báo cáo. Đây là hình dạng của sự cố thật ở khách pilot (xuất luỹ kế giảm, lỗi âm kho dạt sang mã khác), dựng lại bằng số hư cấu.

KY_DEN_SAU = "15/07/2026"

# Phát sinh mới HỢP LỆ: số luỹ kế chỉ tăng. Không được sinh phát hiện nào (đối chứng của phép so).
_PHAT_SINH_MOI: dict[str, dict[str, Any]] = {
    "LC-COOL-200": {"out_qty": 25, "out_value": 10_000_000},     # bán thêm 5 phuy, cùng đơn giá bình quân 400.000
    "KM-4T-08": {"out_qty": 150},                                # tặng thêm 30 chai khuyến mại, vẫn không ghi giá trị
}

# Ba chỗ sửa hồi tố. Khoá = mã hàng; giá trị = (loại phát hiện mong đợi, các trường bị sửa).
_SUA_HOI_TO: dict[str, tuple[str, dict[str, Any]]] = {
    # Một phiếu xuất 40 can bị đổi mã: DN-SG-18 mất 40 (xuất luỹ kế GIẢM dù kỳ dài hơn), DN-TL-46 tăng đúng 40.
    "DN-SG-18": ("history_decreased", {"out_qty": 100, "out_value": 36_500_000}),
    "DN-TL-46": ("", {"out_qty": 210, "out_value": 63_525_000}),   # mã nhận: tăng hợp lệ, không bị gắn cờ riêng, nhưng được nêu là "mã nhận" ở DN-SG-18
    # Giá vốn tồn đầu kỳ bị tính lại: báo cáo kỳ trước đã nộp thì nay lệch.
    "DN-CF4-200": ("opening_changed", {"opening_value": 88_000_000}),
    # Cùng 600 chai nhập mà giá trị khác đi: đơn giá trên một phiếu nhập đã qua bị sửa.
    "DN-PHANH-1": ("purchase_value_changed", {"in_value": 46_200_000}),
}

DONG_BAN_SAU = [
    replace(d, **_PHAT_SINH_MOI.get(d.code, {}), **_SUA_HOI_TO.get(d.code, ("", {}))[1]) for d in DONG
]

# Đáp án của phép so: mã hàng -> loại phát hiện. `tests/contracts/test_sample_data.py` đối chiếu với kết quả thật.
LOI_HOI_TO: dict[str, str] = {ma: loai for ma, (loai, _) in _SUA_HOI_TO.items() if loai}


# ---------------------------------------------------------------------------
# Danh sách đối tác (kiểu MISA) — đề bài cho soi công nợ (`core/receivables.py`)
# ---------------------------------------------------------------------------
# Tên và mã số thuế HƯ CẤU (đầu số 099, đúng số kiểm tra trừ một mã cố ý sai). Mỗi lỗi nhắm một phép kiểm; hai dòng cuối bảng khách (cá nhân, khách số dư 0) là đối chứng sạch.
# Màn "Dòng tiền" của Body soi TỪNG file riêng, nên không gieo lỗi "vừa mua vừa bán" (chỉ phép soi gộp hai danh sách mới thấy).


@dataclass
class DoiTac:
    code: str
    name: str
    balance: float
    tax_id: str = ""


_KHACH = [
    DoiTac("KH001", "Công ty TNHH Vận tải Mẫu Đại Phát", 210_000_000, "0990002918"),     # một khách chiếm 40% phải thu; ba khách lớn nhất chiếm 76%
    DoiTac("KH002", "Công ty CP Xây dựng Mẫu Hưng Long", 105_000_000, "0990004288"),
    DoiTac("KH003", "Garage Mẫu Tiến Phát", 80_000_000, "0990004425"),
    DoiTac("KH004", "Cửa hàng Dầu nhớt Mẫu Minh Quân", 40_000_000, "0990007987"),
    DoiTac("KH005", "Công ty TNHH Cơ khí Mẫu Sao Việt", -8_500_000, "0990009494"),       # phải thu ÂM
    DoiTac("KH006", "Công ty TNHH Nông nghiệp Mẫu Phú Điền", 25_000_000, "0990002919"),  # mã số thuế sai số kiểm tra
    DoiTac("KH007", "Công ty CP Thương mại Mẫu An Bình", 18_000_000),                      # tổ chức mà thiếu mã số thuế
    DoiTac("KH008", "Doanh nghiệp Mẫu Thành Công", 15_000_000, "0990009631"),             # một mã số thuế hai mã khách
    DoiTac("KH009", "Doanh nghiệp Mẫu Thành Công - CN 2", 7_000_000, "0990009631"),
    DoiTac("KH010", "Anh Lê Văn Mẫu", 20_000_000),                                          # cá nhân, không MST: sạch
    DoiTac("KH011", "Công ty TNHH Mẫu Bình Minh", 0, "0990010179"),                        # số dư 0: sạch
]
_NCC = [
    DoiTac("NCC001", "Công ty TNHH Dầu nhớt Mẫu Phương Nam", 95_000_000, "0990010316"),
    DoiTac("NCC002", "Tổng kho Mẫu Miền Bắc", 43_000_000, "0990013878"),
    DoiTac("NCC003", "Công ty CP Hoá chất Mẫu Trường An", 12_000_000, "0990015385"),
    DoiTac("NCC004", "Công ty CP Bao bì Mẫu Đông Á", -5_000_000, "0990015522"),            # phải trả ÂM
]

DOI_TAC = {"khách hàng": _KHACH, "nhà cung cấp": _NCC}
# Đáp án: vai trò -> [(loại phát hiện, mã)], đối chiếu ở tests/contracts/test_sample_data.py. Phép "ba khách lớn nhất" không gắn mã nào.
LOI_DOI_TAC: dict[str, list[tuple[str, str]]] = {
    "khách hàng": [("customer_concentration", ""), ("customer_concentration", "KH001"), ("duplicate_partner", "KH008"),
                   ("invalid_tax_id", "KH006"), ("missing_tax_id", "KH007"), ("negative_receivable", "KH005")],
    "nhà cung cấp": [("negative_payable", "NCC004")],
}


def bang_doi_tac(vai_tro: str) -> list[list[object]]:
    """Bảng đúng khuôn MISA: tiêu đề, dòng trống, STT | Mã | Tên | Địa chỉ | Công nợ | Mã số thuế | Điện thoại, rồi dòng 'Tổng' bỏ trống."""
    chu = "khách hàng" if vai_tro == "khách hàng" else "nhà cung cấp"
    rows: list[list[object]] = [
        [f"DANH SÁCH {chu.upper()}"],
        [],
        ["STT", f"Mã {chu}", f"Tên {chu}", "Địa chỉ", "Công nợ", "Mã số thuế", "Điện thoại"],
    ]
    for i, d in enumerate(DOI_TAC[vai_tro], 1):
        rows.append([i, d.code, d.name, "Hà Nội (hư cấu)", d.balance, d.tax_id, f"09000000{i:02d}"])
    rows.append(["", "", "Tổng", "", "", "", ""])
    return rows


# ---------------------------------------------------------------------------
# Chứng từ cho phần CẦN MÔ HÌNH: ảnh hoá đơn cước (mô hình đọc chữ, mã tính lại) và một quy chế nội bộ (kho tri thức)
# ---------------------------------------------------------------------------
# Tên, mã số thuế, biển số, số tiền đều HƯ CẤU. Bản "sai" chỉ khác dòng tổng cộng in lệch 100.000đ: mô hình đọc đúng chữ trên giấy, còn việc phát hiện lệch là của mã (R1).

HOA_DON_CUOC: dict[str, Any] = {
    "carrier_name": "CÔNG TY TNHH VẬN TẢI HƯ CẤU SAO MAI",
    "carrier_tax_code": "0990016006",
    "invoice_no": "0000123",
    "invoice_date": "20/11/2026",
    "origin": "Bình Dương",
    "destination": "Cần Thơ",
    "vehicle_type": "Xe tải 8 tấn",
    "plate_number": "61C-000.00",
    "khoan": [("Cước vận chuyển một chuyến", 1, 4_500_000), ("Phụ phí bốc xếp", 1, 300_000)],
    "vat_rate": 8,
    "subtotal": 4_800_000,
    "vat_amount": 384_000,
    "total": 5_184_000,
}
LECH_HOA_DON = 100_000      # bản lỗi in tổng cộng 5.284.000

TEN_QUY_CHE = "quy_che_cong_no_mau.txt"
CAU_HOI_QUY_CHE = "Theo quy chế bán hàng trả chậm, đại lý cấp 1 được trả chậm tối đa bao nhiêu ngày?"
DAP_AN_QUY_CHE = "45"
QUY_CHE = """QUY CHẾ BÁN HÀNG TRẢ CHẬM (tài liệu HƯ CẤU để chạy thử)
Công ty TNHH Dầu nhớt Mẫu Phương Nam. Áp dụng từ ngày 01/01/2026.

Điều 1. Thời hạn trả chậm
Đại lý cấp 1 được trả chậm tối đa 45 ngày kể từ ngày giao hàng. Đại lý cấp 2 được trả chậm tối đa 30 ngày. Khách mua lẻ thanh toán ngay khi nhận hàng.

Điều 2. Hạn mức công nợ
Hạn mức của mỗi đại lý cấp 1 là 200.000.000 đồng. Hạn mức của mỗi đại lý cấp 2 là 80.000.000 đồng.

Điều 3. Chiết khấu thanh toán sớm
Khách thanh toán trong 7 ngày kể từ ngày giao hàng được chiết khấu 1,5% trên giá trị hoá đơn.

Điều 4. Công nợ quá hạn
Công nợ quá hạn trên 15 ngày thì tạm ngừng giao hàng cho đến khi thu đủ phần quá hạn.
"""

# Font có đủ dấu tiếng Việt: Windows, Ubuntu (Colab, CI), rồi bản DejaVu đi kèm matplotlib.
_FONT_UNG_VIEN = ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")


def tim_font() -> str | None:
    for f in _FONT_UNG_VIEN:
        if Path(f).is_file():
            return f
    import importlib.util

    mpl = importlib.util.find_spec("matplotlib")
    if mpl and mpl.origin:
        f2 = Path(mpl.origin).parent / "mpl-data" / "fonts" / "ttf" / "DejaVuSans.ttf"
        if f2.is_file():
            return str(f2)
    return None


def _tien(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def ghi_anh_hoa_don(path: Path, lech: int = 0) -> Path:
    """Vẽ hoá đơn cước thành ảnh PNG như một tờ in rõ nét. `lech` cộng vào dòng TỔNG CỘNG (bản lỗi)."""
    from PIL import Image, ImageDraw, ImageFont

    font = tim_font()
    if font is None:
        raise RuntimeError("không tìm thấy font có dấu tiếng Việt để vẽ ảnh hoá đơn")
    h = HOA_DON_CUOC
    anh = Image.new("RGB", (1240, 1000), "white")
    ve = ImageDraw.Draw(anh)
    to, thuong, nho = (ImageFont.truetype(font, c) for c in (40, 30, 26))

    def chu(x: int, y: int, s: str, f: Any = thuong) -> None:
        ve.text((x, y), s, fill="black", font=f)

    chu(60, 40, h["carrier_name"], to)
    chu(60, 100, f"Mã số thuế: {h['carrier_tax_code']}")
    chu(60, 160, "HOÁ ĐƠN GIÁ TRỊ GIA TĂNG - CƯỚC VẬN CHUYỂN", to)
    chu(60, 225, f"Số: {h['invoice_no']}        Ngày: {h['invoice_date']}")
    chu(60, 275, f"Tuyến: {h['origin']} - {h['destination']}")
    chu(60, 320, f"Phương tiện: {h['vehicle_type']}        Biển số: {h['plate_number']}")
    cot = (60, 140, 690, 830, 1010, 1180)
    y = 390
    ve.line([(cot[0], y), (cot[-1], y)], fill="black", width=2)
    for x, s in zip(cot, ("STT", "Nội dung", "Số lượng", "Đơn giá", "Thành tiền")):
        chu(x + 8, y + 10, s, nho)
    y += 56
    for i, (ten, sl, gia) in enumerate(h["khoan"], 1):
        ve.line([(cot[0], y), (cot[-1], y)], fill="black", width=1)
        for x, s in zip(cot, (str(i), ten, str(sl), _tien(gia), _tien(sl * gia))):
            chu(x + 8, y + 12, s, nho)
        y += 60
    ve.line([(cot[0], y), (cot[-1], y)], fill="black", width=2)
    for x in cot:
        ve.line([(x, 390), (x, y)], fill="black", width=1)
    chu(620, y + 40, "Cộng tiền hàng:")
    chu(1010, y + 40, _tien(h["subtotal"]))
    chu(620, y + 95, f"Thuế suất GTGT: {h['vat_rate']}%")
    chu(620, y + 150, "Tiền thuế GTGT:")
    chu(1010, y + 150, _tien(h["vat_amount"]))
    chu(620, y + 215, "TỔNG CỘNG:", to)
    chu(990, y + 215, _tien(h["total"] + lech), to)
    chu(60, y + 330, "Chứng từ hư cấu dùng để chạy thử, không có giá trị pháp lý.", nho)
    path.parent.mkdir(parents=True, exist_ok=True)
    anh.save(path)
    return path


def ghi_quy_che(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(QUY_CHE, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Ghi file
# ---------------------------------------------------------------------------

def _so(value: float, kieu_chuoi: bool) -> object:
    """Số thật, hoặc chuỗi định dạng Việt Nam khi muốn thử bộ đọc số."""
    if not kieu_chuoi:
        return round(value, 2)
    nguyen = f"{abs(value):,.0f}".replace(",", ".")
    return f"-{nguyen}" if value < 0 else nguyen


def bang(ky_den: str = KY_DEN, dong: list[Dong] | None = None) -> list[list[object]]:
    """Ma trận ô, đúng bố cục MISA kiểu A. Mặc định là bản xuất đến 30/06; `dong` và `ky_den` cho bản xuất muộn hơn."""
    rows: list[list[object]] = [
        ["CÔNG TY TNHH THƯƠNG MẠI VÀ VẬN TẢI MẪU"],
        ["MST: 0991234566"],
        [],
        ["BẢNG TỔNG HỢP NHẬP - XUẤT - TỒN"],
        [f"Từ ngày {KY_TU} đến ngày {ky_den}"],
        [],
    ]
    # Ô gộp: tên nhóm chỉ xuất hiện ở cột ĐẦU của nhóm, các cột sau để trống —
    # `_build_columns` phải tự kéo sang phải. Bỏ chi tiết này là dựng một bài
    # dễ hơn thực tế, và bài dễ thì không kiểm được gì.
    rows.append(
        ["Tên kho", "Mã hàng", "Tên hàng", "ĐVT",
         "Đầu kỳ", "", "", "Nhập kho", "", "", "Xuất kho", "", "", "Cuối kỳ", "", ""]
    )
    # `[*..., *...]` thay cho `list + list`: phép cộng suy ra `list[str]`, mypy không nhận vào `list[list[object]]` (lộ ra khi `kiem_tich_hop_body.py` import file này).
    rows.append([*["", "", "", ""], *["Số lượng", "Giá trị", "Đơn giá BQ"] * 4])

    for d in (DONG if dong is None else dong):
        ck_q, ck_v = d.ck_qty(), d.ck_value()
        rows.append([
            KHO, d.code, d.name, d.unit,
            _so(d.opening_qty, d.chuoi_viet), _so(d.opening_value, d.chuoi_viet),
            _so(_dv(d.opening_qty, d.opening_value), d.chuoi_viet),
            _so(d.in_qty, d.chuoi_viet), _so(d.in_value, d.chuoi_viet),
            _so(_dv(d.in_qty, d.in_value), d.chuoi_viet),
            _so(d.out_qty, d.chuoi_viet), _so(d.out_value, d.chuoi_viet),
            _so(_dv(d.out_qty, d.out_value), d.chuoi_viet),
            _so(ck_q, d.chuoi_viet), _so(ck_v, d.chuoi_viet),
            _so(_dv(ck_q, ck_v), d.chuoi_viet),
        ])

    rows.append([])
    rows.append(["", "", "Tổng cộng", "", "", "", "", "", "", "", "", "", "", "", "", ""])
    return rows


def _ghi(path: Path, rows: list[list[object]], ten_sheet: str) -> Path:
    try:
        from openpyxl import Workbook
    except ImportError:
        sys.exit("Thiếu openpyxl. Chạy: pip install openpyxl")

    wb = Workbook()
    ws = wb.active
    ws.title = ten_sheet
    for row in rows:
        ws.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def ghi_xlsx(path: Path, ky_den: str = KY_DEN, dong: list[Dong] | None = None) -> Path:
    return _ghi(path, bang(ky_den, dong), "Tong hop NXT")


def ghi_doi_tac(path: Path, vai_tro: str) -> Path:
    return _ghi(path, bang_doi_tac(vai_tro), "Danh sach")


def main() -> None:
    path = ghi_xlsx(Path(__file__).parent / "ton_kho_mau.xlsx")
    sau = ghi_xlsx(Path(__file__).parent / "ton_kho_mau_ban_sau.xlsx", KY_DEN_SAU, DONG_BAN_SAU)
    print(f"Đã ghi: {path}")
    print(f"Đã ghi: {sau}  (cùng kỳ, đến {KY_DEN_SAU}, {len(LOI_HOI_TO)} chỗ sửa hồi tố: {', '.join(LOI_HOI_TO)})")
    print(f"  {len(DONG)} mã hàng, kỳ {KY_TU} – {KY_DEN}")
    print(f"  {len(LOI_GIEO)} mã có lỗi gieo sẵn:")
    for code, loi in LOI_GIEO.items():
        print(f"    {code:14s} {', '.join(loi)}")
    for ten, vai_tro in (("khach_hang_mau.xlsx", "khách hàng"), ("nha_cung_cap_mau.xlsx", "nhà cung cấp")):
        f = ghi_doi_tac(Path(__file__).parent / ten, vai_tro)
        print(f"Đã ghi: {f}  ({len(DOI_TAC[vai_tro])} {vai_tro}, {len(LOI_DOI_TAC[vai_tro])} điểm cần xem gieo sẵn)")
    q = ghi_quy_che(Path(__file__).parent / TEN_QUY_CHE)
    print(f"Đã ghi: {q}  (nạp ở trang Tài liệu rồi hỏi: {CAU_HOI_QUY_CHE} Đáp án: {DAP_AN_QUY_CHE})")
    try:
        for ten, lech in (("hoa_don_cuoc_mau.png", 0), ("hoa_don_cuoc_mau_sai_tong.png", LECH_HOA_DON)):
            a = ghi_anh_hoa_don(Path(__file__).parent / ten, lech)
            print(f"Đã ghi: {a}  (tổng cộng in trên tờ: {_tien(HOA_DON_CUOC['total'] + lech)}; tính đúng: {_tien(HOA_DON_CUOC['total'])})")
    except (ImportError, RuntimeError) as e:
        print(f"Bỏ qua ảnh hoá đơn mẫu: {e}")
    print("\nTải file này lên mục Tồn kho bên Body để chạy thử bộ soi lỗi sổ sách.")


if __name__ == "__main__":
    main()
