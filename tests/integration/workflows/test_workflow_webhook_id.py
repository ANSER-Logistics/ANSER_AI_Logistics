"""
tests/integration/workflows/test_workflow_webhook_id.py — mọi node webhook trong workflows/logistics/ có `webhookId`.

VÌ SAO (#80, đo trên n8n 2.48.5 ngày 19/11/2026)
------------------------------------------------
Thiếu `webhookId`, workflow nhập bằng `n8n import:workflow` rồi `n8n publish:workflow` được
báo là đang bật, nhưng gọi webhook thì nhận **404, chưa đăng ký**: khách nhắn báo giá mà luồng
không chạy, và không có lỗi nào nói ra điều đó. Có `webhookId` thì webhook trả 200.

Đường Body dùng để nạp workflow bằng mã (`POST /api/v1/workflows` rồi `/activate`) tự sinh
`webhookId` khi file thiếu, và giữ nguyên giá trị khi file có. Nên trường này cần cho đường
dòng lệnh, và vô hại cho đường REST. Đường "Import from File" trên giao diện chưa thử.
"""

from __future__ import annotations

import json
import pathlib
import uuid

import pytest

THU_MUC = pathlib.Path(__file__).resolve().parents[3] / "workflows" / "logistics"
FILES = sorted(THU_MUC.glob("*.json"))


def _node_webhook() -> list[tuple[str, dict]]:
    ra = []
    for f in FILES:
        for n in json.loads(f.read_text(encoding="utf-8"))["nodes"]:
            if n.get("type") == "n8n-nodes-base.webhook":
                ra.append((f"{f.name}::{n['name']}", n))
    return ra


NODE_WEBHOOK = _node_webhook()


def test_co_node_webhook_de_kiem():
    """Chốt chống xanh suông: parametrize trên danh sách rỗng sinh ra một ca SKIP (#29)."""
    assert len(NODE_WEBHOOK) >= 2, [ten for ten, _ in NODE_WEBHOOK]


@pytest.mark.parametrize("ten,node", NODE_WEBHOOK, ids=[ten for ten, _ in NODE_WEBHOOK])
def test_node_webhook_co_webhook_id_dang_uuid(ten, node):
    wid = node.get("webhookId")
    assert wid, f"{ten}: thiếu webhookId — nhập bằng `n8n import:workflow` thì webhook trả 404"
    assert str(uuid.UUID(wid)) == wid, f"{ten}: webhookId phải là UUID viết thường, có gạch: {wid!r}"


def test_webhook_id_khong_trung_nhau():
    """Chép một node webhook sang workflow khác mà giữ nguyên id thì hai node mang cùng id."""
    ids = [n["webhookId"] for _, n in NODE_WEBHOOK if n.get("webhookId")]
    assert len(ids) == len(set(ids)), ids
