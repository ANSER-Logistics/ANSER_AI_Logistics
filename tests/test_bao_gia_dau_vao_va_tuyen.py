"""
tests/test_bao_gia_dau_vao_va_tuyen.py — báo giá vận tải: đúng TUYẾN, và ghi lại
giá/thời điểm ĐẦU VÀO.

Hai lỗ hổng, cùng một nguồn gốc (đợt soát 12/11/2026):

1. Workflow n8n `logistics_quote_request` lọc giá chào chỉ theo `vehicle_type`
   và `valid_to`; không đọc sheet Routes, không xét `route_id`. Brain sau đó giữ
   giá chào CUỐI của mỗi nhà xe. Kết quả trên dữ liệu mẫu: yêu cầu xe 3T đi Bắc
   Ninh bị tính bằng giá chào tuyến Bắc Giang của cùng nhà xe — sai, im lặng, và
   đi tới khách. Cùng hình dạng với BR-01.

2. AGENTS §3.1c nói kết quả báo giá "ghi kèm thời điểm và giá đầu vào đã dùng".
   `internal` chỉ có `fuel_ratio`: một báo giá đã gửi không cho biết nó dùng giá
   dầu nào, lấy ngày nào.

Phần n8n chạy ĐOẠN JS THẬT của workflow bằng Node (không mô phỏng lại bằng
Python — mô phỏng lại là kiểm cái mình viết, không phải cái đang chạy).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core.pricing import PricingRule, compute_quote

WORKFLOW = Path(__file__).resolve().parent.parent / "workflows" / "logistics" / "logistics_quote_request.json"

# ---------------------------------------------------------------------------
# 1. Giá và thời điểm đầu vào của báo giá
# ---------------------------------------------------------------------------

_RULE = PricingRule(base_margin_pct=10, fuel_baseline_price=25_000)


def test_inputs_ghi_lai_dung_nhung_so_da_dung():
    out = compute_quote(
        1_000_000, _RULE, 27_500, fuel_price_as_of="2026-11-05", today=date(2026, 11, 12)
    )
    assert out["internal"]["inputs"] == {
        "carrier_cost": 1_000_000,
        "current_fuel_price": 27_500,
        "fuel_baseline_price": 25_000,
        "fuel_price_as_of": "2026-11-05",
        "fuel_price_age_days": 7,
        "fuel_adjustment_applied": True,
    }
    assert out["warnings"] == []


def test_khong_co_gia_dau_thi_noi_thang_la_khong_dieu_chinh():
    """Trước đây thiếu CẢ HAI giá dầu không để lại dấu vết nào."""
    out = compute_quote(1_000_000, PricingRule(base_margin_pct=10))
    ins = out["internal"]["inputs"]
    assert ins["fuel_adjustment_applied"] is False
    assert ins["current_fuel_price"] is None and ins["fuel_price_age_days"] is None


def test_thieu_mot_trong_hai_gia_dau_thi_khong_dieu_chinh_va_van_canh_bao():
    out = compute_quote(1_000_000, _RULE, None)       # có giá gốc, thiếu giá hiện tại
    assert out["internal"]["inputs"]["fuel_adjustment_applied"] is False
    assert any("Chưa lấy được giá dầu" in w for w in out["warnings"])


def test_ngay_gia_dau_trong_tuong_lai_bi_canh_bao():
    out = compute_quote(1_000_000, _RULE, 27_500, fuel_price_as_of="2026-12-01", today=date(2026, 11, 12))
    assert out["internal"]["inputs"]["fuel_price_age_days"] == -19
    assert any("SAU hôm nay" in w for w in out["warnings"])


@pytest.mark.parametrize("sai", ["05/11/2026", "2026-13-40", "hôm qua", "20261105"])
def test_ngay_sai_dinh_dang_bi_tu_choi_chu_khong_doan(sai):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        compute_quote(1_000_000, _RULE, 27_500, fuel_price_as_of=sai)


def test_gia_tinh_ra_khong_doi_khi_them_ngay_gia_dau():
    """Chỉ GHI THÊM — con số báo giá không được đổi vì có thêm thông tin."""
    a = compute_quote(1_000_000, _RULE, 27_500)
    b = compute_quote(1_000_000, _RULE, 27_500, fuel_price_as_of="2026-11-05", today=date(2026, 11, 12))
    assert a["quote"] == b["quote"]
    assert a["internal"]["margin"] == b["internal"]["margin"]


_CLIENT = TestClient(app)


@pytest.fixture(autouse=True)
def _khong_phu_thuoc_token_moi_truong(monkeypatch):
    """Test HTTP ở đây không bàn về cổng token; một API_AUTH_TOKEN còn sót trong môi trường
    của người chạy sẽ biến chúng thành 401 vô cớ (review độc lập 12/11/2026)."""
    import src.api.dependencies as deps
    import src.api.main as main_mod

    monkeypatch.setattr(deps, "API_AUTH_TOKEN", "")
    monkeypatch.setattr(main_mod, "API_AUTH_TOKEN", "")
_BODY = {
    "carrier_cost": 1_000_000,
    "pricing_rule": {"base_margin_pct": 10, "fuel_baseline_price": 25_000},
    "current_fuel_price": 27_500,
}


def test_endpoint_ghi_thoi_diem_tinh_chi_o_phan_noi_bo():
    r = _CLIENT.post("/tools/quote", json=_BODY | {"fuel_price_as_of": "2026-11-05"})
    assert r.status_code == 200
    out = r.json()
    computed_at = out["internal"]["computed_at"]
    assert computed_at.endswith("+00:00") and len(computed_at) == len("2026-11-12T00:00:00+00:00")
    assert out["internal"]["inputs"]["fuel_price_as_of"] == "2026-11-05"
    # Phần ĐƯA RA KHÁCH CUỐI không được lộ gì thêm (P2: biên và đầu vào là nội bộ).
    assert set(out["quote"]) == {"quoted_price", "surcharges", "currency"}


def test_endpoint_van_nhan_loi_goi_cu_khong_co_ngay_gia_dau():
    """Hợp đồng với Body/n8n cũ: trường mới là TUỲ CHỌN, không có thì vẫn chạy."""
    r = _CLIENT.post("/tools/quote", json=_BODY)
    assert r.status_code == 200
    assert r.json()["internal"]["inputs"]["fuel_price_as_of"] is None


def test_endpoint_tra_422_khi_ngay_sai_dinh_dang():
    r = _CLIENT.post("/tools/quote", json=_BODY | {"fuel_price_as_of": "05/11/2026"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 2. Workflow n8n: đúng tuyến
# ---------------------------------------------------------------------------

def _workflow() -> dict:
    return json.loads(WORKFLOW.read_text(encoding="utf-8"))


def _code_of(name: str) -> str:
    for n in _workflow()["nodes"]:
        if n["name"] == name:
            return n["parameters"]["jsCode"]
    raise AssertionError(f"không có node {name!r}")


def test_workflow_doc_sheet_routes_va_noi_day_dung_thu_tu():
    """Cấu trúc (luôn chạy, không cần Node): Routes nằm trên đường tới 'Ghép dữ liệu'."""
    wf = _workflow()
    nodes = {n["name"]: n for n in wf["nodes"]}
    assert nodes["Đọc Routes"]["parameters"]["sheetName"] == "Routes"
    def tiep(ten):
        return [link["node"] for nhanh in wf["connections"][ten]["main"] for link in nhanh]

    assert tiep("Đọc FuelIndex") == ["Đọc Routes"]
    assert tiep("Đọc Routes") == ["Ghép dữ liệu"]


_CO_NODE = shutil.which("node") is not None

# Có skip có lý do, và CI (ubuntu-latest) có sẵn Node nên ở đó các ca này CHẠY.
# Nếu một ngày CI mất Node thì #29 (CI đỏ khi có skip chưa khai) phải bắt được.
_can_node = pytest.mark.skipif(
    not _CO_NODE, reason="cần Node để chạy đoạn JS thật của workflow n8n (CI có sẵn Node)"
)

_HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const rows = r => ({ all: () => r.map(json => ({ json })), first: () => ({ json: r[0] }) });
const nodes = {};
for (const [k, v] of Object.entries(input.nodes)) nodes[k] = Array.isArray(v) ? rows(v) : { first: () => ({ json: v }), all: () => [{ json: v }] };
const $ = name => { if (!(name in nodes)) throw new Error('node không có trong harness: ' + name); return nodes[name]; };
$.input = rows(input.input || [{}]);
const fn = new Function('$', '$input', input.code);
try { console.log(JSON.stringify({ ok: fn($, $.input)[0].json })); }
catch (e) { console.log(JSON.stringify({ error: e.message })); }
"""


def _chay(code: str, nodes: dict, input_rows: list | None = None) -> dict:
    payload = json.dumps({"code": code, "nodes": nodes, "input": input_rows}, ensure_ascii=False)
    p = subprocess.run(
        ["node", "-e", _HARNESS],
        input=payload, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


_ROUTES = [
    {"id": "R001", "origin": "Hữu Nghị", "destination": "Hải Phòng", "origin_lat": "21.0451", "origin_lon": "105.85"},
    {"id": "R002", "origin": "Hữu Nghị", "destination": "Bắc Giang", "origin_lat": "21.0451", "origin_lon": "105.85"},
    {"id": "R003", "origin": "Hữu Nghị", "destination": "Bắc Ninh", "origin_lat": "21.0451", "origin_lon": "105.85"},
]
_XA = "2999-12-31"
_DA = "2000-01-01"


def _quote(carrier, route, price, vt="3T", vf=_DA, vto=_XA):
    return {"carrier_id": carrier, "route_id": route, "vehicle_type": vt, "price": price,
            "valid_from": vf, "valid_to": vto}


def _ctx(req, quotes, routes=None, fuels=None):
    return {
        "Nhận yêu cầu báo giá": {"body": req},
        "Đọc Carriers": [{"id": "C001", "name": "Hùng Phát", "vehicle_types": "3T|5T"}],
        "Đọc CarrierQuotes": quotes,
        "Đọc PricingRules": [{"name": "Mặc định", "base_margin_pct": "12", "fuel_baseline_price": "25000"}],
        "Đọc FuelIndex": fuels if fuels is not None else [{"date": "2026-11-05", "fuel_type": "diesel", "price": "27500"}],
        "Đọc Routes": routes if routes is not None else _ROUTES,
    }


def _ghep(req, quotes, **kw):
    return _chay(_code_of("Ghép dữ liệu"), _ctx(req, quotes, **kw))


_REQ = {"origin": "Hữu Nghị", "destination": "Bắc Ninh", "vehicle_type": "3T"}


@_can_node
def test_gia_chao_chi_lay_dung_tuyen():
    """Ca thật trên dữ liệu mẫu: C001 có giá cho Bắc Giang (R002) và Bắc Ninh (R003)."""
    out = _ghep(_REQ, [_quote("C001", "R002", 1_800_000), _quote("C001", "R003", 2_000_000)])
    assert out["ok"]["route_id"] == "R003"
    offers = out["ok"]["payloadSelection"]["offers"]
    assert offers == [{"carrier_id": "C001", "price": 2_000_000}], (
        f"lẫn giá chào của tuyến khác: {offers}"
    )


@_can_node
@pytest.mark.parametrize("o, d", [("huu nghi", "bac ninh"), ("HỮU  NGHỊ ", " Bắc Ninh"), ("Huu Nghi", "BẮC NINH")])
def test_ten_dia_diem_khop_khong_phan_biet_hoa_thuong_dau_khoang_trang(o, d):
    out = _ghep(_REQ | {"origin": o, "destination": d}, [_quote("C001", "R003", 2_000_000)])
    assert out["ok"]["route_id"] == "R003"


@_can_node
def test_thieu_tuyen_thi_dung_va_noi_ro_khong_doan():
    out = _ghep(_REQ | {"destination": "Lạng Sơn"}, [_quote("C001", "R003", 2_000_000)])
    assert "error" in out and "Chưa có tuyến" in out["error"] and "Lạng Sơn" in out["error"]


@_can_node
def test_routes_trung_tuyen_thi_dung():
    out = _ghep(_REQ, [_quote("C001", "R003", 2_000_000)],
                routes=_ROUTES + [{"id": "R099", "origin": "Hữu Nghị", "destination": "Bắc Ninh"}])
    assert "error" in out and "R003" in out["error"] and "R099" in out["error"]


@_can_node
def test_chi_nhan_gia_chao_dang_con_hieu_luc_ca_hai_dau():
    out = _ghep(_REQ, [
        _quote("C001", "R003", 1_111_111, vto="2000-01-02"),                  # đã hết hạn
        _quote("C002", "R003", 2_222_222, vf="2999-01-01"),                   # chưa tới ngày hiệu lực
        _quote("C003", "R003", 3_333_333),                                    # hợp lệ
        _quote("C004", "R003", 4_444_444, vf="", vto=""),                     # không giới hạn
    ])
    gia = sorted(o["price"] for o in out["ok"]["payloadSelection"]["offers"])
    assert gia == [3_333_333, 4_444_444]


@_can_node
def test_khong_lay_gia_cua_xe_khac_loai():
    out = _ghep(_REQ, [_quote("C001", "R003", 2_000_000, vt="5T")])
    assert out["ok"]["payloadSelection"]["offers"] == []


@_can_node
def test_toa_do_diem_di_duoc_truyen_tu_routes():
    out = _ghep(_REQ, [_quote("C001", "R003", 2_000_000)])
    rq = out["ok"]["payloadSelection"]["request"]
    assert rq["origin_lat"] == 21.0451 and rq["origin_lon"] == 105.85


@_can_node
@pytest.mark.parametrize("ngay, mong", [("2026-11-05", "2026-11-05"), ("2026-11-05T00:00:00", "2026-11-05"),
                                         ("05/11/2026", None), ("", None)])
def test_ngay_gia_dau_chi_di_tiep_khi_dung_dinh_dang(ngay, mong):
    """Sheet có thể trả ngày kiểu khác; sai định dạng thì để None, không để Brain trả 422 cả báo giá."""
    out = _ghep(_REQ, [_quote("C001", "R003", 2_000_000)],
                fuels=[{"date": ngay, "fuel_type": "diesel", "price": "27500"}])
    assert out["ok"]["fuel_price_as_of"] == mong


@_can_node
def test_ngay_gia_dau_di_het_chuoi_toi_tools_quote():
    ghep = _ghep(_REQ, [_quote("C001", "R003", 2_000_000)])["ok"]
    sel = {"ranked": [{"carrier_id": "C001", "name": "Hùng Phát", "offer_price": 2_000_000}], "rejected": []}
    pick = _chay(_code_of("Lấy hãng đầu bảng"), {"Ghép dữ liệu": ghep}, [sel])
    assert pick["ok"]["quotePayload"]["fuel_price_as_of"] == "2026-11-05"
    assert pick["ok"]["quotePayload"]["current_fuel_price"] == 27500


@_can_node
def test_gui_toi_brain_van_duoc_chap_nhan():
    """Payload n8n dựng ra phải qua được schema `extra='forbid'` của Brain (kẻo 422 cả báo giá)."""
    ghep = _ghep(_REQ, [_quote("C001", "R003", 2_000_000)])["ok"]
    r1 = _CLIENT.post("/tools/carrier-selection", json=ghep["payloadSelection"])
    assert r1.status_code == 200, r1.text
    sel = {"ranked": r1.json()["ranked"], "rejected": []}
    pick = _chay(_code_of("Lấy hãng đầu bảng"), {"Ghép dữ liệu": ghep}, [sel])["ok"]
    r2 = _CLIENT.post("/tools/quote", json=pick["quotePayload"])
    assert r2.status_code == 200, r2.text
    assert r2.json()["internal"]["inputs"]["fuel_price_as_of"] == "2026-11-05"


# ---------------------------------------------------------------------------
# 3. Review độc lập 12/11/2026: n8n chạy MỖI DÒNG ĐẦU VÀO, và ngày từ Sheet
# ---------------------------------------------------------------------------

def test_moi_node_doc_sheet_chi_chay_mot_lan_du_webhook_co_nhieu_dong():
    """Node n8n chạy một lần cho MỖI item đến. Webhook gửi N dòng thì đọc Sheet N lần và
    `.all()` nhân bản dữ liệu: cùng một giá chào lọt vào `offers` N lần."""
    # Chỉ node ĐỌC (không có `operation`, mặc định là đọc): node ghi như "Lưu nháp vào Sheet"
    # (append) phải chạy theo từng item, đặt executeOnce cho nó là làm mất dòng.
    doc = [n for n in _workflow()["nodes"]
           if n["type"] == "n8n-nodes-base.googleSheets" and not n["parameters"].get("operation")]
    assert len(doc) == 5, f"mong 5 node đọc Sheet, thấy {[n['name'] for n in doc]}"
    thieu = [n["name"] for n in doc if n.get("executeOnce") is not True]
    assert not thieu, f"node đọc Sheet thiếu executeOnce: {thieu}"


@_can_node
@pytest.mark.parametrize("ngay", ["31/12/2000", "15/07/2999", "hôm qua", "2026-02-30"])
def test_valid_to_khong_doc_duoc_thi_bo_gia_chu_khong_coi_la_con_han(ngay):
    """Bản cũ so CHUỖI THÔ: "31/12/2000" >= "2026-11-12" (vì '3' > '2') nên giá ĐÃ HẾT HẠN
    được dùng — im lặng, và gửi tới khách."""
    out = _ghep(_REQ, [_quote("C001", "R003", 2_000_000, vto=ngay), _quote("C002", "R003", 3_000_000)])["ok"]
    assert [o["carrier_id"] for o in out["payloadSelection"]["offers"]] == ["C002"]
    assert any("C001" in w and "valid_to" in w for w in out["canh_bao_du_lieu"]), out["canh_bao_du_lieu"]


@_can_node
def test_valid_from_khong_doc_duoc_thi_bo_gia():
    out = _ghep(_REQ, [_quote("C001", "R003", 2_000_000, vf="01/01/2000")])["ok"]
    assert out["payloadSelection"]["offers"] == []
    assert any("valid_from" in w for w in out["canh_bao_du_lieu"])


@_can_node
def test_dong_fuelindex_ngay_la_khong_duoc_chen_len_dong_hop_le():
    """"31/12/2000" xếp SAU "2026-11-05" khi so chuỗi -> bản cũ coi nó là giá MỚI NHẤT."""
    fuels = [{"date": "2026-11-05", "fuel_type": "diesel", "price": "27500"},
             {"date": "31/12/2000", "fuel_type": "diesel", "price": "9999"}]
    out = _ghep(_REQ, [_quote("C001", "R003", 2_000_000)], fuels=fuels)["ok"]
    assert out["current_fuel_price"] == 27500 and out["fuel_price_as_of"] == "2026-11-05"
    assert any("FuelIndex" in w for w in out["canh_bao_du_lieu"])


@_can_node
def test_khong_co_dong_fuelindex_doc_duoc_thi_khong_dieu_chinh_gia_dau():
    out = _ghep(_REQ, [_quote("C001", "R003", 2_000_000)],
                fuels=[{"date": "05/11/2026", "fuel_type": "diesel", "price": "27500"}])["ok"]
    assert out["current_fuel_price"] is None and out["fuel_price_as_of"] is None


@_can_node
def test_ngay_hop_le_khong_sinh_canh_bao():
    out = _ghep(_REQ, [_quote("C001", "R003", 2_000_000)])["ok"]
    assert out["canh_bao_du_lieu"] == []


# Brain: ngày đầu vào được GHI LẠI nguyên văn nên chỉ nhận đúng YYYY-MM-DD.
@pytest.mark.parametrize("sai", ["2026-W45-1", "2026-W45", "2026-305"])
def test_ngay_gia_dau_dang_tuan_iso_cung_bi_tu_choi(sai):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        compute_quote(1_000_000, _RULE, 27_500, fuel_price_as_of=sai)


def test_model_khong_duoc_tu_dien_ngay_gia_dau_vao_tool_quote():
    from src.core.doc_dau_vao import chot_dau_vao

    args, _, _ = chot_dau_vao(
        "quote",
        {"carrier_cost": 12_500_000, "pricing_rule": {"base_margin_pct": 8},
         "fuel_price_as_of": "2026-11-12"},
        "Báo giá giúp tôi, giá nhà xe 12.500.000đ",
    )
    assert "fuel_price_as_of" not in args


def test_gỡ_ngày_giá_dầu_cả_khi_câu_rỗng_và_không_đụng_tool_khác():
    from src.core.doc_dau_vao import chot_dau_vao

    assert "fuel_price_as_of" not in chot_dau_vao("quote", {"fuel_price_as_of": "2026-11-12"}, "")[0]
    giu, _, _ = chot_dau_vao("vat", {"fuel_price_as_of": "x"}, "")
    assert giu == {"fuel_price_as_of": "x"}      # chỉ `quote` có khái niệm này
