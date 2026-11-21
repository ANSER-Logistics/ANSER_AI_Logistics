"""
tests/test_sua_lien_ket_noop.py — bỏ liên kết tới node `noOp` KHÔNG tồn tại trước khi kiểm workflow (#91, chủ dự án đồng ý 20/11/2026).

Đo ở v4 (8/14 ca hỏng) và v5 (2/5): nhánh "không" của IF nối tới `noOp` mà kế hoạch im lặng nên workflow không có node ấy. `noOp` nghĩa là
"không làm gì" = để nhánh trống. Cái dễ sai ở đây là cái không báo lỗi: sửa quá tay (che luôn lỗi thật như nối tới `Trả 200` không có), sửa mà
đổi đối tượng gốc, hoặc sửa ở production mà phép đo không sửa (hai bên chấm khác nhau, R4).
"""

from __future__ import annotations

import copy
import json
import os

import pytest

from offline_training.benchmark_v3 import score_n8n
from offline_training.cham_lai_n8n import cham_nhanh, main
from src.core.workflow_schema import reload_catalog, sua_lien_ket_noop, validate_workflow


@pytest.fixture(autouse=True)
def _tra_lai_catalog():
    """`cham_lai_n8n.main` nạp catalog thật (đặt `N8N_TEMPLATES_DIR` thẳng vào `os.environ`, từ #175); trả lại sau mỗi test để
    `test_training_pipeline_v3` (so vân tay catalog mặc định) không thấy biến rò."""
    cu = os.environ.get("N8N_TEMPLATES_DIR")
    yield
    if cu is None:
        os.environ.pop("N8N_TEMPLATES_DIR", None)
    else:
        os.environ["N8N_TEMPLATES_DIR"] = cu
    reload_catalog()


def _wf(dich_nhanh_khong: str | None, them_nut: list[dict] | None = None) -> dict:
    nodes = [
        {"name": "Lịch", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0], "parameters": {}},
        {"name": "Có gì?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [250, 0], "parameters": {}},
        {"name": "Soạn", "type": "n8n-nodes-base.set", "typeVersion": 3, "position": [500, 0], "parameters": {}},
    ] + (them_nut or [])
    nhanh_khong = [] if dich_nhanh_khong is None else [{"node": dich_nhanh_khong, "type": "main", "index": 0}]
    con = {"Lịch": {"main": [[{"node": "Có gì?", "type": "main", "index": 0}]]},
           "Có gì?": {"main": [[{"node": "Soạn", "type": "main", "index": 0}], nhanh_khong]}}
    return {"action": "create_workflow", "name": "x", "payload": {"nodes": nodes, "connections": con}}


def test_workflow_nen_hop_le_de_cac_ca_duoi_co_nghia():
    assert validate_workflow(_wf(None)) == (True, "")


@pytest.mark.parametrize("ten", ["noOp", "NoOp", "no-op", "No Op", "no_op", "NO OP", "No Operation", "do nothing", "DoNothing"])
def test_lien_ket_toi_noop_khong_ton_tai_thi_bi_bo_va_workflow_hop_le(ten):
    wf = _wf(ten)
    assert validate_workflow(wf)[0] is False, "chốt chống xanh suông: trước khi sửa phải hỏng"
    moi, da_bo = sua_lien_ket_noop(wf)
    assert da_bo == [f"Có gì? -> {ten}"]
    assert validate_workflow(moi) == (True, "")
    assert moi["payload"]["connections"]["Có gì?"]["main"][1] == []


def test_khong_doi_doi_tuong_goc():
    wf = _wf("noOp")
    truoc = copy.deepcopy(wf)
    moi, _ = sua_lien_ket_noop(wf)
    assert wf == truoc and moi is not wf


def test_co_node_ten_noop_that_thi_giu_nguyen():
    nut = {"name": "noOp", "type": "n8n-nodes-base.noOp", "typeVersion": 1, "position": [500, 200], "parameters": {}}
    wf = _wf("noOp", [nut])
    moi, da_bo = sua_lien_ket_noop(wf)
    assert da_bo == [] and moi is wf
    assert validate_workflow(wf) == (True, "")


@pytest.mark.parametrize("dich", ["Trả 200", "Gửi email", "noOp2", "Không làm gì", "node_khong_co"])
def test_khong_che_loi_that_ten_khac_noop(dich):
    """Đích không tồn tại mà tên KHÔNG phải noop là lỗi thật: không sửa, validate vẫn đỏ và nêu đúng tên."""
    wf = _wf(dich)
    moi, da_bo = sua_lien_ket_noop(wf)
    assert da_bo == [] and moi is wf
    ok, ly_do = validate_workflow(moi)
    assert ok is False and dich in ly_do


def test_loi_that_va_noop_cung_luc_thi_chi_bo_noop():
    wf = _wf("noOp")
    wf["payload"]["connections"]["Soạn"] = {"main": [[{"node": "Trả 200", "type": "main", "index": 0}]]}
    moi, da_bo = sua_lien_ket_noop(wf)
    assert da_bo == ["Có gì? -> noOp"]
    ok, ly_do = validate_workflow(moi)
    assert ok is False and "Trả 200" in ly_do


@pytest.mark.parametrize("vao", [None, "chuỗi", 5, [], {}, {"payload": None}, {"payload": {"nodes": []}},
                                 {"payload": {"nodes": [], "connections": []}},
                                 {"payload": {"nodes": [{"name": "a"}], "connections": {"a": "hỏng"}}},
                                 {"payload": {"nodes": [{"name": "a"}], "connections": {"a": {"main": [3, None]}}}}])
def test_dau_vao_hinh_dang_la_khong_no_va_tra_nguyen(vao):
    moi, da_bo = sua_lien_ket_noop(vao)
    assert moi is vao and da_bo == []


def test_benchmark_cham_sau_khi_sua_va_co_co_de_tai_tao_cach_cham_cu():
    wf = json.dumps(_wf("noOp"))
    hong = json.dumps(_wf("Trả 200"))
    rows = [{"_id": "a"}, {"_id": "b"}]
    moi = score_n8n(rows, [wf, hong], ["stop", "stop"])
    cu = score_n8n(rows, [wf, hong], ["stop", "stop"], sua_noop=False)
    assert moi["per_row"] == [True, False] and moi["n_sua_noop"] == 1 and moi["sua_noop"] == ["a"]
    assert cu["per_row"] == [False, False] and cu["n_sua_noop"] == 0


def test_cham_lai_tu_dau_ra_tho_cuu_dung_cau_va_khong_lam_hong_cau_nao():
    dong = [{"nhanh": "n8n", "_id": "a", "finish": "stop", "output": json.dumps(_wf("noOp"))},
            {"nhanh": "n8n", "_id": "b", "finish": "stop", "output": json.dumps(_wf("Trả 200"))},
            {"nhanh": "n8n", "_id": "c", "finish": "stop", "output": json.dumps(_wf(None))}]
    kq = cham_nhanh(dong)
    assert (kq["hop_le_cu"], kq["hop_le_moi"]) == (1, 2)
    assert kq["duoc_cuu"] == ["a"] and kq["bi_lam_hong"] == []
    assert [i for i, _ in kq["con_hong"]] == ["b"]


def test_cham_lai_main_doc_file_tho_va_ghi_json(tmp_path, capsys):
    f = tmp_path / "v_tho.jsonl"
    f.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in [
        {"nhanh": "n8n", "_id": "a", "finish": "stop", "output": json.dumps(_wf("noOp"))},
        {"nhanh": "extraction", "_id": "x", "finish": "stop", "output": "{}"}]), encoding="utf-8")
    ra = tmp_path / "kq.json"
    assert main([str(f), "--json", str(ra)]) == 0
    out = capsys.readouterr().out
    assert "0/1 (cách cũ) -> 1/1" in out and "được cứu: a" in out
    assert json.loads(ra.read_text(encoding="utf-8"))["v_tho.jsonl"]["n8n"]["duoc_cuu"] == ["a"]
    assert main([str(tmp_path / "khong_co.jsonl")]) == 2


def test_chat_dung_cung_ham_sua_voi_phep_do():
    """R4: /chat và benchmark phải gọi MỘT hàm; thêm một bản thứ hai ở đâu là hai bên chấm khác nhau."""
    from src.api.routes import chat as chat_mod

    assert chat_mod.sua_lien_ket_noop is sua_lien_ket_noop
    moi = chat_mod._sua_noop(_wf("noOp"), "req-1")
    assert validate_workflow(moi) == (True, "")
    assert chat_mod._sua_noop(None, "req-1") is None


# ---------------------------------------------------------------------------
# Đường /chat thật (TECHNICAL): sửa noOp xảy ra TRƯỚC khi kiểm, nên không tốn lần thử lại
# ---------------------------------------------------------------------------

from tests.test_chat_routing import (  # noqa: E402,F401  (fixture dựng runtime tối thiểu)
    _hoi,
    moi_truong,
)


def _chay_chat_technical(moi_truong, monkeypatch, cac_lan_viet: list[str]):  # noqa: F811
    """Chạy một lượt /chat TECHNICAL với `coder.write_code` trả lần lượt `cac_lan_viet`; trả (câu trả lời, số lần coder được gọi)."""
    from src.api import dependencies as deps

    moi_truong.category = "TECHNICAL"
    gia_tri_goi: list[dict] = []

    async def plan_or_ask(self_or_msg, *a, **k):
        return "[PLAN]\n1. Mỗi ngày\n2. Có gì?\n3. Soạn"

    class _Coder:
        async def write_code(self, user_msg, plan, feedback=None):
            gia_tri_goi.append({"feedback": feedback})
            return cac_lan_viet[min(len(gia_tri_goi), len(cac_lan_viet)) - 1]

    monkeypatch.setattr(moi_truong, "plan_or_ask", plan_or_ask, raising=False)
    monkeypatch.setattr(deps.runtime, "coder", _Coder(), raising=False)
    return _hoi("tạo quy trình tự động báo khi có hàng tồn thấp"), gia_tri_goi


def test_chat_workflow_noop_duoc_sua_khong_can_thu_lai(moi_truong, monkeypatch):  # noqa: F811
    cau_tra_loi, da_goi = _chay_chat_technical(moi_truong, monkeypatch, [json.dumps(_wf("noOp"))])
    wf = json.loads(cau_tra_loi)
    assert validate_workflow(wf) == (True, "")
    assert wf["payload"]["connections"]["Có gì?"]["main"][1] == []
    assert len(da_goi) == 1, "sửa trước khi kiểm thì coder chỉ được gọi một lần, không phải thử lại"


def test_chat_loi_that_van_thu_lai_mot_lan_roi_tu_choi(moi_truong, monkeypatch):  # noqa: F811
    """Đối chứng: lỗi KHÔNG phải noOp thì đường thử lại và lời từ chối giữ nguyên."""
    hong = json.dumps(_wf("Trả 200"))
    cau_tra_loi, da_goi = _chay_chat_technical(moi_truong, monkeypatch, [hong, hong])
    assert len(da_goi) == 2 and da_goi[1]["feedback"]
    assert "chưa dựng được quy trình hợp lệ" in cau_tra_loi
