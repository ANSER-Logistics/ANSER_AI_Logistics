"""
tests/test_grammar_gioi_han_chuoi.py — giới hạn độ dài chuỗi trong grammar workflow, sau cờ `WORKFLOW_GRAMMAR_MAX_STRING` (#91).

Lỗ hở: `parameters` và `connections` là object tự do, nên model lặp một chuỗi tới hết trần token (5 ca v4, 1 ca v5; đọc nguyên văn 20/11/2026).
Mặc định TẮT: schema production không đổi một byte. Bật thì mọi chuỗi (kể cả sâu trong mảng và object lồng) bị chặn độ dài.
KHÔNG đo được ở đây: xgrammar của vLLM 0.11.2 có biên dịch được schema đệ quy không (Colab, Thành).
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

from src.core import workflow_schema as ws  # noqa: E402

GOC = Path(__file__).resolve().parent.parent


def _wf(tham_so: dict, ket_noi: dict | None = None) -> dict:
    return {"action": "create_workflow", "name": "thu", "payload": {
        "nodes": [{"name": "A", "type": "n8n-nodes-base.webhook", "typeVersion": 1, "position": [0, 0], "parameters": tham_so}],
        "connections": ket_noi or {}}}


def test_mac_dinh_tat_va_schema_khong_doi(monkeypatch):
    monkeypatch.delenv("WORKFLOW_GRAMMAR_MAX_STRING", raising=False)
    s = ws.build_workflow_schema()
    assert "$defs" not in s and s["properties"]["payload"]["properties"]["connections"] == {"type": "object"}
    assert s == ws._build_workflow_schema_goc()


@pytest.mark.parametrize("gia_tri", ["abc", "-1", "10", "49", "1.5"])
def test_gia_tri_hong_la_loi_to(monkeypatch, gia_tri):
    monkeypatch.setenv("WORKFLOW_GRAMMAR_MAX_STRING", gia_tri)
    with pytest.raises(RuntimeError, match="WORKFLOW_GRAMMAR_MAX_STRING"):
        ws.gioi_han_chuoi_grammar()


def test_bat_co_chan_chuoi_lap_vo_tan(monkeypatch):
    monkeypatch.setenv("WORKFLOW_GRAMMAR_MAX_STRING", "600")
    s = ws.build_workflow_schema()
    jsonschema.Draft202012Validator.check_schema(s)
    v = jsonschema.Draft202012Validator(s)
    assert v.is_valid(_wf({"url": "x" * 600}))
    assert not v.is_valid(_wf({"documentId": "ab" * 2000}))                       # đúng kiểu lỗi v4/v5
    assert not v.is_valid(_wf({"a": {"b": [{"c": "y" * 601}]}}))                  # sâu trong object và mảng
    assert not v.is_valid(_wf({}, {"A": {"main": [[{"node": "z" * 1000, "type": "main", "index": 0}]]}}))   # connections
    assert not v.is_valid(_wf({"k" * 81: 1}))                                     # tên khoá cũng bị giới hạn
    assert not v.is_valid(_wf({"a": list(range(41))}))                           # mảng có trần


def test_moi_mau_that_cua_body_va_logistics_van_qua_khi_bat_co(monkeypatch):
    """Hiệu chỉnh: trần 600 không được từ chối workflow thật nào (chuỗi dài nhất trong mẫu Body: 329)."""
    monkeypatch.setenv("WORKFLOW_GRAMMAR_MAX_STRING", "600")
    v = jsonschema.Draft202012Validator(ws.build_workflow_schema())
    tep = sorted(glob.glob(str(GOC / "data" / "n8n_templates" / "*.json")) + glob.glob(str(GOC / "workflows" / "logistics" / "*.json")))
    assert len(tep) >= 30
    loi = []
    for f in tep:
        w = json.loads(Path(f).read_text(encoding="utf-8"))
        nodes = w.get("nodes", w.get("payload", {}).get("nodes", []))
        ket_noi = w.get("connections", w.get("payload", {}).get("connections", {}))
        for n in nodes:
            if n.get("type") not in ws.allowed_types():
                continue   # node ngoài catalog dự phòng: grammar enum chặn từ trước, không liên quan phép kiểm này
        doi_tuong = {"action": "create_workflow", "name": "x", "payload": {"nodes": [
            {"name": n["name"], "type": n["type"], "typeVersion": n.get("typeVersion", 1), "position": [0, 0],
             "parameters": n.get("parameters", {})} for n in nodes if n.get("type") in ws.allowed_types()] or [
            {"name": "A", "type": ws.allowed_types()[0], "typeVersion": 1, "position": [0, 0], "parameters": {}}],
            "connections": ket_noi}}
        for e in v.iter_errors(doi_tuong):
            if "maxLength" in str(e.validator) or "maxItems" in str(e.validator):
                loi.append(f"{Path(f).name}: {e.message[:80]}")
    assert not loi, "\n".join(loi[:10])
