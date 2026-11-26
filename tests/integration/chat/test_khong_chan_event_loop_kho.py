"""
tests/integration/chat/test_khong_chan_event_loop_kho.py — mọi truy cập `KnowledgeBase` đi qua MỘT worker, ngoài event loop
(AGENTS §4.1 quy tắc 2, brain#223, BR-27 PR-C).

HAI ĐIỀU PHẢI ĐÚNG CÙNG LÚC
---------------------------
1. Không chặn event loop. `search` (embedding, rerank), `add_document` (cắt đoạn, embedding, ghi) tốn vài trăm
   ms tới vài giây; gọi thẳng trong `async def` thì `/health` và việc poll tác vụ đứng chờ.
2. Không chạy SONG SONG với nhau. Embedder, chromadb và cache BM25 dùng chung, và `add_document` nạp lại tài
   liệu cùng nguồn bằng "xoá đoạn cũ rồi thêm đoạn mới". Chạy song song với `search`, đoạn chứa GIÁ CŨ có thể
   nằm cạnh bản mới, và một câu hỏi giá cước được trả lời bằng bảng giá đã thay.

Nên không thể chỉ ném vào pool mặc định (`asyncio.to_thread`): nó đạt điều 1 và phá điều 2. Test dưới dựng một
KB giả với đầu dò đếm số thao tác ĐANG CHẠY CÙNG LÚC; sáu chỗ gọi phải cho tối đa 1, trên đúng một thread.

CHUYỂN NỬA VỜI. Spec BR-27 đòi chuyển cả sáu chỗ (chat.py hai: `search` và chẩn đoán lệch phạm vi; routes/
knowledge.py bốn) trong CÙNG một PR. Một chỗ còn lại ở event loop vẫn chạy song song với worker, nên test
ép mọi đường đi qua cùng một đầu dò, không kiểm riêng từng đường.
"""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from src.api import dependencies as deps
from src.api.chay_ngoai_loop import chay_ngoai_loop, chay_tren_kho
from tests.integration.chat.test_khong_chan_event_loop import (
    NGUONG,
    TRE_CHAN,
    _do_khoang_tre_lon_nhat,
    _may_khach,
)

AI = {"X-User-Id": "1", "X-Store-Id": "1"}


class _KhoDauDo:
    """
    KB giả: mỗi thao tác ngủ `tre` giây và ghi lại (thread, số thao tác đang chạy cùng lúc).

    Mượn chữ ký thật của `KnowledgeBase` cho năm thao tác route gọi tới.
    """

    def __init__(self):
        self.tre = 0.0
        self.dang_chay = 0
        self.dong_thoi_toi_da = 0
        self.thread_ids: list[int] = []
        self.da_goi: list[str] = []
        self._khoa = threading.Lock()

    def _thao_tac(self, ten: str):
        with self._khoa:
            self.dang_chay += 1
            self.dong_thoi_toi_da = max(self.dong_thoi_toi_da, self.dang_chay)
            self.thread_ids.append(threading.get_ident())
            self.da_goi.append(ten)
        try:
            if self.tre:
                time.sleep(self.tre)
        finally:
            with self._khoa:
                self.dang_chay -= 1

    def search(self, workspace_id, query, top_k=5, on_date=None):
        self._thao_tac("search")
        return []

    def add_document(self, workspace_id, text, source="", effective_from=None, effective_to=None, doc_type=None):
        self._thao_tac("add_document")
        return SimpleNamespace(source=source, chunks=1, replaced=False, skipped_unchanged=False, warnings=[])

    def list_documents(self, workspace_id):
        self._thao_tac("list_documents")
        return []

    def delete_document(self, workspace_id, source):
        self._thao_tac("delete_document")
        return 1

    def workspaces(self):
        self._thao_tac("workspaces")
        return ["khach-khac"]


@pytest.fixture
def kho(monkeypatch):
    k = _KhoDauDo()
    monkeypatch.setattr(deps.runtime, "kb", k, raising=False)
    return k


def _yeu_cau_tai_lieu() -> dict[str, Any]:
    nd = "QUY ĐỊNH MẪU\nKhách hàng thanh toán trong 30 ngày kể từ ngày nhận hàng.\n"
    return {"files": {"file": ("quy_dinh.txt", nd.encode("utf-8"), "text/plain")},
            "data": {"workspace_id": "khach-mau"}}


async def _sau_thao_tac(ac) -> list:
    """Sáu đường chạm KB, phát cùng lúc: bốn endpoint /knowledge và hai nhánh của /chat RETRIEVAL."""
    cau_hoi_luat = "nghị định 72 quy định thuế suất bao nhiêu"
    return await asyncio.gather(
        ac.post("/knowledge/documents", headers=AI, **_yeu_cau_tai_lieu()),
        ac.get("/knowledge/documents", headers=AI, params={"workspace_id": "khach-mau"}),
        ac.delete("/knowledge/documents", headers=AI, params={"workspace_id": "khach-mau", "source": "a.txt"}),
        ac.post("/knowledge/search", headers=AI, json={"workspace_id": "khach-mau", "query": "giá cước"}),
        ac.post("/chat", headers=AI, json={"user_id": 1, "store_id": 1, "message": cau_hoi_luat}),
    )


# ---------------------------------------------------------------------------
# Hàm chạy chung
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chay_tren_kho_giu_nguyen_ket_qua_ngoai_le_va_chay_tren_mot_thread():
    ids: set[int] = set()

    def ghi(x, *, mu=1):
        ids.add(threading.get_ident())
        return x ** mu

    assert await chay_tren_kho(ghi, 3, mu=2) == 9
    assert await chay_tren_kho(ghi, 4) == 4
    assert len(ids) == 1 and threading.get_ident() not in ids

    def no(_):
        raise KeyError("k")

    with pytest.raises(KeyError):
        await chay_tren_kho(no, 1)


@pytest.mark.asyncio
async def test_pool_mac_dinh_KHONG_du_vi_chay_song_song():
    """Bằng chứng cho lý do `chay_tren_kho` tồn tại: `to_thread` đạt điều 1 mà phá điều 2."""
    dang, toi_da, khoa = 0, 0, threading.Lock()

    def viec():
        nonlocal dang, toi_da
        with khoa:
            dang += 1
            toi_da = max(toi_da, dang)
        time.sleep(0.1)
        with khoa:
            dang -= 1

    await asyncio.gather(*(chay_ngoai_loop(viec) for _ in range(4)))
    assert toi_da > 1, "đầu dò không phân biệt được song song với tuần tự: các ca dưới sẽ xanh suông"

    dang, toi_da = 0, 0
    await asyncio.gather(*(chay_tren_kho(viec) for _ in range(4)))
    assert toi_da == 1


# ---------------------------------------------------------------------------
# Điều 1: không chặn loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tim_kiem_kho_khong_dong_bang_loop(moi_truong, kho):  # noqa: F811
    async with _may_khach() as ac:
        body = {"workspace_id": "khach-mau", "query": "giá cước"}
        assert (await ac.post("/knowledge/search", headers=AI, json=body)).status_code == 200   # nạp trước
        kho.thread_ids.clear()

        kho.tre = TRE_CHAN
        resp, khoang = await _do_khoang_tre_lon_nhat(
            lambda: ac.post("/knowledge/search", headers=AI, json=body)
        )
    assert resp.status_code == 200
    assert len(kho.thread_ids) == 1
    assert khoang < NGUONG, f"event loop bị giữ {khoang:.3f}s trong lúc tìm trong kho"
    assert kho.thread_ids[0] != threading.get_ident()


@pytest.mark.asyncio
async def test_chat_retrieval_tim_kho_khong_dong_bang_loop(moi_truong, kho):  # noqa: F811
    moi_truong.category = "RETRIEVAL"
    ai_hoi = {"user_id": 1, "store_id": 1, "message": "chính sách công nợ bên mình thế nào"}   # nội bộ: không tra web
    async with _may_khach() as ac:
        assert (await ac.post("/chat", headers=AI, json=ai_hoi)).status_code == 200
        kho.thread_ids.clear()
        kho.da_goi.clear()

        kho.tre = TRE_CHAN
        resp, khoang = await _do_khoang_tre_lon_nhat(lambda: ac.post("/chat", headers=AI, json=ai_hoi))
        assert resp.status_code == 200
        for _ in range(200):
            kq = (await ac.get(f"/api/v1/task/{resp.json()['task_id']}", headers=AI)).json()
            if kq["status"] != "processing":
                break
            await asyncio.sleep(0.02)
    assert kq["status"] == "completed", kq
    # `search` rỗng rồi kho có phạm vi khác -> thêm lời gọi chẩn đoán `workspaces`: cả hai qua worker.
    assert kho.da_goi == ["search", "workspaces"], kho.da_goi
    assert khoang < NGUONG, f"event loop bị giữ {khoang:.3f}s trong lúc /chat tìm trong kho"
    assert all(t != threading.get_ident() for t in kho.thread_ids)


# ---------------------------------------------------------------------------
# Điều 2: không song song, trên đúng một thread
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sau_duong_cham_kho_khong_bao_gio_chay_cung_luc(moi_truong, kho):  # noqa: F811
    moi_truong.category = "RETRIEVAL"
    kho.tre = 0.1
    async with _may_khach() as ac:
        ket_qua = await _sau_thao_tac(ac)
        for r in ket_qua:
            assert r.status_code in (200, 404), r.text   # 404 của DELETE là hợp lệ, không phải lỗi
        # `/chat` trả task_id ngay; chờ nó xong để các lời gọi KB của nó cũng đã chạy.
        tid = ket_qua[-1].json()["task_id"]
        for _ in range(300):
            if (await ac.get(f"/api/v1/task/{tid}", headers=AI)).json()["status"] != "processing":
                break
            await asyncio.sleep(0.02)

    assert {"search", "add_document", "list_documents", "delete_document"} <= set(kho.da_goi), kho.da_goi
    assert kho.dong_thoi_toi_da == 1, (
        f"{kho.dong_thoi_toi_da} thao tác KnowledgeBase chạy CÙNG LÚC: nạp lại tài liệu có thể "
        "xen vào giữa một lần tìm và để lại đoạn giá cũ cạnh bản mới"
    )
    assert len(set(kho.thread_ids)) == 1, "các thao tác kho chạy trên nhiều thread"
    assert threading.get_ident() not in kho.thread_ids
