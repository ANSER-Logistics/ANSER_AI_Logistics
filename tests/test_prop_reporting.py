"""
tests/test_prop_reporting.py — TÍNH CHẤT (property-based) của engine báo cáo `src/core/reporting.py`.

VÌ SAO CÓ FILE NÀY
------------------
Các test viết tay (`test_assistant_upgrades.py`, `test_chua_biet_khong_phai_0.py`) khoá từng VÍ DỤ: hai quý,
một dòng thiếu giá vốn, một kỳ chỉ có chi phí. Chúng không nói gì về cái gì xảy ra với dòng thứ 7, ngày thứ
31, hay khi hai dòng đổi chỗ cho nhau. Engine này là phần "không được phép sai" của R1: con số sai mà nghe có
vẻ đúng không ai phát hiện tới lúc quyết toán. Nên ở đây ta khoá các ĐIỀU LUÔN ĐÚNG, rồi để `hypothesis` đi tìm
chỗ chúng gãy.

CÁCH LÀM ĐỂ KẾT QUẢ TIN ĐƯỢC
----------------------------
- Có một mô hình tham chiếu viết lại ĐỘC LẬP (`_ky`, `mau_cac_ky`, `mau_mat_hang`): dùng `Fraction` nên cộng
  là chính xác tuyệt đối, và xếp kỳ bằng SỐ (năm, thứ tự) chứ không bằng chuỗi như mã thật.
- Số tiền sinh ra là bội của 1/4 đồng (tối đa 10^12), nên cộng bằng `float` trong mã thật cũng chính xác:
  mọi lệch kết quả là lỗi logic, không phải nhiễu dấu phẩy động. Thứ tự cộng khi đó cũng không ảnh hưởng.
- Dữ liệu hoàn toàn hư cấu (R2). Ngày nằm trong 2025–2026 để nhiều dòng rơi vào cùng một kỳ.

BA ĐIỀU CỐ Ý KHÔNG KHOÁ (đọc mã thấy không phải hợp đồng)
--------------------------------------------------------
- `cogs_coverage_pct` tính theo DOANH THU có giá vốn trên tổng doanh thu, KHÔNG theo số dòng. Test khoá đúng
  cách tính thật (một dòng 10 đồng có giá vốn không "phủ" bằng một dòng 900 đồng có giá vốn).
- Làm tròn tiền bằng `round()` (chẵn gần nhất). Test chỉ đòi sai số <= 0,5 đồng mỗi kỳ, không đòi cách làm tròn.
- Thứ tự các mặt hàng HÒA nhau về lãi và doanh thu phụ thuộc thứ tự dòng đầu vào (sắp xếp ổn định).

CÁC TEST `xfail(strict=True)` là LỖI THẬT của `reporting.py` mà `hypothesis` tìm ra, chưa sửa vì việc này chỉ
thêm test (nếu sửa thì test XPASS và `strict` báo để gỡ dấu). Cùng cách đã dùng ở PR #60.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, replace
from datetime import date, timedelta
from fractions import Fraction
from typing import Optional

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from src.core.reporting import (
    GRANULARITIES,
    ExpenseLine,
    ReportRequest,
    SaleLine,
    build_report,
    period_key,
    product_profitability,
)

# Một chỗ cấu hình dùng chung: tất định (cùng ví dụ mỗi lần chạy, CI không chập chờn), không lưu DB ví dụ.
CAU_HINH = settings(derandomize=True, max_examples=200, deadline=None, database=None)

_MAX = 10**12            # trần số tiền một dòng
_TAT_CA = 40             # periods_back lớn nhất mà /tools/report nhận: không kỳ nào bị cắt
_KHOA_KY = {
    "period", "revenue", "cogs", "gross_profit", "operating_expenses", "net_profit",
    "gross_margin_pct", "net_margin_pct", "orders", "cogs_coverage_pct",
    "revenue_growth_pct", "net_profit_growth_pct",
}
_KHOA_TREN = {"granularity", "periods", "products", "explain", "warnings"}
_KHOA_EXPLAIN = {"cogs_coverage_pct", "confidence", "formula", "period_count"}
_TIN_CAY = {"cao", "trung bình", "thấp", "không có dữ liệu"}
_HANG = {"thấp": 0, "trung bình": 1, "cao": 2}


# ---------------------------------------------------------------------------
# Mô hình tham chiếu (độc lập với mã thật)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Ban:
    """Một dòng bán ở dạng chính xác. `von=None` là CHƯA BIẾT giá vốn."""
    ngay: date
    tien: Fraction
    ten: str
    sl: Fraction
    von: Optional[Fraction]

    def dong(self) -> SaleLine:
        return SaleLine(
            date=self.ngay.isoformat(), revenue=float(self.tien), product=self.ten,
            quantity=float(self.sl), cogs=None if self.von is None else float(self.von),
        )


@dataclass(frozen=True)
class Chi:
    ngay: date
    tien: Fraction

    def dong(self) -> ExpenseLine:
        return ExpenseLine(date=self.ngay.isoformat(), amount=float(self.tien))


def _ky(ngay: date, muc: str) -> tuple[int, int, str]:
    """(năm, thứ tự trong năm, nhãn). Thứ tự bằng SỐ: không dính lỗi xếp chuỗi của mã thật."""
    y, m = ngay.year, ngay.month
    if muc == "month":
        return y, m, f"{y}-{m:02d}"
    if muc == "quarter":
        q = (m + 2) // 3
        return y, q, f"{y}-Q{q}"
    if muc == "half":
        h = 1 if m <= 6 else 2
        return y, h, f"{y}-H{h}"
    return y, 1, str(y)


@dataclass
class KyMau:
    nhan: str
    dt: Fraction = Fraction(0)          # doanh thu
    von: Fraction = Fraction(0)         # giá vốn đã biết
    dt_co_von: Fraction = Fraction(0)   # doanh thu của các dòng CÓ giá vốn
    chi: Fraction = Fraction(0)
    don: int = 0

    @property
    def lai_gop(self) -> Fraction:
        return self.dt_co_von - self.von

    @property
    def lai_rong(self) -> Fraction:
        return self.lai_gop - self.chi


def mau_cac_ky(ban: list[Ban], chi: list[Chi], muc: str) -> list[KyMau]:
    """Mọi kỳ có dữ liệu, theo thứ tự thời gian tăng dần."""
    khoa: dict[tuple[int, int], KyMau] = {}
    for b in ban:
        y, i, nhan = _ky(b.ngay, muc)
        k = khoa.setdefault((y, i), KyMau(nhan))
        k.dt += b.tien
        k.don += 1
        if b.von is not None:
            k.von += b.von
            k.dt_co_von += b.tien
    for c in chi:
        y, i, nhan = _ky(c.ngay, muc)
        khoa.setdefault((y, i), KyMau(nhan)).chi += c.tien
    return [khoa[k] for k in sorted(khoa)]


@dataclass
class HangMau:
    dt: Fraction
    sl: Fraction
    thieu: bool
    lai: Optional[Fraction]


def mau_mat_hang(ban: list[Ban]) -> dict[str, HangMau]:
    nhom: dict[str, list[Ban]] = {}
    for b in ban:
        nhom.setdefault(b.ten.strip() or "(không rõ tên)", []).append(b)
    out = {}
    for ten, ds in nhom.items():
        dt = sum((b.tien for b in ds), Fraction(0))
        thieu = any(b.von is None for b in ds)
        lai = None if thieu else dt - sum((b.von for b in ds if b.von is not None), Fraction(0))
        out[ten] = HangMau(dt, sum((b.sl for b in ds), Fraction(0)), thieu, lai)
    return out


def _khop_pct(got: Optional[float], part: Fraction, whole: Fraction, nd: int) -> bool:
    """`got` là phần trăm làm tròn `nd` chữ số của part/whole; None khi chia cho 0."""
    if whole == 0:
        return got is None
    if got is None:
        return False
    chinh_xac = float(part / whole * 100)
    return abs(got - chinh_xac) <= 0.5 * 10 ** -nd + 1e-9 + 4e-16 * abs(chinh_xac)


# ---------------------------------------------------------------------------
# Chiến lược sinh dữ liệu
# ---------------------------------------------------------------------------

_MUC = st.sampled_from(GRANULARITIES)
# Một lần rút (số nguyên) thay cho ba lần rút của st.dates: sinh nhanh hơn rõ rệt, đủ phủ 24 tháng.
_NGAY = st.integers(0, 729).map(lambda i: date(2025, 1, 1) + timedelta(days=i))
# Có cả tên trùng sau khi cắt khoảng trắng và tên rỗng (-> "(không rõ tên)").
_TEN = st.sampled_from(["Gạo", "  Gạo ", "Dầu DO", "Xi măng", "", "   "])


def _tien(mau: int = 1, toi_da: int = _MAX, am: bool = False):
    """Số tiền là bội của 1/mau (mau=1: đồng nguyên; mau=4: có lẻ 0,25) và nằm trong float chính xác."""
    return st.integers(-toi_da * mau if am else 0, toi_da * mau).map(lambda n: Fraction(n, mau))


def _ban(mau: int = 1, am: bool = False, thieu: bool = True):
    von = _tien(mau)
    return st.builds(
        Ban, ngay=_NGAY, tien=_tien(mau, am=am), ten=_TEN,
        sl=_tien(mau, toi_da=10**6), von=(st.none() | von) if thieu else von,
    )


def _ds_ban(mau: int = 1, am: bool = False, thieu: bool = True, toi_da: int = 6):
    return st.lists(_ban(mau, am, thieu), max_size=toi_da)


def _ds_chi(mau: int = 1, toi_da: int = 4):
    return st.lists(st.builds(Chi, ngay=_NGAY, tien=_tien(mau)), max_size=toi_da)


def _chay(ban, chi=(), muc: str = "quarter", lui: int = _TAT_CA, top_n: int = 100) -> dict:
    return build_report(ReportRequest(
        granularity=muc, periods_back=lui, top_n=top_n,
        sales=[b.dong() for b in ban], expenses=[c.dong() for c in chi],
    ))


def _theo_ky(out: dict) -> dict[str, dict]:
    return {p["period"]: p for p in out["periods"]}


# ===========================================================================
# 1. period_key
# ===========================================================================

@CAU_HINH
@given(nam=st.integers(1000, 9998))
def test_period_key_chia_mot_nam_thanh_12_4_2_1_ky_lien_khoi_long_nhau(nam):
    """Mỗi năm đúng 12 tháng / 4 quý / 2 nửa năm / 1 năm; nhãn không bao giờ đảo thứ tự; kỳ nhỏ nằm trọn trong kỳ lớn."""
    so_ngay = (date(nam + 1, 1, 1) - date(nam, 1, 1)).days
    ngay = [date(nam, 1, 1) + timedelta(days=i) for i in range(so_ngay)]
    ky = {m: [period_key(d, m) for d in ngay] for m in GRANULARITIES}
    for muc, so_ky in zip(GRANULARITIES, (12, 4, 2, 1)):
        assert ky[muc] == sorted(ky[muc]), f"{muc}: nhãn kỳ đảo thứ tự theo ngày"
        assert len(set(ky[muc])) == so_ky, f"{muc}: năm {nam} phải có đúng {so_ky} kỳ"
        assert all(k.startswith(str(nam)) for k in ky[muc])
    for min_, lon in (("month", "quarter"), ("quarter", "half"), ("half", "year")):
        cap = set(zip(ky[min_], ky[lon]))
        assert len(cap) == len(set(ky[min_])), f"một {min_} bị chia vào hai {lon}"


@CAU_HINH
@given(muc=st.text().filter(lambda s: s not in GRANULARITIES))
def test_period_key_tu_choi_muc_la(muc):
    """Mức lạ là lỗi rõ ràng (ValueError), không âm thầm đoán một kỳ."""
    with pytest.raises(ValueError):
        period_key(date(2026, 7, 27), muc)


# ===========================================================================
# 2. Doanh thu, thứ tự, cộng dòng
# ===========================================================================

@CAU_HINH
@given(ban=_ds_ban(am=True), muc=_MUC)
def test_tong_doanh_thu_cac_ky_bang_tong_cac_dong(ban, muc):
    """Không dòng nào mất, không dòng nào đếm hai lần: Σ doanh thu các kỳ = Σ doanh thu các dòng (kể cả dòng trả hàng âm)."""
    out = _chay(ban, [], muc)
    assert sum(p["revenue"] for p in out["periods"]) == sum(b.tien for b in ban)
    assert sum(p["orders"] for p in out["periods"]) == len(ban)
    dung = {k.nhan: k.dt for k in mau_cac_ky(ban, [], muc)}
    assert {k: p["revenue"] for k, p in _theo_ky(out).items()} == dung


@CAU_HINH
@given(ban=_ds_ban(mau=4), chi=_ds_chi(mau=4), muc=_MUC)
def test_cac_khoan_tien_cua_ky_khop_mo_hinh_chinh_xac_trong_nua_dong(ban, chi, muc):
    """Doanh thu, giá vốn, lãi gộp, chi phí, lãi ròng của từng kỳ = số chính xác, chỉ lệch vì làm tròn (<= 0,5 đồng)."""
    out = _chay(ban, chi, muc)
    mau = mau_cac_ky(ban, chi, muc)
    assert [p["period"] for p in out["periods"]] == [k.nhan for k in mau]
    for p, k in zip(out["periods"], mau):
        for truong, dung in (("revenue", k.dt), ("cogs", k.von), ("gross_profit", k.lai_gop),
                             ("operating_expenses", k.chi), ("net_profit", k.lai_rong)):
            assert abs(p[truong] - dung) <= Fraction(1, 2), f"{k.nhan}.{truong}: {p[truong]} vs {dung}"
        assert p["orders"] == k.don


@CAU_HINH
@given(ban=_ds_ban(mau=4), chi=_ds_chi(mau=4), muc=_MUC, data=st.data())
def test_tat_dinh_khong_sua_dau_vao_va_khong_phu_thuoc_thu_tu_cac_dong(ban, chi, muc, data):
    """Gọi hai lần ra một kết quả và không sửa `ReportRequest`; đảo thứ tự dòng không đổi kỳ, tổng, độ tin cậy, cảnh báo, số liệu từng mặt hàng."""
    ban2 = data.draw(st.permutations(ban))
    chi2 = data.draw(st.permutations(chi))
    req = ReportRequest(granularity=muc, periods_back=_TAT_CA, top_n=100,
                        sales=[b.dong() for b in ban], expenses=[c.dong() for c in chi])
    anh = copy.deepcopy(req)
    a = build_report(req)
    assert req == anh, "build_report sửa đầu vào"
    assert build_report(req) == a, "cùng đầu vào, hai lần gọi cho hai kết quả"
    b = _chay(ban2, chi2, muc)
    assert a["periods"] == b["periods"]
    assert a["explain"] == b["explain"]
    assert a["warnings"] == b["warnings"]
    assert {r["product"]: r for r in a["products"]} == {r["product"]: r for r in b["products"]}


_SO = ("revenue", "cogs", "gross_profit", "operating_expenses", "net_profit", "orders")


@CAU_HINH
@given(ban=_ds_ban(), chi=_ds_chi(), them=_ban(), muc=_MUC)
def test_them_mot_dong_thi_ky_do_tang_dung_so_tien_cua_dong_do(ban, chi, them, muc):
    """Thêm dòng bán x vào một kỳ: doanh thu kỳ đó tăng ĐÚNG x, đơn +1; giá vốn/lãi gộp tăng đúng phần dòng đó có giá vốn; kỳ khác không đổi."""
    truoc, sau = _theo_ky(_chay(ban, chi, muc)), _theo_ky(_chay([*ban, them], chi, muc))
    ky = _ky(them.ngay, muc)[2]
    t, s = truoc.get(ky, dict.fromkeys(_SO, 0)), sau[ky]
    von = them.von
    lai = 0 if von is None else them.tien - von
    assert s["revenue"] == t["revenue"] + them.tien
    assert s["orders"] == t["orders"] + 1
    assert s["cogs"] == t["cogs"] + (0 if von is None else von)
    assert s["gross_profit"] == t["gross_profit"] + lai
    assert s["net_profit"] == t["net_profit"] + lai
    for k in sau:
        if k != ky:
            assert {f: sau[k][f] for f in _SO} == {f: truoc[k][f] for f in _SO}


@CAU_HINH
@given(ban=_ds_ban(), chi=_ds_chi(), muc=_MUC, lui=st.integers(1, _TAT_CA))
def test_chi_giu_cac_ky_gan_nhat_theo_thu_tu_thoi_gian(ban, chi, muc, lui):
    """`periods_back` giữ N kỳ GẦN NHẤT, trả theo thứ tự thời gian; kỳ đầu của báo cáo chưa có kỳ trước nên chưa có tăng trưởng."""
    out = _chay(ban, chi, muc, lui=lui)
    dung = [k.nhan for k in mau_cac_ky(ban, chi, muc)][-lui:]
    assert [p["period"] for p in out["periods"]] == dung
    if out["periods"]:
        assert out["periods"][0]["revenue_growth_pct"] is None
        assert out["periods"][0]["net_profit_growth_pct"] is None
    assert out["explain"]["period_count"] == len(dung)


@CAU_HINH
@given(ban=_ds_ban(mau=4), chi=_ds_chi(mau=4), muc=_MUC, lui=st.integers(1, 6))
def test_bien_loi_nhuan_va_tang_truong_khop_cong_thuc(ban, chi, muc, lui):
    """Biên lãi gộp (trên doanh thu CÓ giá vốn), biên lãi ròng, tăng trưởng DT và lãi ròng đúng công thức; mẫu số 0 thì None."""
    out = _chay(ban, chi, muc, lui=lui)
    mau = mau_cac_ky(ban, chi, muc)[-lui:]
    truoc: Optional[KyMau] = None
    for p, k in zip(out["periods"], mau):
        assert _khop_pct(p["gross_margin_pct"], k.lai_gop, k.dt_co_von, 2), k.nhan
        assert _khop_pct(p["net_margin_pct"], k.lai_rong, k.dt, 2), k.nhan
        if truoc is None:
            assert p["revenue_growth_pct"] is None and p["net_profit_growth_pct"] is None
        else:
            assert _khop_pct(p["revenue_growth_pct"], k.dt - truoc.dt, truoc.dt, 2), k.nhan
            assert _khop_pct(p["net_profit_growth_pct"], k.lai_rong - truoc.lai_rong,
                             abs(truoc.lai_rong), 2), k.nhan
        truoc = k


# ===========================================================================
# 3. Giá vốn thiếu: "chưa biết" không phải 0 (R1)
# ===========================================================================

@CAU_HINH
@given(ban=_ds_ban(), muc=_MUC)
def test_gia_von_none_khong_bao_gio_bi_tinh_nhu_0(ban, muc):
    """Đổi mọi `cogs=None` thành 0 làm lãi gộp phình ĐÚNG bằng doanh thu các dòng đó. Báo cáo gốc không được phình như vậy."""
    voi_none = _theo_ky(_chay(ban, [], muc))
    voi_0 = _theo_ky(_chay([replace(b, von=Fraction(0)) if b.von is None else b for b in ban], [], muc))
    thieu: dict[str, Fraction] = {}
    for b in ban:
        if b.von is None:
            nhan = _ky(b.ngay, muc)[2]
            thieu[nhan] = thieu.get(nhan, Fraction(0)) + b.tien
    for nhan, p in voi_none.items():
        assert p["cogs"] == voi_0[nhan]["cogs"], "dòng thiếu giá vốn không được cộng thêm giá vốn nào"
        assert voi_0[nhan]["gross_profit"] - p["gross_profit"] == thieu.get(nhan, 0)


@CAU_HINH
@given(ban=_ds_ban(), muc=_MUC)
def test_lai_gop_chi_tinh_tren_phan_co_gia_von(ban, muc):
    """Lãi gộp = doanh thu CÓ giá vốn − giá vốn; kỳ còn dòng thiếu giá vốn (doanh thu > 0) thì lãi gộp < doanh thu; biên không vượt 100%."""
    mau = {k.nhan: k for k in mau_cac_ky(ban, [], muc)}
    for p in _chay(ban, [], muc)["periods"]:
        k = mau[p["period"]]
        assert p["gross_profit"] == k.lai_gop
        if k.dt > k.dt_co_von:
            assert p["gross_profit"] < p["revenue"], "lãi gộp = doanh thu là dấu hiệu coi giá vốn thiếu là 0"
        if k.dt_co_von == 0:
            assert p["gross_margin_pct"] is None
        else:
            assert p["gross_margin_pct"] <= 100


@CAU_HINH
@given(ban=_ds_ban(mau=4), muc=_MUC)
def test_phu_gia_von_tinh_theo_doanh_thu_va_nam_trong_0_den_100(ban, muc):
    """`cogs_coverage_pct` = doanh thu có giá vốn / doanh thu (theo kỳ và toàn báo cáo), trong [0,100]; kỳ chưa có doanh thu là None chứ không phải 0."""
    out = _chay(ban, [], muc)
    mau = mau_cac_ky(ban, [], muc)
    for p, k in zip(out["periods"], mau):
        pct = p["cogs_coverage_pct"]
        assert _khop_pct(pct, k.dt_co_von, k.dt, 1), k.nhan
        assert pct is None or 0 <= pct <= 100
    tong = sum(k.dt for k in mau)   # chưa làm tròn: mẫu số làm tròn từng ra 125% (xem mục 6)
    assert _khop_pct(out["explain"]["cogs_coverage_pct"], sum(k.dt_co_von for k in mau), Fraction(tong), 1)


def _tin_cay_dung(co_von: Fraction, tong: Fraction) -> str:
    if tong == 0:
        return "không có dữ liệu"
    ty_le = co_von / tong
    return "cao" if ty_le >= Fraction(19, 20) else "trung bình" if ty_le >= Fraction(7, 10) else "thấp"


def _canh_bao_tin_cay_ok(conf: str, warnings: list[str]) -> bool:
    co = any("doanh thu có giá vốn" in w for w in warnings)
    return co == (conf in ("thấp", "trung bình"))


@CAU_HINH
@given(ban=_ds_ban(), muc=_MUC)
def test_do_tin_cay_theo_ty_le_phu_va_canh_bao_di_kem(ban, muc):
    """Độ tin cậy là hàm của tỷ lệ phủ (>=95% cao, >=70% trung bình, còn lại thấp); thấp/trung bình luôn kèm cảnh báo, cao thì không."""
    out = _chay(ban, [], muc)
    tong = sum((b.tien for b in ban), Fraction(0))
    co_von = sum((b.tien for b in ban if b.von is not None), Fraction(0))
    assert out["explain"]["confidence"] == _tin_cay_dung(co_von, tong)
    assert _canh_bao_tin_cay_ok(out["explain"]["confidence"], out["warnings"])


@CAU_HINH
@given(k=st.integers(1, 10**9), lech=st.integers(-1, 1), moc=st.sampled_from([(19, 20), (7, 10)]),
       muc=_MUC, ngay=_NGAY)
def test_do_tin_cay_doi_dung_tai_hai_bien_95_va_70(k, lech, moc, muc, ngay):
    """Sát hai biên (đúng, thiếu một đồng, dư một đồng): `>=` không được hoá thành `>`, biên không được trôi."""
    tu, mau = moc
    co_von, tong = tu * k + lech, mau * k
    ban = [Ban(ngay, Fraction(co_von), "A", Fraction(1), Fraction(0)),
           Ban(ngay, Fraction(tong - co_von), "A", Fraction(1), None)]
    out = _chay(ban, [], muc)
    assert out["explain"]["confidence"] == _tin_cay_dung(Fraction(co_von), Fraction(tong))
    assert _canh_bao_tin_cay_ok(out["explain"]["confidence"], out["warnings"])


@CAU_HINH
@given(ban=_ds_ban(thieu=False), muc=_MUC, data=st.data())
def test_bot_gia_von_di_thi_phu_va_tin_cay_khong_tang(ban, muc, data):
    """Xoá giá vốn của một số dòng (doanh thu giữ nguyên): tỷ lệ phủ không tăng, độ tin cậy không cao hơn."""
    mat = data.draw(st.lists(st.booleans(), min_size=len(ban), max_size=len(ban)))
    thieu = [replace(b, von=None) if m else b for b, m in zip(ban, mat)]
    a, b = _chay(ban, [], muc)["explain"], _chay(thieu, [], muc)["explain"]
    if a["cogs_coverage_pct"] is None:
        assert b["cogs_coverage_pct"] is None and b["confidence"] == a["confidence"]
    else:
        assert b["cogs_coverage_pct"] <= a["cogs_coverage_pct"]
        assert _HANG[b["confidence"]] <= _HANG[a["confidence"]]


# ===========================================================================
# 4. Lãi ròng, chi phí, cảnh báo
# ===========================================================================

@CAU_HINH
@given(ban=_ds_ban(), chi=_ds_chi(), muc=_MUC)
def test_lai_rong_bang_lai_gop_tru_chi_phi_va_chi_phi_cong_du(ban, chi, muc):
    """Lãi ròng = lãi gộp − chi phí vận hành; Σ chi phí các kỳ = Σ dòng chi phí; kỳ chỉ có chi phí vẫn hiện; cảnh báo 'chưa có chi phí' đúng lúc."""
    out = _chay(ban, chi, muc)
    for p in out["periods"]:
        assert p["net_profit"] == p["gross_profit"] - p["operating_expenses"]
    assert sum(p["operating_expenses"] for p in out["periods"]) == sum(c.tien for c in chi)
    assert [p["period"] for p in out["periods"]] == [k.nhan for k in mau_cac_ky(ban, chi, muc)]
    if ban or chi:
        assert any("Chưa có dữ liệu chi phí" in w for w in out["warnings"]) == (not chi)


# ===========================================================================
# 5. Hình dạng đầu ra: đủ khoá, không ném, không NaN (hợp đồng với Body)
# ===========================================================================

_TIEN_F = st.one_of(st.just(0.0), st.floats(min_value=0.01, max_value=1e12))
_NGAY_XAU = st.sampled_from(["", "27/07/2026", "abc", "2026-13-01", "2026-02-30", "2026/07/27"])
_NGAY_CHUOI = st.one_of(
    _NGAY.map(date.isoformat),
    _NGAY.map(lambda d: d.isoformat() + "T08:30:00"),
    _NGAY_XAU,
)
_SALE_F = st.builds(SaleLine, date=_NGAY_CHUOI, revenue=_TIEN_F, product=_TEN, quantity=_TIEN_F,
                    cogs=st.none() | _TIEN_F)
_EXP_F = st.builds(ExpenseLine, date=_NGAY_CHUOI, amount=_TIEN_F)


@CAU_HINH
@given(sales=st.lists(_SALE_F, max_size=8), expenses=st.lists(_EXP_F, max_size=4), muc=_MUC,
       lui=st.integers(1, _TAT_CA), top_n=st.integers(1, 100))
def test_moi_dau_vao_deu_tra_du_khoa_khong_nem_va_khong_ra_nan(sales, expenses, muc, lui, top_n):
    """Rỗng, chỉ chi phí, chỉ dòng thiếu giá vốn, ngày sai...: luôn trả đủ khoá, không ngoại lệ, không NaN/inf (JSON nghiêm ngặt)."""
    out = build_report(ReportRequest(granularity=muc, periods_back=lui, top_n=top_n,
                                     sales=sales, expenses=expenses))
    json.dumps(out, allow_nan=False)
    assert set(out) == _KHOA_TREN
    ex = out["explain"]
    assert _KHOA_EXPLAIN <= set(ex)
    assert ex["confidence"] in _TIN_CAY
    assert (ex["cogs_coverage_pct"] is None) == (ex["confidence"] == "không có dữ liệu"), \
        "chưa đo được thì phải tự nói là chưa biết, và đã đo thì không được nhãn 'không có dữ liệu'"
    assert ex["cogs_coverage_pct"] is None or 0 <= ex["cogs_coverage_pct"] <= 100
    assert ex["period_count"] == len(out["periods"]) <= lui
    assert len(out["products"]) <= top_n
    assert all(set(p) == _KHOA_KY for p in out["periods"])
    assert all(isinstance(w, str) for w in out["warnings"])


@CAU_HINH
@given(muc=_MUC, lui=st.integers(1, _TAT_CA), top_n=st.integers(1, 100))
def test_dau_vao_rong_tra_khoa_day_du_voi_gia_tri_chua_biet_khong_phai_0(muc, lui, top_n):
    """Không có dòng nào: `cogs_coverage_pct` là None (chưa đo), KHÔNG phải 0; vẫn đủ bốn khoá Body render (AGENTS R1)."""
    ex = _chay([], [], muc, lui, top_n)["explain"]
    assert ex["cogs_coverage_pct"] is None and ex["confidence"] == "không có dữ liệu"
    assert _KHOA_EXPLAIN <= set(ex) and ex["period_count"] == 0


@CAU_HINH
@given(ban=_ds_ban(thieu=False).map(lambda ds: [replace(b, von=None) for b in ds]), muc=_MUC)
def test_chi_co_dong_thieu_gia_von_phu_la_0_do_duoc_va_tin_cay_thap(ban, muc):
    """Có doanh thu mà không dòng nào có giá vốn: phủ 0,0% LÀ phép đo (khác None) và độ tin cậy 'thấp'; không doanh thu thì None."""
    out = _chay(ban, [], muc)
    ex = out["explain"]
    if sum(b.tien for b in ban) > 0:
        assert ex["cogs_coverage_pct"] == 0.0 and ex["confidence"] == "thấp"
        assert any("CHƯA đủ" in w for w in out["warnings"])
    else:
        assert ex["cogs_coverage_pct"] is None
    assert all(r["missing_cogs"] and r["gross_profit"] is None for r in out["products"])


@CAU_HINH
@given(ban=_ds_ban(), chi=_ds_chi(), xau_ban=st.lists(_NGAY_XAU, max_size=4),
       xau_chi=st.lists(_NGAY_XAU, max_size=3), muc=_MUC)
def test_dong_ngay_sai_duoc_dem_canh_bao_va_khong_vao_cac_ky(ban, chi, xau_ban, xau_chi, muc):
    """Dòng sai ngày không đổi bất kỳ kỳ nào, và được đếm ĐÚNG SỐ trong một cảnh báo duy nhất."""
    sach = _chay(ban, chi, muc)
    them_ban = [SaleLine(date=x, revenue=999.0, product="Z", quantity=1.0, cogs=1.0) for x in xau_ban]
    them_chi = [ExpenseLine(date=x, amount=999.0) for x in xau_chi]
    out = build_report(ReportRequest(
        granularity=muc, periods_back=_TAT_CA, top_n=100,
        sales=[*(b.dong() for b in ban), *them_ban], expenses=[*(c.dong() for c in chi), *them_chi]))
    assert out["periods"] == sach["periods"] and out["explain"] == sach["explain"]
    nhan = [w for w in out["warnings"] if "ngày sai định dạng" in w]
    so_sai = len(xau_ban) + len(xau_chi)
    assert (len(nhan) == 1 and nhan[0].startswith(f"{so_sai} dòng")) if so_sai else not nhan


@CAU_HINH
@given(ban=_ds_ban(), chi=_ds_chi(), muc=_MUC,
       hau_to=st.sampled_from(["T00:00:00", " 23:59", "T10:30:00+07:00"]))
def test_gio_di_kem_ngay_khong_doi_ky(ban, chi, muc, hau_to):
    """Ngày kèm giờ ('2026-07-27T10:30:00') vẫn là ngày đó: cùng báo cáo như khi chỉ có ngày."""
    thuong = _chay(ban, chi, muc)
    out = build_report(ReportRequest(
        granularity=muc, periods_back=_TAT_CA, top_n=100,
        sales=[replace(b.dong(), date=b.dong().date + hau_to) for b in ban],
        expenses=[replace(c.dong(), date=c.dong().date + hau_to) for c in chi]))
    assert out == thuong


@CAU_HINH
@given(so_dong=st.integers(1, 15), ban=st.data(), muc=_MUC)
def test_so_tien_lon_toi_10_mu_12_khong_tran_va_ra_so_nguyen(so_dong, ban, muc):
    """Tới 15 dòng, mỗi dòng sát 10^12 đồng: tổng đúng từng đồng, kiểu số nguyên, biên không vượt 100%, JSON được."""
    lon = st.integers(_MAX - 1000, _MAX).map(Fraction)
    ds = ban.draw(st.lists(st.builds(Ban, ngay=_NGAY, tien=lon, ten=_TEN, sl=lon, von=st.none() | lon),
                           min_size=so_dong, max_size=so_dong))
    out = _chay(ds, [], muc)
    json.dumps(out, allow_nan=False)
    assert sum(p["revenue"] for p in out["periods"]) == sum(b.tien for b in ds)
    assert all(type(p[f]) is int for p in out["periods"] for f in _SO)
    assert all(p["gross_margin_pct"] is None or p["gross_margin_pct"] <= 100 for p in out["periods"])


# ===========================================================================
# 6. Bảng mặt hàng
# ===========================================================================

@CAU_HINH
@given(ban=_ds_ban(mau=4), top_n=st.integers(1, 100))
def test_bang_mat_hang_khop_mo_hinh_va_xep_hang_dung_quy_uoc(ban, top_n):
    """Tên được cắt khoảng trắng; doanh thu/sản lượng/lãi đúng; thiếu giá vốn THÌ gross_profit=None (không phải 0); xếp lãi giảm dần trước, thiếu giá vốn sau theo doanh thu."""
    rows = product_profitability([b.dong() for b in ban], top_n=top_n)
    mau = mau_mat_hang(ban)
    assert len(rows) == min(top_n, len(mau))
    for r in rows:
        m = mau[r["product"]]
        assert abs(r["revenue"] - m.dt) <= Fraction(1, 2)
        assert r["quantity"] == float(m.sl)
        assert r["missing_cogs"] == m.thieu
        if m.thieu:
            assert r["gross_profit"] is None and r["gross_margin_pct"] is None
        else:
            assert abs(r["gross_profit"] - m.lai) <= Fraction(1, 2)
            assert _khop_pct(r["gross_margin_pct"], m.lai, m.dt, 2)
    for a, b in zip(rows, rows[1:]):
        if a["gross_profit"] is None:
            assert b["gross_profit"] is None, "có lãi tính được phải đứng trước mặt hàng thiếu giá vốn"
            assert a["revenue"] >= b["revenue"]
        elif b["gross_profit"] is not None:
            assert a["gross_profit"] >= b["gross_profit"]
    # Cắt top-N không làm đổi thứ hạng hay số liệu: nó đúng là N dòng đầu của bảng đầy đủ.
    assert rows == product_profitability([b.dong() for b in ban], top_n=100)[:top_n]


@CAU_HINH
@given(ban=_ds_ban(), muc=_MUC)
def test_ty_trong_doanh_thu_mat_hang_cong_lai_xap_xi_100(ban, muc):
    """Tỷ trọng doanh thu của các mặt hàng trong [0,100], cộng lại ~100% (sai số làm tròn); tổng doanh thu 0 thì None; và khớp tổng các kỳ."""
    out = _chay(ban, [], muc)
    tong = sum(b.tien for b in ban)
    chia = [r["revenue_share_pct"] for r in out["products"]]
    if tong == 0:
        assert all(c is None for c in chia)
    else:
        assert all(0 <= c <= 100 for c in chia)
        assert abs(sum(chia) - 100) <= 0.005 * len(chia) + 1e-9
    # Hai cách nhìn của CÙNG một báo cáo phải khớp khi dữ liệu sạch và không kỳ nào bị cắt.
    assert sum(r["revenue"] for r in out["products"]) == sum(p["revenue"] for p in out["periods"])


# ===========================================================================
# 7. LỖI THẬT do hypothesis tìm ra (xfail strict: sửa mã thì test này XPASS và phải gỡ dấu)
# ===========================================================================

@pytest.mark.xfail(strict=True, reason=(
    "Kỳ gần nhất chọn bằng sorted() trên CHUỖI nhãn, mà period_key không đệm số 0 cho năm: năm 999 ra '999', "
    "lớn hơn '1000' theo chuỗi. Phản ví dụ nhỏ nhất: granularity='year', periods_back=1, dòng ngày "
    "0999-12-31 và 1000-01-01 -> báo cáo giữ kỳ '999' thay vì '1000'. Chỉ đụng ngày gõ nhầm năm 3 chữ số "
    "(mức thấp), nhưng gõ nhầm đó đẩy dữ liệu thật ra khỏi báo cáo."))
@CAU_HINH
@example(d1=date(999, 12, 31), d2=date(1000, 1, 1), muc="year")
@given(d1=st.dates(), d2=st.dates(), muc=_MUC)
def test_ky_gan_nhat_la_ky_cua_ngay_muon_nhat_ca_voi_nam_ngan(d1, d2, muc):
    """Hai ngày bất kỳ (mọi năm hợp lệ của `date`): periods_back=1 phải giữ kỳ của ngày muộn hơn."""
    muon = max(d1, d2)
    out = _chay([Ban(d, Fraction(1), "A", Fraction(1), None) for d in (d1, d2)], [], muc, lui=1)
    assert [p["period"] for p in out["periods"]] == [_ky(muon, muc)[2]]


@pytest.mark.xfail(strict=True, reason=(
    "Giá trị vô hạn lọt qua schema Pydantic (float chấp nhận Infinity) rồi làm round() ném OverflowError — "
    "không phải ValueError nên /tools/report không đổi thành 422 mà thành 500. Phản ví dụ nhỏ nhất: "
    "SaleLine(date='2026-01-01', revenue=float('inf')). (NaN thì ném ValueError -> 422, chấp nhận được.)"))
@CAU_HINH
@example(vi_tri="revenue", xau=float("inf"))
@given(vi_tri=st.sampled_from(["revenue", "cogs", "amount"]), xau=st.sampled_from([float("inf"), float("-inf")]))
def test_gia_tri_vo_han_chi_duoc_nem_value_error(vi_tri, xau):
    """Đầu vào số vô hạn: hoặc trả kết quả, hoặc ValueError (endpoint đổi thành 422) — không ngoại lệ nào khác."""
    sale = SaleLine(date="2026-01-01", revenue=xau if vi_tri == "revenue" else 5.0,
                    cogs=xau if vi_tri == "cogs" else 1.0)
    exp = [ExpenseLine(date="2026-01-01", amount=xau)] if vi_tri == "amount" else []
    try:
        build_report(ReportRequest(sales=[sale], expenses=exp))
    except ValueError:
        pass


@pytest.mark.xfail(strict=True, reason=(
    "Dòng ngày sai bị cảnh báo là 'đã bỏ qua' nhưng build_report vẫn đưa `req.sales` nguyên vẹn vào "
    "product_profitability, nên doanh thu của chúng nằm trong bảng mặt hàng mà không nằm trong kỳ nào. "
    "Phản ví dụ nhỏ nhất: một dòng hợp lệ + SaleLine(date='', revenue=1.0, product='Z') -> bảng mặt hàng "
    "có thêm 'Z'. (Đánh giá: mâu thuẫn với chính câu cảnh báo; nếu chủ ý để bảng mặt hàng tính cả dòng "
    "sai ngày thì sửa câu cảnh báo và gỡ test này.)"))
@CAU_HINH
@example(co_ban=Ban(date(2026, 1, 1), Fraction(5), "A", Fraction(1), None), xau="", tien=1)
@given(co_ban=_ban(), xau=_NGAY_XAU, tien=st.integers(1, 10**6))
def test_dong_ngay_sai_khong_lot_vao_bang_mat_hang(co_ban, xau, tien):
    """Cảnh báo nói 'đã bỏ qua' thì dòng sai ngày không được xuất hiện ở đâu trong báo cáo, kể cả bảng mặt hàng."""
    bo_qua = SaleLine(date=xau, revenue=float(tien), product="Z", quantity=1.0, cogs=None)
    goc = build_report(ReportRequest(sales=[co_ban.dong()]))
    them = build_report(ReportRequest(sales=[co_ban.dong(), bo_qua]))
    assert them["products"] == goc["products"]


@pytest.mark.xfail(strict=True, reason=(
    "Schema /tools/report không chặn revenue âm (dòng trả hàng), và phủ giá vốn tính bằng "
    "doanh_thu_có_giá_vốn/doanh_thu nên có thể ra ngoài [0,100]. Phản ví dụ nhỏ nhất: dòng (100đ, chưa có giá "
    "vốn) + dòng (-50đ, giá vốn 10đ) cùng một kỳ -> cogs_coverage_pct = -100,0. Chỉ lỗi nếu dòng trả hàng "
    "âm là đầu vào hợp lệ (schema cho phép; chưa rõ Body có gửi)."))
@CAU_HINH
@example(ban=[Ban(date(2026, 1, 1), Fraction(100), "A", Fraction(1), None),
              Ban(date(2026, 1, 2), Fraction(-50), "A", Fraction(1), Fraction(10))], muc="quarter")
@given(ban=_ds_ban(am=True), muc=_MUC)
def test_phu_gia_von_nam_trong_0_den_100_ca_khi_co_dong_tra_hang_am(ban, muc):
    """Phần trăm phủ giá vốn không bao giờ ra ngoài [0,100] dù có dòng doanh thu âm."""
    out = _chay(ban, [], muc)
    for pct in [p["cogs_coverage_pct"] for p in out["periods"]] + [out["explain"]["cogs_coverage_pct"]]:
        assert pct is None or 0 <= pct <= 100


# ===========================================================================
# 6. Hồi quy: phủ giá vốn không vượt 100% vì làm tròn (Hypothesis tìm ra khi chạy cùng test_prop_pricing)
# ===========================================================================

def test_phu_gia_von_khong_vuot_100_khi_doanh_thu_le_duoi_mot_dong():
    """Doanh thu 1,25 có giá vốn: tử chưa tròn / mẫu đã tròn từng ra 125%."""
    out = build_report(ReportRequest(granularity="month", periods_back=1, top_n=1, expenses=[], sales=[
        SaleLine(date="2025-01-01", revenue=1.25, product="Gạo", quantity=1.0, cogs=0.0)]))
    assert out["explain"]["cogs_coverage_pct"] == 100.0


def test_doanh_thu_duoi_nua_dong_van_la_co_doanh_thu():
    """Doanh thu 0,4 làm tròn về 0 không được rơi vào nhánh 'không có doanh thu'."""
    out = build_report(ReportRequest(granularity="month", periods_back=1, top_n=1, expenses=[], sales=[
        SaleLine(date="2025-01-01", revenue=0.4, product="Gạo", quantity=1.0, cogs=0.1)]))
    assert out["explain"]["confidence"] != "không có dữ liệu"
    assert out["explain"]["cogs_coverage_pct"] == 100.0
