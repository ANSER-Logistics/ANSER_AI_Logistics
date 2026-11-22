"""
src/core/so_tien_ocr.py — đọc số tiền IN TRÊN GIẤY mà model thị giác chép ra (A8, brain#326; BR-19 phần 2b).

VÌ SAO CẦN
----------
Đo 18/11/2026 (Thành, 28 ảnh): cả 18 ca `Qwen3-VL-2B` sai tổng đều lệch ĐÚNG 1.000 lần. Tờ in `55.192.500`, model đọc thành `55192`: dấu chấm hàng nghìn bị coi là dấu thập phân. Mọi số trên tờ
lệch CÙNG LÚC nên `validate_invoice_total` và `freight_invoice.verify` (đều là kiểm nhất quán nội bộ) không thấy gì: cộng nhân vẫn khớp nhau. Prompt cũ còn dạy đúng cái lỗi đó: "mọi số tiền là số
nguyên VND, không dùng dấu phân cách hàng nghìn" bắt model vừa đọc vừa đổi quy ước số, trong khi đổi quy ước số là việc của mã, không phải của model (R1).

Cách làm: để model CHÉP chữ như in (chuỗi), mã đọc chuỗi đó thành số bằng MỘT quy tắc tất định, và từ chối thay vì đoán khi chuỗi không theo cách viết số Việt Nam. `parse_vn_number` (nơi duy nhất
định nghĩa dấu chấm là nhóm nghìn khi mọi nhóm sau nó đủ 3 chữ số) làm phần đọc số; module này thêm phần bọc riêng cho số tiền VND in trên chứng từ.

KHÔNG ĐOÁN
----------
- `None` (hoặc chuỗi rỗng) là "chưa đọc được", giữ nguyên, KHÔNG thành 0.
- Số tiền VND không có phần thập phân (trừ ",00"). `12.5` hay `1,5` trong một ô tiền gần như chắc chắn là `12.500` bị đổi dấu hoặc `1.500` bị đọc ngược: TỪ CHỐI, không đưa ra 12,5 đồng.
- Dấu ngăn cách lẫn lộn kiểu Anh/Việt (`55,192,500`, `1.234.567,89.1`): từ chối.
- Từ chối nghĩa là trả `None` kèm tên trường trong danh sách lỗi; chỗ gọi hạ cờ `needs_manual_review`. Không chỗ nào bù bằng số đoán.
- Giá trị ĐÃ LÀ SỐ (model trả `55192` như prompt cũ) đi qua nguyên vẹn: không có thông tin nào để biết nó lệch. Muốn bắt trường hợp đó cần `freight_invoice.verify` (kiểm quy mô) hoặc đổi prompt sang chuỗi.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

from src.core.inventory_import import parse_vn_number

# CHỈ chữ số ASCII 0-9: `\d` của Python khớp cả chữ số Ả Rập, toàn chiều rộng..., và `float()` nuốt chúng, nên "٥٥١٩٢" lọt qua thành 55192.
# Đơn vị tiền in cạnh số: "55.192.500 đ", "VNĐ 1.000", "₫". Không có chữ "d" trần: ".../d" lẫn với đơn vị khác.
_TIEN_TE = re.compile(r"(?i)(?:vnđ|vnd|đồng|₫|đ)\.?")
_NHOM_KHOANG_TRANG = re.compile(r"[0-9]{1,3}(?: [0-9]{3})+(?:,[0-9]+)?")
_CHI_SO = re.compile(r"-?[0-9.,]+")

TRUONG_TIEN_BAN_LE = ("total",)                       # cùng `items[].price`
TRUONG_TIEN_CUOC = ("subtotal", "vat_amount", "total")  # cùng `charges[].unit_price`


def doc_tien_in(gia_tri: Any) -> tuple[Optional[float], Optional[str]]:
    """
    (số, lý do không đọc được). `(None, None)` = chưa đọc được (ô rỗng/null), `(None, lý do)` = có chữ nhưng không theo cách viết số tiền Việt Nam.

        '55.192.500' -> 55192500    '55.192.500 đ' -> 55192500    '55 192 500' -> 55192500    '1.250,00' -> 1250
        '55,192,500' -> từ chối     '12.5' -> từ chối             '1,5' -> từ chối            '' / None -> chưa đọc
    """
    if gia_tri is None:
        return None, None
    if isinstance(gia_tri, bool):
        return None, "không phải số tiền"
    if isinstance(gia_tri, (int, float)):
        return (float(gia_tri), None) if math.isfinite(gia_tri) else (None, "số không hữu hạn")
    if not isinstance(gia_tri, str):
        return None, "không phải số tiền"

    chuoi = _TIEN_TE.sub("", gia_tri.replace(" ", " ").replace(" ", " ")).strip()
    if not chuoi:
        return None, None
    if _NHOM_KHOANG_TRANG.fullmatch(chuoi):
        chuoi = chuoi.replace(" ", "")
    if not _CHI_SO.fullmatch(chuoi) or not any(c in "0123456789" for c in chuoi):
        return None, "có ký tự không phải chữ số hay dấu ngăn cách"
    if chuoi.count(",") > 1 or ("," in chuoi and "." in chuoi and chuoi.rfind(".") > chuoi.rfind(",")):
        return None, "dấu ngăn cách không theo cách viết số Việt Nam"
    so = parse_vn_number(chuoi)
    if so is None or not math.isfinite(so):
        return None, "không đọc được thành số"
    if so != int(so):
        return None, "số tiền VND không có phần thập phân (nghi dấu chấm hàng nghìn bị đọc thành thập phân)"
    return float(int(so)), None


def doc_ty_le(gia_tri: Any) -> tuple[Optional[float], Optional[str]]:
    """Thuế suất in trên tờ: số, hoặc chuỗi như '8%' hay '5,5 %'. Cùng quy tắc không đoán."""
    if isinstance(gia_tri, str):
        chuoi = gia_tri.replace("%", "").strip()
        if not chuoi:
            return None, None
        so = parse_vn_number(chuoi) if _CHI_SO.fullmatch(chuoi.replace(" ", "")) else None
        return (so, None) if so is not None and math.isfinite(so) else (None, "không đọc được thành tỉ lệ phần trăm")
    if gia_tri is None:
        return None, None
    if isinstance(gia_tri, bool) or not isinstance(gia_tri, (int, float)) or not math.isfinite(gia_tri):
        return None, "không phải tỉ lệ phần trăm"
    return float(gia_tri), None


def _doi(d: dict, khoa: str, ten: str, loi: list[str], ham=doc_tien_in) -> None:
    """Đổi `d[khoa]` nếu nó là CHUỖI (hoặc kiểu lạ); số và None đi qua nguyên vẹn. Hỏng thì None và ghi tên trường."""
    if khoa not in d or d[khoa] is None or (isinstance(d[khoa], (int, float)) and not isinstance(d[khoa], bool)):
        return
    so, ly_do = ham(d[khoa])
    d[khoa] = so
    if ly_do:
        loi.append(ten)


def _chuan_hoa(du_lieu: dict, truong_goc: tuple[str, ...], khoa_dong: str, truong_dong: str, kieu_ty_le: tuple[str, ...] = ()) -> tuple[dict, list[str]]:
    ra = dict(du_lieu)
    loi: list[str] = []
    for khoa in truong_goc:
        _doi(ra, khoa, khoa, loi)
    for khoa in kieu_ty_le:
        _doi(ra, khoa, khoa, loi, ham=doc_ty_le)
    dong = ra.get(khoa_dong)
    if isinstance(dong, list):
        moi = []
        for i, d in enumerate(dong):
            if isinstance(d, dict):
                d = dict(d)
                _doi(d, truong_dong, f"{khoa_dong}[{i}].{truong_dong}", loi)
            moi.append(d)
        ra[khoa_dong] = moi
    return ra, loi


def chuan_hoa_ban_le(du_lieu: dict) -> tuple[dict, list[str]]:
    """Hoá đơn bán lẻ `{items: [{price}], total}`: chuỗi tiền thành số. Trả (bản mới, danh sách tên trường không đọc được). Không sửa bản gốc."""
    return _chuan_hoa(du_lieu, TRUONG_TIEN_BAN_LE, "items", "price")


def chuan_hoa_cuoc(du_lieu: dict) -> tuple[dict, list[str]]:
    """Hoá đơn cước vận tải: `subtotal`, `vat_amount`, `total`, `charges[].unit_price` là tiền; `vat_rate` là phần trăm."""
    return _chuan_hoa(du_lieu, TRUONG_TIEN_CUOC, "charges", "unit_price", kieu_ty_le=("vat_rate",))
