"""
src/core/freight_invoice.py — hoá đơn CƯỚC VẬN TẢI: lược đồ + kiểm số học.

VÌ SAO KHÔNG DÙNG `InvoicePayload`
---------------------------------
`InvoicePayload` là `{items: [{name, price, qty}], total}` — lược đồ hoá đơn BÁN
LẺ. Hoá đơn nhà xe không có hình dạng đó. Nó có tuyến (điểm đi/điểm đến), loại
xe, biển số, số chuyến, và một loạt phụ phí đứng riêng: bốc xếp, lưu ca, cầu
đường, phí quay đầu. Nhét chúng vào `items` là mất hết ý nghĩa — không phân biệt
được "3 chuyến × 12 triệu" với "3 khoản phụ phí", nên không kiểm chéo được gì.

TẤT ĐỊNH TRƯỚC (P1)
-------------------
VLM chỉ ĐỌC CHỮ. Mọi phép cộng nhân đều tính lại ở đây bằng code thuần, rồi đối
chiếu với con số in trên tờ hoá đơn. Lệch thì báo — KHÔNG tự sửa, và KHÔNG âm
thầm dùng số mình tính.

Đây là lớp phòng thủ quan trọng nhất của cả nhánh VLM: nó bắt được lỗi đọc mà
không cần người ngồi soi. Đọc nhầm `12.000.000` thành `72.000.000` thì tổng
không khớp và hệ thống tự biết mình sai. Sai mà biết mình sai thì còn dùng được;
sai mà tự tin thì không.
"""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from src.core import vat_catalog

# Kế toán làm tròn đến đồng; đừng báo lệch vì chênh 1 đồng do làm tròn VAT.
ABS_TOL_VND = 1000.0
REL_TOL = 0.005     # 0,5%

# Quy mô: tổng cộng của một hoá đơn cước vận tải dưới ngưỡng này gần như chắc là đọc lệch 1.000 lần (đo 18/11/2026: tờ `55.192.500` đọc thành
# `55192`, mọi số lệch cùng lúc nên kiểm nhất quán không thấy). Chỉ HẠ CỜ để người xem, không từ chối: một hoá đơn phí cầu đường lẻ có thể nhỏ thật.
# Ngưỡng do agent chọn, chưa kế toán hay chủ dự án xác nhận; một chuyến xe tải nội thành rẻ nhất cũng trên mức này.
TONG_CUOC_TOI_THIEU_VND = 100_000.0


class FreightCharge(BaseModel):
    """Một khoản trên hoá đơn: cước chuyến hoặc phụ phí."""
    kind: Literal["cước", "bốc xếp", "lưu ca", "cầu đường", "quay đầu", "khác"] = "khác"
    description: str = ""
    quantity: float = Field(1.0, ge=0, description="Số chuyến / số lần / số tấn")
    unit_price: float = Field(..., ge=0, description="Đơn giá (VND), CHƯA thuế")

    @property
    def amount(self) -> float:
        return self.quantity * self.unit_price


class FreightInvoice(BaseModel):
    """
    Hoá đơn cước vận tải do nhà xe phát hành.

    Trường `Optional` là CHƯA ĐỌC ĐƯỢC, không phải bằng 0 — cùng nguyên tắc với
    `reporting.py`. Hoá đơn viết tay mờ có thể không đọc ra biển số, nhưng vẫn
    đọc được tổng tiền; ép về 0 là bịa ra một khẳng định.
    """
    carrier_name: Optional[str] = Field(None, description="Tên nhà xe")
    carrier_tax_code: Optional[str] = Field(None, description="MST nhà xe")
    invoice_no: Optional[str] = None
    invoice_date: Optional[str] = Field(None, description="YYYY-MM-DD")

    origin: Optional[str] = Field(None, description="Điểm đi")
    destination: Optional[str] = Field(None, description="Điểm đến")
    vehicle_type: Optional[str] = Field(None, description="xe tải 5 tấn, container 20ft...")
    plate_number: Optional[str] = Field(None, description="Biển số xe")

    charges: list[FreightCharge] = Field(default_factory=list)

    vat_rate: Optional[float] = Field(None, ge=0, le=100, description="% VAT ghi trên hoá đơn")
    subtotal: Optional[float] = Field(None, ge=0, description="Cộng tiền hàng ghi trên hoá đơn")
    vat_amount: Optional[float] = Field(None, ge=0, description="Tiền thuế ghi trên hoá đơn")
    total: Optional[float] = Field(None, ge=0, description="TỔNG CỘNG ghi trên hoá đơn")

    @field_validator("invoice_date")
    @classmethod
    def _date_shape(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return None
        return v.strip()


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(ABS_TOL_VND, REL_TOL * max(abs(a), abs(b)))


def verify(invoice: FreightInvoice) -> dict[str, Any]:
    """
    Tính lại toàn bộ số tiền bằng code, đối chiếu với số in trên hoá đơn.

    Trả về `ok` CHỈ khi mọi phép đối chiếu làm được đều khớp. Thiếu dữ liệu để
    đối chiếu thì `ok` là False kèm lý do — "không kiểm được" khác hẳn "đã kiểm
    và đúng", và gộp hai thứ đó lại là cách nhanh nhất để một tờ hoá đơn sai đi
    lọt.

    VAT CHƯA ĐỌC ĐƯỢC ≠ VAT BẰNG 0
    ------------------------------
    Thuế suất và tiền thuế đều là `None` thì không có cơ sở nào để nói thuế là
    bao nhiêu. Bản cũ lấy 0 thay vào, tính tổng = cộng tiền hàng, và khi số in
    trên tờ cũng trùng thì báo `ok` — đúng thứ `FreightInvoice` tự cấm ("Optional
    là CHƯA ĐỌC ĐƯỢC, không phải bằng 0"). Một tờ hoá đơn VAT 8% bị mờ dòng thuế,
    đồng thời tổng bị đọc nhầm thành cộng tiền hàng, sẽ lọt vào sổ như tờ sạch.

    Nên khi cả hai đều trống: không chạy phép kiểm tổng cộng (không ghi nó vào
    `checks_performed`), thêm một `issues` nói đúng nguyên nhân, và để
    `computed.vat_amount` / `computed.total` là `None`. Hai khoá VẪN CÓ MẶT
    vì Body đọc cả ba khoá của `computed` (`BrainFreightInvoice` trong
    `frontend/src/server/brain.ts`) và hàm hiển thị `vnd()` ở
    `frontend/src/app/dashboard/documents/page.tsx` đã đổi `null` thành "—" —
    giữ khoá kèm `null` thì màn hình nói đúng "chưa biết". (Đo 15/11/2026: Body
    khai `vat_amount: number | null` nhưng `total: number`; kiểu khai báo chưa
    theo kịp thứ giao diện thật sự chịu được. Đó là việc của Body, đã nêu trong
    PR chứ không sửa ở đây.) (Khác `MCPServer.validate_invoice_total`, nơi không
    ai đòi khoá nên bỏ hẳn là cách đúng — xem AGENTS.md §R1.)

    Hoá đơn thật sự không có VAT vẫn qua được, miễn VLM đọc ra `vat_rate = 0`
    hoặc `vat_amount = 0` — "ghi rõ 0" là một giá trị đã đọc.
    """
    issues: list[str] = []
    checks: list[str] = []

    tinh_subtotal = sum(c.amount for c in invoice.charges)

    if not invoice.charges:
        issues.append("Không đọc được khoản nào — chưa có gì để kiểm.")

    # 1) Cộng tiền hàng
    if invoice.subtotal is not None and invoice.charges:
        checks.append("cộng_tiền_hàng")
        if not _close(tinh_subtotal, invoice.subtotal):
            issues.append(
                f"Cộng tiền hàng lệch: tính lại {tinh_subtotal:,.0f} nhưng hoá đơn ghi "
                f"{invoice.subtotal:,.0f} (chênh {abs(tinh_subtotal - invoice.subtotal):,.0f})"
            )

    goc = invoice.subtotal if invoice.subtotal is not None else tinh_subtotal

    # 2) Tiền thuế. Có thuế suất là tính được, kể cả khi gốc bằng 0 (0 × x% = 0
    # là phép tính thật; "không có khoản nào" đã có `issues` riêng ở trên).
    tinh_vat: Optional[float] = None
    if invoice.vat_rate is not None:
        tinh_vat = goc * invoice.vat_rate / 100.0
        if invoice.vat_amount is not None:
            checks.append("tiền_thuế")
            if not _close(tinh_vat, invoice.vat_amount):
                issues.append(
                    f"Tiền thuế lệch: {invoice.vat_rate:g}% của {goc:,.0f} là "
                    f"{tinh_vat:,.0f} nhưng hoá đơn ghi {invoice.vat_amount:,.0f}"
                )

    # 3) Tổng cộng — trường quan trọng nhất.
    # VAT dùng để cộng: số in trên tờ nếu có, không thì số tính từ thuế suất.
    # Cả hai đều trống thì `vat_dung` là None, KHÔNG phải 0 (xem docstring).
    vat_dung = invoice.vat_amount if invoice.vat_amount is not None else tinh_vat
    tinh_total: Optional[float] = None if vat_dung is None else goc + vat_dung

    if invoice.total is None:
        issues.append("Không đọc được TỔNG CỘNG — trường bắt buộc.")
    if tinh_total is None:
        issues.append(
            "Không đọc được VAT (cả thuế suất lẫn tiền thuế) nên không tính lại được "
            "tổng cộng. Hoá đơn có thể có VAT bị mờ, hoặc thật sự không có VAT — "
            "cần người xác nhận."
        )
    elif invoice.total is not None:
        checks.append("tổng_cộng")
        if not _close(tinh_total, invoice.total):
            issues.append(
                f"Tổng cộng lệch: tính lại {tinh_total:,.0f} nhưng hoá đơn ghi "
                f"{invoice.total:,.0f} (chênh {abs(tinh_total - invoice.total):,.0f})"
            )

    # 4) Mức 8% chỉ được áp tới hết `vat_catalog.HIEU_LUC_DEN` (A15, #200). Chỉ bắt trường hợp CHẮC: ngày ISO hợp lệ, SAU hạn, mà hoá đơn vẫn ghi 8%.
    # Trước hạn hay ngày không đọc được thì không nói gì ở đây (nghị quyết trước cũng từng cho 8%; ngày mờ đã có `missing_required`).
    if (invoice.vat_rate is not None and abs(invoice.vat_rate - 8.0) < 1e-9 and invoice.invoice_date
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", invoice.invoice_date) and invoice.invoice_date > vat_catalog.HIEU_LUC_DEN):
        checks.append("hiệu_lực_thuế_8%")
        issues.append(
            f"Hoá đơn ghi thuế 8% nhưng lập ngày {invoice.invoice_date}, sau {vat_catalog.HIEU_LUC_DEN} "
            f"({vat_catalog.CAN_CU_CHUNG}): mức 8% hết hiệu lực, cần kế toán xác nhận."
        )

    # 5) Quy mô (xem `TONG_CUOC_TOI_THIEU_VND`). KHÔNG ghi vào `checks`: không phải phép đối chiếu, và `ok` đòi ít nhất một phép đối chiếu thật.
    tong_xet = invoice.total if invoice.total is not None else tinh_total
    if tong_xet is not None and 0 < tong_xet < TONG_CUOC_TOI_THIEU_VND:
        issues.append(
            f"Tổng cộng {tong_xet:,.0f} đ nhỏ bất thường cho một hoá đơn cước vận tải (dưới {TONG_CUOC_TOI_THIEU_VND:,.0f} đ): "
            f"nghi đọc lệch 1.000 lần (dấu chấm hàng nghìn bị coi là dấu thập phân, ví dụ 55.192.500 thành 55.192). Cần người xem lại."
        )

    return {
        # `ok` đòi CẢ HAI: không có vấn đề nào, VÀ đã thật sự kiểm được ít nhất
        # một phép. Không có vế sau thì một tờ đọc ra rỗng cũng "ok".
        "ok": not issues and bool(checks),
        "checks_performed": checks,
        "issues": issues,
        "computed": {
            "subtotal": round(tinh_subtotal),
            "vat_amount": None if tinh_vat is None else round(tinh_vat),
            # None = không tính được (VAT chưa đọc), không phải 0. Khoá vẫn có mặt.
            "total": None if tinh_total is None else round(tinh_total),
        },
        "stated": {
            "subtotal": invoice.subtotal,
            "vat_amount": invoice.vat_amount,
            "total": invoice.total,
        },
        # Trường bắt buộc đúng thì mới dùng được; thiếu thì phải người xem lại.
        "missing_required": [
            ten for ten, gt in (
                ("carrier_name", invoice.carrier_name),
                ("invoice_date", invoice.invoice_date),
                ("total", invoice.total),
            ) if gt in (None, "")
        ],
    }


_TRUONG_TIEN_LUOC_DO = (("subtotal", "vat_amount", "total"), ("unit_price",))     # (ở gốc, ở FreightCharge)
_CHUOI_HOAC_NULL = {"anyOf": [{"type": "string", "maxLength": 40}, {"type": "null"}]}


def json_schema(so_tien_chuoi: bool = False) -> dict[str, Any]:
    """
    Lược đồ cho `guided_json` — ép VLM sinh đúng hình dạng ngay lúc giải mã.

    `so_tien_chuoi=True` (BR-19 phần 2b): các trường TIỀN là chuỗi (hoặc null) để model chép nguyên văn như in; `so_tien_ocr.chuan_hoa_cuoc` đọc thành số.
    Giữ nguyên mô tả của từng trường. `vat_rate` vẫn là số.
    """
    luoc_do = FreightInvoice.model_json_schema()
    if not so_tien_chuoi:
        return luoc_do
    goc, dong = _TRUONG_TIEN_LUOC_DO
    for noi, ten_truong in ((luoc_do.get("properties", {}), goc), (luoc_do.get("$defs", {}).get("FreightCharge", {}).get("properties", {}), dong)):
        for t in ten_truong:
            if t in noi:
                noi[t] = {**_CHUOI_HOAC_NULL, **({"description": noi[t]["description"]} if "description" in noi[t] else {})}
    return luoc_do


__all__ = ["FreightCharge", "FreightInvoice", "json_schema", "verify"]
