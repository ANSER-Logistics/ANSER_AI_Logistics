"""
src/core/nguong_p95.py — ngưỡng độ trễ p95 của một lời gọi model (NFR-03).

VÌ SAO HAI NGƯỠNG (chủ dự án chốt 28/10/2026)
--------------------------------------------
BR-04 đo p95 ≈ 8,5–9,1 giây trên L4, vượt ngưỡng tham chiếu 5.000ms của
ARCHITECTURE §13. Nhưng request tự dừng sau ~217 token ở ~25 token/giây: đó là
thời gian SINH, không phải hàng đợi. Một ngưỡng tổng duy nhất không phân biệt
được "máy chậm" với "câu trả lời dài" — câu dài nào cũng vượt.

  - `P95_MS_MOI_TOKEN` (mặc định 60): p95 của (độ trễ / số token sinh ra). Đo
    SỨC KHOẺ của server: hàng đợi nghẽn, batching hỏng, GPU tranh chấp đều làm
    nó tăng, bất kể câu dài hay ngắn. Đo được ~40ms/token ở 1× và 4× (BR-04).
  - `P95_NGUONG_MS` (mặc định 5000): p95 tổng — thứ người dùng cảm thấy. Giữ
    để thấy, nhưng vượt nó với câu dài là chuyện đã biết, không phải sự cố.

Đổi qua biến môi trường, không sửa số trong mã. Module chỉ dùng thư viện chuẩn
để script đo (`offline_training/`) import được mà không kéo theo cả Brain.
"""

from __future__ import annotations

import math
import os

MAC_DINH_NGUONG_MS = 5000.0
MAC_DINH_MS_MOI_TOKEN = 60.0


def _doc(ten: str, mac_dinh: float) -> float:
    tho = os.getenv(ten, "").strip()
    if not tho:
        return mac_dinh
    try:
        v = float(tho)
    except ValueError:
        raise ValueError(f"{ten}={tho!r} không phải số") from None
    if v <= 0:
        raise ValueError(f"{ten}={tho!r} phải > 0")
    return v


def doc_nguong() -> tuple[float, float]:
    """(ngưỡng tổng ms, ngưỡng ms/token) từ env, rơi về mặc định khi trống."""
    return (_doc("P95_NGUONG_MS", MAC_DINH_NGUONG_MS),
            _doc("P95_MS_MOI_TOKEN", MAC_DINH_MS_MOI_TOKEN))


# ---------------------------------------------------------------------------
# Kết luận LÚC CHẠY trên /health (#9, chủ dự án chốt 12/11/2026)
# ---------------------------------------------------------------------------
# - Cửa sổ 200 lượt gần nhất: p95 trên cả đời service không phản ứng với sự cố
#   đang xảy ra.
# - Tối thiểu 30 mẫu ms/token: dưới đó "không đủ dữ liệu", KHÔNG báo đạt — p95
#   trên 3 lượt là vô nghĩa. Ba mức theo đúng tiền lệ của benchmark_v3.
# - Chỉ ms/token được hạ `degraded`. Tổng ms chỉ báo cáo: câu trả lời dài vượt
#   nó là chuyện đã biết, để nó báo động là tạo báo động giả đều đặn.
MAC_DINH_CUA_SO = 200
MAC_DINH_MAU_TOI_THIEU = 30
DAT, CHUA_DAT, KHONG_DU = "đạt", "chưa đạt", "không đủ dữ liệu"


def doc_cua_so() -> tuple[int, int]:
    """(số lượt trong cửa sổ, số mẫu ms/token tối thiểu) từ env."""
    cua_so = int(_doc("P95_CUA_SO", MAC_DINH_CUA_SO))
    toi_thieu = int(_doc("P95_MAU_TOI_THIEU", MAC_DINH_MAU_TOI_THIEU))
    if toi_thieu > cua_so:
        raise ValueError(
            f"P95_MAU_TOI_THIEU={toi_thieu} lớn hơn P95_CUA_SO={cua_so} — "
            "không bao giờ đủ mẫu, /health sẽ mãi báo 'không đủ dữ liệu'"
        )
    return cua_so, toi_thieu


def p95(mau: list[float]) -> float | None:
    """Phân vị 95 kiểu nearest-rank (ceil(n×0,95)−1): n nhỏ thì p95 ≈ max, không
    tụt về phần tử thứ 2 từ cuối như `int(n×0,95)`."""
    if not mau:
        return None
    xep = sorted(mau)
    return xep[min(len(xep) - 1, math.ceil(len(xep) * 0.95) - 1)]


def ket_luan(ms_moi_token: list[float], tong_ms: list[float], so_luot: int) -> dict:
    """
    Kết luận p95 cho /health trên các mẫu của cửa sổ hiện tại.

    `ms_moi_token`: chỉ các lượt BIẾT số token (đã lọc ở metrics). `muc` chỉ
    xét ms/token; tổng ms đi kèm để đọc, không quyết định gì.
    """
    nguong_ms, nguong_tok = doc_nguong()
    cua_so, toi_thieu = doc_cua_so()
    p_tok = p95(ms_moi_token)
    p_tong = p95(tong_ms)
    if len(ms_moi_token) < toi_thieu:
        muc = KHONG_DU
    else:
        muc = DAT if p_tok is not None and p_tok <= nguong_tok else CHUA_DAT
    return {
        "muc": muc,
        "ms_moi_token": None if p_tok is None else round(p_tok, 1),
        "nguong_ms_moi_token": nguong_tok,
        "so_mau_ms_moi_token": len(ms_moi_token),
        "mau_toi_thieu": toi_thieu,
        "tong_ms": None if p_tong is None else round(p_tong),
        "nguong_tong_ms": nguong_ms,
        "tong_dat": None if p_tong is None else p_tong <= nguong_ms,   # chỉ báo cáo
        "so_luot": so_luot,
        "cua_so": cua_so,
    }


def danh_gia(p95_ms: float | None, p95_ms_moi_token: float | None) -> dict:
    """Đạt/vượt cho từng ngưỡng. None = không đo được -> không kết luận."""
    nguong_ms, nguong_tok = doc_nguong()
    return {
        "nguong_ms": nguong_ms,
        "nguong_ms_moi_token": nguong_tok,
        "tong_dat": None if p95_ms is None else p95_ms <= nguong_ms,
        "moi_token_dat": None if p95_ms_moi_token is None else p95_ms_moi_token <= nguong_tok,
    }


__all__ = [
    "CHUA_DAT", "DAT", "KHONG_DU",
    "MAC_DINH_CUA_SO", "MAC_DINH_MAU_TOI_THIEU", "MAC_DINH_MS_MOI_TOKEN", "MAC_DINH_NGUONG_MS",
    "danh_gia", "doc_cua_so", "doc_nguong", "ket_luan", "p95",
]
