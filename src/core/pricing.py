"""
src/core/pricing.py — engine tính báo giá vận tải. CODE THUẦN, KHÔNG LLM (P1).

NGHIỆP VỤ (từ khảo sát khách logistics)
---------------------------------------
Khách là trung gian: hỏi giá nhà xe -> cộng biên -> báo lại khách của họ.
Giá cước đổi theo ngày vì giá dầu biến động ("dầu 25.000đ lên 28.000đ").
Hiện tại chủ doanh nghiệp tự tính tay ngoài MISA rồi nhập lại — chậm, và khi
đang lái xe thì không làm được. Engine này thay đúng phần "tự tính tay" đó.

CÔNG THỨC
---------
    điều_chỉnh_nhiên_liệu = giá_nhà_xe × fuel_sensitivity × (dầu_hiện_tại/dầu_gốc − 1)
    chi_phí_hiệu_chỉnh    = giá_nhà_xe + điều_chỉnh_nhiên_liệu
    phụ_phí               = tổng surcharge (hàng lạnh, bốc xếp, chờ...)
    biên                  = max(chi_phí_hiệu_chỉnh × base_margin_pct/100, min_margin_amount)
    báo_giá               = làm_tròn_1000₫(chi_phí_hiệu_chỉnh + phụ_phí + biên)

`fuel_sensitivity` = tỷ trọng nhiên liệu trong cơ cấu chi phí nhà xe (0..1).
Xe tải đường dài thường 0.30-0.40. Dầu tăng 12% với sensitivity 0.35 thì chi
phí tăng ~4.2% — không phải tăng cả 12%.

BẢO MẬT (P2): PricingRule chứa biên lợi nhuận — BÍ MẬT KINH DOANH CỐT LÕI của
khách. Kết quả trả về tách làm hai phần:
  - `quote`    : đưa được cho khách cuối (chỉ giá chốt + phụ phí công khai)
  - `internal` : breakdown đầy đủ có biên — CHỈ hiển thị nội bộ, không bao giờ
                 đưa vào email/Zalo gửi khách cuối, không đưa vào prompt gửi
                 ra ngoài hạ tầng.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional

from src.core.utils import hom_nay_vn  # định nghĩa duy nhất của "hôm nay" (R4); giữ tên ở đây

# Báo giá vận tải VN chốt theo bậc nghìn đồng.
_QUOTE_STEP_VND = 1000


def _huu_han(ten: str, gia_tri: Optional[float]) -> None:
    """NaN và vô cực không phải số tiền: `x <= 0` với NaN luôn False nên các phép kiểm `< 0` để NaN lọt, vô cực thì làm `Decimal` ném lỗi."""
    if gia_tri is not None and not math.isfinite(gia_tri):
        raise ValueError(f"{ten} phải là số hữu hạn")


def _round_step(amount: float, step: int = _QUOTE_STEP_VND) -> int:
    """Làm tròn về bậc `step` VND, round-half-up (không dùng banker's rounding). Số không hữu hạn hay quá lớn thì ValueError (route trả 422, không phải 500)."""
    _huu_han("số tiền", amount)
    try:
        d = Decimal(str(amount)) / Decimal(step)
        return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * step
    except InvalidOperation:
        raise ValueError("số tiền quá lớn để làm tròn") from None


@dataclass
class Surcharge:
    """Phụ phí một khoản: cố định (amount) hoặc theo % chi phí hiệu chỉnh (pct)."""
    name: str
    amount: float = 0.0     # VND cố định; ÂM được phép (một dòng giảm giá, chủ dự án chốt 21/11/2026), nhưng báo giá cuối phải dương
    pct: float = 0.0        # % trên chi_phí_hiệu_chỉnh (0..100)

    def __post_init__(self):
        _huu_han("amount", self.amount)
        _huu_han("pct", self.pct)


@dataclass
class PricingRule:
    """
    Quy tắc giá của MỘT khách hàng (workspace). Nhập một lần, dùng mãi.

    ⚠️ Bảng chứa dữ liệu này (`pricing_rules`) là bảng nhạy cảm nhất hệ thống —
    xem ARCHITECTURE.md §10.
    """
    base_margin_pct: float                 # biên chuẩn, % trên chi phí hiệu chỉnh
    fuel_sensitivity: float = 0.35         # tỷ trọng nhiên liệu trong chi phí (0..1)
    fuel_baseline_price: Optional[float] = None   # giá dầu lúc nhà xe chốt bảng giá
    min_margin_amount: float = 0.0         # sàn biên tuyệt đối (VND)
    surcharges: list[Surcharge] = field(default_factory=list)

    def __post_init__(self):
        for ten in ("base_margin_pct", "fuel_sensitivity", "fuel_baseline_price", "min_margin_amount"):
            _huu_han(ten, getattr(self, ten))
        if not 0 <= self.fuel_sensitivity <= 1:
            raise ValueError("fuel_sensitivity phải trong [0, 1]")
        if self.base_margin_pct < 0:
            raise ValueError("base_margin_pct không được âm")
        if self.min_margin_amount < 0:
            raise ValueError("min_margin_amount không được âm")


# Ngưỡng TUỔI GIÁ DẦU (số ngày). Chủ dự án uỷ quyền agent chọn (12/11/2026); đổi bằng env,
# không cần sửa mã. "Hôm nay 25 nghìn, ngày mai 30 nghìn" (AGENTS §3.1c): báo giá dựa trên
# giá dầu cũ là con số sai mà trông đúng, nên CHỈ cảnh báo thì chưa đủ.
#   tuổi >= CANH_BAO  -> cảnh báo (vẫn tính, chủ doanh nghiệp thấy trên bản nháp)
#   tuổi >= TU_CHOI   -> từ chối (ValueError -> 422): đồng bộ giá dầu đã chết từ lâu
MAC_DINH_CANH_BAO_NGAY = 2
MAC_DINH_TU_CHOI_NGAY = 7


def doc_nguong_tuoi_gia_dau() -> tuple[int, int]:
    """(ngày cảnh báo, ngày từ chối) từ `FUEL_PRICE_WARN_DAYS` / `FUEL_PRICE_MAX_DAYS`.

    Trống thì dùng mặc định. Giá trị hỏng là lỗi CẤU HÌNH, không phải lỗi người gọi, nên ném
    RuntimeError (không phải ValueError: route sẽ đọc ValueError thành 422 và đổ lỗi cho khách).
    Hai biến không phải bí mật.
    """
    import os

    def _doc(ten: str, mac_dinh: int) -> int:
        tho = os.getenv(ten, "").strip()
        if not tho:
            return mac_dinh
        try:
            return int(tho)
        except ValueError:
            raise RuntimeError(f"{ten}={tho!r} không phải số nguyên") from None

    warn = _doc("FUEL_PRICE_WARN_DAYS", MAC_DINH_CANH_BAO_NGAY)
    toi_da = _doc("FUEL_PRICE_MAX_DAYS", MAC_DINH_TU_CHOI_NGAY)
    if not 1 <= warn <= toi_da:
        raise RuntimeError(
            f"FUEL_PRICE_WARN_DAYS={warn} và FUEL_PRICE_MAX_DAYS={toi_da} phải thoả 1 <= WARN <= MAX"
        )
    return warn, toi_da


def _tuoi_gia_dau(
    fuel_price_as_of: Optional[str], today: Optional[date]
) -> tuple[Optional[int], Optional[str]]:
    """(số ngày tuổi, cảnh báo) của giá dầu. Không có ngày -> (None, None).

    Hàm này CHỈ ĐO tuổi, không quyết giá bao nhiêu ngày là quá cũ: đó là con số
    nghiệp vụ (hôm nay 25 nghìn, mai 30 nghìn — AGENTS §3.1c) thuộc chủ dự án.
    Ngày sai định dạng là lỗi của người gọi: ném ValueError (route trả 422) thay
    vì đoán, vì một ngày bị đoán sai làm tuổi giá dầu nhìn như "mới".
    """
    if not fuel_price_as_of:
        return None, None
    try:
        # Đúng dạng YYYY-MM-DD bằng regex: `date.fromisoformat` từ Python 3.11 còn nhận
        # "20261105" VÀ "2026-W45-1" (tuần ISO, cũng dài đúng 10 ký tự nên bản kiểm
        # `len == 10` cho qua). Giá trị này được GHI LẠI nguyên văn nên phải đồng nhất.
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fuel_price_as_of):
            raise ValueError
        ngay = date.fromisoformat(fuel_price_as_of)
    except ValueError:
        raise ValueError("fuel_price_as_of phải có dạng YYYY-MM-DD") from None
    tuoi = ((today or hom_nay_vn()) - ngay).days
    if tuoi < 0:
        return tuoi, (
            f"Ngày giá dầu ({fuel_price_as_of}) nằm SAU hôm nay — kiểm tra lại "
            "nguồn giá dầu hoặc đồng hồ của hệ thống gọi."
        )
    return tuoi, None


def compute_quote(
    carrier_cost: float,
    rule: PricingRule,
    current_fuel_price: Optional[float] = None,
    extra_surcharges: Optional[list[Surcharge]] = None,
    *,
    fuel_price_as_of: Optional[str] = None,
    today: Optional[date] = None,
    canh_bao_ngay: int = MAC_DINH_CANH_BAO_NGAY,
    tu_choi_ngay: int = MAC_DINH_TU_CHOI_NGAY,
) -> dict[str, Any]:
    """
    Tính báo giá từ giá nhà xe + quy tắc giá + giá dầu hiện tại.

    Trả dict hai phần `quote` (đưa khách cuối được) và `internal` (có biên —
    nội bộ). LLM diễn giải từ `internal` cho CHỦ doanh nghiệp, nhưng nội dung
    gửi KHÁCH CUỐI chỉ được lấy từ `quote`.

    `internal.inputs` ghi lại ĐÚNG những con số đã dùng (giá nhà xe, giá dầu hiện
    tại, giá dầu gốc, ngày của giá dầu và tuổi của nó). AGENTS §3.1c đòi điều này
    — "để khi giá đổi, biết báo giá cũ dựa trên gì" — nhưng bản trước chỉ có
    `fuel_ratio`, nên một báo giá đã gửi không cho biết nó dùng giá dầu nào.
    """
    _huu_han("carrier_cost", carrier_cost)
    _huu_han("current_fuel_price", current_fuel_price)
    if carrier_cost <= 0:
        raise ValueError("carrier_cost phải > 0")
    if not 1 <= canh_bao_ngay <= tu_choi_ngay:
        raise ValueError("ngưỡng tuổi giá dầu phải thoả 1 <= canh_bao_ngay <= tu_choi_ngay")
    tuoi_gia_dau, canh_bao_ngay_dau_vao = _tuoi_gia_dau(fuel_price_as_of, today)

    warnings: list[str] = []
    if canh_bao_ngay_dau_vao:
        warnings.append(canh_bao_ngay_dau_vao)

    # ---- 1. Điều chỉnh nhiên liệu ----------------------------------------
    fuel_adjustment = 0.0
    fuel_ratio: Optional[float] = None
    if current_fuel_price is not None and rule.fuel_baseline_price:
        if current_fuel_price <= 0 or rule.fuel_baseline_price <= 0:
            raise ValueError("giá nhiên liệu phải > 0")
        fuel_ratio = current_fuel_price / rule.fuel_baseline_price
        fuel_adjustment = carrier_cost * rule.fuel_sensitivity * (fuel_ratio - 1)
    elif current_fuel_price is not None and not rule.fuel_baseline_price:
        warnings.append(
            "Có giá dầu hiện tại nhưng quy tắc giá chưa khai báo giá dầu gốc "
            "(fuel_baseline_price) — bỏ qua điều chỉnh nhiên liệu."
        )
    elif current_fuel_price is None and rule.fuel_baseline_price:
        warnings.append(
            "Chưa lấy được giá dầu hiện tại — báo giá KHÔNG có điều chỉnh "
            "nhiên liệu, có thể lệch nếu giá dầu đã biến động."
        )

    # ---- 1b. Tuổi giá dầu: chỉ có nghĩa khi giá dầu THỰC SỰ được dùng -------
    # Giá dầu không dùng để điều chỉnh (thiếu giá gốc/giá hiện tại) thì tuổi của nó không
    # làm sai báo giá — từ chối ở đó là chặn oan.
    if tuoi_gia_dau is None:
        fuel_price_status = "unknown"           # chưa biết ngày: KHÔNG phải "mới"
    elif tuoi_gia_dau < 0:
        fuel_price_status = "future"            # cảnh báo riêng ở `_tuoi_gia_dau`
    elif fuel_ratio is None:
        fuel_price_status = "not_applied"
    elif tuoi_gia_dau >= tu_choi_ngay:
        raise ValueError(
            f"Giá dầu lấy ngày {fuel_price_as_of}, cách {tuoi_gia_dau} ngày (tối đa "
            f"{tu_choi_ngay - 1}). Kiểm tra workflow đồng bộ giá dầu trước khi báo giá."
        )
    elif tuoi_gia_dau >= canh_bao_ngay:
        fuel_price_status = "stale_warn"
        warnings.append(
            f"Giá dầu lấy ngày {fuel_price_as_of}, cách {tuoi_gia_dau} ngày — điều chỉnh "
            "nhiên liệu có thể lệch nếu giá dầu đã đổi; kiểm tra đồng bộ giá dầu trước khi duyệt."
        )
    else:
        fuel_price_status = "ok"

    adjusted_cost = carrier_cost + fuel_adjustment

    # ---- 2. Phụ phí -------------------------------------------------------
    all_surcharges = list(rule.surcharges) + list(extra_surcharges or [])
    surcharge_lines = []
    surcharge_total = 0.0
    for s in all_surcharges:
        value = s.amount + adjusted_cost * (s.pct / 100.0)
        surcharge_total += value
        surcharge_lines.append({"name": s.name, "value": _round_step(value, 1)})

    # ---- 3. Biên ----------------------------------------------------------
    margin_by_pct = adjusted_cost * (rule.base_margin_pct / 100.0)
    margin = max(margin_by_pct, rule.min_margin_amount)
    margin_floored = margin > margin_by_pct
    if margin_floored:
        warnings.append(
            f"Biên theo % ({_round_step(margin_by_pct, 1):,}đ) thấp hơn sàn "
            f"{_round_step(rule.min_margin_amount, 1):,}đ — áp sàn."
        )

    # ---- 4. Chốt giá ------------------------------------------------------
    quoted_price = _round_step(adjusted_cost + surcharge_total + margin)
    if quoted_price <= 0:
        raise ValueError("báo giá không dương: phụ phí âm lớn hơn tổng chi phí và biên; kiểm tra các dòng giảm giá")
    # Phụ phí âm được phép (lỗ có chủ ý), nên báo giá có thể thấp hơn giá nhà xe: nói thẳng, kèm số tiền lỗ.
    below_cost = quoted_price < carrier_cost
    if below_cost:
        warnings.append(
            f"Báo giá {quoted_price:,}đ THẤP HƠN giá nhà xe {_round_step(carrier_cost, 1):,}đ: lỗ "
            f"{_round_step(carrier_cost - quoted_price, 1):,}đ trước khi tính khoản nào khác."
        )

    return {
        # Phần ĐƯA ĐƯỢC cho khách cuối
        "quote": {
            "quoted_price": quoted_price,
            "surcharges": surcharge_lines,   # phụ phí là khoản công khai trên báo giá
            "currency": "VND",
        },
        # Phần NỘI BỘ — có biên, không gửi ra ngoài
        "internal": {
            "inputs": {
                "carrier_cost": _round_step(carrier_cost, 1),
                "current_fuel_price": current_fuel_price,
                "fuel_baseline_price": rule.fuel_baseline_price,
                "fuel_price_as_of": fuel_price_as_of,
                "fuel_price_age_days": tuoi_gia_dau,
                "fuel_price_status": fuel_price_status,
                # Nói thẳng báo giá này CÓ hay KHÔNG được điều chỉnh theo dầu. Thiếu
                # một trong hai giá dầu thì không điều chỉnh; trước đây trường hợp
                # thiếu CẢ HAI không để lại dấu vết nào (không cảnh báo, không cờ),
                # nên một báo giá không theo dầu trông y hệt một báo giá theo dầu
                # mà giá dầu không đổi.
                "fuel_adjustment_applied": fuel_ratio is not None,
            },
            "carrier_cost": _round_step(carrier_cost, 1),
            "fuel_ratio": None if fuel_ratio is None else round(fuel_ratio, 4),
            "fuel_adjustment": _round_step(fuel_adjustment, 1),
            "adjusted_cost": _round_step(adjusted_cost, 1),
            "surcharge_total": _round_step(surcharge_total, 1),
            "margin": _round_step(margin, 1),
            "margin_pct_effective": round(margin / adjusted_cost * 100, 2) if adjusted_cost else None,
            "margin_floored": margin_floored,
            "below_cost": below_cost,
            "rounding_step": _QUOTE_STEP_VND,
        },
        "warnings": warnings,
    }


__all__ = ["Surcharge", "PricingRule", "compute_quote"]
