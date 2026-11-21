"""
tests/test_nhan_tro_ly_ai.py — mọi câu trả lời của `/chat` mang nhãn "trợ lý AI, kết quả tham khảo" do MÃ gắn (#209).

Nhãn đi theo hai đường mà Body nhận được kết quả: đọc trạng thái task (`GET /api/v1/task/{id}`) và webhook gọi về Body.
Model không sinh nhãn nên không bỏ sót hay sửa chữ được.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import app
from src.core.config import AI_NOTICE
from tests.test_chat_routing import moi_truong  # noqa: F401  (fixture dựng runtime tối thiểu)

client = TestClient(app)
AI = {"X-User-Id": "1", "X-Store-Id": "1"}


def test_nhan_co_chu_ai():
    assert "AI" in AI_NOTICE


def test_task_hoan_thanh_co_nhan(moi_truong):  # noqa: F811
    r = client.post("/chat", headers=AI, json={"user_id": 1, "store_id": 1, "message": "xin chào"})
    ket_qua = client.get(f"/api/v1/task/{r.json()['task_id']}", headers=AI).json()
    assert ket_qua["status"] == "completed"
    assert ket_qua["ai_notice"] == AI_NOTICE


def test_task_chua_xong_khong_gan_nhan_vao_ket_qua_rong():
    from src.core.engine import TASK_REGISTRY
    TASK_REGISTRY.set("t-nhan-1", {"status": "running", "_owner": "1"})
    ket_qua = client.get("/api/v1/task/t-nhan-1", headers=AI).json()
    assert ket_qua["status"] == "running" and "ai_notice" not in ket_qua


def test_webhook_ve_body_co_nhan(moi_truong, monkeypatch):  # noqa: F811
    import src.api.routes.chat as chat_mod
    da_gui: list[dict] = []

    async def gui_gia(client_, url, payload, headers, task_id):
        da_gui.append(payload)
        return True

    monkeypatch.setenv("BODY_CALLBACK_URL", "http://body.invalid/cb")
    monkeypatch.setattr(chat_mod, "_gui_webhook", gui_gia)
    r = client.post("/chat", headers=AI, json={"user_id": 1, "store_id": 1, "message": "xin chào"})
    assert r.status_code == 200
    client.get(f"/api/v1/task/{r.json()['task_id']}", headers=AI)
    assert da_gui and da_gui[0]["ai_notice"] == AI_NOTICE
