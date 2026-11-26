"""
src/api/giu_tep_trong_ram.py — tệp tải lên ở lại trong RAM, không chạm đĩa (#219, R2).

VÌ SAO
------
`/tools/inventory-import`, `/tools/partner-import`, `/tools/product-import` và `POST /knowledge/documents` hứa "File KHÔNG ghi ra
đĩa": sổ sách, danh sách khách, hợp đồng, bảng giá cước của khách không được nằm lại trên máy Brain (có thể là GPU thuê). Nhưng
FastAPI phân tích multipart bằng `starlette.formparsers.MultiPartParser`, và phần tệp được giữ trong `SpooledTemporaryFile` với
ngưỡng 1 MiB. Vượt 1 MiB là Starlette ghi ra tệp tạm trên đĩa TRƯỚC khi handler chạy. Đo 26/11/2026 (Starlette 1.10.0): tệp 2 MB
và 5 MB tới cả ba route trên đều tạo một tệp tạm; tệp 0,5 MB thì không.

CÁCH LÀM
--------
Nâng ngưỡng đó lên bằng trần thân request (`TRAN_THAN_MAC_DINH`, `gioi_han_than.py`). `GioiHanThanMiddleware` nằm ngoài cùng và cắt
mọi thân vượt trần đó, nên một phần tệp không bao giờ lớn hơn ngưỡng giữ trong RAM: không có gì để tràn ra đĩa. Một con số (R4):
nâng `MAX_UPLOAD_BYTES` thì trần thân và ngưỡng này nâng theo.

Áp cho MỌI route multipart, kể cả `/upload`, `/ocr`, `/ocr/freight`. Ba route đó vẫn CỐ Ý ghi tệp tạm trong handler
(`_read_upload_to_tmp`, để đưa đường dẫn cho vision); chỉ khác là bản đệm trước handler giờ ở RAM thay vì một tệp tạm thứ hai.

RAM: mỗi request tải tệp giữ tối đa ~6 MiB (bản đệm) cộng bản `await file.read()` (≤ 5 MiB) trong lúc xử lý, tức ~11 MiB đỉnh. Trước
đây là 1 MiB đệm cộng bản đọc vào RAM: handler vẫn đọc hết tệp vào RAM, chỉ là bản đệm nằm trên đĩa. Tăng thêm ~5 MiB mỗi request
tải tệp đồng thời.

TÊN THUỘC TÍNH ĐỔI THEO PHIÊN BẢN STARLETTE (review của Minh trên PR #279)
-----------------------------------------------------------------------
`requirements.txt` chỉ chặn `fastapi<1`, nên trình cài đặt được phép chọn một Starlette cũ. Ngưỡng là thuộc tính lớp, không phải API
công khai, và đã đổi tên. Đối chiếu mã nguồn `starlette/formparsers.py` trong wheel trên PyPI, 26/11/2026:

| Starlette     | Thuộc tính       | Dùng ở                                         |
|---------------|------------------|------------------------------------------------|
| 0.27 – 0.45.3 | `max_file_size`  | `SpooledTemporaryFile(max_size=self.max_file_size)`  |
| 0.46.0 – 1.10 | `spool_max_size` | `SpooledTemporaryFile(max_size=self.spool_max_size)` |

Ví dụ một bộ hợp lệ theo `requirements.txt`: FastAPI 0.115.8 + Starlette 0.45.3. Bản đầu của hàm này chỉ biết `spool_max_size`, nên
với bộ đó API không khởi động được. Giờ hàm nhận cả hai tên, ưu tiên tên mới.

Bản cũ hơn 0.27 (ví dụ 0.13.6) không có thuộc tính nào trong hai cái trên trên parser: hàm ném `RuntimeError` lúc khởi động, thay vì
lặng lẽ để tệp chạm đĩa lại. Thư viện đổi tên lần nữa cũng vậy, và `tests/integration/api/test_giu_tep_trong_ram_219.py` đỏ.
"""

from __future__ import annotations

from starlette.formparsers import MultiPartParser

from src.api.gioi_han_than import TRAN_THAN_MAC_DINH

# Tên mới trước: nếu một bản sau này có cả hai, `spool_max_size` mới là cái đặt cỡ bản đệm.
TEN_NGUONG = ("spool_max_size", "max_file_size")


def giu_trong_ram(tran: int = TRAN_THAN_MAC_DINH) -> str:
    """
    Đặt ngưỡng giữ tệp multipart trong RAM ≥ `tran`. Không bao giờ hạ ngưỡng xuống.

    Trả về tên thuộc tính đã dùng. Không tìm thấy thuộc tính nào hợp lệ thì ném RuntimeError.
    """
    for ten in TEN_NGUONG:
        hien_tai = getattr(MultiPartParser, ten, None)
        if isinstance(hien_tai, int) and not isinstance(hien_tai, bool):
            if hien_tai < tran:
                setattr(MultiPartParser, ten, tran)
            return ten
    raise RuntimeError(
        "starlette.formparsers.MultiPartParser không có thuộc tính spool_max_size (Starlette ≥ 0.46) hay max_file_size "
        "(0.27–0.45). Không biết tệp tải lên có chạm đĩa hay không, nên dừng thay vì chạy tiếp (#219, R2)."
    )
