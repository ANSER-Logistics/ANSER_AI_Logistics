"""
src/api/giu_tep_trong_ram.py — tệp tải lên ở lại trong RAM, không chạm đĩa (#219, R2).

VÌ SAO
------
`/tools/inventory-import`, `/tools/partner-import`, `/tools/product-import` và `POST /knowledge/documents` hứa "File KHÔNG ghi ra
đĩa": sổ sách, danh sách khách, hợp đồng, bảng giá cước của khách không được nằm lại trên máy Brain (có thể là GPU thuê). Nhưng
FastAPI phân tích multipart bằng `starlette.formparsers.MultiPartParser`, và phần tệp được giữ trong `SpooledTemporaryFile` với
`spool_max_size` = 1 MiB. Vượt 1 MiB là Starlette ghi ra tệp tạm trên đĩa TRƯỚC khi handler chạy. Đo 26/11/2026 (Starlette 1.10.0):
tệp 2 MB và 5 MB tới cả ba route trên đều tạo một tệp tạm; tệp 0,5 MB thì không.

CÁCH LÀM
--------
Nâng `MultiPartParser.spool_max_size` lên bằng trần thân request (`TRAN_THAN_MAC_DINH`, `gioi_han_than.py`). `GioiHanThanMiddleware`
nằm ngoài cùng và cắt mọi thân vượt trần đó, nên một phần tệp không bao giờ lớn hơn ngưỡng giữ trong RAM: không có gì để tràn ra đĩa.
Một con số (R4): nâng `MAX_UPLOAD_BYTES` thì trần thân và ngưỡng này nâng theo.

Áp cho MỌI route multipart, kể cả `/upload`, `/ocr`, `/ocr/freight`. Ba route đó vẫn CỐ Ý ghi tệp tạm trong handler
(`_read_upload_to_tmp`, để đưa đường dẫn cho vision); chỉ khác là bản đệm trước handler giờ ở RAM thay vì một tệp tạm thứ hai.

RAM: mỗi request tải tệp giữ tối đa ~6 MiB (bản đệm) cộng bản `await file.read()` (≤ 5 MiB) trong lúc xử lý, tức ~11 MiB đỉnh. Trước
đây là 1 MiB đệm cộng bản đọc vào RAM: handler vẫn đọc hết tệp vào RAM, chỉ là bản đệm nằm trên đĩa. Tăng thêm ~5 MiB mỗi request
tải tệp đồng thời.

`spool_max_size` là thuộc tính lớp của thư viện, không phải API công khai. Nâng Starlette mà thuộc tính đổi tên thì `giu_trong_ram()`
ném lỗi lúc khởi động (và `tests/test_giu_tep_trong_ram_219.py` đỏ), thay vì lặng lẽ để tệp chạm đĩa lại.
"""

from __future__ import annotations

from starlette.formparsers import MultiPartParser

from src.api.gioi_han_than import TRAN_THAN_MAC_DINH


def giu_trong_ram(tran: int = TRAN_THAN_MAC_DINH) -> None:
    """Đặt ngưỡng giữ tệp multipart trong RAM ≥ `tran`. Không bao giờ hạ ngưỡng xuống. Thư viện đổi khác thì ném RuntimeError."""
    hien_tai = getattr(MultiPartParser, "spool_max_size", None)
    if not isinstance(hien_tai, int) or isinstance(hien_tai, bool):
        raise RuntimeError(
            "starlette.formparsers.MultiPartParser không còn thuộc tính spool_max_size (đổi phiên bản Starlette?). "
            "Không biết tệp tải lên có chạm đĩa hay không, nên dừng thay vì chạy tiếp (#219, R2)."
        )
    if hien_tai < tran:
        MultiPartParser.spool_max_size = tran
