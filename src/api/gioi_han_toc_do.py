"""
src/api/gioi_han_toc_do.py — giới hạn TỐC ĐỘ theo khách: một khách gửi dồn không được chiếm hết hàng chờ GPU của các khách khác (#218, A22).

VÌ SAO CẦN
----------
Trước đây chỉ có `ConcurrencyGuard` TOÀN CỤC (`src/core/serving.py`: 4 lượt chạy cùng lúc, 16 chỗ chờ). Một khách gửi 40 lượt `/chat` liên tiếp lấp đầy 16 chỗ chờ, và khách thứ hai nhận 503 "đầy"
dù mới gửi một lượt. Không nơi nào có 429, không nơi nào biết "của ai". Thân request đã có trần (#210), thân thì chưa đủ: tốc độ cũng cần trần.

QUYẾT ĐỊNH (chốt 21/11/2026 ở #218, uỷ quyền chủ dự án, đảo lại được)
-------------------------------------------------------------------
1. KHOÁ ĐẾM là `(key_id HMAC, X-Store-Id)`. `X-Store-Id` do client khai nên CHỈ ĐƯỢC TIN khi yêu cầu đã qua HMAC (`hmac_auth.da_xac_thuc`, chỉ ở chế độ `enforce`). Chưa qua HMAC thì dùng MỘT
   xô chung cho cả nhóm: một cửa hàng gửi dồn sẽ làm mọi cửa hàng chậm lại, nhưng đúng là cái hàng chờ GPU đang bị như vậy, và không có cách nào phân biệt khách thật khi danh tính do chính họ
   tự khai. Không dùng IP (sau Cloudflare Tunnel mọi yêu cầu cùng một địa chỉ).
2. BỘ ĐẾM nằm trong tiến trình, token bucket, tối đa `TOI_DA_KHOA` khoá (cũ nhất bị bỏ). Đúng khi một tiến trình (`--workers 1`, compose hiện nay); nhiều worker thì mỗi worker đếm riêng và hạn
   mức thực tế nhân lên (chuyển sang Redis khi cần, cùng giao diện `KhoXo.thu`). LỖI BẤT KỲ trong lớp này thì CHO QUA (fail-open) và ghi log: hạn mức bảo vệ tải, không phải cổng bảo mật; một
   lỗi ở đây mà chặn Body thì thành sự cố do chính lớp bảo vệ gây ra.
3. TỰ VIẾT, không thêm thư viện, không thêm service (R3).

HAI NHÓM, KHÁC NGƯỠNG
---------------------
- `gpu`: route chạm model hoặc embedding/xếp hạng lại nặng: `POST /chat`, `/ocr`, `/ocr/freight`, `/upload`, `/knowledge/search`, `/knowledge/documents`. Mặc định 30 lượt/phút, đỉnh 10.
- `tools`: route tất định `/tools/*` và `/mcp/*`, rẻ hơn nhiều. Mặc định 300 lượt/phút, đỉnh 60.
Không giới hạn: `/health`, `GET /api/v1/task/{id}` (Body hỏi kết quả mỗi giây), `OPTIONS`, các route đọc nhẹ còn lại.

NÚM (R5, đọc lúc gọi; `0` ở số lượt/phút = tắt nhóm đó; giá trị hỏng thì dịch vụ KHÔNG khởi động, vì đặt sai mà chạy tiếp là tưởng đã bảo vệ)
    RATE_LIMIT_GPU_PER_MIN, RATE_LIMIT_GPU_BURST, RATE_LIMIT_TOOLS_PER_MIN, RATE_LIMIT_TOOLS_BURST

VƯỢT HẠN MỨC -> 429 kèm `Retry-After` (giây, làm tròn lên, tối thiểu 1). Đếm vào `/health.rate_limit`. Nhật ký chỉ ghi nhóm và `key_id` (tên khoá HMAC, không phải dữ liệu khách), KHÔNG
ghi `X-Store-Id` hay đường dẫn kèm tham số (R2).

THỨ TỰ MIDDLEWARE: đăng ký TRƯỚC `HmacMiddleware` trong `main.py`, tức nằm TRONG hơn nó: chạy sau khi HMAC đã kiểm và đặt `da_xac_thuc`/`key_id_xac_thuc`, và vẫn TRƯỚC khi FastAPI đọc thân
(một tệp 10 MB gửi dồn không bị đọc rồi mới nhận 429).
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from src.api import hmac_auth
from src.core.utils import loai_loi

logger = logging.getLogger("projecta.api.gioi_han_toc_do")

NHOM_GPU = "gpu"
NHOM_TOOLS = "tools"
TOI_DA_KHOA = 10_000
TOI_DA_MOI_PHUT = 100_000
TOI_DA_DO_DAI_STORE_ID = 64

# (số lượt mỗi phút, đỉnh) mặc định. Một khách pilot 4 đến 5 người dùng chat cỡ vài lượt mỗi phút; hàng chờ GPU chỉ có 16 chỗ.
MAC_DINH: dict[str, tuple[float, int]] = {NHOM_GPU: (30.0, 10), NHOM_TOOLS: (300.0, 60)}
TEN_BIEN: dict[str, tuple[str, str]] = {
    NHOM_GPU: ("RATE_LIMIT_GPU_PER_MIN", "RATE_LIMIT_GPU_BURST"),
    NHOM_TOOLS: ("RATE_LIMIT_TOOLS_PER_MIN", "RATE_LIMIT_TOOLS_BURST"),
}

_ROUTE_GPU = frozenset({"/chat", "/ocr", "/ocr/freight", "/upload", "/knowledge/search", "/knowledge/documents"})


@dataclass(frozen=True)
class HanMuc:
    moi_phut: float     # <= 0 nghĩa là TẮT nhóm này
    dinh: int


def doc_cau_hinh(env: Optional[Mapping[str, str]] = None) -> dict[str, HanMuc]:
    """Hạn mức hai nhóm từ môi trường. Giá trị hỏng (không phải số, âm, quá lớn, đỉnh < 1 khi nhóm bật) thì ném RuntimeError nêu tên biến, không nêu giá trị khác."""
    env = os.environ if env is None else env
    ra: dict[str, HanMuc] = {}
    for nhom, (ten_phut, ten_dinh) in TEN_BIEN.items():
        mac_phut, mac_dinh = MAC_DINH[nhom]
        tho_phut = (env.get(ten_phut) or "").strip()
        tho_dinh = (env.get(ten_dinh) or "").strip()
        try:
            phut = float(tho_phut) if tho_phut else mac_phut
        except ValueError:
            raise RuntimeError(f"{ten_phut} không phải số") from None
        try:
            dinh = int(tho_dinh) if tho_dinh else mac_dinh
        except ValueError:
            raise RuntimeError(f"{ten_dinh} không phải số nguyên") from None
        if not math.isfinite(phut) or phut < 0 or phut > TOI_DA_MOI_PHUT:
            raise RuntimeError(f"{ten_phut} phải từ 0 (tắt) đến {TOI_DA_MOI_PHUT}")
        if phut > 0 and not 1 <= dinh <= TOI_DA_MOI_PHUT:
            raise RuntimeError(f"{ten_dinh} phải từ 1 đến {TOI_DA_MOI_PHUT} khi {ten_phut} bật")
        ra[nhom] = HanMuc(phut, dinh)
    return ra


def kiem_cau_hinh() -> None:
    """Gọi lúc khởi động: cấu hình hỏng thì từ chối chạy thay vì lặng lẽ bỏ qua hạn mức."""
    doc_cau_hinh()


def nhom_cua(method: str, path: str) -> Optional[str]:
    """Nhóm hạn mức của một yêu cầu; None = không giới hạn."""
    if method == "OPTIONS":
        return None
    if method == "POST" and path in _ROUTE_GPU:
        return NHOM_GPU
    if path.startswith("/tools/") or path.startswith("/mcp/"):
        return NHOM_TOOLS
    return None


class KhoXo:
    """Token bucket theo khoá. Trong tiến trình, một khoá (thread) bảo vệ; tối đa `toi_da_khoa` khoá, cũ nhất (ít dùng nhất) bị bỏ."""

    def __init__(self, toi_da_khoa: int = TOI_DA_KHOA) -> None:
        if toi_da_khoa < 1:
            raise ValueError("toi_da_khoa phải >= 1")
        self._toi_da = toi_da_khoa
        self._xo: "OrderedDict[tuple[str, str, str], tuple[float, float]]" = OrderedDict()
        self._khoa = threading.Lock()

    def thu(self, khoa: tuple[str, str, str], han_muc: HanMuc, bay_gio: float) -> float:
        """0.0 = cho qua (đã trừ một token). Lớn hơn 0 = số giây phải chờ để có một token."""
        toc_do = han_muc.moi_phut / 60.0
        with self._khoa:
            con, lan_cuoi = self._xo.get(khoa, (float(han_muc.dinh), bay_gio))
            con = min(float(han_muc.dinh), con + max(0.0, bay_gio - lan_cuoi) * toc_do)
            if con >= 1.0:
                self._xo[khoa] = (con - 1.0, bay_gio)
                self._xo.move_to_end(khoa)
                cho = 0.0
            else:
                self._xo[khoa] = (con, bay_gio)
                self._xo.move_to_end(khoa)
                cho = (1.0 - con) / toc_do
            while len(self._xo) > self._toi_da:
                self._xo.popitem(last=False)
            return cho

    def __len__(self) -> int:
        return len(self._xo)

    def xoa(self) -> None:
        with self._khoa:
            self._xo.clear()


kho = KhoXo()
_dem: dict[str, int] = {}
_khoa_dem = threading.Lock()


def ghi_nhan_tu_choi(nhom: str) -> None:
    with _khoa_dem:
        _dem[nhom] = _dem.get(nhom, 0) + 1


def thong_ke() -> dict[str, Any]:
    """Cho `/health`: hạn mức đang áp, số lần từ chối từ lúc khởi động, số khoá đang theo dõi. Không có khoá nào của khách."""
    han: Any
    try:
        han = {n: {"per_min": h.moi_phut, "burst": h.dinh} for n, h in doc_cau_hinh().items()}
    except RuntimeError:
        han = "cau_hinh_hong"        # lúc chạy, lớp lọc fail-open; /health nói thẳng thay vì ném
    with _khoa_dem:
        tu_choi = dict(_dem)
    return {"limits": han, "rejected": tu_choi, "tracked_keys": len(kho)}


def dat_lai() -> None:
    """Cho test."""
    kho.xoa()
    with _khoa_dem:
        _dem.clear()


def khoa_dem(scope: Mapping[str, Any], nhom: str) -> tuple[str, str, str]:
    """`(nhóm, key_id, store_id)`. Chỉ tin `X-Store-Id` khi đã qua HMAC enforce; không thì cả nhóm dùng một xô chung."""
    if not hmac_auth.da_xac_thuc.get():
        return (nhom, "-", "")
    store = ""
    for k, v in scope.get("headers", ()):
        if k.lower() == b"x-store-id":
            store = v.decode("latin-1").strip()[:TOI_DA_DO_DAI_STORE_ID]
            break
    return (nhom, hmac_auth.key_id_xac_thuc.get() or "-", store)


_THAN_429 = b'{"detail":"Too Many Requests"}'


class GioiHanTocDoMiddleware:
    """Middleware ASGI thuần. Xem docstring module."""

    def __init__(
        self,
        app,
        cau_hinh: Callable[[], dict[str, HanMuc]] = doc_cau_hinh,
        kho_xo: Optional[KhoXo] = None,
        dong_ho: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self._cau_hinh = cau_hinh
        self._kho = kho_xo if kho_xo is not None else kho
        self._dong_ho = dong_ho

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        nhom = nhom_cua(scope["method"], scope["path"])
        cho = 0.0
        key_id = "-"
        if nhom is not None:
            try:
                han = self._cau_hinh()[nhom]
                if han.moi_phut > 0:
                    khoa = khoa_dem(scope, nhom)
                    key_id = khoa[1]
                    cho = self._kho.thu(khoa, han, self._dong_ho())
            except Exception:       # noqa: BLE001 - fail-open có chủ đích (xem docstring)
                logger.warning("Giới hạn tốc độ lỗi, cho qua (nhóm=%s, loi=%s)", nhom, loai_loi())
                cho = 0.0
        if cho > 0:
            giay = max(1, math.ceil(cho))
            ghi_nhan_tu_choi(nhom or "?")
            logger.info("429 nhóm=%s key_id=%s chờ=%ds", nhom, key_id, giay)
            await send({
                "type": "http.response.start", "status": 429,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(_THAN_429)).encode()),
                            (b"retry-after", str(giay).encode())],
            })
            await send({"type": "http.response.body", "body": _THAN_429})
            return
        await self.app(scope, receive, send)
