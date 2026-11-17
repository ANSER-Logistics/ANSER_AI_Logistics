"""
Kiểm LOGIC của `offline_training/do_router_dung_chung_embedder.py` (#85) bằng embedder giả.

Phép đo thật cần GPU và embedder thật, nên chạy trên Colab. Ở đây chỉ chứng minh rằng script
nhận ra được đúng thứ nó sinh ra để tìm: nếu embedder hỏng khi hai thread `encode` cùng lúc thì
script phải báo CÓ VẤN ĐỀ, không được in "không thấy vấn đề". Một phép đo không bắt được lỗi
mình đang tìm thì kết luận "an toàn" của nó vô nghĩa.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import threading
import time

import numpy as np
import pytest

import src.core.knowledge as knowledge
from offline_training import do_router_dung_chung_embedder as do85
from tests.test_knowledge import FakeCollection, FakeReranker


class EmbedderGia:
    """Vector tất định theo nội dung; ngủ một chút để worker và router thật sự chạy chồng."""

    def __init__(self, ngu_s: float = 0.002):
        self.ngu_s = ngu_s

    def _vec(self, t: str) -> np.ndarray:
        h = hashlib.sha256(t.encode("utf-8")).digest()
        return np.frombuffer(h[:16], dtype=np.uint8).astype(np.float32) / 255.0

    def encode(self, texts, **kwargs):
        time.sleep(self.ngu_s)
        return np.stack([self._vec(t) for t in texts])


class EmbedderKhongAnToanLuong(EmbedderGia):
    """Bắt chước tokenizer nhanh của HuggingFace: bị gọi chồng thì ném `Already borrowed`."""

    def __init__(self):
        super().__init__(ngu_s=0.003)
        self._dang_dung = threading.Lock()

    def encode(self, texts, **kwargs):
        if not self._dang_dung.acquire(blocking=False):
            raise RuntimeError("Already borrowed")
        try:
            return super().encode(texts, **kwargs)
        finally:
            self._dang_dung.release()


def _tham_so(luot: int = 300, duong: str = "moi") -> argparse.Namespace:
    return argparse.Namespace(luot=luot, device="cpu", so_tai_lieu=2, hang_doi=4, nap_moi=5, out="",
                              duong=duong)


_KHO_GOC = knowledge.KnowledgeBase


def _gan_kho(monkeypatch, embedder) -> None:
    def tao(persist_dir="./data/vector_db", *, device=None, **_):
        return _KHO_GOC(
            persist_dir, embedder=embedder, reranker=FakeReranker(),
            collection=FakeCollection(), device=device,
        )
    monkeypatch.setattr(knowledge, "KnowledgeBase", tao)


@pytest.mark.parametrize("duong", ["moi", "cu"])
def test_embedder_an_toan_thi_khong_thay_van_de(monkeypatch, duong):
    _gan_kho(monkeypatch, EmbedderGia())
    ma, bc = asyncio.run(do85.do(_tham_so(duong=duong)))
    assert bc["duong"] == duong and bc["tre_loop_ms"]["so_nhip"] > 0
    assert bc["dung_chung_embedder"] is True
    assert bc["so_cau_di_toi_embedding"] > 0
    assert bc["luot_router_chay_chong"] >= do85.LUOT_CHONG_TOI_THIEU, bc
    assert bc["ngoai_le"] == {} and bc["router_lech"] == 0 and bc["search_lech"] == 0
    assert ma == 0, bc["ket_luan"]


def test_embedder_khong_an_toan_luong_thi_bat_duoc(monkeypatch):
    # Đường cũ (encode trên loop, chồng với worker): script phải bắt được lỗi nó sinh ra để tìm.
    _gan_kho(monkeypatch, EmbedderKhongAnToanLuong())
    ma, bc = asyncio.run(do85.do(_tham_so(duong="cu")))
    assert ma == 1, bc.get("ket_luan")
    assert any("Already borrowed" in k for k in bc["ngoai_le"]), bc["ngoai_le"]
    assert bc["ket_luan"] == "CÓ VẤN ĐỀ"


def test_duong_moi_khong_de_encode_chong_nhau(monkeypatch):
    # PR #116: câu cần embedding chạy trên worker DUY NHẤT của kho -> cùng embedder không thread-safe
    # mà không lỗi nào. Đây là điều #116 hứa; lỗi lại là ai đó đưa router ra khỏi worker.
    _gan_kho(monkeypatch, EmbedderKhongAnToanLuong())
    ma, bc = asyncio.run(do85.do(_tham_so(duong="moi")))
    assert bc["ngoai_le"] == {}, bc["ngoai_le"]
    assert ma == 0, bc["ket_luan"]


def test_khong_nap_duoc_embedder_thi_ma_2_khong_phai_dat(monkeypatch):
    class KhoHong(knowledge.KnowledgeBase):
        @property
        def embedder(self):
            raise OSError("không tải được model")

    monkeypatch.setattr(knowledge, "KnowledgeBase",
                        lambda d, *, device=None, **_: KhoHong(d, collection=FakeCollection(), device=device))
    ma, bc = asyncio.run(do85.do(_tham_so()))
    assert ma == 2
    assert "không nạp được embedder" in bc["khong_do_duoc"]


@pytest.mark.parametrize("so", [0, 3])
def test_tai_lieu_hu_cau_doi_theo_phien_ban(so):
    assert do85.tai_lieu_hu_cau(so, 0) != do85.tai_lieu_hu_cau(so, 1)
