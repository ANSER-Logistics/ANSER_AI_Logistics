"""
tests/test_task_registry_redis.py — TASK_REGISTRY dùng chung giữa các worker (#15).

Câu cần chứng minh không phải "đọc lại được thứ vừa ghi": một tiến trình đọc
lại thứ chính nó ghi thì RAM cũng làm được. Câu cần chứng minh là HAI TIẾN
TRÌNH KHÁC NHAU thấy cùng một task_id — đúng tình huống worker A nhận POST /chat
còn worker B nhận lượt hỏi kết quả.

Test hai tiến trình cần Redis THẬT, đọc từ `REDIS_TEST_URL` (CI dựng sẵn một
dịch vụ redis:7). Không có thì test BỎ QUA kèm lý do in ra, không xanh giả.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import subprocess
import sys
import uuid

import pytest

from src.core import engine as eng

GOC = pathlib.Path(__file__).resolve().parent.parent
URL = os.getenv("REDIS_TEST_URL", "").strip()
can_redis = pytest.mark.skipif(
    not URL, reason="cần Redis thật: đặt REDIS_TEST_URL (CI có sẵn dịch vụ redis:7)")


def test_khong_co_redis_url_thi_dung_RAM(monkeypatch):
    """ENV=LOCAL không có hạ tầng nào vẫn chạy (AGENTS §3.1)."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    r = eng.tao_task_registry()
    assert isinstance(r, eng.TaskRegistry)
    assert r.mo_ta() == {"backend": "ram", "redis_loi": False}


def test_bo_test_chay_voi_RAM():
    """conftest gỡ REDIS_URL trước khi import src — máy dev có đặt cũng không lẫn vào."""
    assert isinstance(eng.TASK_REGISTRY, eng.TaskRegistry)


def test_redis_khong_toi_duoc_thi_lui_ve_RAM_va_bao_loi(caplog):
    """Redis chết không được làm sập /chat, và không được nuốt lỗi im lặng."""
    pytest.importorskip("redis", reason="cần gói `redis` (requirements.txt)")
    r = eng.RedisTaskRegistry("redis://127.0.0.1:1/0")       # cổng 1: không ai nghe
    with caplog.at_level(logging.ERROR, logger="projecta.engine"):
        r.set("t1", {"status": "processing", "_owner": "u1"})
        r.set("t1", {"status": "completed", "result": {"answer": "x"}})
        doc = r.get("t1")
    assert doc["status"] == "completed" and doc["_owner"] == "u1", "_owner mang theo cả ở RAM"
    assert r.mo_ta()["redis_loi"] is True, "/health phải thấy được"
    assert any("lùi về RAM" in m for m in caplog.messages), "không được lỗi im lặng"


_GHI = """
import sys
from src.core.engine import RedisTaskRegistry
r = RedisTaskRegistry(sys.argv[1])
r.set(sys.argv[2], {"status": "processing", "_owner": "user-42"})
"""

_DOC = """
import json, sys
from src.core.engine import RedisTaskRegistry
print(json.dumps(RedisTaskRegistry(sys.argv[1]).get(sys.argv[2])))
"""


def _chay(ma: str, *doi_so: str) -> str:
    kq = subprocess.run(
        [sys.executable, "-c", ma, URL, *doi_so], cwd=GOC, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(GOC), "ENV": "LOCAL"}, timeout=60,
    )
    assert kq.returncode == 0, kq.stderr[-2000:]
    return kq.stdout


@can_redis
def test_hai_tien_trinh_thay_cung_task_id():
    """Tiến trình A ghi (như worker nhận POST /chat), tiến trình B đọc (như
    worker nhận lượt hỏi kết quả). Với RAM, B trả None — đúng lỗi 'Task not found'."""
    task_id = f"test-{uuid.uuid4()}"
    _chay(_GHI, task_id)

    # Tiến trình hiện tại (thứ ba) ghi tiếp chặng `completed` mà KHÔNG mang `_owner`,
    # đúng như background_worker làm.
    ba = eng.RedisTaskRegistry(URL)
    ba.set(task_id, {"status": "completed", "result": {"answer": "xong"}})

    doc = json.loads(_chay(_DOC, task_id))
    assert doc["status"] == "completed"
    assert doc["result"] == {"answer": "xong"}
    assert doc["_owner"] == "user-42", "kiểm quyền đọc phải còn sau khi worker khác ghi đè"
    assert ba.mo_ta()["redis_loi"] is False


@can_redis
def test_co_ttl_de_redis_khong_tich_task_mai():
    r = eng.RedisTaskRegistry(URL, ttl_s=120)
    task_id = f"test-{uuid.uuid4()}"
    r.set(task_id, {"status": "processing"})
    ttl = r._r.ttl(eng._KHOA_REDIS + task_id)
    assert 0 < ttl <= 120


@can_redis
def test_thu_khong_json_duoc_thi_bao_loi_khong_bien_thanh_chuoi():
    """`default=str` sẽ lặng lẽ làm hỏng dữ liệu; phải ném lỗi."""
    r = eng.RedisTaskRegistry(URL)
    with pytest.raises(TypeError):
        r.set(f"test-{uuid.uuid4()}", {"status": "completed", "result": object()})
