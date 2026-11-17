"""
tests/test_router_ms_metric.py — đo thời gian phân loại câu hỏi và nơi nó chạy (#85).

VÌ SAO CÓ FILE NÀY
------------------
PR #116 đẩy phần phân loại cần embedding sang worker duy nhất của kho, để event loop không bị chặn. Thành đo
trên GPU thật ngày 17/11: event loop gần như hết bị chặn (p95 từ 230–277 ms xuống 0,3–1,0 ms), nhưng khi kho
bận, câu cần embedding phải chờ: p50 3,5 s, p95 4,6 s với embedder kho trên CPU (mặc định production), cỡ 1 s
trên GPU. Chủ dự án chọn "đẩy sang kho" từ trước; chưa có lưu lượng thật nên chưa biết kho có bận đúng lúc có
người chat không. Quyết định: giữ nguyên, và ghi `router_ms` cùng `router_cach` mỗi lượt để có số đo ngoài đời
mà quyết tiếp (embedder riêng cho router tốn RAM chưa đo; embedder kho trên GPU tranh VRAM với vLLM).
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routes import chat as chat_mod
from src.core import metrics
from tests.test_chat_routing import (  # noqa: F401  (fixture dựng runtime tối thiểu)
    _ManagerGia,
    moi_truong,
)

client = TestClient(app)
AI = {"X-User-Id": "1", "X-Store-Id": "1"}


# ---------------------------------------------------------------------------
# TurnMetric và summarize
# ---------------------------------------------------------------------------

def test_hai_truong_moi_mac_dinh_la_none_khong_phai_khong():
    m = metrics.TurnMetric(request_id="r", route="GENERAL", ok=True, latency_ms=1)
    assert m.router_ms is None and m.router_cach is None
    d = asdict(m)
    assert "router_ms" in d and "router_cach" in d


def _ghi_jsonl(duong, dong: list[dict]):
    duong.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in dong), encoding="utf-8")


def _dong(**kw):
    return {"request_id": "r", "route": "GENERAL", "ok": True, "latency_ms": 10, **kw}


def test_summarize_gom_theo_noi_chay_va_bo_dong_thieu_so_do(tmp_path):
    p = tmp_path / "m.jsonl"
    _ghi_jsonl(p, [
        _dong(router_ms=1, router_cach="ngay"),
        _dong(router_ms=3, router_cach="ngay"),
        _dong(router_ms=1000, router_cach="kho"),
        _dong(router_ms=3000, router_cach="kho"),
        _dong(router_ms=4600, router_cach="kho"),
        _dong(),                                    # lượt cũ, chưa có trường: KHÔNG được coi là 0
        _dong(router_ms=None, router_cach="kho"),   # có cách mà thiếu số: bỏ
    ])
    ra = metrics.summarize(str(p))["router_ms"]
    assert set(ra) == {"ngay", "kho"}
    assert ra["ngay"]["n"] == 2 and ra["ngay"]["max"] == 3
    assert ra["kho"]["n"] == 3 and ra["kho"]["p50"] == 3000 and ra["kho"]["p95"] == 4600 and ra["kho"]["max"] == 4600


def test_summarize_khong_co_so_do_nao_thi_la_none_khong_phai_rong_hay_khong(tmp_path):
    p = tmp_path / "m.jsonl"
    _ghi_jsonl(p, [_dong(), _dong()])
    assert metrics.summarize(str(p))["router_ms"] is None


def test_summarize_bo_so_am_va_rac(tmp_path):
    p = tmp_path / "m.jsonl"
    _ghi_jsonl(p, [_dong(router_ms=-5, router_cach="kho"), _dong(router_ms="nhanh", router_cach="kho"),
                   _dong(router_ms=7, router_cach="kho")])
    ra = metrics.summarize(str(p))["router_ms"]
    assert ra == {"kho": {"n": 1, "p50": 7.0, "p95": 7.0, "max": 7.0}}


# ---------------------------------------------------------------------------
# Đường chạy thật của /chat
# ---------------------------------------------------------------------------

class _ManagerCoCach(_ManagerGia):
    """Manager có `cach_chay` và `phan_loai` như bản thật, để `_phan_loai` đi đường mới."""

    def __init__(self, cach: str):
        super().__init__(category="GENERAL")
        self._cach = cach

    def cach_chay(self, text):
        return self._cach

    def phan_loai(self, text):
        return {"category": "GENERAL", "score": 1.0, "margin": 1.0, "method": "test"}


@pytest.fixture
def ghi_metric(monkeypatch):
    ds: list = []
    monkeypatch.setattr(metrics, "record", ds.append)
    return ds


def _hoi(cau: str = "xin chào"):
    resp = client.post("/chat", headers=AI, json={"user_id": 1, "store_id": 1, "message": cau})
    assert resp.status_code == 200, resp.text
    ket_qua = client.get(f"/api/v1/task/{resp.json()['task_id']}", headers=AI).json()
    assert ket_qua["status"] == "completed", ket_qua


@pytest.mark.parametrize("cach", ["ngay", "kho", "ngoai_loop"])
def test_chat_ghi_router_ms_va_noi_chay(moi_truong, ghi_metric, monkeypatch, cach):  # noqa: F811
    from src.api import dependencies as deps

    monkeypatch.setattr(deps.runtime, "kb", None, raising=False)
    monkeypatch.setattr(deps.runtime, "manager", _ManagerCoCach(cach), raising=False)
    _hoi()
    assert len(ghi_metric) == 1
    m = ghi_metric[0]
    assert m.router_cach == cach
    assert isinstance(m.router_ms, int) and m.router_ms >= 0


def test_manager_khong_co_cach_chay_thi_noi_chay_la_none_nhung_van_do_thoi_gian(moi_truong, ghi_metric, monkeypatch):  # noqa: F811
    from src.api import dependencies as deps

    monkeypatch.setattr(deps.runtime, "kb", None, raising=False)
    _hoi()                                           # `_ManagerGia` không có `cach_chay` (như đồ giả cũ)
    m = ghi_metric[0]
    assert m.router_cach is None
    assert isinstance(m.router_ms, int) and m.router_ms >= 0


def test_cach_phan_loai_loi_thi_none_khong_lam_hong_nghiep_vu():
    class Hong:
        def cach_chay(self, text):
            raise RuntimeError("hỏng")

    assert chat_mod._cach_phan_loai(Hong(), "x") is None
    assert chat_mod._cach_phan_loai(object(), "x") is None


def test_dau_do_bat_duoc_viec_thieu_do_thoi_gian(moi_truong, ghi_metric, monkeypatch):  # noqa: F811
    """Chứng minh test không câm: nếu `_cach_phan_loai` bị bỏ khỏi đường chạy thì `router_cach` ra None."""
    from src.api import dependencies as deps

    monkeypatch.setattr(deps.runtime, "kb", None, raising=False)
    monkeypatch.setattr(deps.runtime, "manager", _ManagerCoCach("kho"), raising=False)
    monkeypatch.setattr(chat_mod, "_cach_phan_loai", lambda manager, msg: None)
    _hoi()
    assert ghi_metric[0].router_cach is None, "đầu dò phải thấy nơi chạy bị mất"
