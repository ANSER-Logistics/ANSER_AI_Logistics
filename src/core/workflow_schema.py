"""
src/core/workflow_schema.py — NGUỒN SỰ THẬT DUY NHẤT cho định dạng workflow n8n.

VÌ SAO CÓ FILE NÀY
------------------
Trước bản này, định dạng workflow được định nghĩa ở BỐN nơi với BA định dạng khác
nhau (ARCHITECTURE.md §11.1):

  1. src/data/blueprints/*.json   -> Make.com   (dữ liệu fine-tune)
  2. prompts.py::CODER_SYSTEM     -> n8n rút gọn, dùng "edges"
  3. agent_middleware.py          -> engine nội bộ Body, dùng "params"
  4. chat.py::_validate_workflow  -> n8n rút gọn

Model được fine-tune trên (1), prompt bằng (2), đưa danh mục (3), validate theo (4).
Đó là nguyên nhân gốc khiến JSON workflow hỏng liên tục — KHÔNG phải model yếu.

CATALOG PHẢI RÚT RA TỪ WORKFLOW THẬT, KHÔNG ĐƯỢC BỊA
----------------------------------------------------
Body đã có sẵn n8n self-hosted (Docker) kèm một số workflow đang chạy thật. Danh
mục node và ví dụ few-shot PHẢI lấy từ đó, vì:

  - Node type và typeVersion phụ thuộc phiên bản n8n mà Body đang chạy. Đoán sai
    typeVersion là workflow không import được.
  - Workflow thật đã dùng đúng credential, đúng biến môi trường, đúng quy ước đặt
    tên của Body. Few-shot từ ví dụ thật dạy được những thứ đó; ví dụ bịa thì không.
  - Body là nguồn sự thật về việc n8n instance đó làm được gì.

Vì repo Body chưa merge vào đây, module hoạt động theo hai chế độ:

  * CÓ template  -> quét thư mục, rút node type + typeVersion + ví dụ THẬT đang dùng
  * CHƯA có      -> dùng DEFAULT_NODE_CATALOG bên dưới, và GHI LOG CẢNH BÁO

Trỏ `N8N_TEMPLATES_DIR` tới thư mục chứa workflow thật của Body là module tự
cấu hình lại. Không phải sửa code. Thư mục bên Body tên `frontend/n8n-workflows/`
(không phải `workflow_templates/` như bản trước ghi). Lấy về lúc triển khai:

    python offline_training/dong_bo_n8n_body.py tai     # -> deploy/n8n-body/
    python offline_training/dong_bo_n8n_body.py kiem    # lệch thì mã thoát 1
"""

from __future__ import annotations

import copy
import ipaddress
import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger("projecta.workflow_schema")


# ---------------------------------------------------------------------------
# Catalog dự phòng — CHỈ dùng khi chưa có template thật
# ---------------------------------------------------------------------------
# Cố tình giữ ngắn. Mỗi node thừa làm giảm độ chính xác chọn node của model và tốn
# token prompt. Khi Body merge vào, catalog thật sẽ thay thế toàn bộ phần này.
#
# ĐỐI CHIẾU VỚI BODY 09/11/2026 (#20) — `frontend/n8n-workflows/` của
# ANSER-logistics-body, n8n `latest`. Trước đó ba node lệch typeVersion và hai
# node Body dùng mà ở đây không có:
#
#   httpRequest  4.2 -> 4.4   (Body)
#   if           2   -> 1     tham số mẫu vốn là kiểu v1 (`conditions.number`);
#                             khai 2 là dạy model ghép tham số v1 với version v2
#   webhook      2   -> 1
#   emailSend    + 2.1        Body gửi mail bằng SMTP, KHÔNG có credential Gmail
#   splitOut     + 1
#
# Kiểm lại bằng lệnh, không bằng nhớ:
#   python offline_training/dong_bo_n8n_body.py kiem

DEFAULT_NODE_CATALOG: dict[str, dict[str, Any]] = {
    "n8n-nodes-base.scheduleTrigger": {
        "trigger": True,
        "typeVersion": 1.2,
        "desc": "Chạy theo lịch (mỗi N giờ/ngày, hoặc giờ cố định)",
        "example": {"rule": {"interval": [{"field": "hours", "hoursInterval": 4}]}},
    },
    "n8n-nodes-base.webhook": {
        "trigger": True,
        "typeVersion": 1,
        "desc": "Nhận HTTP request từ ANSER Body hoặc hệ thống ngoài",
        "example": {"path": "anser-hook", "httpMethod": "POST"},
    },
    "n8n-nodes-base.httpRequest": {
        "trigger": False,
        "typeVersion": 4.4,
        "desc": "Gọi HTTP. Dùng cho MỌI thao tác ghi dữ liệu (qua API Body), gọi tool ANSER, và gửi Discord",
        "example": {
            "url": "={{$env.ANSER_API}}/api/n8n/internal/low-stock",
            "method": "GET",
        },
    },
    "n8n-nodes-base.postgres": {
        "trigger": False,
        "typeVersion": 2.4,
        "desc": "Truy vấn CSDL. CHỈ SELECT — mọi lệnh ghi đều bị từ chối",
        "example": {
            "operation": "executeQuery",
            "query": "SELECT name, stock_quantity FROM products WHERE stock_quantity < 15",
        },
    },
    "n8n-nodes-base.googleSheets": {
        "trigger": False,
        "typeVersion": 4.5,
        "desc": "Đọc/ghi Google Sheets",
        "example": {"operation": "append", "documentId": "SHEET_ID", "sheetName": "Sheet1"},
    },
    "n8n-nodes-base.emailSend": {
        "trigger": False,
        "typeVersion": 2.1,
        "desc": "Gửi email qua SMTP — cách Body đang gửi mail (ví dụ: gửi báo giá vận tải cho khách)",
        "example": {
            "fromEmail": "alerts@anser.local",
            "toEmail": "={{ $json.email_to }}",
            "subject": "={{ $json.email_subject }}",
            "html": "={{ $json.email_html }}",
            "options": {},
        },
    },
    "n8n-nodes-base.gmail": {
        "trigger": False,
        "typeVersion": 2.1,
        "desc": "Gửi email qua Gmail — Body CHƯA cấu hình credential Gmail; gửi mail thì dùng emailSend",
        "example": {
            "operation": "send",
            "sendTo": "khach@example.com",
            "subject": "Báo giá vận chuyển",
            "message": "={{$json.body}}",
        },
    },
    "n8n-nodes-base.if": {
        "trigger": False,
        "typeVersion": 1,
        "desc": "Rẽ nhánh theo điều kiện. Nhánh true = output 0, false = output 1",
        "example": {
            "conditions": {
                "number": [
                    {"value1": "={{$json.stock_quantity}}", "operation": "smaller", "value2": 15}
                ]
            }
        },
    },
    "n8n-nodes-base.set": {
        "trigger": False,
        "typeVersion": 3.4,
        "desc": "Gán/đổi tên trường dữ liệu",
        "example": {
            "assignments": {
                "assignments": [
                    {"name": "message", "value": "={{$json.name}}", "type": "string"}
                ]
            }
        },
    },
    "n8n-nodes-base.splitInBatches": {
        "trigger": False,
        "typeVersion": 3,
        "desc": "Lặp qua từng item của mảng",
        "example": {"batchSize": 1},
    },
    "n8n-nodes-base.splitOut": {
        "trigger": False,
        "typeVersion": 1,
        "desc": "Tách một trường mảng thành nhiều item (mỗi phần tử một item)",
        "example": {"fieldToSplitOut": "warehouses", "options": {}},
    },
    "n8n-nodes-base.noOp": {
        "trigger": False,
        "typeVersion": 1,
        "desc": "Node rỗng — dùng làm điểm hợp nhánh",
        "example": {},
    },
}

# Node bị chặn dù có xuất hiện trong template thật.
# `code` cho phép chạy JS tuỳ ý trong n8n -> vượt qua mọi luật an toàn ta đặt ở
# tầng trên. Nếu Body thực sự cần, gỡ khỏi đây một cách có chủ đích.
BLOCKED_NODE_TYPES = {
    "n8n-nodes-base.code",
    "n8n-nodes-base.executeCommand",
    "n8n-nodes-base.ssh",
}

_TRIGGER_HINT = re.compile(r"trigger$|^n8n-nodes-base\.webhook$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Rút catalog từ workflow n8n thật
# ---------------------------------------------------------------------------

def _iter_template_files(template_dir: Path):
    for path in sorted(template_dir.glob("*.json")):
        try:
            yield path, json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Bỏ qua template không đọc được %s: %s", path.name, exc)


def load_catalog_from_templates(template_dir: str | Path) -> dict[str, dict[str, Any]]:
    """
    Quét workflow n8n thật, rút ra node type + typeVersion + parameters mẫu.

    Chỉ giữ typeVersion CAO NHẤT gặp được cho mỗi type — template cũ có thể còn
    typeVersion lỗi thời, sinh theo bản cũ thì n8n cảnh báo deprecated.
    """
    template_dir = Path(template_dir)
    if not template_dir.is_dir():
        return {}

    catalog: dict[str, dict[str, Any]] = {}

    for path, data in _iter_template_files(template_dir):
        nodes = data.get("nodes")
        if not isinstance(nodes, list):
            continue

        for node in nodes:
            if not isinstance(node, dict):
                continue
            ntype = node.get("type")
            if not isinstance(ntype, str) or ntype in BLOCKED_NODE_TYPES:
                continue

            tversion = node.get("typeVersion")
            if not isinstance(tversion, (int, float)):
                continue

            existing = catalog.get(ntype)
            if existing and existing["typeVersion"] >= tversion:
                continue

            params = node.get("parameters")
            catalog[ntype] = {
                "trigger": bool(_TRIGGER_HINT.search(ntype)),
                "typeVersion": tversion,
                "desc": f"Dùng trong template thật: {path.stem}",
                "example": params if isinstance(params, dict) else {},
            }

    if catalog:
        logger.info(
            "Catalog rút từ %d template thật tại %s — %d node type",
            len(list(template_dir.glob("*.json"))), template_dir, len(catalog),
        )
    return catalog


def _sanitize_example_node(node: dict) -> dict:
    """
    Cắt node thật về ĐÚNG hình dạng mà schema sinh cho phép.

    Node trong workflow thật mang thêm `id`, `retryOnFail`, `maxTries`,
    `waitBetweenTries`... Schema sinh đặt additionalProperties=False — nếu
    few-shot dạy model các field đó, grammar sẽ CHẶN đúng token mà ví dụ vừa dạy,
    model bị ép rẽ sang nhánh kém hơn giữa chừng. Ví dụ và grammar phải khớp nhau
    tuyệt đối.
    """
    return {
        "name": node.get("name", ""),
        "type": node.get("type", ""),
        "typeVersion": node.get("typeVersion", 1),
        "position": node.get("position", [0, 0]),
        "parameters": node.get("parameters", {}),
    }


def load_examples_from_templates(template_dir: str | Path, limit: int = 2) -> list[dict]:
    """
    Lấy vài workflow thật làm few-shot, ưu tiên workflow nhỏ.

    Thực tế đo trên 32 template của Body: 69/262 node là `code` (bị chặn khi
    SINH) — lọc bỏ cả workflow chứa code thì gần như không còn ứng viên. Vì vậy
    thay vì bỏ cả workflow, ta THAY node code bằng noOp giữ nguyên tên/vị trí:
    cấu trúc luồng (trigger -> gọi API -> rẽ nhánh -> gửi đi) vẫn là của thật,
    còn ví dụ chỉ chứa node mà model được phép sinh.
    """
    template_dir = Path(template_dir)
    if not template_dir.is_dir():
        return []

    candidates = []
    for path, data in _iter_template_files(template_dir):
        nodes = data.get("nodes")
        if not isinstance(nodes, list) or not (3 <= len(nodes) <= 7):
            continue

        cleaned = []
        for n in nodes:
            if not isinstance(n, dict):
                break
            node = _sanitize_example_node(n)
            if node["type"] in BLOCKED_NODE_TYPES:
                # Giữ chỗ trong luồng, đổi sang node trung tính được phép sinh
                node["type"] = "n8n-nodes-base.noOp"
                node["typeVersion"] = 1
                node["parameters"] = {}
            cleaned.append(node)
        else:
            # Ưu tiên workflow vốn KHÔNG có node bị chặn (ít bị "vá" nhất)
            n_patched = sum(
                1 for orig in nodes
                if isinstance(orig, dict) and orig.get("type") in BLOCKED_NODE_TYPES
            )
            candidates.append((n_patched, len(cleaned), path.stem, data, cleaned))

    candidates.sort(key=lambda c: (c[0], c[1]))
    return [
        {
            "action": "create_workflow",
            "name": data.get("name") or stem,
            "payload": {
                "nodes": cleaned,
                "connections": data.get("connections", {}),
            },
        }
        for _, _, stem, data, cleaned in candidates[:limit]
    ]


@lru_cache(maxsize=1)
def _active() -> tuple[dict[str, dict[str, Any]], list[dict], bool]:
    """
    (catalog, few_shot_examples, from_real_templates)

    Cache vì được gọi mỗi lần dựng prompt. Đổi N8N_TEMPLATES_DIR lúc chạy thì gọi
    reload_catalog().
    """
    template_dir = os.getenv("N8N_TEMPLATES_DIR", "").strip()

    if template_dir:
        from_templates = load_catalog_from_templates(template_dir)
        if from_templates:
            # HỢP NHẤT: mặc định + template thật, template THẮNG khi trùng type.
            #
            # Vì sao không dùng template-only: 32 workflow thật của Body chỉ chạm
            # 6 node type (mọi thứ đi qua httpRequest gọi service nội bộ). Nhưng
            # gmail/set/googleSheets vẫn có sẵn trong mọi bản n8n chuẩn và cần
            # cho nghiệp vụ chưa có template (gửi email báo giá logistics).
            # Vì sao template thắng: typeVersion của chúng là số ĐÃ CHẠY THẬT
            # trên n8n instance của Body (httpRequest 4.4, if 1 — khác hẳn số
            # tôi đoán), còn số trong DEFAULT chỉ là ước đoán.
            catalog = {**DEFAULT_NODE_CATALOG, **from_templates}
            examples = load_examples_from_templates(template_dir)
            if not examples:
                examples = [_default_example()]
            return catalog, examples, True
        logger.warning(
            "N8N_TEMPLATES_DIR=%s không có workflow n8n hợp lệ — dùng catalog dự phòng",
            template_dir,
        )
    else:
        logger.warning(
            "Chưa đặt N8N_TEMPLATES_DIR — dùng catalog DỰ PHÒNG. "
            "typeVersion có thể không khớp n8n instance của Body. "
            "Chạy `python offline_training/dong_bo_n8n_body.py tai` rồi trỏ biến "
            "này vào deploy/n8n-body/ (bên Body: frontend/n8n-workflows/)."
        )

    return DEFAULT_NODE_CATALOG, [_default_example()], False


def reload_catalog() -> None:
    """Xoá cache — gọi sau khi đổi N8N_TEMPLATES_DIR hoặc thêm template."""
    _active.cache_clear()


def get_node_catalog() -> dict[str, dict[str, Any]]:
    return _active()[0]


def is_using_real_templates() -> bool:
    """Cho /health biết đang chạy catalog thật hay dự phòng."""
    return _active()[2]


def allowed_types() -> list[str]:
    return sorted(get_node_catalog().keys())


def catalog_fingerprint() -> str:
    """
    Vân tay của danh mục node đang dùng (type + typeVersion).

    CODER_SYSTEM được dựng TỪ catalog này, nên dữ liệu fine-tune mang theo
    system prompt của catalog lúc sinh data. Nếu lúc serve `N8N_TEMPLATES_DIR`
    trỏ chỗ khác, prompt đổi mà model không biết — mọi thứ vẫn "chạy" nhưng
    kém đi một cách âm thầm. Dataset ghi lại vân tay này; `preflight_check.py`
    và `/health` đối chiếu.
    """
    import hashlib

    catalog = get_node_catalog()
    payload = "|".join(
        f"{t}@{catalog[t]['typeVersion']}" for t in sorted(catalog)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def trigger_types() -> set[str]:
    return {t for t, meta in get_node_catalog().items() if meta.get("trigger")}


def _default_example() -> dict:
    return {
        "action": "create_workflow",
        "name": "Cảnh báo tồn kho thấp",
        "payload": {
            "nodes": [
                {
                    "name": "Mỗi 4 tiếng",
                    "type": "n8n-nodes-base.scheduleTrigger",
                    "typeVersion": 1.2,
                    "position": [0, 0],
                    "parameters": {
                        "rule": {"interval": [{"field": "hours", "hoursInterval": 4}]}
                    },
                },
                {
                    "name": "Lấy hàng sắp hết",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.4,
                    "position": [220, 0],
                    "parameters": {
                        "url": "={{$env.ANSER_API}}/api/n8n/internal/low-stock",
                        "method": "GET",
                    },
                },
                {
                    "name": "Báo Discord",
                    "type": "n8n-nodes-base.httpRequest",
                    "typeVersion": 4.4,
                    "position": [440, 0],
                    "parameters": {
                        "url": "={{$env.DISCORD_WEBHOOK_URL}}",
                        "method": "POST",
                        "sendBody": True,
                        "bodyParameters": {
                            "parameters": [{"name": "content", "value": "={{$json.message}}"}]
                        },
                    },
                },
            ],
            "connections": {
                "Mỗi 4 tiếng": {
                    "main": [[{"node": "Lấy hàng sắp hết", "type": "main", "index": 0}]]
                },
                "Lấy hàng sắp hết": {
                    "main": [[{"node": "Báo Discord", "type": "main", "index": 0}]]
                },
            },
        },
    }


# ---------------------------------------------------------------------------
# JSON Schema — đưa vào vLLM guided_json
# ---------------------------------------------------------------------------
# Guided decoding ép cấu trúc ở tầng SAMPLING: JSON sai schema trở thành bất khả
# thi, thay vì "hy vọng model làm đúng rồi retry". Vì vậy schema phải chặt nhất
# có thể ở phần diễn tả được.
#
# `connections` để tự do vì khoá của nó là TÊN NODE (động, không biết trước) —
# JSON Schema không ràng buộc được. Phần đó do validate_workflow() lo.

# Lỗ hở grammar (#91, đọc nguyên văn đầu ra v4 ngày 20/11/2026): `parameters` và `connections` là `{"type": "object"}` không ràng buộc gì, nên model có thể
# lặp MỘT chuỗi tự do (`url`, `documentId`, `smtpPassword`) tới hết trần 2.048 token và workflow cụt. 5 ca của v4 và 1 ca của v5 hỏng đúng kiểu đó, không sửa
# được bằng dữ liệu. Chuỗi dài nhất trong các node được phép ở 33 mẫu thật của Body là 329 ký tự (0 chuỗi trên 400), nên trần 600 có biên rộng.
#
# `WORKFLOW_GRAMMAR_MAX_STRING` (số ký tự mỗi chuỗi trong `parameters`/`connections`; MẶC ĐỊNH 0 = TẮT, hành vi production KHÔNG đổi). Bật thì cả ba chân của R4
# (grammar `guided_json` lúc phục vụ, `benchmark_v3`, bộ kiểm) cùng thấy giới hạn vì cùng dựng từ hàm này. Thành đo trên Colab (cùng bốn tập, bật cờ = 600), rồi chủ
# dự án mới đổi mặc định.
#
# LẦN ĐO ĐẦU TRÊN vLLM 0.11.2 (23/11/2026, Thành, #91) THẤT BẠI VÌ MỘT TỪ KHOÁ: bản đầu của hàm dưới có `propertyNames` (giới hạn độ dài tên khoá). vLLM 0.11.2
# coi `propertyNames` là tính năng xgrammar KHÔNG hỗ trợ (`has_xgrammar_unsupported_json_features`, cùng nhóm `patternProperties`, `minProperties`,
# `maxProperties`), chuyển sang backend guidance, và guidance trả 400 `Unimplemented keys: ["propertyNames"]` cho MỌI request n8n. `$defs`/`$ref` đệ quy thì
# KHÔNG bị chặn. Giờ schema không chứa từ khoá nào trong nhóm đó (có test canh, kèm bản sao hàm kiểm của vLLM). Hệ quả: tên khoá KHÔNG còn bị giới hạn độ dài;
# lỗi lặp vô tận đã gặp (#91) đều ở GIÁ TRỊ (`url`, `documentId`, `smtpPassword`), không ở khoá. Nếu lần đo sau vẫn thấy ca cụt vì khoá lặp thì đó là chỗ hở
# còn lại, không bù được bằng JSON Schema mà xgrammar chấp nhận.
_GRAMMAR_MAX_ITEMS = 40


def gioi_han_chuoi_grammar() -> int:
    """Đọc `WORKFLOW_GRAMMAR_MAX_STRING`. 0 hay rỗng = tắt. Giá trị hỏng thì lỗi to: cấu hình bảo vệ sai không được chạy lặng lẽ."""
    import os
    tho = os.getenv("WORKFLOW_GRAMMAR_MAX_STRING", "").strip()
    if not tho:
        return 0
    try:
        v = int(tho)
    except ValueError:
        raise RuntimeError(f"WORKFLOW_GRAMMAR_MAX_STRING={tho!r} không phải số nguyên") from None
    if v < 0 or (0 < v < 50):
        raise RuntimeError(f"WORKFLOW_GRAMMAR_MAX_STRING={v} phải là 0 (tắt) hoặc từ 50 trở lên")
    return v


def _doi_tuong_co_gioi_han(toi_da_chuoi: int) -> dict[str, Any]:
    """`{"type": "object"}` thay bằng một giá trị đệ quy MỌI chuỗi giá trị đều có `maxLength`, mảng có `maxItems`. Tên khoá KHÔNG bị giới hạn: `propertyNames` bị vLLM 0.11.2 từ chối."""
    return {
        "$defs": {"giaTri": {"anyOf": [
            {"type": "string", "maxLength": toi_da_chuoi},
            {"type": "number"},
            {"type": "boolean"},
            {"type": "null"},
            {"type": "array", "maxItems": _GRAMMAR_MAX_ITEMS, "items": {"$ref": "#/$defs/giaTri"}},
            {"type": "object", "additionalProperties": {"$ref": "#/$defs/giaTri"}},
        ]}},
        "type": "object", "additionalProperties": {"$ref": "#/$defs/giaTri"},
    }


def build_workflow_schema() -> dict[str, Any]:
    schema = _build_workflow_schema_goc()
    toi_da = gioi_han_chuoi_grammar()
    if toi_da:
        tu_do = _doi_tuong_co_gioi_han(toi_da)
        defs = tu_do.pop("$defs")
        schema["$defs"] = defs
        payload = schema["properties"]["payload"]["properties"]
        payload["nodes"]["items"]["properties"]["parameters"] = tu_do
        payload["connections"] = dict(tu_do)
    return schema


def _build_workflow_schema_goc() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create_workflow"]},
            "name": {"type": "string", "minLength": 1, "maxLength": 120},
            "payload": {
                "type": "object",
                "properties": {
                    "nodes": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 12,
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "minLength": 1, "maxLength": 60},
                                "type": {"type": "string", "enum": allowed_types()},
                                "typeVersion": {"type": "number"},
                                "position": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                    "minItems": 2,
                                    "maxItems": 2,
                                },
                                "parameters": {"type": "object"},
                            },
                            "required": [
                                "name", "type", "typeVersion", "position", "parameters",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "connections": {"type": "object"},
                },
                "required": ["nodes", "connections"],
                "additionalProperties": False,
            },
        },
        "required": ["action", "name", "payload"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Sinh phần prompt — dẫn xuất, không viết tay
# ---------------------------------------------------------------------------

def render_node_catalog() -> str:
    """Chuỗi mô tả node nhét vào prompt CoderAgent."""
    lines = []
    for node_type, meta in get_node_catalog().items():
        tag = " [TRIGGER]" if meta.get("trigger") else ""
        example = json.dumps(meta.get("example", {}), ensure_ascii=False)
        if len(example) > 400:                      # ví dụ dài quá thì cắt
            example = example[:400] + "…"
        lines.append(
            f'- {node_type} (typeVersion {meta["typeVersion"]}){tag}\n'
            f'    {meta.get("desc", "")}\n'
            f'    parameters mẫu: {example}'
        )
    return "\n".join(lines)


def render_examples() -> str:
    """Few-shot. Ví dụ THẬT của Body nếu có, ngược lại ví dụ dự phòng."""
    return "\n\n".join(
        json.dumps(ex, ensure_ascii=False) for ex in _active()[1]
    )


# ---------------------------------------------------------------------------
# Validate — lớp an toàn cuối
# ---------------------------------------------------------------------------
# Khi guided_json đã bật, hàm này hiếm khi bắt lỗi CẤU TRÚC. Nó tồn tại để bắt
# thứ JSON Schema không diễn tả được: toàn vẹn tham chiếu giữa connections và
# nodes, số lượng trigger, node mồ côi, và các luật an toàn.

_DANGEROUS_SQL = re.compile(
    r"\b(DROP|TRUNCATE|DELETE|ALTER|UPDATE|INSERT|GRANT|REVOKE|CREATE)\b",
    re.IGNORECASE,
)


def _collect_sql(node: dict) -> list[str]:
    params = node.get("parameters") or {}
    return [
        params[key]
        for key in ("query", "sql", "statement")
        if isinstance(params.get(key), str)
    ]


# Liên kết tới node "không làm gì" mà workflow KHÔNG có (#91, chủ dự án đồng ý 20/11/2026).
#
# Đo ở anser-v4 và v5: nhánh "không" của một IF nối tới node tên `noOp`, trong khi kế hoạch im lặng về nhánh đó nên workflow không hề
# có node ấy (v4: 8 trong 14 ca hỏng; v5: 2 trong 5). `noOp` nghĩa là "không làm gì", đúng bằng để nhánh trống. Nên bỏ liên kết
# đó là SỬA BẰNG MÃ, không để model quyết (R1), và kết quả đúng ý kế hoạch. Hẹp có chủ ý:
#   - chỉ bỏ liên kết có ĐÍCH không tồn tại VÀ tên đích chuẩn hoá (chữ thường, bỏ ký tự không phải chữ số hay chữ cái) là noop,
#     nooperation hay donothing. Có node tên `noOp` thật thì giữ nguyên;
#   - không đụng liên kết tới node không tồn tại với tên khác ("Trả 200"): đó là lỗi thật, `validate_workflow` vẫn báo;
#   - không đổi đối tượng gốc; trả bản sao và danh sách liên kết đã bỏ để người gọi ghi nhật ký.
_TEN_NOOP = {"noop", "nooperation", "donothing"}


def _chuan_ten_nut(ten: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(ten).lower())


def sua_lien_ket_noop(obj: Any) -> tuple[Any, list[str]]:
    """(workflow_đã_sửa, ["nguồn -> đích", ...]). Đầu vào không phải workflow hình dạng đúng thì trả nguyên và danh sách rỗng."""
    try:
        nodes = obj["payload"]["nodes"]
        con = obj["payload"]["connections"]
        ten_nut = {n["name"] for n in nodes if isinstance(n, dict) and "name" in n}
    except (TypeError, KeyError):
        return obj, []
    if not isinstance(con, dict):
        return obj, []
    moi = copy.deepcopy(obj)
    da_bo: list[str] = []
    for src, ra in moi["payload"]["connections"].items():
        main = ra.get("main") if isinstance(ra, dict) else None
        if not isinstance(main, list):
            continue
        for nhanh in main:
            if not isinstance(nhanh, list):
                continue
            giu = []
            for lk in nhanh:
                dich = lk.get("node") if isinstance(lk, dict) else None
                if isinstance(lk, dict) and dich not in ten_nut and _chuan_ten_nut(dich) in _TEN_NOOP:
                    da_bo.append(f"{src} -> {dich}")
                else:
                    giu.append(lk)
            nhanh[:] = giu
    return (moi, da_bo) if da_bo else (obj, [])


# Khoá trong `parameters` có dạng chỗ đặt BÍ MẬT (20/11/2026, R2b). Đo ở `anser-v4`: hai lần model tự viết
# `smtpPassword` thẳng vào `parameters.options` của node emailSend (giá trị là chuỗi rác lặp), thay vì dùng mục
# credentials của n8n. Giá trị rác vô hại, nhưng chỗ đó là chỗ người dùng sẽ điền mật khẩu THẬT, và workflow nằm
# nguyên văn trong n8n và trong lịch sử chat. Bí mật chỉ được nằm trong credentials của n8n.
_KHOA_BI_MAT = re.compile(
    r"pass(?:word|wd|phrase)?$|secret|api[_-]?key|private[_-]?key|access[_-]?token|auth[_-]?token|bearer",
    re.IGNORECASE,
)


def _khoa_bi_mat(obj: Any, duong: str = "") -> str | None:
    """Đường dẫn tới khoá giống chỗ đặt bí mật có GIÁ TRỊ chữ khác rỗng và không phải biểu thức n8n, hoặc None."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            tai = f"{duong}.{k}" if duong else str(k)
            if _KHOA_BI_MAT.search(str(k)) and isinstance(v, str) and v.strip() and not v.lstrip().startswith("="):
                return tai
            thay = _khoa_bi_mat(v, tai)
            if thay:
                return thay
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            thay = _khoa_bi_mat(v, f"{duong}[{i}]")
            if thay:
                return thay
    return None



# ---------------------------------------------------------------------------
# Biểu thức và tham số nguy hiểm (A8, #196)
# ---------------------------------------------------------------------------
# Vì sao: n8n đã vá ít nhất năm lần cùng một loại lỗi (thoát hộp cát biểu thức -> chạy mã trên máy chủ; CVE-2025-68613, CVE-2026-1470,
# CVE-2026-25049...), mỗi lần qua một dạng cú pháp mà danh sách chặn của chính n8n chưa lường (`with`, destructuring, `this` trong hàm mũi
# tên). `validate_workflow` trước đây KHÔNG đọc chữ của biểu thức. Workflow do model sinh phải qua cổng này trước khi tới n8n.
#
# shortcut: kiểm bằng vài biểu thức chính quy trên chuỗi, không phải bộ phân tích cú pháp JS đầy đủ. Mức hạn chế: biểu thức hợp lệ nhưng
# phong phú (`.map(i => ...)`) bị từ chối và đi vào vòng thử lại; cần bộ lexer allowlist đủ ngữ pháp (ghi chú nghiên cứu 20/11/2026, mục
# Q(a)2) khi đo thấy từ chối oan trên workflow thật của Body.

_LITERAL_CHUOI = re.compile(r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*\"""")
_TU_CAM = re.compile(
    r"(?<![\w$])(?:constructor|__proto__|prototype|process|require|module|exports|global|globalThis|window|self|this|arguments|eval|"
    r"Function|AsyncFunction|GeneratorFunction|Object|Reflect|Proxy|Symbol|Buffer|fetch|XMLHttpRequest|WebAssembly|import|setTimeout|"
    r"setInterval|setImmediate|mainModule|binding|child_process|__define\w+__|__lookup\w+__|__sanitize|___n8n_data|resumeUrl)(?![\w$])",
    re.IGNORECASE,
)
_TU_KHOA = re.compile(
    r"(?<![\w$])(?:with|function|class|extends|new|var|let|const|return|yield|await|async|delete|typeof|instanceof|void)(?![\w$])")
_GOC_DOLLAR = {"json", "input", "node", "now", "today", "env", "workflow", "execution", "itemIndex", "runIndex", "items", "item", "prevNode"}
_ENV_CAM = re.compile(r"^(?:DB_|POSTGRES|PGPASS|N8N_ENCRYPTION|N8N_USER_MANAGEMENT|N8N_RUNNERS_AUTH|.*ENCRYPTION|.*JWT_SECRET|.*MASTER_KEY|.*PRIVATE_KEY)", re.IGNORECASE)
# Chủ dự án chốt 21/11/2026 là 2 phút, nhưng mẫu thật `retail_sepay_poll` của Body hỏi SePay MỖI PHÚT (minutesInterval=1); đặt 2 thì mẫu đó
# bị từ chối và rớt khỏi dữ liệu huấn luyện. Giữ 1 tới khi Body đổi mẫu đó sang 2 phút, rồi đổi hằng này (một chỗ) và test.
LICH_TOI_THIEU_PHUT = 1
_HEADER_BI_MAT = {"authorization", "cookie", "x-api-key", "x-api-token", "x-auth-token"}


def _loi_bieu_thuc(bt: str) -> str | None:
    """Lý do một chuỗi biểu thức n8n (bắt đầu bằng `=`) bị chặn, hoặc None. Chỉ kiểm phần trong `{{ }}`; phần ngoài là chữ thường."""
    for seg in re.findall(r"\{\{(.*?)\}\}", bt, re.S):
        tho = _LITERAL_CHUOI.sub("''", seg)       # bỏ nội dung chuỗi chữ: chữ "process" trong câu thông báo không phải mã
        if re.search(r"[\\`;]|=>|/\*|//|\.\.\.", tho):
            return "ký tự không được phép (\\ ` ; => ... // /*)"
        m = _TU_CAM.search(tho) or _TU_KHOA.search(re.sub(r"\bnew\s+Date\b", "Date", tho))   # `new Date()` có thật trong mẫu của Body
        if m:
            return f'từ "{m.group(0)}" bị chặn'
        for d in re.findall(r"\$([A-Za-z_]+)", tho):
            if d not in _GOC_DOLLAR:
                return f'biến "${d}" không được phép'
        if re.search(r"\[(?!\s*(?:''|\d+)?\s*\])", tho):    # sau khi bỏ chuỗi chữ: chỉ nhận [], [số] hoặc ['chuỗi chữ'] đứng một mình
            return "truy cập thuộc tính bằng chỉ số tính toán ([...]) không được phép; chỉ nhận số nguyên hoặc chuỗi chữ"
        for lit in re.findall(r"\[\s*['\"]((?:[^'\"\\]|\\.)*)['\"]\s*\]", seg):
            if "\\" in lit or _TU_CAM.search(lit):
                return f'khoá thuộc tính "{lit[:30]}" bị chặn'
        for env in re.findall(r"\$env\s*(?:\.\s*|\[\s*['\"])([A-Za-z0-9_]+)", seg):
            if _ENV_CAM.search(env):
                return f'biến môi trường "{env}" là cấu hình của n8n/máy chủ, không được đọc'
    return None


def _duyet_bieu_thuc(obj: Any, duong: str = "") -> str | None:
    if isinstance(obj, str):
        if obj.lstrip().startswith("="):
            ly_do = _loi_bieu_thuc(obj.lstrip())
            if ly_do:
                return f'"{duong}": {ly_do}'
    elif isinstance(obj, dict):
        for k, v in obj.items():
            r = _duyet_bieu_thuc(v, f"{duong}.{k}" if duong else str(k))
            if r:
                return r
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            r = _duyet_bieu_thuc(v, f"{duong}[{i}]")
            if r:
                return r
    return None


def _loi_url(url: str) -> str | None:
    if url.lstrip().startswith("="):
        if re.match(r"^=\s*(?:\{\{\s*\$env\.\w+\s*\}\}|https?://[^/{}\s]+)", url.lstrip()):
            return None
        # Địa chỉ nằm ở trường dữ liệu của chính luồng (`$json.target_url`, có thật trong mẫu `shared_notify`) thì nhận;
        # dữ liệu do người gọi webhook gửi (`body`, `query`, `headers`, `params`) hay chuỗi ghép thì không.
        tr = re.fullmatch(r"=\s*\{\{\s*\$json((?:\.\w+)+)\s*\}\}", url.lstrip())
        if tr and not re.search(r"\.(?:body|query|headers|params)(?:\.|$)", tr.group(1)):
            return None
        return ("URL dựng từ biểu thức ở phần máy chủ; chỉ nhận biến môi trường, máy chủ viết sẵn, hoặc một trường dữ liệu của luồng "
                "(không phải body/query/headers/params của webhook)")
    u = urlparse(url.strip())
    host = (u.hostname or "").lower()
    if host == "localhost" and u.port == 5678 and u.path.startswith("/webhook"):
        return None    # workflow gọi webhook của chính n8n: có thật trong mẫu của Body (retail_sepay_poll, retail_woo_poll)
    if u.scheme not in ("http", "https") or not host:
        return "URL phải là http hoặc https và có máy chủ"
    if u.username is not None or u.password is not None:
        return "URL không được chứa tên đăng nhập/mật khẩu"
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost")) or host.startswith("metadata."):
        return f'máy chủ nội bộ "{host}" không được gọi'
    try:
        if not ipaddress.ip_address(host).is_global:
            return f'địa chỉ IP không công khai "{host}" không được gọi'
    except ValueError:
        if re.fullmatch(r"(?:0x[0-9a-f]+|\d+)(?:\.(?:0x[0-9a-f]+|\d+))*", host):
            return f'địa chỉ IP dạng rút gọn/số "{host}" không được gọi'
    return None


def _loi_tham_so_nguy_hiem(ntype: str, params: dict) -> str | None:
    if ntype == "n8n-nodes-base.httpRequest":
        url = params.get("url")
        if isinstance(url, str) and (r := _loi_url(url)):
            return r
        opt = params.get("options") or {}
        if not isinstance(opt, dict):
            opt = {}
        if opt.get("allowUnauthorizedCerts") is True:
            return "không được tắt kiểm chứng chỉ TLS (allowUnauthorizedCerts)"
        if opt.get("proxy"):
            return "không được đặt proxy"
        hp = params.get("headerParameters")
        for h in (hp.get("parameters", []) if isinstance(hp, dict) else []):
            if (isinstance(h, dict) and str(h.get("name", "")).strip().lower() in _HEADER_BI_MAT
                    and isinstance(h.get("value"), str) and h["value"].strip() and not h["value"].lstrip().startswith("=")):
                return f'header "{h.get("name")}" mang giá trị viết sẵn; bí mật phải nằm trong credentials của n8n hoặc biến môi trường'
    if ntype == "n8n-nodes-base.scheduleTrigger":
        rule = params.get("rule") or {}
        ds = rule.get("interval") if isinstance(rule, dict) else None
        for it in ds if isinstance(ds, list) else []:
            if not isinstance(it, dict):
                continue
            if it.get("field") == "seconds":
                return f"lịch chạy theo giây không được phép (tối thiểu {LICH_TOI_THIEU_PHUT} phút một lần)"
            mi = it.get("minutesInterval")
            if it.get("field") == "minutes" and isinstance(mi, (int, float)) and mi < LICH_TOI_THIEU_PHUT:
                return f"lịch chạy dưới {LICH_TOI_THIEU_PHUT} phút không được phép"
            cron = str(it.get("expression", "")).split()
            if it.get("field") == "cronExpression":
                if len(cron) > 5:
                    return "biểu thức cron 6 trường (có giây) không được phép"
                if LICH_TOI_THIEU_PHUT > 1 and cron and cron[0] in ("*", "*/1"):
                    return f"cron chạy mỗi phút không được phép (tối thiểu {LICH_TOI_THIEU_PHUT} phút một lần)"
    return None


def validate_workflow(obj: Any) -> tuple[bool, str]:
    """
    Kiểm tra workflow n8n. Trả (ok, lý_do_lỗi).

    Lý do lỗi viết tiếng Việt, CỤ THỂ — nó được đưa thẳng vào feedback retry, và
    feedback cụ thể sửa đúng hơn nhiều so với "thử lại đi".
    """
    catalog = get_node_catalog()

    if not isinstance(obj, dict):
        return False, "output không phải object JSON"
    if obj.get("action") != "create_workflow":
        return False, 'thiếu hoặc sai "action" (phải là "create_workflow")'

    name = obj.get("name")
    if not isinstance(name, str) or not name.strip():
        return False, 'thiếu "name" của workflow'

    payload = obj.get("payload")
    if not isinstance(payload, dict):
        return False, 'thiếu "payload"'

    nodes = payload.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return False, '"payload.nodes" rỗng hoặc không phải mảng'

    if obj.get("active") is True or payload.get("active") is True:
        return False, 'không được đặt "active": true; workflow do model sinh ra phải tạo ở trạng thái tắt, người duyệt mới bật'
    if payload.get("pinData"):
        return False, 'không được kèm "pinData" (dữ liệu cố định nhúng trong workflow)'

    node_names: set[str] = set()
    trigger_count = 0

    for idx, node in enumerate(nodes):
        if not isinstance(node, dict):
            return False, f"node[{idx}] không phải object"

        nname = node.get("name")
        if not isinstance(nname, str) or not nname.strip():
            return False, f'node[{idx}] thiếu "name"'
        if nname in node_names:
            return False, (
                f'trùng tên node: "{nname}". '
                "n8n định tuyến theo TÊN nên tên phải là duy nhất"
            )
        node_names.add(nname)

        ntype = node.get("type")
        if ntype in BLOCKED_NODE_TYPES:
            return False, (
                f'node "{nname}" dùng "{ntype}" — bị chặn vì cho phép chạy mã tuỳ ý. '
                "Dùng httpRequest gọi API của ANSER Body thay thế."
            )
        if ntype not in catalog:
            return False, (
                f'node "{nname}" dùng type không được phép: "{ntype}". '
                f"Chỉ được dùng: {', '.join(allowed_types())}"
            )

        if not isinstance(node.get("typeVersion"), (int, float)):
            return False, (
                f'node "{nname}" thiếu "typeVersion" '
                f'(đúng phải là {catalog[ntype]["typeVersion"]})'
            )

        pos = node.get("position")
        if (
            not isinstance(pos, list)
            or len(pos) != 2
            or not all(isinstance(v, (int, float)) for v in pos)
        ):
            return False, f'node "{nname}" có "position" sai — phải là mảng 2 số [x, y]'

        if not isinstance(node.get("parameters"), dict):
            return False, f'node "{nname}" thiếu "parameters" (object, có thể rỗng {{}})'

        cho_bi_mat = _khoa_bi_mat(node["parameters"])
        if cho_bi_mat:
            return False, (
                f'node "{nname}" ghi bí mật thẳng vào parameters ("{cho_bi_mat}"). '
                "Mật khẩu, khoá API, token KHÔNG được nằm trong workflow: dùng mục credentials của n8n "
                "và để parameters không chứa giá trị đó."
            )

        loi = _duyet_bieu_thuc(node["parameters"]) or _loi_tham_so_nguy_hiem(ntype, node["parameters"])
        if loi:
            return False, (
                f'node "{nname}" có biểu thức/tham số không an toàn: {loi}. '
                "Chỉ dùng biểu thức đơn giản ({{ $json.truong }}, $('Tên node').item.json.truong, $now) và gọi máy chủ qua biến môi trường."
            )

        if catalog[ntype].get("trigger"):
            trigger_count += 1

        # Luật an toàn: postgres chỉ đọc
        if ntype == "n8n-nodes-base.postgres":
            for sql in _collect_sql(node):
                hit = _DANGEROUS_SQL.search(sql)
                if hit:
                    return False, (
                        f'node "{nname}" chứa lệnh SQL ghi dữ liệu ({hit.group(0).upper()}). '
                        "Node postgres CHỈ được SELECT; muốn ghi thì dùng httpRequest "
                        "gọi API của ANSER Body."
                    )
                if "SELECT" not in sql.upper():
                    return False, f'node "{nname}" phải là câu SELECT'

    if trigger_count == 0:
        return False, (
            "workflow không có node trigger. Phải có đúng 1 trong: "
            + ", ".join(sorted(trigger_types()))
        )
    if trigger_count > 1:
        return False, f"workflow có {trigger_count} node trigger, chỉ được đúng 1"

    connections = payload.get("connections")
    if not isinstance(connections, dict):
        return False, '"payload.connections" phải là object'
    if len(nodes) > 1 and not connections:
        return False, "workflow nhiều node nhưng connections rỗng — các node không nối với nhau"

    linked: set[str] = set()

    for src, outputs in connections.items():
        if src not in node_names:
            return False, f'connections trỏ từ node không tồn tại: "{src}"'
        if not isinstance(outputs, dict):
            return False, f'connections["{src}"] phải là object có khoá "main"'

        main = outputs.get("main")
        if not isinstance(main, list):
            return False, f'connections["{src}"].main phải là mảng'

        for branch in main:
            if not isinstance(branch, list):
                return False, (
                    f'connections["{src}"].main phải là MẢNG CỦA MẢNG '
                    "(mỗi output một mảng đích)"
                )
            for link in branch:
                if not isinstance(link, dict):
                    return False, f'connections["{src}"] có phần tử không phải object'
                dest = link.get("node")
                if dest not in node_names:
                    return False, f'connections["{src}"] trỏ tới node không tồn tại: "{dest}"'
                linked.add(dest)
                linked.add(src)

    if len(nodes) > 1:
        orphans = node_names - linked
        if orphans:
            return False, (
                "node không được nối vào luồng nào: "
                + ", ".join(f'"{o}"' for o in sorted(orphans))
            )

    return True, ""


__all__ = [
    "DEFAULT_NODE_CATALOG",
    "BLOCKED_NODE_TYPES",
    "load_catalog_from_templates",
    "load_examples_from_templates",
    "reload_catalog",
    "get_node_catalog",
    "is_using_real_templates",
    "allowed_types",
    "catalog_fingerprint",
    "trigger_types",
    "build_workflow_schema",
    "gioi_han_chuoi_grammar",
    "render_node_catalog",
    "render_examples",
    "validate_workflow",
]
