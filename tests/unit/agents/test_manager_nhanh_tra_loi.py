"""
tests/unit/agents/test_manager_nhanh_tra_loi.py — ba nhánh DATA_INTERNAL, REPORT, EXPLAIN của `ManagerAgent` đưa đúng số liệu engine vào prompt.

VÌ SAO CÓ FILE NÀY
------------------
Ba hàm này ghép `context` (khối JSON do engine tất định tính) vào system prompt bằng `str.format`. Trước file này
chưa test nào gọi chúng, nên ba lỗi sau không bị chặn: prompt có dấu `{` lạ làm `.format` ném `KeyError` (cả nhánh
sập), `context` không tới được model (model phải tự đoán số, R1), và context rỗng làm model nhận chuỗi trống thay
vì một câu nói rõ là chưa có số liệu.
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest

from src.agents.manager import ManagerAgent
from src.core.prompts import Prompts


class _EngineGhi:
    def __init__(self):
        self.lan_goi: list[dict] = []

    async def generate_chat(self, system, user, max_tokens, temperature, json_schema=None, history=None):
        self.lan_goi.append({"system": system, "user": user, "temperature": temperature, "history": history})
        return "ok"


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("ENV", "LOCAL")  # router không nạp embedder
    eng = _EngineGhi()
    return ManagerAgent(eng, memory=None), eng


NHANH = [
    ("answer_data", "DATA_SYSTEM", "(chưa có dữ liệu)"),
    ("answer_report", "REPORT_SYSTEM", "(chưa có số liệu)"),
    ("explain_result", "EXPLAIN_SYSTEM", None),  # explain luôn có context: chat.py chỉ gọi khi đã tìm thấy khối engine
]


@pytest.mark.parametrize("ham, ten_prompt, _rong", NHANH)
def test_context_cua_engine_vao_nguyen_van_system_prompt(agent, ham, ten_prompt, _rong):
    a, eng = agent
    khoi = json.dumps({"explain": {"gross_profit": 12_345_000, "cogs_coverage_pct": 87.5}}, ensure_ascii=False)
    lich_su = [{"role": "user", "content": "báo cáo quý 3"}]
    asyncio.run(getattr(a, ham)("vì sao lãi gộp ra số này?", khoi, history=lich_su))
    goi = eng.lan_goi[-1]
    assert goi["system"] == getattr(Prompts, ten_prompt).format(context=khoi)
    assert khoi in goi["system"], "số của engine phải tới được model, không để model tự đoán (R1)"
    assert goi["user"] == "vì sao lãi gộp ra số này?"
    assert goi["history"] == lich_su


@pytest.mark.parametrize("ham, ten_prompt, chu_rong", [n for n in NHANH if n[2]])
def test_context_rong_thi_noi_ro_la_chua_co_so_lieu(agent, ham, ten_prompt, chu_rong):
    a, eng = agent
    asyncio.run(getattr(a, ham)("doanh thu tháng này?"))
    system = eng.lan_goi[-1]["system"]
    assert chu_rong in system
    assert "{context}" not in system


def test_nhanh_du_lieu_dung_nhiet_do_thap_nhat(agent):
    """Dữ liệu thật thì không được bịa: nhánh DATA thấp hơn hoặc bằng mọi nhánh văn xuôi khác."""
    a, eng = agent
    asyncio.run(a.answer_data("tồn kho?", "{}"))
    asyncio.run(a.answer_report("báo cáo", "{}"))
    asyncio.run(a.answer_general("chào"))
    nhiet_data, *khac = [g["temperature"] for g in eng.lan_goi]
    assert all(nhiet_data <= t for t in khac)


def test_prompt_khong_ton_tai_thi_lui_ve_consult_va_canh_bao(caplog):
    with caplog.at_level(logging.WARNING, logger="projecta.agents.manager"):
        assert ManagerAgent._get_prompt("KHONG_CO_PROMPT_NAY") == Prompts.CONSULT_SYSTEM
    assert "KHONG_CO_PROMPT_NAY" in caplog.text
