"""
Chạy việc CHẶN ngoài event loop (AGENTS §4.1 quy tắc 2).

Một handler `async def` mà gọi hàm đồng bộ tốn thời gian (đọc xlsx, trích văn bản từ PDF,
tìm web) làm cả server đứng hình trong lúc đó: `/health`, poll tác vụ nền và mọi request khác
đều chờ. Hàm này đẩy việc sang thread của pool mặc định.

CHỈ dùng cho việc KHÔNG dùng chung trạng thái. Việc đụng `KnowledgeBase` (embedder, chromadb,
cache BM25) phải đi qua MỘT worker duy nhất — việc đó thuộc PR sau, vì ném nó vào pool mặc
định mà không tuần tự hoá sẽ mở ra race thật (nạp lại tài liệu cùng nguồn).

Quy tắc dùng: truyền HÀM, không truyền kết quả, và tra tên hàm ngay lúc gọi
(`await chay_ngoai_loop(web_search_fallback, q)`), không chụp tham chiếu lúc import — để
`monkeypatch.setattr(chat_mod, "web_search_fallback", ...)` trong test vẫn bắt được. Ngoại lệ
của hàm lan ra y nguyên, nên `try/except` quanh lời gọi giữ nguyên nghĩa.

Chỉ dùng thư viện chuẩn, không import `src.*`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


async def chay_ngoai_loop(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    return await asyncio.to_thread(fn, *args, **kwargs)
