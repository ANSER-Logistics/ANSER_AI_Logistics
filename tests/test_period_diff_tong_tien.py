"""
tests/test_period_diff_tong_tien.py — `tổng_tiền_ảnh_hưởng` không được âm thầm bỏ phát hiện
chưa quy ra tiền.

`money_impact=None` nghĩa là "chưa quy ra tiền được" (xem `findings.py`), khác 0. Bản cũ
cộng `f["money_impact"] or 0`, nên một mã biến mất mà không có giá trị cuối kỳ đóng góp 0 vào
con số đầu bảng chủ doanh nghiệp đọc — tổng thấp hơn thực tế mà không nói.

Cùng họ lỗi "chưa biết ≠ 0" với PR #40; chỗ này tách riêng vì có một cái bẫy: `warnings`
KHÔNG được dùng để báo, vì Body hiểu `warnings` không rỗng là Brain TỪ CHỐI so.
"""

from __future__ import annotations

from src.core.inventory import InventoryLine
from src.core.inventory_import import ParseResult
from src.core.period_diff import doi_chieu_hai_lan_xuat


def _ky(lines, den, tu="2026-01-01") -> ParseResult:
    return ParseResult(lines=lines, warehouse="KHO", period_start=tu, period_end=den)


def _dong(code, **kw) -> InventoryLine:
    goc = dict(name="Hàng thử", unit="Lít", opening_qty=0.0, opening_value=0.0,
               in_qty=0.0, in_value=0.0, out_qty=0.0, out_value=0.0,
               closing_qty=0.0, closing_value=0.0)
    goc.update(kw)
    return InventoryLine(code=code, **goc)


def _truoc_sau(*, bien_mat_biet_gia_tri: bool):
    """Hai mã cùng biến mất ở bản sau: A có giá trị cuối kỳ 5.000.000, B thì tuỳ ca."""
    a = _dong("A", closing_qty=10, closing_value=5_000_000)
    b = _dong("B", closing_qty=4, closing_value=None if bien_mat_biet_gia_tri else 2_000_000)
    con_lai = _dong("C", closing_qty=1, closing_value=100)
    return _ky([a, b, con_lai], "2026-02-28"), _ky([con_lai], "2026-03-31")


def test_phat_hien_chua_quy_ra_tien_duoc_dem_rieng_khong_cong_nhu_0():
    kq = doi_chieu_hai_lan_xuat(*_truoc_sau(bien_mat_biet_gia_tri=True))
    s = kq["summary"]
    assert s["tổng_tiền_ảnh_hưởng"] == 5_000_000          # chỉ phần đã quy ra tiền
    assert s["số_phát_hiện_chưa_quy_ra_tiền"] == 1        # và nói thẳng còn một phần chưa
    assert s["số_phát_hiện"] == 2


def test_du_gia_tri_thi_khong_co_phan_chua_quy():
    kq = doi_chieu_hai_lan_xuat(*_truoc_sau(bien_mat_biet_gia_tri=False))
    s = kq["summary"]
    assert s["tổng_tiền_ảnh_hưởng"] == 7_000_000
    assert s["số_phát_hiện_chưa_quy_ra_tiền"] == 0


def test_khong_dung_warnings_de_bao_vi_body_hieu_do_la_tu_choi_so():
    """Hợp đồng với Body: `warnings` KHÔNG rỗng nghĩa là Brain từ chối so. Ca này vẫn so được."""
    kq = doi_chieu_hai_lan_xuat(*_truoc_sau(bien_mat_biet_gia_tri=True))
    assert kq["warnings"] == []
    assert kq["summary"]["so_sánh_được"] is True


def test_khong_co_phat_hien_nao_thi_ca_hai_deu_la_0():
    _, sau = _truoc_sau(bien_mat_biet_gia_tri=False)
    s = doi_chieu_hai_lan_xuat(sau, sau)["summary"]
    assert s["tổng_tiền_ảnh_hưởng"] == 0 and s["số_phát_hiện_chưa_quy_ra_tiền"] == 0


# ---------------------------------------------------------------------------
# Review độc lập 12/11/2026: giá trị cuối kỳ = 0 là ĐÃ BIẾT, không phải chưa biết
# ---------------------------------------------------------------------------

def test_gia_tri_cuoi_ky_bang_0_la_biet_chu_khong_phai_chua_quy_ra_tien():
    """`abs(x) if x else None` coi 0.0 giống None: một mã biến mất với giá trị đúng bằng 0
    bị đếm vào "chưa quy ra tiền", làm người đọc tưởng còn dữ liệu thiếu."""
    a = _dong("A", closing_qty=10, closing_value=0.0)
    con_lai = _dong("C", closing_qty=1, closing_value=100)
    kq = doi_chieu_hai_lan_xuat(_ky([a, con_lai], "2026-02-28"), _ky([con_lai], "2026-03-31"))
    s = kq["summary"]
    assert s["số_phát_hiện_chưa_quy_ra_tiền"] == 0
    assert s["tổng_tiền_ảnh_hưởng"] == 0


def test_ma_moi_co_ton_dau_ky_gia_tri_0_cung_la_biet():
    moi = _dong("N", opening_qty=5, opening_value=0.0, closing_qty=5, closing_value=0.0)
    c = _dong("C", closing_qty=1, closing_value=100)
    kq = doi_chieu_hai_lan_xuat(_ky([c], "2026-02-28"), _ky([c, moi], "2026-03-31"))
    assert kq["summary"]["số_phát_hiện_chưa_quy_ra_tiền"] == 0
