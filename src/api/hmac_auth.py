"""
src/api/hmac_auth.py — xác thực HMAC-SHA256 từng yêu cầu, thay token tĩnh dùng chung (A6, issue #193).

VÌ SAO
------
`API_AUTH_TOKEN` là một chuỗi cố định dùng chung cho Body, n8n và mọi bên gọi: ai chép được một lần là gọi Brain mãi, và thu hồi
một bên thì hỏng cả hai. HMAC ký từng yêu cầu bằng khoá riêng của từng bên gọi, kèm thời điểm và số dùng một lần (nonce), nên
yêu cầu bị chép lại thì vô dụng sau 5 phút, sửa một byte là sai chữ ký, và thu hồi được từng bên.

GIAO THỨC (V1; nghiên cứu: `NGHIEN_CUU_HMAC` ở repo tài liệu, bốn vector vàng ở `tests/test_hmac_auth.py`)
------------------------------------------------------------------------------------------------------
Bên gọi gửi bốn header:

    X-Key-Id:     [a-z0-9][a-z0-9-]{0,31}        khoá nào (mỗi bên gọi một khoá)
    X-Timestamp:  10 chữ số, giây Unix
    X-Nonce:      32 ký tự hex thường, MỚI cho từng lần gửi (kể cả thử lại)
    X-Signature:  v1=<64 hex thường>

Chuỗi cần ký (UTF-8, nối bằng "\\n", KHÔNG có "\\n" cuối):

    ANSER-HMAC-V1
    <key id>
    <timestamp>
    <nonce>
    <METHOD viết hoa>
    <đường dẫn chính xác>
    <chuỗi truy vấn THÔ như đã gửi, không có dấu ?>
    <SHA-256 hex thường của các byte THÔ của thân; thân rỗng thì băm chuỗi rỗng>

Chữ ký = HMAC-SHA256(khoá, chuỗi cần ký) hex thường. Khoá là chuỗi ≥ 32 ký tự, dùng NGUYÊN VĂN như văn bản UTF-8 (không giải mã hex),
để Python và TypeScript không lệch ở bước giải mã.

KHÔNG ký: `Host` và các header đi qua proxy (Cloudflare tự thêm và sửa), `Content-Type` (server từ chối `Content-Encoding`).

CHẾ ĐỘ (`API_HMAC_MODE`)
-----------------------
- `off` (mặc định): không đổi gì, chỉ dùng `X-Api-Token` như cũ.
- `log`: VẪN bắt `X-Api-Token` như cũ; thêm kiểm HMAC và GHI kết quả (mã lý do, key id, không bao giờ ghi chữ ký, thân hay khoá). Không từ chối vì HMAC.
- `enforce`: BẮT BUỘC HMAC hợp lệ; `X-Api-Token` không còn là đường vào.

KHOÁ (R2b): biến môi trường `API_HMAC_KEY_<ID>`, ví dụ `API_HMAC_KEY_BODY` có key id `body`, `API_HMAC_KEY_BODY_2` có key id `body-2`.
Xoay khoá: đặt thêm `..._BODY_2`, đổi Body sang `body-2`, rồi xoá `..._BODY`. Không khoá nào nằm trong mã.

CHỐNG PHÁT LẠI: nonce nhớ 660 giây (cửa sổ ±300 giây đối xứng thì phải nhớ 2 x 300 + đệm; TTL bằng cửa sổ để hở). Chỉ ghi nhận SAU khi chữ ký đúng,
để kẻ gửi rác không làm đầy bộ nhớ nonce của người thật. Bộ nhớ nonce nằm TRONG TIẾN TRÌNH: đúng khi chạy một tiến trình (compose hiện nay); nhiều
bản sao thì phải chuyển sang Redis (BR-08) sau cùng một giao diện `KhoNonce`.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Mapping, Optional

logger = logging.getLogger("anser.hmac")

PHIEN_BAN = "ANSER-HMAC-V1"
CUA_SO_LECH_GIO_S = 300          # ±5 phút, mặc định của Stripe và Slack
NONCE_NHO_S = 2 * CUA_SO_LECH_GIO_S + 60
NONCE_TOI_DA = 200_000           # trần bộ nhớ: ~100 byte/mục, vài chục MB
KHOA_TOI_THIEU = 32
TIEN_TO_KHOA = "API_HMAC_KEY_"
CAC_CHE_DO = ("off", "log", "enforce")
TOI_DA_THAN_MAC_DINH = 26 * 1024 * 1024

_RE_KEY_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,31}", re.ASCII)
_RE_TS = re.compile(r"[0-9]{10}", re.ASCII)
_RE_NONCE = re.compile(r"[0-9a-f]{32}", re.ASCII)
_RE_SIG = re.compile(r"v1=([0-9a-f]{64})", re.ASCII)
_RE_PATH = re.compile(r"[A-Za-z0-9._/-]+", re.ASCII)

# Lý do (cố định, không chứa nội dung): đưa vào log và bộ đếm.
OK, TAT, THIEU_HEADER, SAI_DINH_DANG, KHOA_LA, HET_HAN, SAI_CHU_KY, PHAT_LAI, SAI_DUONG_DAN, THAN_QUA_LON, CO_NEN = (
    "ok", "tat", "thieu_header", "sai_dinh_dang", "khoa_la", "het_han", "sai_chu_ky", "phat_lai", "sai_duong_dan",
    "than_qua_lon", "co_content_encoding",
)

# Đã xác thực bằng HMAC trong lượt yêu cầu hiện tại: `require_api_token` trong từng handler (lớp thứ hai) dựa vào đây
# để không đòi `X-Api-Token` ở chế độ `enforce`. Đặt bởi `auth_guard`, cùng tác vụ asyncio với handler.
da_xac_thuc: ContextVar[bool] = ContextVar("anser_hmac_da_xac_thuc", default=False)


# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------

def che_do() -> str:
    """`off` | `log` | `enforce`. Đọc LÚC GỌI để test và `/health` thấy giá trị hiện tại. Giá trị lạ: xem `kiem_cau_hinh`."""
    return os.getenv("API_HMAC_MODE", "off").strip().lower() or "off"


def nap_khoa() -> dict[str, bytes]:
    """`{key_id: khoá UTF-8}` từ các biến `API_HMAC_KEY_<ID>`. Biến rỗng bị bỏ qua."""
    khoa: dict[str, bytes] = {}
    for ten, gia_tri in os.environ.items():
        if not ten.startswith(TIEN_TO_KHOA):
            continue
        v = gia_tri.strip()
        if not v:
            continue
        key_id = ten[len(TIEN_TO_KHOA):].lower().replace("_", "-")
        khoa[key_id] = v.encode("utf-8")
    return khoa


def kiem_cau_hinh() -> None:
    """
    Gọi lúc khởi động. Ném `RuntimeError` nếu cấu hình HMAC sai: một cổng xác thực cấu hình sai không được chạy lặng lẽ.
    Không bao giờ in giá trị khoá.
    """
    cd = che_do()
    if cd not in CAC_CHE_DO:
        raise RuntimeError(f"API_HMAC_MODE={cd!r} không hợp lệ; chỉ nhận {', '.join(CAC_CHE_DO)}.")
    if cd == "off":
        return
    khoa = nap_khoa()
    if not khoa:
        raise RuntimeError(f"API_HMAC_MODE={cd} nhưng không có biến {TIEN_TO_KHOA}<ID> nào được đặt.")
    for key_id, k in khoa.items():
        if not _RE_KEY_ID.fullmatch(key_id):
            raise RuntimeError(f"Tên biến {TIEN_TO_KHOA}* cho key id {key_id!r} không hợp lệ (chỉ a-z, 0-9, dấu gạch ngang; tối đa 32).")
        if len(k) < KHOA_TOI_THIEU:
            raise RuntimeError(f"Khoá HMAC của key id {key_id!r} ngắn hơn {KHOA_TOI_THIEU} ký tự.")


def dang_cuong_che() -> bool:
    return che_do() == "enforce"


# ---------------------------------------------------------------------------
# Nonce
# ---------------------------------------------------------------------------

class KhoNonce:
    """Nhớ nonce đã dùng, theo (key id, nonce), trong `NONCE_NHO_S` giây. Trong tiến trình; một khoá (thread) bảo vệ."""

    def __init__(self, nho_s: int = NONCE_NHO_S, toi_da: int = NONCE_TOI_DA) -> None:
        self._nho_s, self._toi_da = nho_s, toi_da
        self._d: "OrderedDict[tuple[str, str], float]" = OrderedDict()
        self._khoa = threading.Lock()

    def da_gap_roi_ghi(self, key_id: str, nonce: str, bay_gio: float) -> bool:
        """`True` nếu nonce này đã dùng trong cửa sổ nhớ (phát lại). Chưa thì ghi lại và trả `False`."""
        k = (key_id, nonce)
        with self._khoa:
            han = bay_gio - self._nho_s
            while self._d:                                    # OrderedDict theo thứ tự ghi: hết hạn ở đầu
                dau = next(iter(self._d))
                if self._d[dau] > han:
                    break
                self._d.popitem(last=False)
            if k in self._d:
                return True
            if len(self._d) >= self._toi_da:
                # Đầy: bỏ mục cũ nhất thay vì từ chối người thật. Cửa sổ phát lại của mục bị bỏ mở lại, nên ghi ra log.
                self._d.popitem(last=False)
                logger.warning("Bộ nhớ nonce đầy (%d mục): bỏ mục cũ nhất", self._toi_da)
            self._d[k] = bay_gio
            return False

    def __len__(self) -> int:
        return len(self._d)


kho_nonce = KhoNonce()


# ---------------------------------------------------------------------------
# Ký và kiểm
# ---------------------------------------------------------------------------

def chuoi_can_ky(key_id: str, timestamp: str, nonce: str, method: str, path: str, raw_query: str, body: bytes) -> str:
    return "\n".join([
        PHIEN_BAN, key_id, timestamp, nonce, method.upper(), path, raw_query, hashlib.sha256(body).hexdigest(),
    ])


def ky(khoa: bytes, key_id: str, timestamp: str, nonce: str, method: str, path: str, raw_query: str, body: bytes) -> str:
    """Chữ ký hex thường (không kèm tiền tố `v1=`). Dùng cho test và cho công cụ ký phía Brain (ví dụ webhook về Body)."""
    cs = chuoi_can_ky(key_id, timestamp, nonce, method, path, raw_query, body)
    return hmac.digest(khoa, cs.encode("utf-8"), "sha256").hex()


@dataclass(frozen=True)
class KetQua:
    ok: bool
    ly_do: str
    key_id: str = ""


def kiem(
    *,
    method: str,
    path: str,
    raw_query: str,
    headers: Mapping[str, str],
    body: bytes,
    bay_gio: Optional[float] = None,
    kho: Optional[KhoNonce] = None,
    khoa: Optional[Mapping[str, bytes]] = None,
) -> KetQua:
    """
    Kiểm một yêu cầu. Thứ tự (rẻ trước, tốn trước sau): dạng header, đường dẫn, khoá, cửa sổ giờ, chữ ký (so sánh hằng thời gian), nonce.
    Nonce chỉ được ghi sau khi chữ ký đúng. KHÔNG ném ngoại lệ cho đầu vào xấu; mọi thất bại là một `KetQua` có lý do cố định.
    """
    bay_gio = time.time() if bay_gio is None else bay_gio
    kho = kho or kho_nonce
    khoa = nap_khoa() if khoa is None else khoa

    key_id = headers.get("x-key-id")
    ts = headers.get("x-timestamp")
    nonce = headers.get("x-nonce")
    sig = headers.get("x-signature")
    if key_id is None or ts is None or nonce is None or sig is None:
        return KetQua(False, THIEU_HEADER)
    m_sig = _RE_SIG.fullmatch(sig)
    if not (_RE_KEY_ID.fullmatch(key_id) and _RE_TS.fullmatch(ts) and _RE_NONCE.fullmatch(nonce) and m_sig):
        return KetQua(False, SAI_DINH_DANG)
    if headers.get("content-encoding"):
        return KetQua(False, CO_NEN, key_id)
    if not _RE_PATH.fullmatch(path):
        return KetQua(False, SAI_DUONG_DAN, key_id)
    k = khoa.get(key_id)
    if k is None:
        return KetQua(False, KHOA_LA, key_id)
    if abs(bay_gio - int(ts)) > CUA_SO_LECH_GIO_S:
        return KetQua(False, HET_HAN, key_id)
    mong_doi = ky(k, key_id, ts, nonce, method, path, raw_query, body).encode("ascii")
    if not hmac.compare_digest(mong_doi, m_sig.group(1).encode("ascii")):
        return KetQua(False, SAI_CHU_KY, key_id)
    if kho.da_gap_roi_ghi(key_id, nonce, bay_gio):
        return KetQua(False, PHAT_LAI, key_id)
    return KetQua(True, OK, key_id)


# ---------------------------------------------------------------------------
# Bộ đếm (nhìn thấy ở /health)
# ---------------------------------------------------------------------------

_dem: dict[str, int] = {}
_khoa_dem = threading.Lock()


def ghi_nhan(ket_qua: KetQua) -> None:
    with _khoa_dem:
        _dem[ket_qua.ly_do] = _dem.get(ket_qua.ly_do, 0) + 1


def thong_ke() -> dict[str, object]:
    with _khoa_dem:
        dem = dict(_dem)
    return {"mode": che_do(), "key_ids": sorted(nap_khoa()), "counts": dem}


def dat_lai_thong_ke() -> None:
    """Cho test."""
    with _khoa_dem:
        _dem.clear()
    kho_nonce._d.clear()


# ---------------------------------------------------------------------------
# Middleware ASGI thuần
# ---------------------------------------------------------------------------

class HmacMiddleware:
    """
    Kiểm HMAC ở tầng ASGI, TRƯỚC khi FastAPI đọc thân.

    Vì sao không phải dependency: FastAPI đọc và phân tích thân (JSON, multipart) TRƯỚC khi chạy dependency. Dependency gọi
    `request.body()` thì JSON còn được, nhưng multipart ném `RuntimeError: Stream consumed` (500) vì `request.form()` đã tiêu thụ
    luồng (đo 20/11/2026 trên cả app thật và app thử). Thân JSON sai cú pháp cũng ra 422 trước khi kiểm. Middleware ASGI thuần đệm thân (có trần),
    kiểm, rồi phát lại đúng các thông điệp đó cho ứng dụng; các lần `receive()` sau đó chuyển tiếp xuống luồng thật để tín hiệu ngắt kết nối vẫn tới.

    - `off`: chuyển thẳng, không đọc gì.
    - `log`: đệm, kiểm, ghi nhận; luôn chuyển tiếp.
    - `enforce`: đệm, kiểm; hỏng thì trả 401 (mọi lý do cùng một thân), thân quá trần thì 413.
    `mien`: các đường dẫn không cần chữ ký (như `/health`).
    """

    def __init__(self, app, mien: Optional[frozenset[str]] = None) -> None:
        self.app = app
        self.mien = mien or frozenset()

    async def __call__(self, scope, receive, send):
        cd = che_do()
        if scope["type"] != "http" or cd == "off" or scope["path"] in self.mien or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return

        tran = int(os.getenv("API_HMAC_MAX_BODY_BYTES", str(TOI_DA_THAN_MAC_DINH)))
        dau = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        dai = dau.get("content-length")
        cac_tin: list[dict] = []
        than = bytearray()
        qua_lon = bool(dai is not None and dai.isdigit() and int(dai) > tran)
        if not qua_lon:
            while True:
                tin = await receive()
                cac_tin.append(tin)
                if tin["type"] != "http.request":      # http.disconnect: không còn gì để đọc
                    break
                than += tin.get("body", b"")
                if len(than) > tran:
                    qua_lon = True
                    break
                if not tin.get("more_body", False):
                    break

        if qua_lon:
            kq = KetQua(False, THAN_QUA_LON)
        else:
            kq = kiem(method=scope["method"], path=scope["path"], raw_query=scope.get("query_string", b"").decode("latin-1"),
                      headers=dau, body=bytes(than))
        ghi_nhan(kq)
        ten = f'{scope["method"]} {scope["path"]}'
        if cd == "log":
            (logger.info if kq.ok or kq.ly_do == THIEU_HEADER else logger.warning)(
                "hmac(log) %s key_id=%s ly_do=%s", ten, kq.key_id or "-", kq.ly_do)
        elif not kq.ok:
            logger.warning("hmac(enforce) từ chối %s key_id=%s ly_do=%s", ten, kq.key_id or "-", kq.ly_do)
            ma, noi_dung = (413, b'{"detail":"Payload Too Large"}') if kq.ly_do == THAN_QUA_LON else (401, b'{"detail":"Unauthorized"}')
            await send({"type": "http.response.start", "status": ma,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(noi_dung)).encode())]})
            await send({"type": "http.response.body", "body": noi_dung})
            return

        hang_doi = list(cac_tin)

        async def phat_lai():
            if hang_doi:
                return hang_doi.pop(0)
            return await receive()

        dat = None
        if cd == "enforce" and kq.ok:
            dat = da_xac_thuc.set(True)
        try:
            await self.app(scope, phat_lai, send)
        finally:
            if dat is not None:
                da_xac_thuc.reset(dat)
