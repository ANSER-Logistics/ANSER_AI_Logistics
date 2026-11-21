"""
tests/test_workflow_bieu_thuc_an_toan.py — `validate_workflow` đọc chữ của biểu thức và tham số nguy hiểm (A8, #196).

Hai chiều, vì chiều nào hỏng cũng đắt:
- 20 workflow đối kháng (mô tả ở ghi chú nghiên cứu 20/11/2026) PHẢI bị từ chối, kèm lý do;
- các biểu thức hợp lệ có thật (mẫu của repo, mẫu logistics, ví dụ catalog) PHẢI qua. `test_workflow_khong_chua_bi_mat` đã chạy mọi
  workflow mẫu của Body qua cổng này.
"""

from __future__ import annotations

import pytest

from src.core import workflow_schema as ws


def _wf(node: dict, *, goc: dict | None = None, payload: dict | None = None) -> dict:
    n = {"name": "Buoc", "typeVersion": 1, "position": [240, 0], "parameters": {}, **node}
    obj = {
        "action": "create_workflow",
        "name": "thu",
        "payload": {
            "nodes": [
                {"name": "Hen gio", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0], "parameters": {}},
                n,
            ],
            "connections": {"Hen gio": {"main": [[{"node": "Buoc", "type": "main", "index": 0}]]}},
            **(payload or {}),
        },
        **(goc or {}),
    }
    return obj


def _set(gia_tri: str) -> dict:
    return {"type": "n8n-nodes-base.set", "typeVersion": 3.4, "parameters": {"assignments": {"assignments": [{"name": "x", "value": gia_tri}]}}}


def _http(url: str, **them) -> dict:
    return {"type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "parameters": {"url": url, "method": "GET", **them}}


def _ly_do(obj) -> str:
    ok, ly_do = ws.validate_workflow(obj)
    assert ok is False, "workflow đối kháng lọt qua cổng"
    return ly_do


def test_nen_hop_le():
    assert ws.validate_workflow(_wf(_set("={{ $json.ten }}"))) == (True, "")


# 1..6: sandbox escape bằng biểu thức
@pytest.mark.parametrize("bt", [
    "={{ this.constructor.constructor('return process')() }}",                        # 1: dotted
    "={{ $json['constructor']['constructor']('return 1')() }}",                       # 2: bracket với chuỗi chữ bị chặn
    "={{ $json['con' + 'structor'] }}",                                               # 3: khoá ghép lúc chạy
    "={{ $json[`constructor`] }}",                                                    # 3b: template literal
    "={{ $json.c\\u006fnstructor }}",                                                 # 4: unicode escape
    "={{ with(function(){}){ constructor('return 1')() } }}",                         # 5: CVE-2026-1470
    "={{ (() => { const {constructor} = () => {}; return constructor })() }}",        # 6: CVE-2026-25049
    "={{ process.env.N8N_ENCRYPTION_KEY }}",
    "={{ require('child_process').execSync('id') }}",
    "={{ $json.a ; $json.b }}",
    "={{ [1,2,3] }}",                                                                 # mảng/chỉ số tính toán
    "={{ $json[$json.k] }}",
    "={{ eval('1') }}",
    "={{ new Function('return 1')() }}",
])
def test_bieu_thuc_thoat_hop_cat_bi_tu_choi(bt):
    assert "không an toàn" in _ly_do(_wf(_set(bt)))


# 7, 8: lấy bí mật của n8n/máy chủ
@pytest.mark.parametrize("bt", [
    "={{ $env.N8N_ENCRYPTION_KEY }}",
    "={{ $env['N8N_ENCRYPTION_KEY'] }}",
    "={{ $env.DB_POSTGRESDB_PASSWORD }}",
    "={{ $secrets.provider.key }}",
    "={{ $vars.mat_khau }}",
    "={{ $getWorkflowStaticData('global') }}",
    "={{ $evaluateExpression('1') }}",
])
def test_doc_bi_mat_cua_n8n_bi_tu_choi(bt):
    assert "không an toàn" in _ly_do(_wf(_set(bt)))


# 12, 13, 14: SSRF
@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
    "http://2130706433/",
    "http://0x7f000001/",
    "http://127.1/",
    "http://0/",
    "http://[::ffff:169.254.169.254]/",
    "http://allowed.example@169.254.169.254/",
    "http://localhost:5678/rest/",
    "http://10.0.0.5/admin",
    "http://metadata.google.internal/",
    "file:///etc/passwd",
    "={{ 'http://' + $json.body.host + '/x' }}",
    "={{$json.body.url}}",
])
def test_url_noi_bo_hoac_do_nguoi_goi_chon_bi_tu_choi(url):
    assert "không an toàn" in _ly_do(_wf(_http(url)))


# 15: tuỳ chọn HTTP
@pytest.mark.parametrize("them", [{"options": {"allowUnauthorizedCerts": True}}, {"options": {"proxy": "http://ngoai.example:8080"}}])
def test_tuy_chon_http_nguy_hiem_bi_tu_choi(them):
    assert "không an toàn" in _ly_do(_wf(_http("https://api.example.com/x", **them)))


# 16: lịch chạy
@pytest.mark.parametrize("rule", [
    {"interval": [{"field": "seconds", "secondsInterval": 1}]},
    {"interval": [{"field": "cronExpression", "expression": "* * * * * *"}]},
])
def test_lich_chay_theo_giay_bi_tu_choi(rule):
    n = {"type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "parameters": {"rule": rule}}
    obj = _wf(_set("x"))
    obj["payload"]["nodes"][0] = {**obj["payload"]["nodes"][0], "parameters": n["parameters"]}
    assert "không an toàn" in _ly_do(obj)


# 18: tự kích hoạt và dữ liệu nhúng
def test_active_true_va_pin_data_bi_tu_choi():
    assert "active" in _ly_do(_wf(_set("x"), goc={"active": True}))
    assert "active" in _ly_do(_wf(_set("x"), payload={"active": True}))
    assert "pinData" in _ly_do(_wf(_set("x"), payload={"pinData": {"Buoc": [{"json": {"ten": "x"}}]}}))


# 19: bí mật nằm ở chỗ mà phép kiểm tên khoá không thấy
def test_header_xac_thuc_viet_san_bi_tu_choi():
    hp = {"parameters": [{"name": "Authorization", "value": "Bearer sk-abcdef0123456789abcdef"}]}
    ly_do = _ly_do(_wf(_http("https://api.example.com/x", headerParameters=hp)))
    assert "sk-abcdef" not in ly_do, "lý do lỗi không được chép lại giá trị bí mật"
    assert ws.validate_workflow(_wf(_http("https://api.example.com/x", headerParameters={
        "parameters": [{"name": "Authorization", "value": "={{ 'Bearer ' + $env.ANSER_WEBHOOK_TOKEN }}"}]}))) == (True, "")


def test_url_co_ten_dang_nhap_bi_tu_choi():
    assert "không an toàn" in _ly_do(_wf(_http("https://user:pass@api.example.com/x")))


# Đối chứng: PHẢI qua (hiệu chỉnh, tránh chặn oan)
@pytest.mark.parametrize("bt", [
    "={{$env.ANSER_API}}/api/n8n/internal/low-stock",
    "={{ $json.email_to }}",
    "={{$json.stock_quantity}}",
    "={{ $('Fetch Orders').item.json.total + 1000 }}",
    "={{ $now.toFormat('yyyy-MM-dd') }}",
    "={{ JSON.stringify($json) }}",
    "={{ $json.name.toLowerCase().trim() }}",
    "={{ $json.ten + ' đã xử lý xong process này' }}",         # từ "process" nằm trong chuỗi chữ
    "={{ $json.items[0].gia }}",
    "={{ $json['ten khach'] }}",
    "={{ $env.N8N_INTERNAL_TOKEN }}",
    "Chữ thường có từ constructor và process, không phải biểu thức",
    "constructor",
])
def test_bieu_thuc_hop_le_van_qua(bt):
    assert ws.validate_workflow(_wf(_set(bt))) == (True, "")


@pytest.mark.parametrize("url", [
    "https://api.example.com/x?a=1",
    "={{$env.BRAIN_BASE_URL}}/tools/quote",
    "https://discord.com/api/webhooks/123/abc",
])
def test_url_hop_le_van_qua(url):
    assert ws.validate_workflow(_wf(_http(url))) == (True, "")


def test_lich_chay_theo_phut_gio_van_qua():
    obj = _wf(_set("x"))
    obj["payload"]["nodes"][0]["parameters"] = {"rule": {"interval": [{"field": "hours", "hoursInterval": 4}]}}
    assert ws.validate_workflow(obj) == (True, "")
    obj["payload"]["nodes"][0]["parameters"] = {"rule": {"interval": [{"field": "cronExpression", "expression": "0 7 * * 1-5"}]}}
    assert ws.validate_workflow(obj) == (True, "")
