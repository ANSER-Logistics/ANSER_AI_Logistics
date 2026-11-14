"""
tests/test_nguong_tuoi_gia_dau.py — báo giá dựa trên giá dầu CŨ phải bị chặn, không chỉ ghi lại.

AGENTS §3.1c: "hôm nay 25 nghìn, ngày mai 30 nghìn". PR #41 mới ĐO tuổi giá dầu; con số
ngưỡng chờ chủ dự án. Chủ dự án uỷ quyền agent chọn (12/11/2026): tuổi >= 2 ngày thì cảnh
báo, >= 7 ngày thì từ chối (422) — CHỈ khi giá dầu thật sự được dùng để điều chỉnh giá.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core.pricing import PricingRule, compute_quote, doc_nguong_tuoi_gia_dau, hom_nay_vn

HOM_NAY = date(2026, 11, 12)
RULE = PricingRule(base_margin_pct=10, fuel_baseline_price=25_000)


def _tinh(tuoi: int, **kw):
    ngay = (HOM_NAY - timedelta(days=tuoi)).isoformat()
    return compute_quote(1_000_000, kw.pop("rule", RULE), kw.pop("gia", 27_500),
                         fuel_price_as_of=ngay, today=HOM_NAY, **kw)


def _trang_thai(out) -> str:
    return out["internal"]["inputs"]["fuel_price_status"]


@pytest.fixture(autouse=True)
def _khong_phu_thuoc_token(monkeypatch):
    import src.api.dependencies as deps
    import src.api.main as main_mod

    monkeypatch.setattr(deps, "API_AUTH_TOKEN", "")
    monkeypatch.setattr(main_mod, "API_AUTH_TOKEN", "")


# ---------------------------------------------------------------------------
# Biên: giá dầu ĐƯỢC DÙNG
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tuoi", [0, 1])
def test_moi_thi_ok_khong_canh_bao(tuoi):
    out = _tinh(tuoi)
    assert _trang_thai(out) == "ok" and out["warnings"] == []


@pytest.mark.parametrize("tuoi", [2, 6])
def test_tu_2_ngay_canh_bao_nhung_van_tinh(tuoi):
    out = _tinh(tuoi)
    assert _trang_thai(out) == "stale_warn"
    assert any(f"cách {tuoi} ngày" in w for w in out["warnings"]), out["warnings"]
    assert out["quote"]["quoted_price"] > 0


@pytest.mark.parametrize("tuoi", [7, 30])
def test_tu_7_ngay_tu_choi_va_noi_ro_cach_sua(tuoi):
    with pytest.raises(ValueError, match="đồng bộ giá dầu"):
        _tinh(tuoi)


def test_ngay_tuong_lai_van_chi_canh_bao_khong_tu_choi():
    out = _tinh(-1)
    assert _trang_thai(out) == "future"
    assert any("SAU hôm nay" in w for w in out["warnings"])


# ---------------------------------------------------------------------------
# Giá dầu KHÔNG được dùng thì tuổi của nó không làm sai báo giá
# ---------------------------------------------------------------------------

def test_thieu_gia_goc_thi_khong_tu_choi_du_ngay_cu():
    out = _tinh(30, rule=PricingRule(base_margin_pct=10))        # không có fuel_baseline_price
    assert _trang_thai(out) == "not_applied"
    assert not any("cách 30 ngày" in w for w in out["warnings"])


def test_thieu_gia_hien_tai_thi_khong_tu_choi_du_ngay_cu():
    out = _tinh(30, gia=None)
    assert _trang_thai(out) == "not_applied"


def test_khong_ghi_ngay_thi_trang_thai_la_chua_biet_khong_phai_moi():
    out = compute_quote(1_000_000, RULE, 27_500)
    assert _trang_thai(out) == "unknown"          # kiểm bằng ==, không dùng falsy


# ---------------------------------------------------------------------------
# Ngưỡng chỉ ĐỔI việc cảnh báo/từ chối, không đổi con số
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tuoi", [0, 2, 6])
def test_so_tien_khong_doi_theo_tuoi(tuoi):
    goc = compute_quote(1_000_000, RULE, 27_500)
    out = _tinh(tuoi)
    for khoa in ("margin", "fuel_adjustment"):
        assert out["internal"][khoa] == goc["internal"][khoa]
    assert out["quote"] == goc["quote"]


def test_nguong_tuy_chinh_qua_tham_so():
    assert _trang_thai(_tinh(3, canh_bao_ngay=5, tu_choi_ngay=10)) == "ok"
    with pytest.raises(ValueError):
        _tinh(3, canh_bao_ngay=1, tu_choi_ngay=3)


@pytest.mark.parametrize("warn, toi_da", [(0, 7), (5, 3), (-1, 7)])
def test_cap_nguong_vo_ly_bi_tu_choi(warn, toi_da):
    with pytest.raises(ValueError, match="1 <= canh_bao_ngay"):
        compute_quote(1_000_000, RULE, 27_500, canh_bao_ngay=warn, tu_choi_ngay=toi_da)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

def _post(tuoi: int):
    ngay = (hom_nay_vn() - timedelta(days=tuoi)).isoformat()
    return TestClient(app).post("/tools/quote", json={
        "carrier_cost": 1_000_000, "pricing_rule": {"base_margin_pct": 10, "fuel_baseline_price": 25_000},
        "current_fuel_price": 27_500, "fuel_price_as_of": ngay,
    })


def test_route_tuoi_7_tra_422_chi_cach_sua():
    r = _post(7)
    assert r.status_code == 422 and "đồng bộ" in r.json()["detail"]


def test_route_tuoi_3_tra_200_kem_canh_bao():
    r = _post(3)
    assert r.status_code == 200 and r.json()["warnings"]


# ---------------------------------------------------------------------------
# Biến môi trường (không phải bí mật)
# ---------------------------------------------------------------------------

def test_env_trong_thi_dung_mac_dinh(monkeypatch):
    monkeypatch.delenv("FUEL_PRICE_WARN_DAYS", raising=False)
    monkeypatch.delenv("FUEL_PRICE_MAX_DAYS", raising=False)
    assert doc_nguong_tuoi_gia_dau() == (2, 7)


def test_env_hop_le_duoc_dung(monkeypatch):
    monkeypatch.setenv("FUEL_PRICE_WARN_DAYS", "1")
    monkeypatch.setenv("FUEL_PRICE_MAX_DAYS", "3")
    assert doc_nguong_tuoi_gia_dau() == (1, 3)


@pytest.mark.parametrize("warn, toi_da", [("rác", "7"), ("0", "7"), ("5", "3"), ("2", "bảy")])
def test_env_hong_la_loi_cau_hinh_neu_ten_bien(monkeypatch, warn, toi_da):
    monkeypatch.setenv("FUEL_PRICE_WARN_DAYS", warn)
    monkeypatch.setenv("FUEL_PRICE_MAX_DAYS", toi_da)
    with pytest.raises(RuntimeError, match="FUEL_PRICE"):
        doc_nguong_tuoi_gia_dau()
