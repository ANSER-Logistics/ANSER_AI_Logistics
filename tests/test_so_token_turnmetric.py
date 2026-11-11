"""
tests/test_so_token_turnmetric.py — số token đi TRỌN ĐƯỜNG tới `TurnMetric` (#16).

Phản hồi HTTP của vLLM (server giả trên socket thật) -> `VLLMServerClient` ->
`ModelEngine` -> `ManagerAgent` THẬT -> `/chat` -> `metrics.record(TurnMetric)`.

Không tiêm `KetQuaSinh` ở giữa: test unit của từng tầng đã có ở test_serving.py
và test_engine_backend.py. Ở đây chỉ hỏi một câu — con số mà vLLM ghi trong
`usage.completion_tokens` có tới được nhật ký phục vụ không, hay rơi ở đâu đó
giữa năm tầng. Đó là đúng chỗ nó từng rơi: `serving.py` đọc `content` rồi vứt
`usage` nằm ngay cạnh.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.agents import manager as manager_mod
from src.api import dependencies as deps
from src.api.main import app
from src.core import metrics
from src.core.engine import ModelEngine
from tests.test_engine_backend import _VllmGia

client = TestClient(app)
_AI = {"X-User-Id": "1", "X-Store-Id": "1"}


def _hoi(cau: str) -> str:
    r = client.post("/chat", headers=_AI, json={"user_id": 1, "store_id": 1, "message": cau})
    assert r.status_code == 200
    kq = client.get(f"/api/v1/task/{r.json()['task_id']}", headers=_AI).json()
    assert kq["status"] == "completed", kq
    return kq["result"]["answer"]


@pytest.fixture
def dung_brain(monkeypatch):
    """Dựng Brain với engine THẬT trỏ vào vLLM giả, và bắt mọi `TurnMetric` ghi ra."""
    dung: list[_VllmGia] = []
    ghi: list[metrics.TurnMetric] = []

    def _dung(so_token: int | None) -> list[metrics.TurnMetric]:
        gia = _VllmGia(noi_dung="  Chào bạn, tôi giúp được việc kho vận.  ",
                       so_token=so_token)
        dung.append(gia)
        monkeypatch.setattr(ModelEngine, "_instance", None)
        monkeypatch.setenv("ENV", "LOCAL")
        monkeypatch.setenv("VLLM_BASE_URL", gia.url + "/v1")
        monkeypatch.setenv("VLLM_MODEL", "anser-v3-awq")
        engine = ModelEngine()
        assert engine.text_backend == "server"

        # Router rơi về lớp từ khoá — không kéo embedder 600MB xuống trong test.
        monkeypatch.setattr(manager_mod.SemanticRouter, "_try_load_embedder",
                            staticmethod(lambda name: None))

        async def khong_lam_gi():
            return None

        monkeypatch.setattr(deps.runtime, "ensure_text_runtime", khong_lam_gi)
        monkeypatch.setattr(deps.runtime, "engine", engine, raising=False)
        monkeypatch.setattr(deps.runtime, "manager",
                            manager_mod.ManagerAgent(engine, memory=None), raising=False)
        monkeypatch.setattr(deps.runtime, "coder", object(), raising=False)
        monkeypatch.setattr(deps.runtime, "memory", None, raising=False)
        monkeypatch.setattr(deps.runtime, "kb", None, raising=False)
        monkeypatch.setattr(metrics, "record", ghi.append)
        return ghi

    yield _dung
    for gia in dung:
        gia.dong()
    monkeypatch.setattr(ModelEngine, "_instance", None)


def test_so_token_cua_vllm_toi_duoc_turnmetric(dung_brain):
    ghi = dung_brain(so_token=23)

    tra_loi = _hoi("Xin chào, bạn giúp được gì cho tôi?")

    assert "kho vận" in tra_loi, "câu trả lời phải đi qua model thật của vLLM giả"
    assert len(ghi) == 1
    m = ghi[0]
    assert m.completion_tokens == 23, "con số phải là `usage.completion_tokens`, không đoán"
    assert m.model_calls == 1
    assert m.model_ms is not None and m.model_ms >= 0
    # Không phải suy từ số ký tự: câu trả lời dài ~40 ký tự, không liên quan 23.
    assert m.answer_chars != 23 * 4


def test_server_khong_tra_usage_thi_ghi_khong_biet_khong_ghi_0(dung_brain):
    ghi = dung_brain(so_token=None)

    _hoi("Xin chào, bạn giúp được gì cho tôi?")

    m = ghi[0]
    assert m.model_calls == 1, "model vẫn được gọi"
    assert m.completion_tokens is None, "KHÔNG BIẾT là None — 0 nghĩa là sinh 0 token"
    # Thời gian gọi đo ở phía client nên vẫn biết; chỉ số token là không biết.
    # Tầng dùng (#9) phải bỏ qua lượt này khi tính ms/token.
    assert m.model_ms is not None
