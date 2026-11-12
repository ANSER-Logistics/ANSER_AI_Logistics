"""
tests/test_n8n_gio_viet_nam.py — "hôm nay" trong workflow n8n phải là ngày GIỜ VIỆT NAM.

Mọi chỗ cũ dùng `new Date().toISOString().slice(0, 10)` — ngày UTC. Từ 00:00 đến 07:00
sáng ở Việt Nam, ngày UTC vẫn là hôm qua, nên:

  - báo giá: giá chào hết hạn hôm qua còn được dùng thêm 7 tiếng; giá bắt đầu hiệu lực
    hôm nay bị loại;
  - nhắc nợ: khoản đáo hạn hôm qua chưa bị coi là quá hạn, số ngày quá hạn lệch một;
  - đồng bộ giá dầu: chạy lúc sáng sớm ở VN thì đóng dấu giá lùi một ngày, và báo giá
    ghi "giá dầu đã cũ 1 ngày" dù vừa lấy (AGENTS §3.1c: giá phải sát thời gian thực).

Chủ dự án uỷ quyền chốt UTC+7 (brain#217; Body PR #33 cũng độc lập chọn UTC+7).

Test chạy ĐOẠN JS THẬT trong Node với `Date.now` bị cố định. Mã mới dùng `Date.now()` chứ
không `new Date()` trần chính là để đồng hồ giả này tác động được.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent / "workflows" / "logistics"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="cần Node để chạy đoạn JS thật của workflow n8n (CI có sẵn Node)",
)

# 20:00 UTC ngày 12/11 = 03:00 sáng ngày 13/11 ở Việt Nam.
KHUYA_UTC = "2026-11-12T20:00:00Z"
VN_NGAY = "2026-11-13"
UTC_NGAY = "2026-11-12"

_HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const t0 = Date.parse(input.now);
Date.now = () => t0;
const rows = r => ({ all: () => r.map(json => ({ json })), first: () => ({ json: r[0] }) });
const nodes = {};
for (const [k, v] of Object.entries(input.nodes || {})) nodes[k] = Array.isArray(v) ? rows(v) : { first: () => ({ json: v }), all: () => [{ json: v }] };
const $ = name => { if (!(name in nodes)) throw new Error('node không có trong harness: ' + name); return nodes[name]; };
$.input = rows(input.input || [{}]);
$.env = {};
const fn = new Function('$', '$input', '$env', input.code);
try { console.log(JSON.stringify({ ok: fn($, $.input, $.env)[0].json })); }
catch (e) { console.log(JSON.stringify({ error: e.message })); }
"""


def _code(file: str, node: str) -> str:
    wf = json.loads((ROOT / file).read_text(encoding="utf-8"))
    return next(n for n in wf["nodes"] if n["name"].startswith(node))["parameters"]["jsCode"]


def _chay(file: str, node: str, *, now: str, nodes: dict | None = None, rows: list | None = None) -> dict:
    payload = json.dumps(
        {"code": _code(file, node), "now": now, "nodes": nodes or {}, "input": rows},
        ensure_ascii=False,
    )
    p = subprocess.run(
        ["node", "-e", _HARNESS], input=payload, capture_output=True,
        text=True, encoding="utf-8", timeout=30,
    )
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert "ok" in out, out
    return out["ok"]


# ---------------------------------------------------------------------------
# Đồng bộ giá dầu
# ---------------------------------------------------------------------------

_HTML = "<td>Dầu DO</td><td>21.500</td>"


def test_dong_bo_gia_dau_dong_dau_ngay_gio_viet_nam():
    ra = _chay("logistics_fuel_price_sync.json", "Bóc giá diesel", now=KHUYA_UTC, rows=[{"data": _HTML}])
    assert ra["date"] == VN_NGAY, f"đóng dấu theo ngày UTC ({UTC_NGAY}) làm giá lùi một ngày: {ra}"
    assert ra["price"] == 21_500


def test_dong_bo_gia_dau_ban_ngay_van_dung():
    ra = _chay("logistics_fuel_price_sync.json", "Bóc giá diesel", now="2026-11-12T05:00:00Z",
               rows=[{"data": _HTML}])
    assert ra["date"] == UTC_NGAY      # 12:00 trưa VN, cùng ngày ở cả hai múi giờ


# ---------------------------------------------------------------------------
# Nhắc nợ
# ---------------------------------------------------------------------------

def _no(due: str) -> dict:
    return {"status": "open", "due_date": due, "amount": 1_000_000, "paid_amount": 0,
            "customer_name": "Hùng Phát", "quote_id": "QD-1"}


def test_nhac_no_khoan_den_han_hom_qua_la_qua_han_theo_gio_vn():
    ra = _chay("logistics_debt_reminder.json", "Lọc quá hạn", now=KHUYA_UTC, rows=[_no(UTC_NGAY)])
    assert ra["has_overdue"] is True, "03:00 ngày 13 ở VN: khoản hạn 12/11 đã quá hạn"
    assert "quá hạn 1 ngày" in json.loads(ra["discord_body"])["embeds"][0]["description"]


def test_nhac_no_khoan_den_han_hom_nay_chua_qua_han():
    ra = _chay("logistics_debt_reminder.json", "Lọc quá hạn", now=KHUYA_UTC, rows=[_no(VN_NGAY)])
    assert ra["has_overdue"] is False


# ---------------------------------------------------------------------------
# Báo giá: hiệu lực của giá chào
# ---------------------------------------------------------------------------

_REQ = {"origin": "Hữu Nghị", "destination": "Bắc Ninh", "vehicle_type": "3T"}


def _ctx(quotes: list) -> dict:
    return {
        "Nhận yêu cầu báo giá": {"body": _REQ},
        "Đọc Carriers": [{"id": "C001", "name": "Hùng Phát", "vehicle_types": "3T"}],
        "Đọc CarrierQuotes": quotes,
        "Đọc PricingRules": [{"name": "Mặc định", "base_margin_pct": "12", "fuel_baseline_price": "25000"}],
        "Đọc FuelIndex": [{"date": "2026-11-05", "fuel_type": "diesel", "price": "27500"}],
        "Đọc Routes": [{"id": "R003", "origin": "Hữu Nghị", "destination": "Bắc Ninh"}],
    }


def _q(carrier: str, gia: int, **kw) -> dict:
    return {"carrier_id": carrier, "route_id": "R003", "vehicle_type": "3T", "price": gia,
            "valid_from": "2000-01-01", "valid_to": "2999-12-31"} | kw


def _offers(quotes: list) -> list[str]:
    ra = _chay("logistics_quote_request.json", "Ghép dữ liệu", now=KHUYA_UTC, nodes=_ctx(quotes))
    return [o["carrier_id"] for o in ra["payloadSelection"]["offers"]]


def test_gia_het_han_hom_qua_khong_duoc_dung_them_7_tieng():
    assert _offers([_q("C1", 1, valid_to=UTC_NGAY), _q("C2", 2)]) == ["C2"]


def test_gia_bat_dau_hieu_luc_hom_nay_theo_gio_vn_duoc_dung():
    assert _offers([_q("C1", 1, valid_from=VN_NGAY), _q("C2", 2, valid_from="2026-11-14")]) == ["C1"]


def test_ma_nhap_nhap_dung_ngay_vn_trong_id_nhap():
    ctx = _ctx([_q("C1", 1)])
    ghep = _chay("logistics_quote_request.json", "Ghép dữ liệu", now=KHUYA_UTC, nodes=ctx)
    nodes = {
        "Ghép dữ liệu": ghep,
        "Lấy hãng đầu bảng": {"top": {"carrier_id": "C1", "name": "Hùng Phát"},
                              "selection": {"explain": {}}, "quotePayload": {}},
    }
    q = {"quote": {"quoted_price": 1, "surcharges": []}, "internal": {}, "warnings": []}
    ra = _chay("logistics_quote_request.json", "Dựng nháp", now=KHUYA_UTC, nodes=nodes, rows=[q])
    assert ra["draftRow"]["id"].startswith("QD-20261113-"), ra["draftRow"]["id"]


# ---------------------------------------------------------------------------
# Phía Brain dùng cùng định nghĩa "hôm nay"
# ---------------------------------------------------------------------------

def test_brain_hom_nay_theo_gio_vn_khong_theo_may_chu():
    from datetime import date, datetime, timezone

    from src.core import pricing

    assert pricing.hom_nay_vn(datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc)) == date(2026, 11, 13)
    assert pricing.hom_nay_vn(datetime(2026, 11, 12, 16, 59, tzinfo=timezone.utc)) == date(2026, 11, 12)
    assert pricing.hom_nay_vn(datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)) == date(2026, 11, 13)


def test_tuoi_gia_dau_mac_dinh_tinh_theo_ngay_vn(monkeypatch):
    from datetime import date

    from src.core import pricing

    monkeypatch.setattr(pricing, "hom_nay_vn", lambda *a, **k: date(2026, 11, 13))
    tuoi, _ = pricing._tuoi_gia_dau("2026-11-13", None)
    assert tuoi == 0, "giá dầu đóng dấu ngày VN hôm nay không được hiện là cũ 1 ngày"
