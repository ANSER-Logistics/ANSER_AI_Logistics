"""
tests/integration/workflows/test_workflow_khong_chua_bi_mat.py — workflow model sinh ra không được ghi bí mật thẳng vào `parameters` (R2b).

VÌ SAO CÓ FILE NÀY
------------------
Đo ở `anser-v4` (Thành, #91, 20/11/2026): hai lần model tự viết `smtpPassword` vào `parameters.options` của node `emailSend`
thay vì dùng credentials của n8n. Giá trị đó là chuỗi rác lặp ("Y7Y7Y7…"), nhưng chỗ đặt mật khẩu bằng chữ thường là chỗ người
dùng sẽ điền mật khẩu THẬT, và workflow nằm nguyên văn trong n8n lẫn lịch sử chat. `validate_workflow` trước đó không có luật nào
chặn nó. Luật mới: khoá giống chỗ đặt bí mật mà có giá trị chữ khác rỗng và không phải biểu thức n8n (`=...`) thì bị từ chối,
kèm lý do chỉ về credentials để vòng thử lại sửa đúng.

Phép kiểm "không chặn oan" quan trọng không kém: mọi workflow thật của Body và mọi mẫu của repo PHẢI vẫn qua.
"""

from __future__ import annotations

import copy
import glob
import json
from pathlib import Path

import pytest

from src.core import workflow_schema as ws

REPO = Path(__file__).resolve().parents[3]


def _wf(tham_so_email: dict) -> dict:
    return {
        "action": "create_workflow",
        "name": "gui bao cao",
        "payload": {
            "nodes": [
                {"name": "Hen gio", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2,
                 "position": [0, 0], "parameters": {}},
                {"name": "Gui mail", "type": "n8n-nodes-base.emailSend", "typeVersion": 2.1,
                 "position": [240, 0], "parameters": tham_so_email},
            ],
            "connections": {"Hen gio": {"main": [[{"node": "Gui mail", "type": "main", "index": 0}]]}},
        },
    }


def test_bat_dau_tu_workflow_hop_le():
    """Chốt chống xanh suông: nếu workflow nền đã hỏng vì lý do khác thì các ca dưới không chứng minh gì."""
    assert ws.validate_workflow(_wf({"toEmail": "a@x.vn", "subject": "bao cao"})) == (True, "")


@pytest.mark.parametrize("tham_so", [
    {"options": {"smtpPassword": "Y7Y7Y7Y7"}},                     # đúng ca của v4
    {"smtpPassword": "matkhau-that"},
    {"password": "abc"},
    {"options": {"nested": [{"apiKey": "sk-xxxx"}]}},               # sâu trong mảng
    {"client_secret": "s3cr3t"},
    {"options": {"privateKey": "-----BEGIN"}},
    {"accessToken": "tok"},
    {"headerParameters": {"parameters": [{"name": "x", "value": "y"}]}, "Bearer": "abc"},
])
def test_khoa_bi_mat_co_gia_tri_chu_thi_bi_tu_choi(tham_so):
    ok, ly_do = ws.validate_workflow(_wf(tham_so))
    assert ok is False
    assert "credentials" in ly_do and "Gui mail" in ly_do
    assert "Y7Y7" not in ly_do and "matkhau-that" not in ly_do, "lý do lỗi không được chép lại giá trị bí mật"


@pytest.mark.parametrize("tham_so", [
    {"options": {"smtpPassword": ""}},                              # rỗng: chưa điền gì
    {"options": {"smtpPassword": "   "}},
    {"password": "={{ $env.SMTP_PASSWORD }}"},                      # biểu thức n8n, không phải giá trị
    {"options": {"smtpPassword": 12345}},                           # không phải chuỗi: không đọc là bí mật chữ
    {"subject": "đặt lại password cho khách", "toEmail": "a@x.vn"}, # từ "password" nằm trong GIÁ TRỊ, không phải khoá
    {"headerParameters": {"parameters": [{"name": "X-Internal-Token", "value": "={{ $env.N8N_INTERNAL_TOKEN }}"}]}},
    {"authentication": "predefinedCredentialType", "nodeCredentialType": "smtp"},
])
def test_khong_chan_oan(tham_so):
    assert ws.validate_workflow(_wf(tham_so)) == (True, "")


def test_ly_do_loi_khong_chua_gia_tri_bi_mat_cua_nhieu_khoa():
    ok, ly_do = ws.validate_workflow(_wf({"options": {"smtpPassword": "ABCDEF-that", "ok": 1}}))
    assert ok is False and "ABCDEF" not in ly_do and "options.smtpPassword" in ly_do


def test_moi_workflow_that_va_mau_cua_repo_van_qua_khoa_bi_mat():
    """Không chặn oan: quét mọi `parameters` của mẫu Body và workflow của repo, không được có khoá bí mật nào bị gắn cờ."""
    da_quet = 0
    for f in glob.glob(str(REPO / "data" / "n8n_templates" / "*.json")) + glob.glob(
            str(REPO / "workflows" / "**" / "*.json"), recursive=True):
        d = json.load(open(f, encoding="utf-8"))
        for n in d.get("nodes", []):
            da_quet += 1
            assert ws._khoa_bi_mat(copy.deepcopy(n.get("parameters", {}))) is None, (f, n.get("name"))
    assert da_quet > 50, f"chỉ quét {da_quet} node: đường dẫn mẫu sai?"
