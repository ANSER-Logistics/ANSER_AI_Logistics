"""
tests/unit/core/test_a4_phu_phi_am_va_doanh_thu_am.py — hành vi MỚI của A4 (22/11/2026), bên cạnh bộ thuộc tính `test_prop_*`.

- Phụ phí ÂM được phép (chủ dự án chốt 21/11/2026: coi là lỗ), nhưng báo giá thấp hơn giá nhà xe phải NÓI THẲNG (cảnh báo + cờ `below_cost`),
  và báo giá không dương thì bị từ chối (422).
- Doanh thu ÂM (trả hàng) không làm phủ giá vốn ra ngoài [0, 100]; có cảnh báo.
- Năm dưới 4 chữ số sắp xếp đúng; dòng ngày sai không nằm trong bảng mặt hàng; vô cực bị từ chối bằng ValueError.
"""

from __future__ import annotations

import pytest

from src.core.pricing import PricingRule, Surcharge, compute_quote
from src.core.reporting import ReportRequest, SaleLine, build_report


def test_phu_phi_am_nho_van_ra_gia_duong_va_khong_lo():
    out = compute_quote(1_000_000, PricingRule(base_margin_pct=10), None, [Surcharge("giam gia", amount=-50_000)])
    assert out["quote"]["quoted_price"] == 1_050_000 and out["internal"]["below_cost"] is False
    assert not any("THẤP HƠN" in w for w in out["warnings"])


def test_phu_phi_am_lam_gia_thap_hon_gia_nha_xe_thi_noi_thang_so_lo():
    out = compute_quote(1_000_000, PricingRule(base_margin_pct=10), None, [Surcharge("giam sau", amount=-200_000)])
    assert out["quote"]["quoted_price"] == 900_000 and out["internal"]["below_cost"] is True
    canh_bao = next(w for w in out["warnings"] if "THẤP HƠN" in w)
    assert "lỗ 100,000đ" in canh_bao.replace(".", ",") or "lỗ 100.000đ" in canh_bao


def test_bao_gia_khong_duong_bi_tu_choi():
    with pytest.raises(ValueError, match="không dương"):
        compute_quote(1_000, PricingRule(base_margin_pct=10), None, [Surcharge("x", amount=-1_600)])


@pytest.mark.parametrize("cost", [1e28, 1e300, float("inf"), float("nan")])
def test_gia_nha_xe_vo_ly_la_value_error(cost):
    with pytest.raises(ValueError):
        compute_quote(cost, PricingRule(base_margin_pct=10), None)


def test_doanh_thu_am_khong_lam_phu_gia_von_ra_ngoai_0_100_va_co_canh_bao():
    out = build_report(ReportRequest(granularity="month", periods_back=1, sales=[
        SaleLine(date="2026-01-05", revenue=100, product="A", quantity=1, cogs=None),
        SaleLine(date="2026-01-06", revenue=-50, product="A", quantity=1, cogs=10)]))
    pct = out["explain"]["cogs_coverage_pct"]
    assert pct is not None and 0 <= pct <= 100 and out["periods"][0]["cogs_coverage_pct"] == 0.0
    assert any("ÂM" in w for w in out["warnings"])


def test_nam_ngan_sap_xep_dung_va_dong_ngay_sai_khong_vao_bang_mat_hang():
    out = build_report(ReportRequest(granularity="year", periods_back=1, sales=[
        SaleLine(date="0999-12-31", revenue=1, product="A", quantity=1, cogs=0),
        SaleLine(date="1000-01-01", revenue=2, product="B", quantity=1, cogs=0),
        SaleLine(date="", revenue=9, product="Z", quantity=1, cogs=0)]))
    assert [p["period"] for p in out["periods"]] == ["1000"]
    assert "Z" not in [r["product"] for r in out["products"]]


@pytest.mark.parametrize("gia_tri", [float("inf"), float("-inf"), float("nan")])
def test_gia_tri_khong_huu_han_trong_bao_cao_la_value_error(gia_tri):
    with pytest.raises(ValueError):
        build_report(ReportRequest(sales=[SaleLine(date="2026-01-01", revenue=gia_tri, product="A", quantity=1, cogs=None)]))
