"""
tests/test_prop_pricing.py — TÍNH CHẤT (property-based) của engine báo giá `src/core/pricing.py` (R1).

VÌ SAO CÓ FILE NÀY
------------------
`test_pricing_and_tools.py` và `test_bao_gia_dau_vao_va_tuyen.py` khoá từng ví dụ viết tay: dầu 25.000 lên 28.000,
biên 10%, mười triệu. Báo giá thì đi thẳng vào email gửi khách cuối, và một ví dụ không nói được điều gì về những
đầu vào người viết không nghĩ tới: biên 0% với giá nhà xe lẻ trăm, dầu rẻ đi tới mức giá gốc chỉ còn 1/40, phụ phí
âm, giá trị vô cực. Ở đây `hypothesis` sinh hàng trăm đầu vào cho mỗi TÍNH CHẤT và co phản ví dụ về dạng nhỏ nhất.

Cách đọc file này
-----------------
Mỗi tính chất là một câu nói được bằng lời, rút từ công thức ở docstring đầu `pricing.py` hoặc từ P1/P2:

  - số học: giá chào khớp công thức (một nhà tính độc lập bằng `Fraction`), tròn bội 1.000đ, nửa bậc làm tròn lên;
  - đơn điệu: giá nhà xe, giá dầu, biên, sàn biên, phụ phí tăng thì giá chào KHÔNG giảm;
  - dầu: giá hiện tại bằng giá gốc thì điều chỉnh bằng 0; dầu lên thì điều chỉnh dương, xuống thì âm;
  - bảo mật (P2): `quote` không chứa khoá nội bộ ở bất kỳ độ sâu nào;
  - tuổi giá dầu (AGENTS §3.1c): đúng bốn bậc ok / cảnh báo / từ chối / tương lai, ĐỒNG HỒ ĐƯỢC TIÊM (`today`),
    không test nào đọc giờ thật của máy;
  - đầu vào hỏng: bị từ chối bằng `ValueError` (route đổi nó thành 422), không ra một con số báo giá lạ.

Phần cuối là các `xfail(strict=True)`: những chỗ hypothesis tìm ra engine HIỆN chưa giữ lời (ghi phản ví dụ nhỏ nhất
ngay tại chỗ). Chúng không phải test bị làm yếu: sửa lỗi xong thì `strict` báo XPASS và buộc người sửa gỡ dấu xfail.

Dữ liệu hoàn toàn hư cấu (R2). Mọi test dùng `CAU_HINH`: `derandomize=True` để CI đỏ thì tái hiện được, không chập
chờn theo hạt giống.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import math
import os
import re
from datetime import date, timedelta
from fractions import Fraction
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from hypothesis import example, given, settings
from hypothesis import strategies as st

import src.api.dependencies as deps
import src.api.main as main_mod
from src.api.main import app
from src.api.routes import tools as tools_mod
from src.core.pricing import (
    MAC_DINH_CANH_BAO_NGAY,
    MAC_DINH_TU_CHOI_NGAY,
    PricingRule,
    Surcharge,
    compute_quote,
    doc_nguong_tuoi_gia_dau,
)

CAU_HINH = settings(derandomize=True, max_examples=200, deadline=None, database=None)

NAN = float("nan")
INF = float("inf")


# ---------------------------------------------------------------------------
# Chiến lược sinh dữ liệu (hư cấu, khoảng thực tế của một chuyến xe tải)
# ---------------------------------------------------------------------------


def _so_thuc(thap: float, cao: float):
    return st.floats(thap, cao, allow_nan=False, allow_infinity=False)


# Giá nhà xe: số NGUYÊN đồng (tiền Việt không có lẻ). Dùng số nguyên cho các tính chất đơn điệu: dấu phẩy động
# đơn điệu theo từng phép nhưng tổ hợp có phép trừ thì có thể lệch 1 ulp, còn bước 1đ lớn hơn sai số đó hàng trăm lần.
GIA_NHA_XE = st.integers(1_000, 10**11).map(float)
GIA_DAU = st.integers(5_000, 200_000).map(float)       # đồng/lít
DO_NHAY = _so_thuc(0.0, 1.0)
BIEN_PCT = _so_thuc(0.0, 200.0)
SAN_BIEN = _so_thuc(0.0, 5e7)

PHU_PHI = st.builds(
    Surcharge,
    name=st.text(min_size=1, max_size=10),
    amount=_so_thuc(0.0, 5e6),
    pct=_so_thuc(0.0, 100.0),
)
DS_PHU_PHI = st.lists(PHU_PHI, max_size=2)

GIA_DAU_HOAC_KHONG = st.one_of(st.none(), GIA_DAU)


def quy_tac(gia_goc=GIA_DAU_HOAC_KHONG, **ghi_de):
    cac_truong = dict(
        base_margin_pct=BIEN_PCT,
        fuel_sensitivity=DO_NHAY,
        fuel_baseline_price=gia_goc,
        min_margin_amount=SAN_BIEN,
        surcharges=DS_PHU_PHI,
    )
    cac_truong.update(ghi_de)
    return st.builds(PricingRule, **cac_truong)


def _gia(cost, rule, gia_dau=None, extra=()):
    """Giá chào (số nguyên VND) của một lần tính."""
    return compute_quote(cost, rule, gia_dau, list(extra))["quote"]["quoted_price"]


def _chinh_xac(cost, rule, gia_dau, extra):
    """Công thức ở docstring đầu `pricing.py`, tính bằng PHÂN SỐ (không sai số dấu phẩy động).

    Trả (chi phí hiệu chỉnh, danh sách phụ phí, biên, biên theo %). Dùng làm "đáp án" cho test số học: đây là bản
    viết lại công thức theo TÀI LIỆU, không phải sao chép thân hàm (không có `_round_step`, không có float).
    """
    f = Fraction
    dieu_chinh = f(0)
    if gia_dau is not None and rule.fuel_baseline_price:
        dieu_chinh = f(cost) * f(rule.fuel_sensitivity) * (f(gia_dau) / f(rule.fuel_baseline_price) - 1)
    chi_phi = f(cost) + dieu_chinh
    phu = [f(s.amount) + chi_phi * f(s.pct) / 100 for s in (*rule.surcharges, *extra)]
    bien_pct = chi_phi * f(rule.base_margin_pct) / 100
    return chi_phi, phu, max(bien_pct, f(rule.min_margin_amount)), bien_pct


def _sai_so(cost, raw: Fraction) -> Fraction:
    """Sai số dấu phẩy động chấp nhận được: 1e-14 tương đối theo cỡ lớn nhất trong phép tính, cộng 1e-6 tuyệt đối."""
    return Fraction(1, 10**6) + (Fraction(cost) + abs(raw)) / 10**14


def _kiem_gia_chao(gia: int, raw: Fraction, cost) -> None:
    """
    `gia` phải đúng bằng `raw` làm tròn nửa-lên về bội 1.000đ, chính xác từng đồng. Chỉ khi `raw` nằm sát một ĐIỂM GIỮA
    (sai số dấu phẩy động đủ để đẩy qua bên kia) mới chấp nhận cả hai bậc kề nhau.
    """
    sai = _sai_so(cost, raw)
    if abs(raw % 1000 - 500) <= sai:
        assert abs(Fraction(gia) - raw) <= 500 + sai
    else:
        assert gia == 1000 * math.floor(raw / 1000 + Fraction(1, 2)), f"raw={float(raw)!r}, gia={gia}"


# ---------------------------------------------------------------------------
# 0. Ví dụ tay đã biết, làm mốc để các tính chất bên dưới không trôi khỏi thực tế
# ---------------------------------------------------------------------------


def test_vi_du_tay_nha_xe_1_trieu_dau_25000_len_27500():
    """Nhà xe 1.000.000, dầu 25.000 -> 27.500, biên 10%, hệ số 0,35: giá chào 1.139.000 (1.138.500 là đúng NỬA bậc)."""
    out = compute_quote(
        1_000_000, PricingRule(base_margin_pct=10, fuel_sensitivity=0.35, fuel_baseline_price=25_000), 27_500
    )
    assert out["internal"]["fuel_adjustment"] == 35_000
    assert out["internal"]["adjusted_cost"] == 1_035_000
    assert out["internal"]["margin"] == 103_500
    assert out["quote"]["quoted_price"] == 1_139_000
    assert out["warnings"] == []


# ---------------------------------------------------------------------------
# 1. Số học
# ---------------------------------------------------------------------------


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(), gia_dau=GIA_DAU_HOAC_KHONG, extra=DS_PHU_PHI)
def test_gia_chao_la_so_nguyen_va_boi_so_cua_buoc_lam_tron(cost, rule, gia_dau, extra):
    """Giá chào là `int` thật (không phải float, không phải bool) và chia hết cho bước làm tròn ghi trong kết quả."""
    out = compute_quote(cost, rule, gia_dau, extra)
    gia = out["quote"]["quoted_price"]
    assert type(gia) is int
    assert out["internal"]["rounding_step"] == 1000
    assert gia % 1000 == 0


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(), gia_dau=GIA_DAU_HOAC_KHONG, extra=DS_PHU_PHI)
def test_gia_chao_khop_cong_thuc_tai_lieu(cost, rule, gia_dau, extra):
    """Giá chào BẰNG giá tính chính xác bằng phân số (công thức ở docstring `pricing.py`) làm tròn nửa-lên về bội 1.000đ."""
    chi_phi, phu, bien, _ = _chinh_xac(cost, rule, gia_dau, extra)
    raw = chi_phi + sum(phu) + bien
    _kiem_gia_chao(compute_quote(cost, rule, gia_dau, extra)["quote"]["quoted_price"], raw, cost)


@CAU_HINH
@given(k=st.integers(1, 10**9))
def test_lam_tron_nua_buoc_len_khong_ve_so_chan(k):
    """Đúng nửa bậc thì làm tròn LÊN (round-half-up), không về số chẵn: 1.000.500 -> 1.001.000, 1.001.500 -> 1.002.000."""
    rule = PricingRule(base_margin_pct=0)
    assert _gia(1000 * k + 500, rule) == 1000 * (k + 1)


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(), gia_dau=GIA_DAU_HOAC_KHONG, extra=DS_PHU_PHI)
@example(cost=1_000_499.0, rule=PricingRule(base_margin_pct=0.0), gia_dau=None, extra=[])
def test_gia_chao_khong_thap_hon_gia_thanh_qua_nua_buoc_lam_tron(cost, rule, gia_dau, extra):
    """
    Biên và phụ phí không âm thì giá chào KHÔNG thấp hơn giá thành (chi phí hiệu chỉnh + phụ phí), trừ phần LÀM TRÒN:
    biên 0% với giá nhà xe 1.000.499 cho giá chào 1.000.000 (thấp hơn giá thành 499đ). Chênh đó phải dưới nửa bậc, và
    biến mất khi biên thực >= nửa bậc.
    """
    chi_phi, phu, bien, _ = _chinh_xac(cost, rule, gia_dau, extra)
    gia_thanh = chi_phi + sum(phu)
    gia = Fraction(compute_quote(cost, rule, gia_dau, extra)["quote"]["quoted_price"])
    sai = _sai_so(cost, gia_thanh + bien)
    assert gia >= gia_thanh - 500 - sai
    if bien >= 500 + sai:
        assert gia >= gia_thanh - sai


@CAU_HINH
@given(
    cost=st.floats(1e12, 1e20, allow_nan=False, allow_infinity=False),
    rule=quy_tac(),
    gia_dau=GIA_DAU_HOAC_KHONG,
)
def test_so_lon_khong_tran_va_van_khop_cong_thuc(cost, rule, gia_dau):
    """Giá nhà xe tới 1e20 đồng (vô lý nhưng hợp lệ): giá chào vẫn là int hữu hạn, vẫn khớp công thức tới sai số tương đối."""
    chi_phi, phu, bien, _ = _chinh_xac(cost, rule, gia_dau, ())
    raw = chi_phi + sum(phu) + bien
    gia = compute_quote(cost, rule, gia_dau)["quote"]["quoted_price"]
    assert type(gia) is int
    _kiem_gia_chao(gia, raw, cost)


# ---------------------------------------------------------------------------
# 2. Đơn điệu: thêm chi phí hoặc thêm biên thì giá chào không giảm
# ---------------------------------------------------------------------------


@CAU_HINH
@given(cost=st.tuples(GIA_NHA_XE, GIA_NHA_XE), rule=quy_tac(), gia_dau=GIA_DAU_HOAC_KHONG, extra=DS_PHU_PHI)
def test_gia_nha_xe_tang_thi_gia_chao_khong_giam(cost, rule, gia_dau, extra):
    thap, cao = sorted(cost)
    assert _gia(thap, rule, gia_dau, extra) <= _gia(cao, rule, gia_dau, extra)


@CAU_HINH
@given(
    cost=GIA_NHA_XE,
    gia_dau=st.tuples(GIA_DAU, GIA_DAU),
    rule=quy_tac(gia_goc=GIA_DAU),
    extra=DS_PHU_PHI,
)
def test_gia_dau_hien_tai_tang_thi_gia_chao_khong_giam(cost, gia_dau, rule, extra):
    """Cùng giá gốc, dầu hôm nay đắt hơn thì báo giá không rẻ đi."""
    thap, cao = sorted(gia_dau)
    assert _gia(cost, rule, thap, extra) <= _gia(cost, rule, cao, extra)


@CAU_HINH
@given(
    cost=GIA_NHA_XE,
    bien=st.tuples(BIEN_PCT, BIEN_PCT),
    rule=quy_tac(),
    gia_dau=GIA_DAU_HOAC_KHONG,
    extra=DS_PHU_PHI,
)
def test_bien_phan_tram_tang_thi_gia_chao_khong_giam(cost, bien, rule, gia_dau, extra):
    thap, cao = sorted(bien)
    r_thap = dataclasses.replace(rule, base_margin_pct=thap)
    r_cao = dataclasses.replace(rule, base_margin_pct=cao)
    assert _gia(cost, r_thap, gia_dau, extra) <= _gia(cost, r_cao, gia_dau, extra)


@CAU_HINH
@given(
    cost=GIA_NHA_XE,
    san=st.tuples(SAN_BIEN, SAN_BIEN),
    rule=quy_tac(),
    gia_dau=GIA_DAU_HOAC_KHONG,
    extra=DS_PHU_PHI,
)
def test_san_bien_tang_thi_gia_chao_khong_giam(cost, san, rule, gia_dau, extra):
    thap, cao = sorted(san)
    r_thap = dataclasses.replace(rule, min_margin_amount=thap)
    r_cao = dataclasses.replace(rule, min_margin_amount=cao)
    assert _gia(cost, r_thap, gia_dau, extra) <= _gia(cost, r_cao, gia_dau, extra)


@CAU_HINH
@given(
    cost=GIA_NHA_XE,
    so_tien=st.tuples(_so_thuc(0, 5e6), _so_thuc(0, 5e6)),
    phan_tram=st.tuples(_so_thuc(0, 100), _so_thuc(0, 100)),
    rule=quy_tac(),
    gia_dau=GIA_DAU_HOAC_KHONG,
)
def test_phu_phi_tang_thi_gia_chao_khong_giam(cost, so_tien, phan_tram, rule, gia_dau):
    """Phụ phí (cố định lẫn theo %) lớn hơn từng phần thì giá chào không giảm."""
    (a1, a2), (p1, p2) = sorted(so_tien), sorted(phan_tram)
    assert _gia(cost, rule, gia_dau, [Surcharge("x", a1, p1)]) <= _gia(
        cost, rule, gia_dau, [Surcharge("x", a2, p2)]
    )


# ---------------------------------------------------------------------------
# 3. Điều chỉnh nhiên liệu
# ---------------------------------------------------------------------------


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(gia_goc=GIA_DAU), extra=DS_PHU_PHI)
def test_gia_dau_bang_gia_goc_thi_dieu_chinh_bang_khong(cost, rule, extra):
    """Dầu hôm nay bằng dầu lúc nhà xe chốt giá: điều chỉnh 0, và giá chào y hệt báo giá không xét nhiên liệu."""
    gia_goc = rule.fuel_baseline_price
    out = compute_quote(cost, rule, gia_goc, extra)
    noi_bo = out["internal"]
    assert noi_bo["fuel_adjustment"] == 0
    assert noi_bo["fuel_ratio"] == 1.0
    assert noi_bo["adjusted_cost"] == noi_bo["carrier_cost"]
    assert noi_bo["inputs"]["fuel_adjustment_applied"] is True
    khong_xet_dau = compute_quote(cost, dataclasses.replace(rule, fuel_baseline_price=None), None, extra)
    assert out["quote"] == khong_xet_dau["quote"]


@CAU_HINH
@given(
    cost=st.integers(1_000_000, 10**11).map(float),
    do_nhay=_so_thuc(0.1, 1.0),
    gia_goc=st.integers(10_000, 100_000).map(float),
    lech=st.one_of(_so_thuc(-0.5, -0.01), _so_thuc(0.01, 1.0)),
)
def test_dau_len_thi_dieu_chinh_duong_dau_xuong_thi_am(cost, do_nhay, gia_goc, lech):
    """Dầu lên so với giá gốc thì điều chỉnh DƯƠNG, xuống thì ÂM (dầu rẻ đi làm báo giá giảm, không chỉ biết tăng)."""
    rule = PricingRule(base_margin_pct=10, fuel_sensitivity=do_nhay, fuel_baseline_price=gia_goc)
    noi_bo = compute_quote(cost, rule, gia_goc * (1 + lech))["internal"]
    assert (noi_bo["fuel_adjustment"] > 0) == (lech > 0)
    assert noi_bo["fuel_adjustment"] != 0
    assert (noi_bo["fuel_ratio"] > 1) == (lech > 0)


@CAU_HINH
@given(cost=GIA_NHA_XE, gia_dau=GIA_DAU, rule=quy_tac(gia_goc=GIA_DAU), extra=DS_PHU_PHI)
def test_do_nhay_bang_khong_thi_gia_dau_khong_anh_huong(cost, gia_dau, rule, extra):
    """`fuel_sensitivity` là tỷ trọng nhiên liệu trong chi phí: bằng 0 thì dầu lên xuống bao nhiêu báo giá vẫn thế."""
    rule = dataclasses.replace(rule, fuel_sensitivity=0.0)
    co_dau = compute_quote(cost, rule, gia_dau, extra)
    assert co_dau["internal"]["fuel_adjustment"] == 0
    khong_dau = compute_quote(cost, dataclasses.replace(rule, fuel_baseline_price=None), None, extra)
    assert co_dau["quote"] == khong_dau["quote"]


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(), gia_dau=GIA_DAU_HOAC_KHONG)
def test_co_dieu_chinh_dau_va_canh_bao_phan_anh_dung_viec_co_dung_gia_dau(cost, rule, gia_dau):
    """
    `fuel_adjustment_applied` đúng khi và chỉ khi có CẢ giá hiện tại lẫn giá gốc. Thiếu một trong hai thì phải NÓI
    (cảnh báo đúng loại), thiếu cả hai thì im có chủ đích; không bao giờ để báo giá không theo dầu trông như báo giá
    theo dầu mà dầu không đổi.
    """
    gia_goc = rule.fuel_baseline_price
    out = compute_quote(cost, rule, gia_dau)
    co_ca_hai = gia_dau is not None and gia_goc is not None
    assert out["internal"]["inputs"]["fuel_adjustment_applied"] is co_ca_hai
    thieu_hien_tai = any("Chưa lấy được giá dầu hiện tại" in w for w in out["warnings"])
    thieu_goc = any("giá dầu gốc" in w for w in out["warnings"])
    assert thieu_hien_tai is (gia_dau is None and gia_goc is not None)
    assert thieu_goc is (gia_dau is not None and gia_goc is None)
    if not co_ca_hai:
        assert out["internal"]["fuel_adjustment"] == 0
        assert out["internal"]["fuel_ratio"] is None


# ---------------------------------------------------------------------------
# 4. Bảo mật (P2): `quote` đưa được cho khách cuối, không lộ gì nội bộ
# ---------------------------------------------------------------------------

_KHOA_CONG_KHAI = {"quoted_price", "surcharges", "currency", "name", "value"}
_MANH_KHOA_NOI_BO = (
    "margin", "fuel", "carrier", "adjust", "baseline", "sensitiv", "input", "computed", "rounding", "floor",
    "min_", "base_", "ratio", "cost",
)


def _moi_khoa(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from _moi_khoa(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _moi_khoa(v)


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(), gia_dau=GIA_DAU_HOAC_KHONG, extra=DS_PHU_PHI)
def test_quote_khong_chua_khoa_noi_bo_o_bat_ky_do_sau(cost, rule, gia_dau, extra):
    """Mọi khoá ở mọi độ sâu của `quote` thuộc danh sách trắng công khai; không khoá nào gợi biên, dầu, giá vốn."""
    out = compute_quote(cost, rule, gia_dau, extra)
    khoa = set(_moi_khoa(out["quote"]))
    assert khoa <= _KHOA_CONG_KHAI, f"lộ khoá ngoài danh sách công khai: {khoa - _KHOA_CONG_KHAI}"
    for k in khoa:
        assert not any(manh in k.lower() for manh in _MANH_KHOA_NOI_BO), k
    assert set(out["quote"]) == {"quoted_price", "surcharges", "currency"}
    assert out["quote"]["currency"] == "VND"
    # Biên và đầu vào nằm ở nhánh NỘI BỘ, không phải ở `quote`.
    assert {"margin", "inputs", "fuel_adjustment"} <= set(out["internal"])


# ---------------------------------------------------------------------------
# 5. Phụ phí, tính giải thích được, tất định
# ---------------------------------------------------------------------------


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(), gia_dau=GIA_DAU_HOAC_KHONG, extra=DS_PHU_PHI)
def test_phu_phi_tren_bao_gia_dung_ten_dung_thu_tu(cost, rule, gia_dau, extra):
    """Phụ phí công khai trên báo giá: đủ tên, đúng thứ tự (của quy tắc rồi tới phụ phí thêm), giá trị nguyên đồng."""
    out = compute_quote(cost, rule, gia_dau, extra)
    chi_phi, phu, _, _ = _chinh_xac(cost, rule, gia_dau, extra)
    dong = out["quote"]["surcharges"]
    assert [d["name"] for d in dong] == [s.name for s in (*rule.surcharges, *extra)]
    for d, chinh_xac in zip(dong, phu):
        assert type(d["value"]) is int
        assert abs(Fraction(d["value"]) - chinh_xac) <= Fraction(1, 2) + _sai_so(cost, chi_phi)


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(), them=DS_PHU_PHI, gia_dau=GIA_DAU_HOAC_KHONG)
def test_phu_phi_them_va_phu_phi_cua_quy_tac_duoc_tinh_nhu_nhau(cost, rule, them, gia_dau):
    """Một phụ phí khai trong quy tắc hay gửi kèm lúc báo giá (`extra_surcharges`) thì kết quả y hệt, từng chữ."""
    gop = dataclasses.replace(rule, surcharges=[*rule.surcharges, *them])
    assert compute_quote(cost, rule, gia_dau, them) == compute_quote(cost, gop, gia_dau, None)


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(), gia_dau=GIA_DAU_HOAC_KHONG, extra=DS_PHU_PHI)
def test_ket_qua_noi_bo_giai_thich_duoc_gia_chao(cost, rule, gia_dau, extra):
    """
    Chủ doanh nghiệp đọc `internal` để biết vì sao ra con số đó, nên các mảnh phải CỘNG LẠI ra giá chào (trong sai số
    làm tròn từng mảnh về 1đ và nửa bậc làm tròn cuối), và `inputs` phải ghi đúng những số đã dùng (AGENTS §3.1c).
    """
    out = compute_quote(cost, rule, gia_dau, extra)
    noi_bo, quote = out["internal"], out["quote"]
    assert noi_bo["carrier_cost"] == cost
    assert abs(noi_bo["adjusted_cost"] - (noi_bo["carrier_cost"] + noi_bo["fuel_adjustment"])) <= 1
    tong = noi_bo["adjusted_cost"] + noi_bo["surcharge_total"] + noi_bo["margin"]
    assert abs(quote["quoted_price"] - tong) <= 500 + 3
    n = len(quote["surcharges"])
    assert abs(sum(d["value"] for d in quote["surcharges"]) - noi_bo["surcharge_total"]) <= n / 2 + 0.5
    assert noi_bo["inputs"]["carrier_cost"] == cost
    assert noi_bo["inputs"]["current_fuel_price"] == gia_dau
    assert noi_bo["inputs"]["fuel_baseline_price"] == rule.fuel_baseline_price
    assert noi_bo["rounding_step"] == 1000


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(), gia_dau=GIA_DAU_HOAC_KHONG, extra=DS_PHU_PHI)
def test_san_bien_chi_ap_khi_bien_phan_tram_thap_hon_va_phai_noi_ro(cost, rule, gia_dau, extra):
    """`margin_floored` và cảnh báo "áp sàn" khớp với việc sàn có THỰC SỰ thắng biên theo % (tránh hai ca sát nút)."""
    _, _, bien, bien_pct = _chinh_xac(cost, rule, gia_dau, extra)
    san = Fraction(rule.min_margin_amount)
    sai = _sai_so(cost, bien)
    out = compute_quote(cost, rule, gia_dau, extra)
    co_canh_bao = any("áp sàn" in w for w in out["warnings"])
    if san > bien_pct + sai:
        assert out["internal"]["margin_floored"] is True and co_canh_bao
        assert abs(Fraction(out["internal"]["margin"]) - san) <= Fraction(1, 2) + sai
    elif san < bien_pct - sai:
        assert out["internal"]["margin_floored"] is False and not co_canh_bao


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(), gia_dau=GIA_DAU_HOAC_KHONG, extra=DS_PHU_PHI)
def test_tat_dinh_hop_le_json_va_khong_sua_dau_vao(cost, rule, gia_dau, extra):
    """
    Hai lần gọi cùng đầu vào cho kết quả giống hệt (`compute_quote` là phép tính thuần; `computed_at` do ROUTE thêm);
    kết quả là JSON hợp lệ không chứa NaN/vô cực; đầu vào không bị sửa (quy tắc giá của khách dùng đi dùng lại).
    """
    truoc = copy.deepcopy((rule, extra))
    a = compute_quote(cost, rule, gia_dau, extra)
    b = compute_quote(cost, rule, gia_dau, extra)
    assert a == b
    assert (rule, extra) == truoc
    json.dumps(a, allow_nan=False)
    assert "computed_at" not in a["internal"]


# ---------------------------------------------------------------------------
# 6. Tuổi giá dầu (AGENTS §3.1c): ĐỒNG HỒ ĐƯỢC TIÊM, không đọc giờ thật
# ---------------------------------------------------------------------------

HOM_NAY = st.dates(min_value=date(1990, 1, 1), max_value=date(2100, 12, 31))
CAP_NGUONG = st.integers(1, 30).flatmap(lambda w: st.tuples(st.just(w), st.integers(w, 60)))


@st.composite
def nguong_va_tuoi(draw):
    """((ngưỡng cảnh báo, ngưỡng từ chối), tuổi giá dầu). Tuổi bị kéo về các BIÊN của ngưỡng, nơi lỗi lệch một ngày nằm."""
    canh_bao, tu_choi = draw(CAP_NGUONG)
    bien = [-1, 0, canh_bao - 1, canh_bao, tu_choi - 1, tu_choi, tu_choi + 1]
    return (canh_bao, tu_choi), draw(st.one_of(st.integers(-3, tu_choi + 3), st.sampled_from(bien)))

_RULE_CO_GOC = PricingRule(base_margin_pct=10, fuel_baseline_price=25_000)


@CAU_HINH
@given(hom_nay=HOM_NAY, nguong_tuoi=nguong_va_tuoi())
@example(hom_nay=date(2026, 11, 12), nguong_tuoi=((2, 7), -1))
@example(hom_nay=date(2026, 11, 12), nguong_tuoi=((2, 7), 1))
@example(hom_nay=date(2026, 11, 12), nguong_tuoi=((2, 7), 2))
@example(hom_nay=date(2026, 11, 12), nguong_tuoi=((2, 7), 6))
@example(hom_nay=date(2026, 11, 12), nguong_tuoi=((2, 7), 7))
@example(hom_nay=date(2026, 11, 12), nguong_tuoi=((1, 1), 0))
@example(hom_nay=date(2026, 11, 12), nguong_tuoi=((1, 1), 1))
def test_tuoi_gia_dau_chia_dung_bon_bac(hom_nay, nguong_tuoi):
    """
    Giá dầu ĐƯỢC DÙNG để điều chỉnh: tuổi < 0 là "tương lai" (cảnh báo), < ngưỡng cảnh báo là "ok", tới ngưỡng cảnh
    báo là "stale_warn" (cảnh báo, vẫn tính), tới ngưỡng từ chối thì ValueError (route: 422). Con số báo giá KHÔNG đổi
    vì có thêm ngày (chỉ ghi thêm). `today` truyền vào, nên kết quả không phụ thuộc ngày chạy test.
    """
    (canh_bao, tu_choi), tuoi = nguong_tuoi
    ngay = (hom_nay - timedelta(days=tuoi)).isoformat()
    tham_so = dict(fuel_price_as_of=ngay, today=hom_nay, canh_bao_ngay=canh_bao, tu_choi_ngay=tu_choi)
    if tuoi >= tu_choi:
        with pytest.raises(ValueError, match="Giá dầu"):
            compute_quote(1_000_000, _RULE_CO_GOC, 27_500, **tham_so)
        return
    out = compute_quote(1_000_000, _RULE_CO_GOC, 27_500, **tham_so)
    ghi = out["internal"]["inputs"]
    assert ghi["fuel_price_as_of"] == ngay and ghi["fuel_price_age_days"] == tuoi
    if tuoi < 0:
        assert ghi["fuel_price_status"] == "future"
        assert any("SAU hôm nay" in w for w in out["warnings"])
    elif tuoi >= canh_bao:
        assert ghi["fuel_price_status"] == "stale_warn"
        assert any(f"cách {tuoi} ngày" in w for w in out["warnings"])
    else:
        assert ghi["fuel_price_status"] == "ok"
        assert out["warnings"] == []
    khong_ngay = compute_quote(1_000_000, _RULE_CO_GOC, 27_500)
    assert out["quote"] == khong_ngay["quote"]
    assert out["internal"]["fuel_adjustment"] == khong_ngay["internal"]["fuel_adjustment"]


@CAU_HINH
@given(
    hom_nay=HOM_NAY,
    nguong=CAP_NGUONG,
    tuoi=st.integers(0, 3650),
    thieu=st.sampled_from(["gia_hien_tai", "gia_goc", "ca_hai"]),
)
def test_gia_dau_khong_duoc_dung_thi_tuoi_cua_no_khong_bi_tu_choi(hom_nay, nguong, tuoi, thieu):
    """Thiếu giá hiện tại hoặc giá gốc thì dầu không điều chỉnh gì: giá dầu cũ cỡ nào cũng không làm sai báo giá, từ chối là chặn oan."""
    canh_bao, tu_choi = nguong
    rule = PricingRule(base_margin_pct=10, fuel_baseline_price=None if thieu != "gia_hien_tai" else 25_000)
    gia_hien_tai = None if thieu != "gia_goc" else 27_500
    out = compute_quote(
        1_000_000, rule, gia_hien_tai,
        fuel_price_as_of=(hom_nay - timedelta(days=tuoi)).isoformat(), today=hom_nay,
        canh_bao_ngay=canh_bao, tu_choi_ngay=tu_choi,
    )
    assert out["internal"]["inputs"]["fuel_price_status"] == "not_applied"
    assert out["internal"]["inputs"]["fuel_adjustment_applied"] is False


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(), gia_dau=GIA_DAU_HOAC_KHONG)
def test_khong_co_ngay_gia_dau_thi_trang_thai_la_unknown_chu_khong_phai_moi(cost, rule, gia_dau):
    """Không biết ngày của giá dầu thì nói "unknown" và không từ chối; tuyệt đối không coi là "ok"."""
    ghi = compute_quote(cost, rule, gia_dau)["internal"]["inputs"]
    assert ghi["fuel_price_status"] == "unknown"
    assert ghi["fuel_price_as_of"] is None and ghi["fuel_price_age_days"] is None


_NGAY_ISO_ASCII = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


@CAU_HINH
@given(
    chuoi=st.one_of(
        st.text(max_size=12),
        st.from_regex(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", fullmatch=True),
        st.from_regex(r"\d{4}-\d{2}-\d{2}", fullmatch=True),
        HOM_NAY.map(lambda d: d.isoformat()),
    ),
    hom_nay=HOM_NAY,
)
# Ba chuỗi mà `date.fromisoformat` của Python >= 3.11 NHẬN nhưng không phải YYYY-MM-DD (xem `_tuoi_gia_dau`), cộng
# ngày thật có xuống dòng cuối. Hypothesis hầu như không tự sinh ra chúng, nên ghim lại.
@example(chuoi="2026-W45-1", hom_nay=date(2026, 11, 12))
@example(chuoi="20261105", hom_nay=date(2026, 11, 12))
@example(chuoi="2026-11-12\n", hom_nay=date(2026, 11, 12))
@example(chuoi="2026-11-12", hom_nay=date(2026, 11, 12))
def test_ngay_gia_dau_chi_nhan_dung_YYYY_MM_DD_thuc_su(chuoi, hom_nay):
    """
    Chuỗi ngày bất kỳ: hoặc là ngày ISO ASCII có thật (ghi lại NGUYÊN VĂN), hoặc bị `ValueError` nêu dạng đúng; không
    bao giờ một loại lỗi khác, và không bao giờ đoán (tuần ISO, chữ số Ả Rập, xuống dòng cuối...). Giá dầu không dùng
    để điều chỉnh nên tuổi không gây từ chối, chỉ còn kiểm dạng.
    """
    if not chuoi:
        return  # rỗng nghĩa là "không có ngày": đã kiểm ở test unknown
    hop_le = False
    if _NGAY_ISO_ASCII.fullmatch(chuoi):
        try:
            ngay = date.fromisoformat(chuoi)
            hop_le = True
        except ValueError:
            pass
    rule = PricingRule(base_margin_pct=10)
    if hop_le:
        ghi = compute_quote(1_000_000, rule, None, fuel_price_as_of=chuoi, today=hom_nay)["internal"]["inputs"]
        assert ghi["fuel_price_as_of"] == chuoi
        assert ghi["fuel_price_age_days"] == (hom_nay - ngay).days
    else:
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            compute_quote(1_000_000, rule, None, fuel_price_as_of=chuoi, today=hom_nay)


@CAU_HINH
@given(canh_bao=st.integers(-5, 40), tu_choi=st.integers(-5, 40))
def test_nguong_tuoi_khong_thoa_1_den_canh_bao_den_tu_choi_bi_tu_choi(canh_bao, tu_choi):
    """Cả hàm tính (ValueError) lẫn bộ đọc cấu hình (RuntimeError: lỗi CẤU HÌNH, không đổ lỗi cho khách) giữ 1 <= WARN <= MAX."""
    hop_le = 1 <= canh_bao <= tu_choi
    if hop_le:
        compute_quote(1_000_000, _RULE_CO_GOC, 27_500, canh_bao_ngay=canh_bao, tu_choi_ngay=tu_choi)
    else:
        with pytest.raises(ValueError, match="ngưỡng"):
            compute_quote(1_000_000, _RULE_CO_GOC, 27_500, canh_bao_ngay=canh_bao, tu_choi_ngay=tu_choi)
    env = {"FUEL_PRICE_WARN_DAYS": str(canh_bao), "FUEL_PRICE_MAX_DAYS": str(tu_choi)}
    with mock.patch.dict(os.environ, env):
        if hop_le:
            assert doc_nguong_tuoi_gia_dau() == (canh_bao, tu_choi)
        else:
            with pytest.raises(RuntimeError):
                doc_nguong_tuoi_gia_dau()


def test_bo_doc_nguong_dung_mac_dinh_khi_env_trong():
    with mock.patch.dict(os.environ):
        os.environ.pop("FUEL_PRICE_WARN_DAYS", None)
        os.environ.pop("FUEL_PRICE_MAX_DAYS", None)
        assert doc_nguong_tuoi_gia_dau() == (MAC_DINH_CANH_BAO_NGAY, MAC_DINH_TU_CHOI_NGAY) == (2, 7)


# ---------------------------------------------------------------------------
# 7. Đầu vào hỏng: bị từ chối, không ra con số báo giá lạ
# ---------------------------------------------------------------------------


@CAU_HINH
@given(cost=st.floats(max_value=0.0, allow_nan=False, allow_infinity=True))
def test_gia_nha_xe_khong_duong_bi_tu_choi(cost):
    with pytest.raises(ValueError):
        compute_quote(cost, _RULE_CO_GOC, 27_500)


@CAU_HINH
@given(
    xau=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False),
    hien_tai_xau=st.booleans(),
    cost=GIA_NHA_XE,
)
def test_gia_dau_khong_duong_bi_tu_choi_khi_dung_de_dieu_chinh(xau, hien_tai_xau, cost):
    """Giá dầu hiện tại hoặc giá gốc <= 0 (mà gốc khác 0) thì ValueError. Gốc đúng bằng 0 là "chưa khai", xét ở test sau."""
    if hien_tai_xau:
        rule, gia_dau = _RULE_CO_GOC, xau
    else:
        if xau == 0:
            return
        rule, gia_dau = dataclasses.replace(_RULE_CO_GOC, fuel_baseline_price=xau), 27_500.0
    with pytest.raises(ValueError, match="giá nhiên liệu"):
        compute_quote(cost, rule, gia_dau)


@CAU_HINH
@given(cost=GIA_NHA_XE, gia_dau=GIA_DAU, so_khong=st.sampled_from([0, 0.0, -0.0, None]), rule=quy_tac())
def test_gia_goc_bang_khong_thi_bo_qua_dieu_chinh_va_noi_ro(cost, gia_dau, so_khong, rule):
    """Giá gốc 0 (hay trống) là "chưa khai": KHÔNG điều chỉnh, KHÔNG chia cho 0, và báo rõ trong cảnh báo."""
    rule = dataclasses.replace(rule, fuel_baseline_price=so_khong)
    out = compute_quote(cost, rule, gia_dau)
    assert out["internal"]["inputs"]["fuel_adjustment_applied"] is False
    assert out["internal"]["fuel_adjustment"] == 0
    assert any("giá dầu gốc" in w for w in out["warnings"])
    assert out["quote"] == compute_quote(cost, rule, None)["quote"]


@CAU_HINH
@given(
    do_nhay=st.one_of(_so_thuc(-1e6, -1e-9), _so_thuc(1.0000001, 1e6)),
    bien=_so_thuc(0, 100),
    san=_so_thuc(0, 1e6),
)
def test_quy_tac_gia_sai_bi_tu_choi_ngay_luc_tao(do_nhay, bien, san):
    with pytest.raises(ValueError):
        PricingRule(base_margin_pct=bien, fuel_sensitivity=do_nhay, min_margin_amount=san)
    with pytest.raises(ValueError):
        PricingRule(base_margin_pct=-1e-9 - bien)
    with pytest.raises(ValueError):
        PricingRule(base_margin_pct=bien, min_margin_amount=-1e-9 - san)


# Mỗi (trường, giá trị): NaN và -inf/+inf ở từng đầu vào số. Hợp đồng: bị `ValueError` (route đổi thành 422).
# Ca đánh dấu xfail là chỗ engine HIỆN chưa giữ hợp đồng (xem `_CHUA_TU_CHOI_DUNG` ngay dưới).
_TRUONG_SO = ("cost", "current", "baseline", "margin", "min_margin", "amount", "pct")

# Mọi ca NaN/vô cực đều bị từ chối bằng ValueError từ 21/11/2026 (A4): bảng này rỗng. Ca mới tìm ra lỗi thì thêm vào đây kèm lý do và `xfail(strict)`.
_CHUA_TU_CHOI_DUNG: dict = {}


def _ca_khong_huu_han():
    for truong in _TRUONG_SO:
        for gia_tri in (NAN, INF, -INF):
            ly_do = _CHUA_TU_CHOI_DUNG.get((truong, gia_tri))
            danh_dau = [pytest.mark.xfail(strict=True, reason=ly_do)] if ly_do else []
            yield pytest.param(truong, gia_tri, marks=danh_dau, id=f"{truong}={gia_tri}")


@pytest.mark.parametrize("truong, gia_tri", list(_ca_khong_huu_han()))
def test_dau_vao_khong_huu_han_bi_tu_choi_bang_ValueError(truong, gia_tri):
    """NaN và vô cực ở BẤT KỲ đầu vào số nào: `ValueError` (route đổi nó thành 422), không trả giá, không ném lỗi loại khác."""
    tham_so = dict(cost=1_000_000.0, margin=10.0, baseline=25_000.0, current=27_500.0,
                   min_margin=0.0, amount=0.0, pct=0.0)
    tham_so[truong] = gia_tri
    with pytest.raises(ValueError):
        # Surcharge cũng tự kiểm lúc dựng (từ A4, 21/11/2026), nên dựng NẰM TRONG khối bắt lỗi.
        phu_phi = [Surcharge("phi", tham_so["amount"], tham_so["pct"])] if truong in ("amount", "pct") else []
        rule = PricingRule(
            base_margin_pct=tham_so["margin"], fuel_baseline_price=tham_so["baseline"],
            min_margin_amount=tham_so["min_margin"], surcharges=phu_phi,
        )
        compute_quote(tham_so["cost"], rule, tham_so["current"])


@CAU_HINH
@given(cost=GIA_NHA_XE, amount=_so_thuc(-1e10, 1e10))
@example(cost=1_000.0, amount=-1_600.0)
def test_gia_chao_khong_bao_gio_am_du_phu_phi_la_gi(cost, amount):
    """Với mọi đầu vào ĐƯỢC CHẤP NHẬN, giá chào không âm. (Bị `ValueError` từ chối cũng là một câu trả lời đúng.)"""
    try:
        out = compute_quote(cost, PricingRule(base_margin_pct=10), None, [Surcharge("x", amount)])
    except ValueError:
        return
    assert out["quote"]["quoted_price"] >= 0


@CAU_HINH
@given(cost=st.floats(1e28, 1e300, allow_nan=False, allow_infinity=False))
@example(cost=1e28)
def test_gia_nha_xe_qua_lon_bi_tu_choi_bang_ValueError(cost):
    try:
        compute_quote(cost, PricingRule(base_margin_pct=10), None)
    except ValueError:
        return


# ---------------------------------------------------------------------------
# 8. Route /tools/quote: cùng một tính chất, qua HTTP (hợp đồng với Body và n8n)
# ---------------------------------------------------------------------------

_CLIENT = TestClient(app, raise_server_exceptions=False)  # 500 phải là status 500, không phải ngoại lệ trong test


@pytest.fixture(scope="module", autouse=True)
def _khong_phu_thuoc_token_moi_truong():
    """Test HTTP ở đây không bàn về cổng token; API_AUTH_TOKEN còn sót trong môi trường người chạy thành 401 vô cớ."""
    mp = pytest.MonkeyPatch()
    mp.setattr(deps, "API_AUTH_TOKEN", "")
    mp.setattr(main_mod, "API_AUTH_TOKEN", "")
    yield
    mp.undo()


def _body(cost, rule, gia_dau, extra, ngay=None):
    def phu(s):
        return {"name": s.name, "amount": s.amount, "pct": s.pct}

    return {
        "carrier_cost": cost,
        "pricing_rule": {
            "base_margin_pct": rule.base_margin_pct,
            "fuel_sensitivity": rule.fuel_sensitivity,
            "fuel_baseline_price": rule.fuel_baseline_price,
            "min_margin_amount": rule.min_margin_amount,
            "surcharges": [phu(s) for s in rule.surcharges],
        },
        "current_fuel_price": gia_dau,
        "extra_surcharges": [phu(s) for s in extra],
        "fuel_price_as_of": ngay,
    }


def _post(body):
    return _CLIENT.post("/tools/quote", content=json.dumps(body), headers={"content-type": "application/json"})


@CAU_HINH
@given(cost=GIA_NHA_XE, rule=quy_tac(), gia_dau=GIA_DAU_HOAC_KHONG, extra=DS_PHU_PHI)
def test_route_tra_dung_ket_qua_cua_ham_va_chi_them_computed_at_vao_noi_bo(cost, rule, gia_dau, extra):
    """Route không tự tính gì thêm: `quote` và `warnings` y hệt hàm, `internal` y hệt cộng đúng một khoá `computed_at`."""
    r = _post(_body(cost, rule, gia_dau, extra))
    assert r.status_code == 200
    out = r.json()
    tuoi = tools_mod._NGUONG_GIA_DAU
    mong = compute_quote(cost, rule, gia_dau, extra, canh_bao_ngay=tuoi[0], tu_choi_ngay=tuoi[1])
    computed_at = out["internal"].pop("computed_at")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", computed_at)
    assert out == mong
    assert set(_moi_khoa(out["quote"])) <= _KHOA_CONG_KHAI


@pytest.mark.parametrize("co_dieu_chinh", [True, False], ids=["dung_dau", "khong_dung_dau"])
@pytest.mark.parametrize("tuoi", range(-2, 13))
def test_route_tu_choi_gia_dau_qua_cu_bang_422_theo_dung_nguong_cau_hinh(tuoi, co_dieu_chinh):
    """Ngày trong `fuel_price_as_of` vượt ngưỡng từ chối thì 422 (không 500); dầu không được dùng thì 200. Đồng hồ được TIÊM."""
    _, tu_choi = tools_mod._NGUONG_GIA_DAU
    hom_nay = date(2026, 11, 12)
    rule = PricingRule(base_margin_pct=10, fuel_baseline_price=25_000)
    ngay = (hom_nay - timedelta(days=tuoi)).isoformat()
    with mock.patch("src.core.pricing.hom_nay_vn", return_value=hom_nay):
        r = _post(_body(1_000_000, rule, 27_500 if co_dieu_chinh else None, (), ngay))
    if co_dieu_chinh and tuoi >= tu_choi:
        assert r.status_code == 422 and "Giá dầu" in r.json()["detail"]
    else:
        assert r.status_code == 200


# Ca JSON hỏng gửi thẳng văn bản (có `Infinity`/`NaN`, thứ `json.loads` của Python nhận dù JSON chuẩn không có).
_BODY_GOC = _body(1_000_000.0, PricingRule(base_margin_pct=10, fuel_baseline_price=25_000), 27_500.0, (), None)


def _ca_route(ten, ghi_de, loi=None):
    body = copy.deepcopy(_BODY_GOC)
    for duong, gia_tri in ghi_de.items():
        dich = body
        *dau, cuoi = duong.split(".")
        for khoa in dau:
            dich = dich[int(khoa)] if khoa.isdigit() else dich[khoa]
        dich[cuoi] = gia_tri
    danh_dau = [pytest.mark.xfail(strict=True, reason=loi)] if loi else []
    return pytest.param(body, marks=danh_dau, id=ten)


_PHU_PHI_VO_CUC = {"extra_surcharges": [{"name": "x", "amount": INF, "pct": 0.0}]}
_CA_ROUTE = [
    _ca_route("carrier_cost=NaN", {"carrier_cost": NAN}),
    _ca_route("carrier_cost=0", {"carrier_cost": 0}),
    _ca_route("surcharge.amount=NaN", {"extra_surcharges": [{"name": "x", "amount": NAN, "pct": 0.0}]}),
    _ca_route("carrier_cost=inf", {"carrier_cost": INF}),   # đã sửa ở Brain#179 (allow_inf_nan=False ở _ToolIn)
    _ca_route("carrier_cost=1e28", {"carrier_cost": 1e28}),
    _ca_route("current_fuel_price=inf", {"current_fuel_price": INF}),
    _ca_route("fuel_baseline_price=inf", {"pricing_rule.fuel_baseline_price": INF}),
    _ca_route("base_margin_pct=inf", {"pricing_rule.base_margin_pct": INF}),
    _ca_route("min_margin_amount=inf", {"pricing_rule.min_margin_amount": INF}),
    _ca_route("surcharge.amount=inf", _PHU_PHI_VO_CUC),
    _ca_route("surcharge.amount=-9e9", {"extra_surcharges": [{"name": "x", "amount": -9e9, "pct": 0.0}]}),
]


@pytest.mark.parametrize("body", _CA_ROUTE)
def test_route_tu_choi_dau_vao_hong_bang_422_khong_500_khong_gia_la(body):
    """Đầu vào số hỏng: 422, không 500 (lỗi máy chủ), không 200 kèm một con số báo giá vô lý (âm)."""
    r = _post(body)
    assert r.status_code == 422, f"{r.status_code}: {r.text[:200]}"
