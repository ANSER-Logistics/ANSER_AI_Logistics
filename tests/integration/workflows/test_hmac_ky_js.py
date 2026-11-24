"""
tests/integration/workflows/test_hmac_ky_js.py — bản ký JavaScript (`workflows/logistics/ky_hmac_v1.js`, cho n8n và Body, issue #225) không được lệch khỏi Python.

`hmac_auth.py` là nguồn của giao thức; file JS là BẢN SAO để người bên n8n/Body khỏi tự đoán (R4: bản sao lệch được). Test này chạy file JS bằng Node trên
bốn vector vàng (chuỗi cần ký và chữ ký phải ra đúng từng byte như Python) và cho `hmac_auth.kiem` kiểm lại header do JS tạo ra.

Cần Node (có sẵn trên runner ubuntu-latest của CI và trên máy dev). Thiếu Node thì SKIP: skip này không khai ở SKIP_DA_KHAI vì CI luôn có Node; nếu một
ngày CI mất Node thì guard #29 sẽ đỏ, đúng ý muốn.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.api import hmac_auth as h
from tests.integration.api.test_hmac_auth import KHOA, VECTOR

NODE = shutil.which("node")
JS = Path(__file__).resolve().parents[3] / "workflows" / "logistics" / "ky_hmac_v1.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="không có Node trên máy này")


def _chay(vao: dict) -> dict:
    r = subprocess.run([NODE, str(JS)], input=json.dumps(vao), capture_output=True, text=True, timeout=30, encoding="utf-8")
    assert r.returncode == 0, r.stderr[:500]
    return json.loads(r.stdout)


def _tham_so(v) -> dict:
    _, key_id, ts, nonce, method, path, query, body_hex, _, _ = v
    return {"keyId": key_id, "timestamp": ts, "nonce": nonce, "method": method, "path": path, "rawQuery": query, "bodyHex": body_hex}


def test_js_ra_dung_chuoi_can_ky_va_chu_ky_cua_bon_vector_vang():
    vao = {"chuoi": [_tham_so(v) for v in VECTOR], "ky": [{**_tham_so(v), "key": KHOA.decode()} for v in VECTOR]}
    ra = _chay(vao)
    assert ra["chuoi"] == [v[8] for v in VECTOR]
    assert ra["ky"] == [v[9] for v in VECTOR]


def test_js_khoa_la_van_ban_utf8_khong_giai_ma_hex():
    """Khoá toàn ký tự hex vẫn phải dùng NGUYÊN VĂN như chuỗi, không được giải mã thành byte (lệch Python/TypeScript)."""
    v = VECTOR[0]
    khoa_hex = "0123456789abcdef" * 4
    ra = _chay({"ky": [{**_tham_so(v), "key": khoa_hex}]})
    assert ra["ky"] == [v[9]]
    khac = _chay({"ky": [{**_tham_so(v), "key": bytes.fromhex(khoa_hex).decode("latin-1")}]})
    assert khac["ky"] != [v[9]]


def test_header_do_js_tao_ra_duoc_python_chap_nhan():
    v = VECTOR[0]
    now_ms = 1_790_000_100_000
    ra = _chay({"header": [{"keyId": "body-1", "key": KHOA.decode(), "method": "POST", "path": "/tools/quote", "rawQuery": "", "bodyHex": v[7], "nowMs": now_ms,
                            "nonce": "0123456789abcdef0123456789abcdef"}]})["header"][0]
    assert ra["X-Timestamp"] == "1790000100"
    hdr = {k.lower(): val for k, val in ra.items()}
    kq = h.kiem(method="POST", path="/tools/quote", raw_query="", headers=hdr, body=bytes.fromhex(v[7]), bay_gio=1_790_000_100.0, kho=h.KhoNonce(),
                khoa={"body-1": KHOA})
    assert kq == h.KetQua(True, "ok", "body-1")


def test_moi_lan_goi_co_nonce_moi_va_chu_ky_khac_nhau():
    """Thử lại phải gọi lại hàm ký: nonce không được lặp (Brain từ chối phat_lai)."""
    mot = {"keyId": "n8n-1", "key": KHOA.decode(), "method": "POST", "path": "/tools/ping", "rawQuery": "", "bodyHex": "", "nowMs": 1_790_000_100_000}
    ra = _chay({"header": [mot, mot]})["header"]
    assert ra[0]["X-Nonce"] != ra[1]["X-Nonce"]
    assert ra[0]["X-Signature"] != ra[1]["X-Signature"]
    kho = h.KhoNonce()
    for r in ra:
        hdr = {k.lower(): val for k, val in r.items()}
        kq = h.kiem(method="POST", path="/tools/ping", raw_query="", headers=hdr, body=b"", bay_gio=1_790_000_100.0, kho=kho, khoa={"n8n-1": KHOA})
        assert kq.ok, kq
    # gửi lại Y NGUYÊN lần đầu (cùng nonce) thì bị từ chối
    hdr0 = {k.lower(): val for k, val in ra[0].items()}
    lai = h.kiem(method="POST", path="/tools/ping", raw_query="", headers=hdr0, body=b"", bay_gio=1_790_000_100.0, kho=kho, khoa={"n8n-1": KHOA})
    assert lai.ly_do == h.PHAT_LAI


def test_than_khac_mot_byte_thi_sai_chu_ky():
    v = VECTOR[0]
    ra = _chay({"header": [{"keyId": "body-1", "key": KHOA.decode(), "method": "POST", "path": "/tools/quote", "rawQuery": "", "bodyHex": v[7],
                            "nowMs": 1_790_000_100_000, "nonce": "0123456789abcdef0123456789abcdef"}]})["header"][0]
    hdr = {k.lower(): val for k, val in ra.items()}
    kq = h.kiem(method="POST", path="/tools/quote", raw_query="", headers=hdr, body=bytes.fromhex(v[7]) + b" ", bay_gio=1_790_000_100.0,
                kho=h.KhoNonce(), khoa={"body-1": KHOA})
    assert kq.ly_do == h.SAI_CHU_KY


def test_method_viet_thuong_van_ky_nhu_viet_hoa():
    """Python viết hoa method trước khi ký; JS phải làm giống (n8n hay để method chữ thường)."""
    v = VECTOR[0]
    ra = _chay({"ky": [{**_tham_so(v), "method": "post", "key": KHOA.decode()}]})
    assert ra["ky"] == [v[9]]
