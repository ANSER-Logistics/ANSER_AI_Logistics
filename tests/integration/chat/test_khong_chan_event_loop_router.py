"""
tests/integration/chat/test_khong_chan_event_loop_router.py — phân loại câu hỏi không được chặn event loop (AGENTS §4.1 quy tắc 2).

Đo của Thành (#85, 16/11/2026): `route_with_score` gọi `encode` ngay trên event loop. Khi kho tri thức bận,
trễ router p95 là 230 đến 277 ms và trong khoảng đó `/health` cùng mọi request khác phải chờ. Chủ dự án chọn
hướng "đẩy sang kho": câu cần embedding chạy trên worker duy nhất của kho (cùng embedder dùng chung), câu chỉ cần
từ khoá chạy thẳng trên loop (regex, vài micro giây).

Cách đo cùng nếp `test_khong_chan_event_loop.py`: nhịp tim 10 ms chạy song song, embedder giả `encode` ngủ 0,3 s.
Ngoài ra khoá HAI điều mà chỉ đo độ trễ không thấy:
  - hai lời gọi `encode` KHÔNG bao giờ chồng nhau khi embedder dùng chung với kho (đây mới là điều BR-27 lo);
  - câu từ khoá không phải xếp hàng sau việc của kho.
"""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from src.agents.manager import ManagerAgent, SemanticRouter
from src.api.chay_ngoai_loop import chay_tren_kho
from src.api.routes import chat as chat_mod
from tests.integration.chat.test_khong_chan_event_loop import (
    NGUONG,
    TRE_CHAN,
    _do_khoang_tre_lon_nhat,
)

CAU_KHONG_TU_KHOA = "tư vấn giúp mình một việc hơi lạ về cách làm ăn"      # không khớp luật từ khoá nào
CAU_TU_KHOA = "báo giá xe 5 tấn Hà Nội đi Hải Phòng"                        # khớp luật từ khoá (LOGISTICS)


class _EmbedderGia:
    """encode ngủ `TRE_CHAN` giây, ghi lại thread đã gọi và có hai lời gọi nào chồng nhau không."""

    def __init__(self):
        self.ngu = False            # chỉ ngủ sau khi dựng router (router tự gọi encode lúc khởi tạo để nhúng câu mẫu)
        self.threads: list[str] = []
        self.dang_chay = 0
        self.chong_nhau = False
        self._khoa = threading.Lock()

    def encode(self, texts, *a, **k):
        with self._khoa:
            self.dang_chay += 1
            if self.dang_chay > 1:
                self.chong_nhau = True
        self.threads.append(threading.current_thread().name)
        if self.ngu:
            time.sleep(TRE_CHAN)
        with self._khoa:
            self.dang_chay -= 1
        return np.ones((len(texts), 4), dtype="float32")


def _manager(embedder, *, chung_voi_kho: bool) -> ManagerAgent:
    kb = SimpleNamespace(loaded_embedder=lambda: embedder if chung_voi_kho else object())
    m = ManagerAgent.__new__(ManagerAgent)
    m.kb = kb
    m.router = SemanticRouter(embedder=embedder, tu_nap_embedder=False)
    if embedder is not None:
        embedder.threads.clear()    # bỏ các lời gọi encode lúc khởi tạo router
        embedder.chong_nhau = False
        embedder.ngu = True
    return m


# ---------------------------------------------------------------------------
# cach_chay: chọn đúng chỗ chạy
# ---------------------------------------------------------------------------

def test_cach_chay_cau_tu_khoa_chay_ngay():
    m = _manager(_EmbedderGia(), chung_voi_kho=True)
    assert m.cach_chay(CAU_TU_KHOA) == "ngay"


def test_cach_chay_khong_co_embedder_thi_chay_ngay():
    m = _manager(None, chung_voi_kho=False)
    assert m.cach_chay(CAU_KHONG_TU_KHOA) == "ngay"


def test_cach_chay_embedder_dung_chung_voi_kho():
    m = _manager(_EmbedderGia(), chung_voi_kho=True)
    assert m.cach_chay(CAU_KHONG_TU_KHOA) == "kho"


def test_cach_chay_embedder_rieng_cua_router():
    m = _manager(_EmbedderGia(), chung_voi_kho=False)
    assert m.cach_chay(CAU_KHONG_TU_KHOA) == "ngoai_loop"


def test_phan_loai_dong_bo_cho_cung_ket_qua_voi_analyze_task():
    m = _manager(None, chung_voi_kho=False)
    ket_qua = asyncio.run(m.analyze_task(CAU_TU_KHOA))
    assert ket_qua == m.phan_loai(CAU_TU_KHOA) and ket_qua["category"] == "LOGISTICS"


# ---------------------------------------------------------------------------
# Đường chạy thật trong chat.py: không chặn loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cau_can_embedding_khong_dong_bang_loop_va_chay_tren_worker_cua_kho():
    emb = _EmbedderGia()
    m = _manager(emb, chung_voi_kho=True)
    kq, tre = await _do_khoang_tre_lon_nhat(lambda: chat_mod._phan_loai(m, CAU_KHONG_TU_KHOA))
    assert kq["category"] and tre < NGUONG, f"loop đứng {tre:.3f}s"
    assert emb.threads and all(t.startswith("kho-tri-thuc") for t in emb.threads), emb.threads


@pytest.mark.asyncio
async def test_embedder_rieng_chay_ngoai_loop_khong_chan_loop():
    emb = _EmbedderGia()
    m = _manager(emb, chung_voi_kho=False)
    _, tre = await _do_khoang_tre_lon_nhat(lambda: chat_mod._phan_loai(m, CAU_KHONG_TU_KHOA))
    assert tre < NGUONG
    assert emb.threads and not any(t.startswith("kho-tri-thuc") for t in emb.threads)


@pytest.mark.asyncio
async def test_hai_loi_goi_encode_khong_bao_gio_chong_nhau_khi_dung_chung_voi_kho():
    """Điều BR-27 lo: router và kho gọi cùng một embedder cùng lúc. Một việc của kho đang chạy + hai câu cần embedding."""
    emb = _EmbedderGia()
    m = _manager(emb, chung_voi_kho=True)
    viec_kho = chay_tren_kho(emb.encode, ["thao tác của kho"])
    await asyncio.gather(
        viec_kho,
        chat_mod._phan_loai(m, CAU_KHONG_TU_KHOA),
        chat_mod._phan_loai(m, CAU_KHONG_TU_KHOA),
    )
    assert emb.chong_nhau is False, "hai lời gọi encode chồng nhau: embedder dùng chung bị gọi song song"


@pytest.mark.asyncio
async def test_cau_tu_khoa_khong_phai_xep_hang_sau_viec_cua_kho():
    emb = _EmbedderGia()
    m = _manager(emb, chung_voi_kho=True)
    viec_kho = asyncio.create_task(chay_tren_kho(emb.encode, ["kho đang bận 0,3 giây"]))
    await asyncio.sleep(0.02)                       # để worker của kho bắt đầu việc
    bat_dau = time.perf_counter()
    kq = await chat_mod._phan_loai(m, CAU_TU_KHOA)
    mat = time.perf_counter() - bat_dau
    await viec_kho
    assert kq["category"] == "LOGISTICS"
    assert mat < TRE_CHAN / 3, f"câu từ khoá chờ {mat:.3f}s: đã xếp hàng sau việc của kho"


@pytest.mark.asyncio
async def test_manager_gia_khong_co_phan_loai_van_di_duong_cu():
    class Gia:
        async def analyze_task(self, msg):
            return {"category": "GENERAL", "score": 0.0, "margin": 0.0, "method": "gia"}

    assert (await chat_mod._phan_loai(Gia(), "xin chào"))["method"] == "gia"


@pytest.mark.asyncio
async def test_dau_do_bat_duoc_duong_cu_goi_analyze_task_thang_tren_loop():
    """Chứng minh đầu dò không câm: đường CŨ (gọi thẳng trên loop) làm loop đứng đúng bằng thời gian encode."""
    m = _manager(_EmbedderGia(), chung_voi_kho=True)
    _, tre = await _do_khoang_tre_lon_nhat(lambda: m.analyze_task(CAU_KHONG_TU_KHOA))
    assert tre > NGUONG, f"đầu dò không thấy việc chặn loop (trễ {tre:.3f}s)"
