"""
tests/support/n8n.py — chạy ĐOẠN JS THẬT của một Code node n8n trong Node, với `$()`, `$input`, `$env` giả và đồng hồ cố định.

Mỗi giá trị trong `nodes` là đầu ra của node cùng tên: danh sách = nhiều item (`.all()`), dict = một item (`.first()`).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")

_HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const t0 = Date.parse(input.now);
Date.now = () => t0;
const rows = r => ({ all: () => r.map(json => ({ json })), first: () => ({ json: r[0] }) });
const nodes = {};
for (const [k, v] of Object.entries(input.nodes || {})) nodes[k] = Array.isArray(v) ? rows(v) : rows([v]);
const $ = name => { if (!(name in nodes)) throw new Error('node không có trong harness: ' + name); return nodes[name]; };
const fn = new Function('$', '$input', '$env', input.code);
try { console.log(JSON.stringify({ ok: fn($, rows(input.input || [{}]), input.env || {})[0].json })); }
catch (e) { console.log(JSON.stringify({ error: e.message })); }
"""


def code_node(workflow: str, ten: str) -> str:
    """`workflow` là đường dẫn tính từ gốc repo, ví dụ `workflows/logistics/logistics_quote_request.json`."""
    wf = json.loads((ROOT / workflow).read_text(encoding="utf-8"))
    return next(n for n in wf["nodes"] if n["name"] == ten)["parameters"]["jsCode"]


def chay_code_node(code: str, *, now: str, nodes: dict | None = None, input: list | None = None,
                   env: dict | None = None) -> dict:
    """Trả `{"ok": <json của item đầu ra>}` hoặc `{"error": <thông điệp Error mà node ném>}`."""
    assert NODE, "cần Node trên PATH"
    payload = json.dumps({"code": code, "now": now, "nodes": nodes or {}, "input": input, "env": env or {}},
                         ensure_ascii=False)
    p = subprocess.run([NODE, "-e", _HARNESS], input=payload, capture_output=True, text=True,
                       encoding="utf-8", timeout=30)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)
