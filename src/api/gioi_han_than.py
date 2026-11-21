"""
src/api/gioi_han_than.py — trần kích thước THÂN REQUEST ở tầng ASGI (#210).

VÌ SAO KHÔNG ĐỦ KIỂM TRONG HANDLER
----------------------------------
Mỗi route nhận tệp đã kiểm `MAX_UPLOAD_BYTES` (`_read_upload_to_tmp`, `_doc_file`, `/knowledge/documents`).
Nhưng FastAPI đọc và phân tích HẾT thân multipart TRƯỚC khi gọi handler, nên các phép kiểm đó chạy sau khi
toàn bộ tệp đã vào máy. Đo 21/11/2026: gửi tệp 20 MB tới `/ocr` -> 413 đúng, nhưng server đã đọc đủ 20/20 MB,
kể cả khi `Content-Length` khai sẵn 20 MB. Starlette còn ghi phần tệp vượt 1 MB ra tệp tạm trên đĩa.

Route JSON thì không có trần nào: `/chat` nhận thân 32 MB, trả 200 và đưa vào xử lý.

CÁCH LÀM
--------
Middleware ASGI thuần, đặt NGOÀI CÙNG để từ chối trước mọi lớp đệm thân (kể cả `HmacMiddleware`, có trần riêng
26 MB và chỉ khi bật):
  - `Content-Length` không phải số -> 400; vượt trần -> 413 NGAY, không đọc byte nào.
  - Không có `Content-Length` (chunked) -> đếm byte khi ứng dụng đọc; vượt trần thì ngừng đọc và trả 413.
    Ứng dụng có thể đã định trả 400 (FastAPI bọc lỗi đọc thân thành 400) — phản hồi đó bị THAY bằng 413.

Trần = `MAX_UPLOAD_BYTES` + 1 MiB cho phần bao multipart (ranh giới, header từng phần, trường form). Một núm
duy nhất (R4): nâng trần tệp thì trần request nâng theo. Route JSON dùng chung trần này — thân JSON hợp lệ
lớn hơn một tệp tải lên là điều chưa ai cần, và nếu cần thì đó là quyết định có chủ ý chứ không phải mặc định.
"""

from __future__ import annotations

import logging

from src.core.config import MAX_UPLOAD_BYTES
from src.core.utils import loai_loi

logger = logging.getLogger("projecta.api.gioi_han_than")

PHAN_BAO_MULTIPART = 1024 * 1024
TRAN_THAN_MAC_DINH = MAX_UPLOAD_BYTES + PHAN_BAO_MULTIPART


class _VuotTran(Exception):
    """Ném ra từ `receive` khi thân vượt trần, để ngừng đọc tiếp."""


async def _tra_loi(send, ma: int, noi_dung: bytes) -> None:
    await send({
        "type": "http.response.start",
        "status": ma,
        "headers": [(b"content-type", b"application/json"),
                    (b"content-length", str(len(noi_dung)).encode())],
    })
    await send({"type": "http.response.body", "body": noi_dung})


QUA_LON = b'{"detail":"Payload Too Large"}'
DO_DAI_SAI = b'{"detail":"Invalid Content-Length"}'


class GioiHanThanMiddleware:
    def __init__(self, app, tran: int = TRAN_THAN_MAC_DINH) -> None:
        if tran < 1:
            raise ValueError("tran phải >= 1")
        self.app = app
        self.tran = tran

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        ten = f'{scope["method"]} {scope["path"]}'
        dai = None
        for k, v in scope["headers"]:
            if k.lower() == b"content-length":
                dai = v.decode("latin-1").strip()
                break

        if dai is not None:
            if not dai.isdigit():
                logger.warning("Từ chối %s: Content-Length không hợp lệ %r", ten, dai[:32])
                await _tra_loi(send, 400, DO_DAI_SAI)
                return
            if int(dai) > self.tran:
                logger.warning("Từ chối %s: Content-Length %s > trần %d (chưa đọc byte nào)", ten, dai, self.tran)
                await _tra_loi(send, 413, QUA_LON)
                return

        da_doc = 0
        vuot = False
        da_gui_dau = False

        async def receive_dem():
            nonlocal da_doc, vuot
            if vuot:
                raise _VuotTran()
            tin = await receive()
            if tin["type"] == "http.request":
                da_doc += len(tin.get("body", b""))
                if da_doc > self.tran:
                    vuot = True
                    logger.warning("Từ chối %s: thân vượt trần %d khi đang đọc (đã đọc %d)", ten, self.tran, da_doc)
                    raise _VuotTran()
            return tin

        async def send_chan(tin):
            nonlocal da_gui_dau
            if vuot:
                # Ứng dụng đang trả lời một thân bị cắt (thường là 400 của FastAPI): thay bằng 413, một lần.
                if not da_gui_dau:
                    da_gui_dau = True
                    await _tra_loi(send, 413, QUA_LON)
                return
            if tin["type"] == "http.response.start":
                da_gui_dau = True
            await send(tin)

        try:
            await self.app(scope, receive_dem, send_chan)
        except _VuotTran:
            if not da_gui_dau:
                await _tra_loi(send, 413, QUA_LON)
        except Exception:
            if not vuot:
                raise
            # Lỗi phát sinh DO thân bị cắt (ứng dụng ném thay vì trả lời): phản hồi 413 đã/hoặc sẽ được gửi ở đây.
            logger.warning("Ứng dụng ném lỗi sau khi thân %s bị cắt ở trần %d; trả 413 (loi=%s)", ten, self.tran, loai_loi())
            if not da_gui_dau:
                await _tra_loi(send, 413, QUA_LON)
