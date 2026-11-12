"""
tests/test_tool_noi_bo.py — tool chạy NỘI BỘ phải chạy được khi cổng token BẬT.

Lỗi này nằm ngoài tầm của mọi bộ test trước nó, vì cả 1377 test chạy với
`API_AUTH_TOKEN` rỗng — đúng cấu hình duy nhất mà lỗi KHÔNG xảy ra.

`run_tool` gọi handler của endpoint với `x_api_token=None`, mà mỗi handler lại
gọi `require_api_token`. Đặt `API_AUTH_TOKEN` (compose bắt buộc đặt) thì mọi tool
agentic và mọi lời gọi /mcp/tools/call trả `{"error": "Unauthorized"}`. Vòng
agentic không coi đó là sự cố: nó đưa observation lỗi cho model, model viết câu
trả lời từ một khối lỗi, và `observations` chỉ nhận kết quả của tool chạy được —
nên chốt neo số liệu không có gì để đối chiếu.

Hai nửa của hợp đồng phải cùng đúng:
  - đã qua cổng thì tool CHẠY ĐƯỢC;
  - chưa qua cổng thì /mcp VẪN bị chặn (sửa nửa trên không được mở toang nửa dưới).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import src.api.dependencies as deps
import src.api.main as main_mod
from src.agents.agentic import AgenticLoop
from src.api.main import app
from src.api.routes.tools import run_tool

TOKEN = "token-thu-noi-bo"

_QUOTE_ARGS = {
    "carrier_cost": 12_500_000,
    "pricing_rule": {"base_margin_pct": 8},
}


@pytest.fixture
def bat_xac_thuc(monkeypatch):
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(main_mod, "API_AUTH_TOKEN", TOKEN)


@pytest.mark.asyncio
async def test_run_tool_chay_duoc_khi_token_bat(bat_xac_thuc):
    out = await run_tool("quote", _QUOTE_ARGS)
    assert "error" not in out, (
        f"tool nội bộ bị chặn khi cổng token bật: {out}. "
        f"`run_tool` phải đưa token cấu hình xuống handler."
    )
    # 12.500.000 * 1,08 = 13.500.000 — con số do code tính, không phải model.
    assert out["quote"]["quoted_price"] == 13_500_000


@pytest.mark.asyncio
async def test_run_tool_van_chay_khi_khong_co_token(monkeypatch):
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", "")
    out = await run_tool("quote", _QUOTE_ARGS)
    assert out["quote"]["quoted_price"] == 13_500_000


def test_mcp_tools_call_chay_duoc_voi_token_dung(bat_xac_thuc):
    resp = TestClient(app).post(
        "/mcp/tools/call",
        json={"name": "quote", "arguments": _QUOTE_ARGS},
        headers={"X-API-Token": TOKEN},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["isError"] is False, body
    assert json.loads(body["content"][0]["text"])["quote"]["quoted_price"] == 13_500_000


def test_mcp_tools_call_van_bi_chan_khi_khong_co_token(bat_xac_thuc):
    """Nửa dưới của hợp đồng: sửa `run_tool` không được mở cổng ngoài."""
    resp = TestClient(app).post(
        "/mcp/tools/call", json={"name": "quote", "arguments": _QUOTE_ARGS}
    )
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# Vòng agentic: còn kế hoạch thì KHÔNG nhận câu kết luận
# --------------------------------------------------------------------------

_TOOLS = [{
    "name": "vat", "description": "tính VAT",
    "input_schema": {"properties": {"items": {}, "stated_total": {}},
                     "required": ["items", "stated_total"]},
}]


class _Manager:
    """Backend KHÔNG thực thi grammar: trả đúng thứ ta dặn, bất kể lược đồ."""

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0

    async def generate_chat(self, system, user, **kwargs):
        self.calls += 1
        # Hết kịch bản thì lặp lại quyết định cuối — mô phỏng model cứ kết luận.
        d = self.decisions.pop(0) if len(self.decisions) > 1 else self.decisions[0]
        return json.dumps(d, ensure_ascii=False)


@pytest.mark.asyncio
async def test_ket_luan_som_khong_duoc_nhan_khi_con_ke_hoach():
    chay = []

    def runner(name, args):
        chay.append(name)
        return {"is_valid": False, "difference": 1_000_000}

    manager = _Manager([
        {"thought": "tự cộng", "answer": "Hoá đơn đúng, không lệch."},   # bị từ chối
        {"thought": "gọi tool", "tool": "vat",
         "arguments": {"items": [], "stated_total": 6_500_000}},
        {"thought": "xong", "answer": "Hoá đơn lệch 1.000.000đ."},
    ])

    out = await AgenticLoop(
        manager, _TOOLS, runner, planner=lambda q, n: ["vat"], max_steps=4,
    ).run("Kiểm tra hoá đơn tổng ghi 6.500.000đ")

    assert chay == ["vat"], "tool PHẢI chạy trước khi có câu kết luận"
    assert out["answer"] == "Hoá đơn lệch 1.000.000đ."
    assert "Hoá đơn đúng" not in out["answer"]
    assert any("error" in s for s in out["steps"]), "bước bị từ chối phải để lại dấu vết"


@pytest.mark.asyncio
async def test_model_cu_ket_luan_thi_cham_tran_va_khong_bia_ket_qua():
    manager = _Manager([{"thought": "tự cộng", "answer": "Hoá đơn đúng."}])

    out = await AgenticLoop(
        manager, _TOOLS, lambda n, a: {"x": 1}, planner=lambda q, n: ["vat"], max_steps=3,
    ).run("Kiểm tra hoá đơn")

    assert out["hit_limit"] is True
    assert "Hoá đơn đúng" not in out["answer"]
    assert out["tool_calls"] == 0
    assert manager.calls == 3


@pytest.mark.asyncio
async def test_hoi_lai_van_duoc_khi_con_ke_hoach():
    """Hỏi lại là lối thoát hợp lệ — backstop không được chặn nó."""
    manager = _Manager([{"thought": "thiếu số", "hoi_lai": "Tổng ghi trên hoá đơn là bao nhiêu?"}])

    out = await AgenticLoop(
        manager, _TOOLS, lambda n, a: {}, planner=lambda q, n: ["vat"],
    ).run("Kiểm tra hoá đơn")

    assert out["data_missing"] is True
    assert out["answer"].startswith("Tổng ghi")


# --------------------------------------------------------------------------
# Review độc lập 12/11/2026: lời nhắc không được làm mất câu hỏi gốc
# --------------------------------------------------------------------------

class _GhiLoiGoi:
    """Ghi lại (user, history) của từng lần gọi model, và trả kịch bản có sẵn."""

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls: list[tuple[str, list]] = []

    async def generate_chat(self, system, user, **kwargs):
        self.calls.append((user, list(kwargs.get("history") or [])))
        d = self.decisions.pop(0) if len(self.decisions) > 1 else self.decisions[0]
        return json.dumps(d, ensure_ascii=False)


@pytest.mark.asyncio
async def test_tu_choi_ket_luan_som_van_giu_cau_hoi_goc_cua_khach():
    """Bản đầu gán đè `user_turn`: lần gọi sau chỉ thấy câu nhắc, không còn câu hỏi."""
    manager = _GhiLoiGoi([
        {"thought": "tự tính", "answer": "Giá là 123"},                         # bị từ chối
        {"thought": "gọi tool", "tool": "vat", "arguments": {"items": [], "stated_total": 1}},
        {"thought": "xong", "answer": "Lệch 1đ."},
    ])
    await AgenticLoop(manager, _TOOLS, lambda n, a: {"is_valid": False},
                      planner=lambda q, n: ["vat"], max_steps=4).run("Báo giá HN-HCM 10 tấn")

    user2, _ = manager.calls[1]
    assert "Báo giá HN-HCM 10 tấn" in user2, f"lần gọi sau mất câu hỏi gốc: {user2!r}"
    assert "Phải gọi tool 'vat'" in user2


@pytest.mark.asyncio
async def test_tu_choi_o_buoc_sau_van_giu_ket_qua_tool_truoc_do():
    """Bị từ chối ở bước 2 thì `user_turn` là KẾT QUẢ TOOL của bước 1 — cũng không được mất."""
    manager = _GhiLoiGoi([
        {"thought": "gọi 1", "tool": "vat", "arguments": {"items": [], "stated_total": 1}},
        {"thought": "tự kết luận", "answer": "Xong"},                          # còn 'report' -> từ chối
        {"thought": "gọi 2", "tool": "report", "arguments": {"sales": []}},
        {"thought": "xong", "answer": "Hết"},
    ])
    await AgenticLoop(manager, [*_TOOLS, {"name": "report", "description": "r",
                                          "input_schema": {"properties": {"sales": {}}, "required": ["sales"]}}],
                      lambda n, a: {"ket_qua": n}, planner=lambda q, n: ["vat", "report"],
                      max_steps=6).run("hỏi hai việc")

    user3, hist3 = manager.calls[2]
    assert "KẾT QUẢ TOOL vat" in user3, f"mất kết quả tool trước đó: {user3!r}"
    assert "Phải gọi tool 'report'" in user3
