"""
tests/unit/core/test_grammar_gioi_han_chuoi.py — giới hạn độ dài chuỗi trong grammar workflow, sau cờ `WORKFLOW_GRAMMAR_MAX_STRING` (#91).

Lỗ hở: `parameters` và `connections` là object tự do, nên model lặp một chuỗi tới hết trần token (5 ca v4, 1 ca v5; đọc nguyên văn 20/11/2026).
Mặc định TẮT: schema production không đổi một byte. Bật thì mọi chuỗi (kể cả sâu trong mảng và object lồng) bị chặn độ dài.
Lần đo đầu trên vLLM 0.11.2 (23/11/2026, Thành) trả 400 cho mọi request vì `propertyNames`; đã bỏ. Schema đệ quy (`$defs`/`$ref`) không bị chặn. Biên dịch THẬT bằng xgrammar
0.1.25 đã chạy tay (máy dev, 23/11): cả schema tắt cờ lẫn bật cờ đều biên dịch được. Việc còn lại đo trên Colab (Thành): chạy lại bước D của #91 sau PR này.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

from src.core import workflow_schema as ws  # noqa: E402

GOC = Path(__file__).resolve().parents[3]


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
    assert v.is_valid(_wf({"k" * 81: 1}))                                         # tên khoá KHÔNG bị giới hạn (propertyNames bị vLLM 0.11.2 từ chối)
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


# ---------------------------------------------------------------------------
# vLLM 0.11.2 từ chối schema có từ khoá xgrammar không hỗ trợ (bài học 23/11/2026)
# ---------------------------------------------------------------------------

def _vllm_xgrammar_khong_ho_tro(schema: dict) -> bool:
    """BẢN SAO `has_xgrammar_unsupported_json_features` của vLLM v0.11.2 (`vllm/v1/structured_output/backend_xgrammar.py`, Apache-2.0), chép 23/11/2026.

    True nghĩa là vLLM bỏ xgrammar, chuyển sang guidance, và guidance trả 400 "Unimplemented keys". `STRING_SUPPORTED_FORMATS` của vLLM không dùng ở đây vì
    schema của ta không có `format`; ai thêm `format` thì phải chép nốt danh sách đó.
    """

    def kiem(obj):
        if not isinstance(obj, dict):
            return False
        if obj.get("type") in ("integer", "number") and "multipleOf" in obj:
            return True
        if obj.get("type") == "array" and any(k in obj for k in ("uniqueItems", "contains", "minContains", "maxContains")):
            return True
        if obj.get("type") == "string" and "format" in obj:
            return True
        if obj.get("type") == "object" and any(k in obj for k in ("minProperties", "maxProperties", "propertyNames", "patternProperties")):
            return True
        for v in obj.values():
            if isinstance(v, dict):
                if kiem(v):
                    return True
            elif isinstance(v, list):
                if any(isinstance(i, dict) and kiem(i) for i in v):
                    return True
        return False

    return kiem(schema)


@pytest.mark.parametrize("gia_tri", [None, "600"])
def test_schema_khong_co_tu_khoa_vllm_0_11_2_tu_choi(monkeypatch, gia_tri):
    if gia_tri is None:
        monkeypatch.delenv("WORKFLOW_GRAMMAR_MAX_STRING", raising=False)
    else:
        monkeypatch.setenv("WORKFLOW_GRAMMAR_MAX_STRING", gia_tri)
    assert not _vllm_xgrammar_khong_ho_tro(ws.build_workflow_schema())


def test_ban_sao_ham_kiem_cua_vllm_khong_xanh_suong():
    """Điều khiển âm: đúng schema cũ (có `propertyNames`) phải bị bản sao đánh dấu, nếu không các test trên không chứng minh gì."""
    cu = {"type": "object", "additionalProperties": {"type": "string"}, "propertyNames": {"maxLength": 80}}
    assert _vllm_xgrammar_khong_ho_tro(cu)
    assert _vllm_xgrammar_khong_ho_tro({"properties": {"a": {"anyOf": [{"type": "object", "patternProperties": {}}]}}})
    assert not _vllm_xgrammar_khong_ho_tro({"type": "object", "additionalProperties": {"type": "string", "maxLength": 5}})


def test_khong_con_tu_khoa_nhom_bi_chan_o_bat_ky_dau_trong_schema(monkeypatch):
    """Độc lập với bản sao hàm vLLM: quét tên khoá ở mọi độ sâu (một khoá trùng tên trường, ví dụ thuộc tính tên `contains`, sẽ bị báo: đổi tên thuộc tính)."""
    monkeypatch.setenv("WORKFLOW_GRAMMAR_MAX_STRING", "600")
    cam = {"propertyNames", "patternProperties", "minProperties", "maxProperties", "uniqueItems", "contains", "minContains", "maxContains", "multipleOf", "format"}
    gap = []

    def quet(o, duong):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in cam and "properties" not in duong[-1:]:
                    gap.append("/".join(duong + [k]))
                quet(v, duong + [k])
        elif isinstance(o, list):
            for i, v in enumerate(o):
                quet(v, duong + [str(i)])

    quet(ws.build_workflow_schema(), [])
    assert not gap, gap


# ---------------------------------------------------------------------------
# Biên dịch THẬT bằng xgrammar (chỉ chạy khi có gói; CI không cài vì kéo theo torch, xem requirements-dev.txt; Colab có sẵn qua vLLM)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gia_tri", [None, "600"])
def test_xgrammar_that_bien_dich_duoc_va_chan_chuoi_dai(monkeypatch, gia_tri):
    xg = pytest.importorskip("xgrammar")
    testing = pytest.importorskip("xgrammar.testing")
    chap_nhan = getattr(testing, "_is_grammar_accept_string", None)
    if chap_nhan is None:
        pytest.skip("xgrammar.testing không có _is_grammar_accept_string ở bản này")
    if gia_tri is None:
        monkeypatch.delenv("WORKFLOW_GRAMMAR_MAX_STRING", raising=False)
    else:
        monkeypatch.setenv("WORKFLOW_GRAMMAR_MAX_STRING", gia_tri)
    g = xg.Grammar.from_json_schema(json.dumps(ws.build_workflow_schema()))
    assert chap_nhan(g, json.dumps(_wf({"path": "hook", "httpMethod": "POST"})))
    assert chap_nhan(g, json.dumps(_wf({"url": "x" * 600})))
    # Dài hơn trần: chỉ bị từ chối khi bật cờ. Tắt cờ thì grammar không giới hạn (hành vi production không đổi).
    assert chap_nhan(g, json.dumps(_wf({"url": "x" * 601}))) is (gia_tri is None)
