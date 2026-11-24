"""
tests/integration/chat/test_khong_chan_event_loop_sql.py — bốn lời gọi SQL trong `/chat` không được chặn event loop
(AGENTS §4.1 quy tắc 2, brain#223, BR-27 PR-B).

Bốn hàm đồng bộ chạm DB, gọi thẳng trong `process_chat` (một coroutine):

    _load_history          đọc lịch sử hội thoại           (đầu mỗi lượt)
    saas.lookup_product    tra hàng trong DB cửa hàng       (nhánh DATA_INTERNAL)
    saas.get_sales_report  doanh số theo kỳ                 (nhánh DATA_INTERNAL)
    _save_turn             ghi hai tin nhắn của lượt        (cuối mỗi lượt)

DB chậm 300 ms thì cả server đứng 300 ms: `/health` và việc poll `GET /api/v1/task/{id}` của Body chờ.

ĐO giống PR-A (`test_khong_chan_event_loop.py`): một coroutine nhịp tim tick mỗi 10 ms chạy song song với
request, hàm DB được làm chậm 300 ms; khoảng trễ lớn nhất giữa hai tick phải dưới 0,15 s.

THỨ TỰ GHI TRƯỚC ĐỌC. `_save_turn` PHẢI được `await`, không ném vào nền: lượt sau đọc lại lịch sử, nên
việc ghi phải xong TRƯỚC khi tác vụ báo `completed`. Một bản "sửa" ném việc ghi vào nền sẽ qua phép đo
độ trễ mà vẫn làm lượt sau thấy lịch sử thiếu, nên có phép kiểm riêng cho nó.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest

from src.api import dependencies as deps
from src.api.routes import chat as chat_mod
from tests.integration.chat.test_khong_chan_event_loop import (
    NGUONG,
    TRE_CHAN,
    _do_khoang_tre_lon_nhat,
    _HamCham,
    _may_khach,
)
from tests.support.chat import _SaasGia

AI = {"X-User-Id": "1", "X-Store-Id": "1"}


class _BoNhoGia:
    """Bộ nhớ hội thoại giả: chậm có chủ đích, ghi lại thread và thứ tự gọi."""

    def __init__(self):
        self.tre = 0.0
        self.thread_ids: list[int] = []
        self.da_ghi: list[tuple[str, str]] = []

    def get_history_messages(self, user_id):
        self.thread_ids.append(threading.get_ident())
        if self.tre:
            time.sleep(self.tre)
        return [{"role": "user", "content": "câu trước"}, {"role": "assistant", "content": "đáp trước"}]

    def add_message(self, user_id, store_id, role, content):
        self.thread_ids.append(threading.get_ident())
        if self.tre:
            time.sleep(self.tre)
        self.da_ghi.append((role, content))


@pytest.fixture
def bo_nho(monkeypatch):
    kho = _BoNhoGia()
    monkeypatch.setattr(deps.runtime, "memory", kho, raising=False)
    monkeypatch.setattr(deps.runtime, "kb", None, raising=False)
    return kho


async def _hoi(ac, cau: str):
    return await ac.post("/chat", headers=AI, json={"user_id": 1, "store_id": 1, "message": cau})


async def _cho_xong(ac, task_id: str, toi_da: float = 10.0) -> dict[str, Any]:
    han = time.perf_counter() + toi_da
    while time.perf_counter() < han:
        kq = (await ac.get(f"/api/v1/task/{task_id}", headers=AI)).json()
        if kq["status"] != "processing":
            return kq
        await asyncio.sleep(0.02)
    raise AssertionError("tác vụ không xong trong thời hạn")


@pytest.mark.asyncio
async def test_doc_va_ghi_lich_su_khong_dong_bang_loop(moi_truong, bo_nho):  # noqa: F811
    async with _may_khach() as ac:
        # Lượt đầu không chậm: nạp trước các import lười để không tính vào số đo.
        assert (await _hoi(ac, "xin chào")).status_code == 200
        bo_nho.thread_ids.clear()
        bo_nho.da_ghi.clear()

        bo_nho.tre = TRE_CHAN
        resp, khoang = await _do_khoang_tre_lon_nhat(lambda: _hoi(ac, "xin chào lần hai"))
        assert resp.status_code == 200
        kq = await _cho_xong(ac, resp.json()["task_id"])

    assert kq["status"] == "completed", kq
    assert len(bo_nho.thread_ids) == 3, "một lần đọc và hai lần ghi phải thật sự chạy"
    assert khoang < NGUONG, f"event loop bị giữ {khoang:.3f}s trong lúc đọc/ghi lịch sử"
    assert all(t != threading.get_ident() for t in bo_nho.thread_ids), \
        "lời gọi DB vẫn chạy trên thread của event loop"


@pytest.mark.asyncio
async def test_ghi_xong_truoc_khi_tac_vu_bao_hoan_thanh(moi_truong, bo_nho):  # noqa: F811
    """Ghi trước đọc: thấy `completed` thì cả hai tin nhắn đã nằm trong DB."""
    bo_nho.tre = 0.05
    async with _may_khach() as ac:
        resp = await _hoi(ac, "xin chào")
        kq = await _cho_xong(ac, resp.json()["task_id"])
        da_ghi_khi_hoan_thanh = list(bo_nho.da_ghi)

    assert kq["status"] == "completed", kq
    assert [vai for vai, _ in da_ghi_khi_hoan_thanh] == ["user", "assistant"], \
        "tác vụ báo xong khi việc ghi lịch sử chưa xong: lượt sau sẽ đọc thiếu"
    assert da_ghi_khi_hoan_thanh[0][1] == "xin chào"


@pytest.mark.asyncio
async def test_loi_ghi_lich_su_van_khong_lam_hong_cau_tra_loi(moi_truong, bo_nho, monkeypatch):  # noqa: F811
    """Suy giảm mềm giữ nguyên: DB hỏng thì mất ngữ cảnh, không mất câu trả lời."""
    def hong(*a, **k):
        raise RuntimeError("DB chết")

    monkeypatch.setattr(bo_nho, "add_message", hong)
    monkeypatch.setattr(bo_nho, "get_history_messages", hong)
    async with _may_khach() as ac:
        resp = await _hoi(ac, "xin chào")
        kq = await _cho_xong(ac, resp.json()["task_id"])
    assert kq["status"] == "completed", kq


@pytest.mark.asyncio
async def test_tra_hang_va_doanh_so_khong_dong_bang_loop(moi_truong, bo_nho, monkeypatch):  # noqa: F811
    gia = _SaasGia()
    cham_hang = _HamCham(gia.lookup_product)
    cham_so = _HamCham(gia.get_sales_report)
    gia.lookup_product = cham_hang                       # type: ignore[method-assign]
    gia.get_sales_report = cham_so                       # type: ignore[method-assign]
    monkeypatch.setattr(chat_mod, "_get_saas", lambda: gia)
    moi_truong.category = "DATA_INTERNAL"

    async with _may_khach() as ac:
        assert (await _hoi(ac, "tháng này doanh số thế nào")).status_code == 200   # nạp trước
        cham_hang.thread_ids.clear()
        cham_so.thread_ids.clear()

        cham_hang.tre = cham_so.tre = TRE_CHAN
        resp, khoang = await _do_khoang_tre_lon_nhat(lambda: _hoi(ac, "tháng này doanh số thế nào"))
        assert resp.status_code == 200
        kq = await _cho_xong(ac, resp.json()["task_id"])

    assert kq["status"] == "completed", kq
    assert len(cham_hang.thread_ids) == 1 and len(cham_so.thread_ids) == 1, "cả hai truy vấn phải chạy"
    assert khoang < NGUONG, f"event loop bị giữ {khoang:.3f}s trong lúc truy vấn DB cửa hàng"
    assert all(t != threading.get_ident() for t in cham_hang.thread_ids + cham_so.thread_ids)
