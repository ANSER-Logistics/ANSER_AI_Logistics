"""
Kiểm thử src/core/tax_id.py.

Giá trị mong đợi ở đây tính TAY từ công thức, không lấy từ chính hàm đang kiểm.

Mã số thuế và số định danh trong file này đều là giá trị TỔNG HỢP: không thuộc doanh nghiệp
hay cá nhân nào. Công thức đã được đối chiếu với các mã thật trong hồ sơ của khách pilot khi
viết module (08/2026) và không có mã nào lệch; những mã thật đó KHÔNG được đưa vào repo
công khai (AGENTS.md R2). Cho mã mới thì dùng tiền tố 99 hoặc 09: không phải mã tỉnh nào.
"""

from __future__ import annotations

import pytest

from src.core.tax_id import chuan_hoa, kiem_ma_so_thue, ma_chu_quan

# Mã số thuế tổng hợp, đúng số kiểm tra.
THAT = [
    "0991234566",   # có số 0 đầu, dùng cho các ca Excel làm mất số 0
    "9902000029",
    "0991000021",
    "9904000049",
    "9905000059",
    "9906000069",
    "9907000079",
]


def test_tinh_tay_so_kiem_tra():
    """
    0991234566 — chín chữ số đầu là 0,9,9,1,2,3,4,5,6.

        0·31 + 9·29 + 9·23 + 1·19 + 2·17 + 3·13 + 4·7 + 5·5 + 6·3
      =   0 + 261 + 207 +  19 +  34 +  39 +  28 +  25 +  18  = 631
        631 mod 11 = 4   ->   số kiểm tra = 10 − 4 = 6

    Chữ số cuối đúng là 6.
    """
    kq = kiem_ma_so_thue("0991234566")
    assert kq.hop_le is True
    assert kq.chuan_hoa == "0991234566"
    assert not kq.la_chi_nhanh


@pytest.mark.parametrize("mst", THAT)
def test_moi_ma_so_thue_that_deu_qua(mst):
    assert kiem_ma_so_thue(mst).hop_le is True


def test_doi_mot_chu_so_thi_bat_duoc():
    """Đây là toàn bộ công dụng của số kiểm tra: gõ sai một số là lộ ngay."""
    assert kiem_ma_so_thue("0991234562").hop_le is False
    assert kiem_ma_so_thue("0991244566").hop_le is False


def test_doi_cho_hai_chu_so_lien_ke_cung_bat_duoc():
    """Trọng số khác nhau cho từng vị trí nên hoán vị cũng đổi tổng."""
    assert kiem_ma_so_thue("0992134566").hop_le is False


def test_ly_do_noi_ro_chu_so_dung_phai_la_bao_nhieu():
    kq = kiem_ma_so_thue("0991234562")
    assert "2" in kq.ly_do and "6" in kq.ly_do


# ---------------------------------------------------------------------------
# Chi nhánh 13 số
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mst", [
    "0993000034-001",       # chi nhánh mẫu 1
    "9909000099-001",       # chi nhánh mẫu 2
    "9910000103-002",       # chi nhánh mẫu 3
    "9911000113-068",       # chi nhánh mẫu 4
    "9912000123-003",       # chi nhánh mẫu 5
])
def test_ma_chi_nhanh_that_deu_qua(mst):
    kq = kiem_ma_so_thue(mst)
    assert kq.hop_le is True
    assert kq.la_chi_nhanh


def test_chap_nhan_13_so_lien_khong_gach():
    assert kiem_ma_so_thue("0993000034001").hop_le is True
    assert kiem_ma_so_thue("0993000034001").chuan_hoa == "0993000034-001"


def test_chi_nhanh_000_khong_hop_le():
    assert kiem_ma_so_thue("0993000034-000").hop_le is False


def test_chi_nhanh_sai_thi_phan_10_so_van_phai_dung():
    assert kiem_ma_so_thue("0993000035-001").hop_le is False


# ---------------------------------------------------------------------------
# 'Chưa biết' KHÁC 'sai'
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["", "   ", None])
def test_o_rong_tra_None_chu_khong_tra_False(raw):
    """
    Danh sách khách hàng có 32 khách lẻ không có mã số thuế. Coi đó là 'sai'
    thì báo cáo sẽ buộc tội 32 dòng hoàn toàn bình thường.
    """
    assert kiem_ma_so_thue(raw).hop_le is None


@pytest.mark.parametrize("raw", ["123", "abcdefghij", "09912345660", "0991-234566"])
def test_khuon_la_thi_tra_None_kem_ly_do(raw):
    kq = kiem_ma_so_thue(raw)
    assert kq.hop_le is None
    assert kq.ly_do
    assert not kq.la_dinh_danh_ca_nhan


# ---------------------------------------------------------------------------
# Số định danh cá nhân 12 số — Thông tư 86/2024/TT-BTC
# ---------------------------------------------------------------------------

# Năm số định danh cá nhân tổng hợp (tiền tố 700, không phải mã tỉnh nào), dạng hộ kinh doanh
# và cá nhân dùng. Bản đầu của module báo cả năm là "không đúng khuôn".
DINH_DANH_THAT = [
    "700000000001",   # HỘ KINH DOANH LÊ VĂN MẪU 1983
    "700000000002",   # TRẦN THỊ MẪU
    "700000000003",   # HỘ KINH DOANH PHẠM VĂN MẪU 1983
    "700000000004",   # HỘ KINH DOANH MẪU MOTOR
    "700000000005",   # VŨ VĂN MẪU
]


@pytest.mark.parametrize("so", DINH_DANH_THAT)
def test_so_dinh_danh_12_so_KHONG_bi_coi_la_sai_khuon(so):
    """
    Từ 01/7/2025, cá nhân và hộ kinh doanh dùng số định danh cá nhân thay mã số
    thuế. Coi chúng là mã số thuế hỏng là buộc tội năm dòng hoàn toàn hợp lệ —
    và là kiểu lỗi sẽ xuất hiện ở MỌI khách hàng bán lẻ, không riêng khách pilot.
    """
    kq = kiem_ma_so_thue(so)
    assert kq.la_dinh_danh_ca_nhan
    assert kq.chuan_hoa == so
    assert "86/2024" in kq.ly_do


@pytest.mark.parametrize("so", DINH_DANH_THAT)
def test_so_dinh_danh_KHONG_khang_dinh_la_hop_le(so):
    """
    Số định danh không có chữ số kiểm tra như mã số thuế. Đúng khuôn nhưng
    không đối chiếu được — nói 'hợp lệ' là hứa một thứ ta không kiểm được.
    """
    assert kiem_ma_so_thue(so).hop_le is None
    assert not bool(kiem_ma_so_thue(so))


def test_khong_nham_dinh_danh_voi_ma_so_thue_chi_nhanh():
    """12 số là định danh cá nhân; 13 số là chi nhánh. Lệch một số là hai thứ khác nhau."""
    assert kiem_ma_so_thue("700000000001").la_dinh_danh_ca_nhan
    assert not kiem_ma_so_thue("0993000034-001").la_dinh_danh_ca_nhan
    assert kiem_ma_so_thue("0993000034001").la_chi_nhanh


def test_ma_chu_quan_giu_nguyen_12_so_cua_dinh_danh():
    """Cắt 10 số đầu sẽ tạo khoá vô nghĩa và có thể gom nhầm hai người."""
    assert ma_chu_quan("700000000001") == "700000000001"


def test_bool_cua_ket_qua_chi_True_khi_thuc_su_hop_le():
    assert bool(kiem_ma_so_thue("0991234566"))
    assert not bool(kiem_ma_so_thue("0991234562"))
    assert not bool(kiem_ma_so_thue(""))


# ---------------------------------------------------------------------------
# Chuẩn hoá
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,mong", [
    (" 0991234566 ", "0991234566"),
    ("0991.234.566", "0991234566"),
    ("0993000034 001", "0993000034001"),
])
def test_chuan_hoa_bo_khoang_trang_va_dau_cham(raw, mong):
    assert chuan_hoa(raw) == mong


def test_ma_chu_quan_gom_chi_nhanh_ve_phap_nhan_me():
    assert ma_chu_quan("0993000034-001") == "0993000034"
    assert ma_chu_quan("0991234566") == "0991234566"
    assert ma_chu_quan("sai") == ""


def test_excel_nuot_so_0_dau_thi_bu_lai():
    """
    Ô định dạng kiểu SỐ làm '0991234566' về tay ta thành 991234566. Không bù
    lại thì mọi mã số thuế bắt đầu bằng 0 — phần lớn mã ở Việt Nam — đều bị báo
    'sai khuôn'.
    """
    assert chuan_hoa(991234566) == "0991234566"
    assert kiem_ma_so_thue(991234566).hop_le is True
    assert chuan_hoa(993000034001) == "0993000034001"
    assert kiem_ma_so_thue(993000034001).hop_le is True


def test_khong_bu_so_0_cho_CHUOI_chin_ky_tu():
    """
    Chuỗi 9 ký tự là dữ liệu sai, không phải bị Excel cắt. Bù số 0 ở đây sẽ
    biến rác thành mã hợp lệ một cách ngẫu nhiên.
    """
    assert chuan_hoa("991234566") == "991234566"
    assert kiem_ma_so_thue("991234566").hop_le is None


def test_so_nguyen_du_10_chu_so_thi_giu_nguyen():
    assert chuan_hoa(9902000029) == "9902000029"
    assert kiem_ma_so_thue(9902000029).hop_le is True
