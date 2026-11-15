"""
Chạy việc CHẶN ngoài event loop (AGENTS §4.1 quy tắc 2).

Một handler `async def` mà gọi hàm đồng bộ tốn thời gian (đọc xlsx, trích văn bản từ PDF,
tìm web) làm cả server đứng hình trong lúc đó: `/health`, poll tác vụ nền và mọi request khác
đều chờ. Hàm này đẩy việc sang thread của pool mặc định.

`chay_ngoai_loop` CHỈ dùng cho việc KHÔNG dùng chung trạng thái. Việc đụng `KnowledgeBase`
(embedder, chromadb, cache BM25) đi qua `chay_tren_kho` bên dưới: MỘT worker duy nhất. Ném nó vào
pool mặc định mà không tuần tự hoá sẽ mở ra race thật khi nạp lại tài liệu cùng nguồn.

Quy tắc dùng: truyền HÀM, không truyền kết quả, và tra tên hàm ngay lúc gọi
(`await chay_ngoai_loop(web_search_fallback, q)`), không chụp tham chiếu lúc import — để
`monkeypatch.setattr(chat_mod, "web_search_fallback", ...)` trong test vẫn bắt được. Ngoại lệ
của hàm lan ra y nguyên, nên `try/except` quanh lời gọi giữ nguyên nghĩa.

Chỉ dùng thư viện chuẩn, không import `src.*`.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

T = TypeVar("T")

# MỘT worker cho MỌI thao tác `KnowledgeBase` (BR-27 PR-C). Không dùng `asyncio.Lock` ở mức module
# (gắn với loop đầu tiên dùng nó, vỡ khi test hay khi uvicorn đổi loop) và không đặt `wait_for` trên
# đường này: hết giờ sẽ thành danh sách rỗng và câu trả lời ra "không có tài liệu" cho tài liệu có
# thật. Tuần tự hoá bằng cách chỉ có một thread: thao tác sau xếp hàng chờ thao tác trước.
#
# Vì sao phải tuần tự: `add_document` nạp lại tài liệu cùng nguồn bằng "xoá đoạn cũ rồi thêm đoạn
# mới". Chạy song song với `search`, đoạn chứa GIÁ CŨ có thể nằm cạnh bản mới, và một câu hỏi giá
# cước được trả lời bằng bảng giá đã thay.
_KHO_WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kho-tri-thuc")


async def chay_ngoai_loop(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    return await asyncio.to_thread(fn, *args, **kwargs)


async def chay_tren_kho(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """
    Chạy MỘT thao tác `KnowledgeBase` trên worker duy nhất, ngoài event loop.

    Mọi chỗ trong `src/api` đụng kho tri thức (search, add_document, list_documents,
    delete_document, workspaces) PHẢI đi qua đây. Chuyển nửa vời tạo ra chính race cần tránh:
    một thao tác ở pool mặc định, thao tác kia ở worker, vẫn chạy song song.
    """
    return await asyncio.get_running_loop().run_in_executor(
        _KHO_WORKER, functools.partial(fn, *args, **kwargs)
    )
