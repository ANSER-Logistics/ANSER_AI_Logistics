"""
tests/test_health_memory_db.py — `/health` phân biệt bốn tình trạng DB (BR-20).

Trước PR này `/health.memory_schema_error` là `null` cho CẢ BỐN hoàn cảnh: đủ bảng, chưa đặt
`DATABASE_URL`, và kết nối hỏng lúc kiểm lược đồ (cộng với "chưa nạp"). Người đọc `null` hiểu là khoẻ.
Trường mới `memory_db` tách chúng ra; `degraded` KHÔNG đổi (chỉ thêm khoá, Body đọc năm khoá cũ).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import runtime
from src.api.main import app
from src.core.memory import BANG_CAN_CO, MemoryManager


def _mm(db_url: str, *, loi_url=None, engine=object()) -> MemoryManager:
    """Dựng MemoryManager KHÔNG qua `__init__` (không cần driver Postgres trong CI)."""
    m = MemoryManager.__new__(MemoryManager)
    m.config = SimpleNamespace(DB_URL=db_url, DB_URL_LOI=loi_url)
    m.engine = engine
    m._luoc_do_da_kiem = False
    m._luoc_do_loi = None
    m._trang_thai_db = "unverified"
    return m


PG = "postgresql+psycopg2://u:p@h/db"


def test_khong_dat_database_url_thi_la_chua_cau_hinh_khong_phai_khoe():
    m = _mm("sqlite:///:memory:")
    assert m.kiem_luoc_do() is None, "hành vi cũ giữ nguyên: không báo lỗi lược đồ"
    assert m.trang_thai_db == "not_configured"


def test_url_sai_la_error():
    m = _mm("sqlite:///:memory:", loi_url="DATABASE_URL có scheme không nhận ra")
    assert m.trang_thai_db == "error" and m.kiem_luoc_do()


def test_khong_dung_duoc_engine_la_error():
    assert _mm(PG, engine=None).trang_thai_db == "error"


def _gia_lap_inspect(monkeypatch, *, co_bang=None, ne=None):
    class Insp:
        def has_table(self, ten):
            if ne:
                raise ne
            return co_bang(ten)

    monkeypatch.setattr("sqlalchemy.inspect", lambda engine: Insp())


def test_du_bang_tren_db_that_la_ok(monkeypatch):
    _gia_lap_inspect(monkeypatch, co_bang=lambda t: True)
    m = _mm(PG)
    assert m.kiem_luoc_do() is None and m.trang_thai_db == "ok"


def test_thieu_bang_la_error_va_van_co_memory_schema_error(monkeypatch):
    _gia_lap_inspect(monkeypatch, co_bang=lambda t: t != BANG_CAN_CO[0])
    m = _mm(PG)
    assert m.kiem_luoc_do() and m.trang_thai_db == "error"


def test_ket_noi_hong_luc_kiem_la_unverified_khong_phai_ok(monkeypatch, caplog):
    """Bản cũ trả None (nghe như khoẻ). Không kiểm được thì KHÔNG biết: nói là chưa kiểm."""
    caplog.set_level(logging.WARNING)
    _gia_lap_inspect(monkeypatch, ne=RuntimeError("không nối được"))
    m = _mm(PG)
    assert m.kiem_luoc_do() is None, "không kéo degraded lên: giữ hành vi cũ, không báo oan"
    assert m.trang_thai_db == "unverified"


def test_trang_thai_db_tu_goi_kiem_luoc_do():
    """Người gọi quên gọi `kiem_luoc_do()` trước thì vẫn ra đúng, không mắc kẹt ở giá trị khởi tạo."""
    m = _mm("sqlite:///:memory:")
    assert m._trang_thai_db == "unverified"
    assert m.trang_thai_db == "not_configured"


# ---------------------------------------------------------------------------
# Đường HTTP
# ---------------------------------------------------------------------------

client = TestClient(app)


@pytest.fixture
def memory(monkeypatch):
    def dat(mm):
        monkeypatch.setattr(runtime, "memory", mm, raising=False)
    return dat


def test_health_chua_nap_memory_thi_not_loaded(monkeypatch):
    monkeypatch.setattr(runtime, "memory", None, raising=False)
    j = client.get("/health").json()
    assert j["memory_db"] == "not_loaded"


def test_health_chua_cau_hinh_db_khong_keo_degraded_len(memory):
    memory(_mm("sqlite:///:memory:"))
    j = client.get("/health").json()
    assert j["memory_db"] == "not_configured"
    assert j["memory_schema_error"] is None
    assert j["degraded"] is False, "dev không DB là chủ ý; production theo hướng 'Body gửi history' cũng vậy"


def test_health_thieu_bang_keo_degraded_va_memory_db_error(memory, monkeypatch):
    _gia_lap_inspect(monkeypatch, co_bang=lambda t: False)
    memory(_mm(PG))
    j = client.get("/health").json()
    assert j["memory_db"] == "error" and j["memory_schema_error"] and j["degraded"] is True


def test_health_nam_khoa_cu_ma_body_doc_van_con():
    j = client.get("/health").json()
    for k in ("status", "degraded", "engine_ready", "vision_ready", "load"):
        assert k in j, f"khoá Body đọc đã mất: {k}"
