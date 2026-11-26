"""Fixtures và đối tượng giả cho các test qua /chat."""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


class _KhoGia:
    """
    KB giả nhưng chữ ký `search` COPY TỪ BẢN THẬT.

    Nếu chỉ viết `def search(self, *args, **kwargs)` thì test này vẫn xanh với
    đúng con bug nó sinh ra để bắt. Ràng buộc dưới đây khoá điều đó lại.
    """

    def __init__(self, passages=None):
        self.passages = passages or []
        self.calls = []

    def search(self, workspace_id: str, query: str, top_k: int = 3, **kw):
        self.calls.append({"workspace_id": workspace_id, "query": query, "top_k": top_k})
        return self.passages

    def workspaces(self):
        return []


class _ManagerGia:
    def __init__(self, category="RETRIEVAL", answer="Trả lời từ tài liệu."):
        self.category = category
        self.answer = answer
        self.contexts = []
        self.decisions = []

    async def analyze_task(self, text):
        return {"category": self.category, "score": 1.0, "margin": 1.0,
                "method": "test"}

    async def answer_retrieval(self, task, context="", history=None):
        self.contexts.append(context)
        return self.answer

    async def answer_general(self, task, history=None):
        return self.answer

    async def answer_data(self, task, context="", history=None):
        self.contexts.append(context)
        return self.answer

    async def generate_chat(self, system, user, **kwargs):
        """Dùng cho vòng agentic — trả lần lượt các quyết định đã soạn."""
        import json
        return json.dumps(self.decisions.pop(0), ensure_ascii=False)


@pytest.fixture
def moi_truong(monkeypatch):
    """Dựng runtime tối thiểu để `/chat` chạy được mà không cần GPU."""
    from src.api import dependencies as deps
    from src.core.engine import ModelEngine

    async def khong_lam_gi():
        return None

    manager = _ManagerGia()
    monkeypatch.setattr(deps.runtime, "ensure_text_runtime", khong_lam_gi)
    monkeypatch.setattr(deps.runtime, "manager", manager, raising=False)
    monkeypatch.setattr(deps.runtime, "coder", object(), raising=False)
    monkeypatch.setattr(deps.runtime, "memory", None, raising=False)
    # `background_worker` là hàm thuần điều phối, không đụng GPU — mượn bản thật
    # để test đi qua đúng đường mà production đi.
    monkeypatch.setattr(
        deps.runtime, "engine",
        ModelEngine.__new__(ModelEngine), raising=False,
    )
    return manager


def _hoi(cau: str) -> str:
    """Gửi một câu vào /chat rồi lấy câu trả lời cuối."""
    # `X-User-Id` ở cả hai lượt: từ 15/08/2026 chỉ chủ của task đọc được kết
    # quả, vì kết quả là câu trả lời đầy đủ của AI. Body gửi header này sẵn.
    ai = {"X-User-Id": "1", "X-Store-Id": "1"}
    resp = client.post("/chat", headers=ai, json={"user_id": 1, "store_id": 1, "message": cau})
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]
    ket_qua = client.get(f"/api/v1/task/{task_id}", headers=ai).json()
    assert ket_qua["status"] == "completed", ket_qua
    return ket_qua["result"]["answer"]


class _SaasGia:
    def __init__(self):
        self.periods = []

    def lookup_product(self, query, workspace_id=1):
        return "[]"

    def get_sales_report(self, workspace_id=1, period="today"):
        self.periods.append(period)
        return {"period": period, "revenue": "20.000.000 VND", "orders": 2}
