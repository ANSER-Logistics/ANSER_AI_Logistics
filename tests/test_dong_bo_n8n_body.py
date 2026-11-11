"""
tests/test_dong_bo_n8n_body.py — phần THUẦN của offline_training/dong_bo_n8n_body.py (#20).

Không gọi mạng: phần tải từ GitHub chỉ là `urllib`, còn phần dễ sai là phân
loại khớp / lệch / thiếu và đọc bản đã tải — chúng được kiểm ở đây trên dữ
liệu dựng tay.
"""

from __future__ import annotations

import json

from offline_training.dong_bo_n8n_body import (
    doc_thu_muc,
    la_loi,
    phien_ban_theo_node,
    so_sanh,
)
from src.core import workflow_schema as ws

CATALOG = {
    "n8n-nodes-base.scheduleTrigger": {"typeVersion": 1.2},
    "n8n-nodes-base.httpRequest": {"typeVersion": 4.2},
    "n8n-nodes-base.gmail": {"typeVersion": 2.1},
}


def _wf(*nodes: tuple[str, float]) -> dict:
    return {"nodes": [{"name": f"n{i}", "type": t, "typeVersion": v}
                      for i, (t, v) in enumerate(nodes)]}


def _kl(bang, node):
    return next(r[3] for r in bang if r[0] == node)


def test_phan_loai_khop_lech_thieu_chan_va_khong_dung():
    body = phien_ban_theo_node({
        "a.json": _wf(("n8n-nodes-base.scheduleTrigger", 1.2),
                      ("n8n-nodes-base.httpRequest", 4.4),
                      ("n8n-nodes-base.emailSend", 2.1),
                      ("n8n-nodes-base.code", 2)),
    })
    bang = so_sanh(body, CATALOG)
    assert _kl(bang, "n8n-nodes-base.scheduleTrigger") == "khớp"
    assert _kl(bang, "n8n-nodes-base.httpRequest") == "LỆCH"
    assert _kl(bang, "n8n-nodes-base.emailSend") == "THIẾU bên Brain"
    assert _kl(bang, "n8n-nodes-base.code") == "bị chặn có chủ đích"
    assert _kl(bang, "n8n-nodes-base.gmail") == "Body không dùng"
    assert {r[0] for r in bang if la_loi(r[3])} == {
        "n8n-nodes-base.httpRequest", "n8n-nodes-base.emailSend"}


def test_mot_node_hai_version_trong_body_la_lech_neu_mot_cai_khac():
    """Hai workflow Body dùng hai version của cùng một node -> phải báo, không lấy bừa một."""
    body = phien_ban_theo_node({
        "a.json": _wf(("n8n-nodes-base.httpRequest", 4.2)),
        "b.json": _wf(("n8n-nodes-base.httpRequest", 4.4)),
    })
    assert _kl(so_sanh(body, CATALOG), "n8n-nodes-base.httpRequest") == "LỆCH"


def test_bo_qua_node_hong_khong_sap():
    body = phien_ban_theo_node({"a.json": {"nodes": [
        "khong-phai-dict", {"type": "x"}, {"type": "y", "typeVersion": True},
        {"type": "n8n-nodes-base.if", "typeVersion": 1},
    ]}})
    assert body == {"n8n-nodes-base.if": {1.0}}, "bool không phải typeVersion"


def test_doc_thu_muc_da_tai(tmp_path):
    wf = _wf(("n8n-nodes-base.webhook", 1))
    (tmp_path / "x.json").write_text(json.dumps(wf), encoding="utf-8")
    (tmp_path / "ghi-chu.md").write_text("không phải workflow", encoding="utf-8")
    assert doc_thu_muc(tmp_path) == {"x.json": wf}


def test_catalog_du_phong_tu_nhat_quan():
    """Tham số mẫu của `if` là kiểu v1 (`conditions.number`) thì version phải là 1
    — khai 2 là dạy model ghép tham số v1 với node v2 (sai trước 09/11/2026)."""
    node_if = ws.DEFAULT_NODE_CATALOG["n8n-nodes-base.if"]
    assert "number" in node_if["example"]["conditions"]
    assert node_if["typeVersion"] == 1
    # Ví dụ few-shot mặc định dùng đúng version của catalog
    for n in ws._default_example()["payload"]["nodes"]:
        assert n["typeVersion"] == ws.DEFAULT_NODE_CATALOG[n["type"]]["typeVersion"], n["name"]
