"""
tests/test_benchmark_thu_lai_n8n.py — đo n8n "sau một lần thử lại" như `/chat` production (#91).

VÌ SAO CÓ FILE NÀY
------------------
`anser-v4` trượt n8n 14/34 ở LẦN THỬ ĐẦU (Thành đo 17/11/2026). Production không chấm một lần: `/chat` thử lại
đúng 1 lần, kèm lý do lỗi cụ thể từ `validate_workflow`. 8 trong 14 ca chỉ là một nhánh IF nối tới node không
tồn tại, và lý do lỗi nói đúng tên node đó. Bộ đo không thử lại nên chưa ai biết 8 ca ấy có sống sót hay không,
và quyết định giữa v3, v4, v5 hay hai LoRA đang dựa trên một con số là cận dưới của thứ khách nhận.

Ba điều test này khoá:
  1. Lời nhắn thử lại của bộ đo và của `/chat` là CÙNG MỘT định nghĩa (R4), không phải hai chuỗi giống nhau.
  2. `thu_lai_n8n` chỉ sinh lại câu hỏng, giữ nguyên câu đã đạt, và đưa đúng lý do lỗi của từng câu.
  3. `compare_runs` chỉ so mục "sau thử lại" khi cả hai bên có.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from offline_training import compare_runs
from offline_training.benchmark_v3 import chat_thu_lai_n8n, score_n8n, thu_lai_n8n
from src.agents.coder import CoderAgent, loi_lan_truoc, soan_yeu_cau
from src.core.agent_middleware import AgentMiddleware

ROOT = Path(__file__).resolve().parent.parent


def _wf_hop_le() -> str:
    return json.dumps({
        "action": "create_workflow",
        "name": "kiem tra",
        "payload": {
            "nodes": [
                {"name": "Lich", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2,
                 "position": [0, 0], "parameters": {"rule": {"interval": [{"field": "hours"}]}}},
                {"name": "Gui", "type": "n8n-nodes-base.noOp", "typeVersion": 1,
                 "position": [200, 0], "parameters": {}},
            ],
            "connections": {"Lich": {"main": [[{"node": "Gui", "type": "main", "index": 0}]]}},
        },
    })


def _wf_noi_toi_node_khong_co() -> str:
    """Nhánh nối tới một node không có. Từ 20/11/2026 `noOp` KHÔNG còn dùng được làm ví dụ: nó được sửa trước khi kiểm (`sua_lien_ket_noop`); lỗi thật là tên khác, như `Trả 200` của v5."""
    d = json.loads(_wf_hop_le())
    d["payload"]["connections"]["Lich"]["main"][0][0]["node"] = "Trả 200"
    return json.dumps(d)


# ---------------------------------------------------------------------------
# 1. Một định nghĩa lời nhắn thử lại
# ---------------------------------------------------------------------------

def test_chat_py_dung_loi_lan_truoc_khong_con_chuoi_rieng():
    src = (ROOT / "src" / "api" / "routes" / "chat.py").read_text(encoding="utf-8")
    assert "loi_lan_truoc(err)" in src
    assert "Lần trước JSON bị lỗi" not in src, "chuỗi thử lại phải chỉ sống ở coder.py (R4)"


def test_write_code_dung_soan_yeu_cau():
    thu: dict = {}

    async def gia(**kw):
        thu.update(kw)
        return "{}"

    agent = CoderAgent.__new__(CoderAgent)
    agent.middleware = AgentMiddleware()
    agent.generate_chat = gia  # type: ignore[method-assign]
    asyncio.run(agent.write_code("tạo luồng", "[PLAN] a", feedback=loi_lan_truoc("hỏng X")))
    assert thu["user"] == soan_yeu_cau("tạo luồng", "[PLAN] a", loi_lan_truoc("hỏng X"))
    assert "hỏng X" in thu["user"] and "LỖI LẦN TRƯỚC" in thu["user"]


def test_khong_co_feedback_thi_khong_co_phan_loi():
    u = soan_yeu_cau("t", "p")
    assert u == "YÊU CẦU: t\nKẾ HOẠCH: p"
    assert "LỖI" not in u


def test_chat_thu_lai_mang_ly_do_va_khong_doi_system():
    chat = chat_thu_lai_n8n("HE THONG", {"task": "t", "plan": "p"}, 'trỏ tới node không tồn tại: "noOp"')
    assert chat[0] == {"role": "system", "content": "HE THONG"}
    assert 'trỏ tới node không tồn tại: "noOp"' in chat[1]["content"]
    assert chat[1]["content"] == soan_yeu_cau("t", "p", loi_lan_truoc('trỏ tới node không tồn tại: "noOp"'))


# ---------------------------------------------------------------------------
# 2. thu_lai_n8n
# ---------------------------------------------------------------------------

class _NhaGia:
    """Nhà sinh giả: ghi lại các cuộc chat nhận được và trả đầu ra đã định."""

    def __init__(self, tra: list[tuple[str, str]]):
        self.tra = tra
        self.nhan: list = []

    def sinh(self, chats, json_schema, max_tokens, temperature):
        self.nhan.append((chats, json_schema, max_tokens, temperature))
        return [t for t, _ in self.tra], [f for _, f in self.tra]


def _lan_dau():
    rows = [{"_id": "A", "task": "ta", "plan": "pa"},
            {"_id": "B", "task": "tb", "plan": "pb"},
            {"_id": "C", "task": "tc", "plan": "pc"}]
    outs = [_wf_hop_le(), _wf_noi_toi_node_khong_co(), '{"action": "create_workflow", "payload": {"nodes": [{"na']
    fins = ["stop", "stop", "length"]
    return rows, score_n8n(rows, outs, fins)


def test_chi_sinh_lai_cau_hong_va_dua_dung_ly_do_cua_tung_cau():
    rows, kq = _lan_dau()
    assert kq["per_row"] == [True, False, False]
    nha = _NhaGia([(_wf_hop_le(), "stop"), ('{"action": "x', "length")])
    tl = thu_lai_n8n(nha, rows, kq, "SYS", {"type": "object"}, 2048)

    chats, schema, tran, nhiet = nha.nhan[0]
    assert len(chats) == 2, "chỉ hai câu hỏng được sinh lại, câu A đã đạt thì giữ nguyên"
    assert schema == {"type": "object"} and tran == 2048 and nhiet == 0.0
    assert 'trỏ tới node không tồn tại: "Trả 200"' in chats[0][1]["content"], "câu B phải nhận đúng lỗi của B"
    assert "tb" in chats[0][1]["content"] and "tc" in chats[1][1]["content"]

    assert tl["n_thu_lai"] == 2 and tl["n_sua_duoc"] == 1
    assert tl["per_row"] == [True, True, False]
    assert tl["n_valid"] == 2 and tl["n"] == 3 and abs(tl["valid_rate"] - 2 / 3) < 1e-9
    assert tl["n_cat_cut"] == 1, "câu C vẫn cụt sau thử lại: phải đếm riêng, không giấu"
    assert tl["ma"] == ["B", "C"]


def test_khong_cau_nao_hong_thi_khong_goi_nha_sinh():
    rows = [{"_id": "A", "task": "t", "plan": "p"}]
    kq = score_n8n(rows, [_wf_hop_le()], ["stop"])
    nha = _NhaGia([])
    tl = thu_lai_n8n(nha, rows, kq, "SYS", {}, 2048)
    assert nha.nhan == [], "không có câu hỏng thì không tốn GPU"
    assert tl["n_thu_lai"] == 0 and tl["per_row"] == [True] and tl["n_valid"] == 1


def test_thu_lai_khong_sua_ket_qua_lan_dau_cua_cong():
    """Cổng chấm theo lần thử đầu; hàm thử lại không được đổi `per_row` gốc tại chỗ."""
    rows, kq = _lan_dau()
    truoc = list(kq["per_row"])
    thu_lai_n8n(_NhaGia([(_wf_hop_le(), "stop"), (_wf_hop_le(), "stop")]), rows, kq, "SYS", {}, 2048)
    assert kq["per_row"] == truoc


def test_dau_do_bat_duoc_viec_khong_dua_ly_do_loi():
    """Chứng minh test không câm: thiếu lý do lỗi thì lời nhắn không còn chứa tên node hỏng."""
    chat = chat_thu_lai_n8n("S", {"task": "t", "plan": "p"}, "")
    assert 'node không tồn tại: "noOp"' not in chat[1]["content"]


# ---------------------------------------------------------------------------
# 3. compare_runs
# ---------------------------------------------------------------------------

def _file(model: str, per_row: list[bool], thu_lai: list[bool] | None) -> dict:
    muc: dict = {"row_ids": ["A", "B", "C"], "per_row": per_row}
    if thu_lai is not None:
        muc["thu_lai"] = {"per_row": thu_lai}
    return {"model": model, "sections": {"n8n": muc}}


def test_compare_so_muc_sau_thu_lai_khi_ca_hai_co(tmp_path, capsys, monkeypatch):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(_file("v3", [True, True, True], [True, True, True])), encoding="utf-8")
    b.write_text(json.dumps(_file("v4", [True, False, False], [True, True, False])), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["compare_runs", str(a), str(b)])
    compare_runs.main()
    out = capsys.readouterr().out
    assert "[n8n]" in out and "[n8n — sau một lần thử lại]" in out
    assert "B LÀM HỎNG" in out


def test_compare_mot_ben_thieu_thu_lai_thi_noi_thang_khong_so_ngam(tmp_path, capsys, monkeypatch):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(_file("v3", [True, True, True], None)), encoding="utf-8")
    b.write_text(json.dumps(_file("v4", [True, False, False], [True, True, False])), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["compare_runs", str(a), str(b)])
    compare_runs.main()
    out = capsys.readouterr().out
    assert "sau một lần thử lại]" not in out
    assert "chỉ một bên đo" in out
