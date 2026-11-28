"""
tests/contracts/test_sample_data.py — bảng tồn kho mẫu phải là ĐỀ BÀI CÓ ĐÁP ÁN.

Dữ liệu giả dựng đại thì bộ soi không tìm ra gì, và ta kết luận nhầm rằng nó
"chạy tốt". Nên bảng mẫu gieo lỗi có chủ đích, và test này đối chiếu hai chiều:

  - thiếu một lỗi gieo  -> bộ soi HỎNG
  - thừa một phát hiện  -> bộ soi BÁO OAN

Chiều thứ hai quan trọng ngang chiều thứ nhất. Một bộ soi gắn cờ 18/18 mã đã
từng xảy ra ở đây (30/07/2026, luật `cost_drift` cũ), và bộ soi kêu ca liên tục
thì người dùng tắt nó đi — tệ hơn là không có.

Test đi qua ĐÚNG đường thật: ghi .xlsx, đọc lại bằng bộ nạp, rồi soi.
"""

from __future__ import annotations

from io import BytesIO

import pytest

from sample_data.make_sample_data import (
    DOI_TAC,
    DONG,
    DONG_BAN_SAU,
    KY_DEN_SAU,
    LOI_DOI_TAC,
    LOI_GIEO,
    LOI_HOI_TO,
    bang,
    ghi_doi_tac,
    ghi_xlsx,
)
from src.core.inventory import audit_inventory
from src.core.inventory_import import parse_inventory_table
from src.core.period_diff import doi_chieu_hai_lan_xuat

pytest.importorskip("openpyxl")


@pytest.fixture(scope="module")
def ket_qua():
    """Đọc bảng mẫu qua đúng bộ nạp mà Body dùng."""
    return parse_inventory_table(bang())


@pytest.fixture(scope="module")
def phat_hien(ket_qua):
    kq = audit_inventory(
        ket_qua.lines, warehouse="Kho Hà Nội",
        period_start="2026-01-01", period_end="2026-06-30",
    )
    theo_ma: dict[str, set[str]] = {}
    for f in kq["findings"]:
        theo_ma.setdefault(f.get("code") or "?", set()).add(f["kind"])
    return theo_ma


# ---------------------------------------------------------------------------
# Bộ nạp
# ---------------------------------------------------------------------------

def test_doc_duoc_moi_dong(ket_qua):
    assert ket_qua.ok, ket_qua.checks
    assert len(ket_qua.lines) == len(DONG)


def test_doc_duoc_so_dinh_dang_viet_nam(ket_qua):
    """
    "24.000.000" phải ra 24 triệu, không phải 24. Bản xuất thật đôi khi ra chuỗi
    thay vì số, và nhầm chỗ này thì mọi con số tiền nhỏ đi một triệu lần.
    """
    dong = next(d for d in ket_qua.lines if d.code == "DN-TL-46")
    assert dong.opening_value == pytest.approx(24_000_000)
    assert dong.opening_qty == pytest.approx(80)


def test_doc_dung_ten_kho_va_don_vi(ket_qua):
    dong = next(d for d in ket_qua.lines if d.code == "MO-EP2-15")
    assert dong.unit == "xô"
    assert "Mỡ bò" in dong.name


# ---------------------------------------------------------------------------
# Bộ soi — chiều thứ nhất: có tìm ra lỗi đã gieo không
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("code,loi", sorted(LOI_GIEO.items()))
def test_tim_ra_loi_da_gieo(phat_hien, code, loi):
    thay = phat_hien.get(code, set())
    thieu = set(loi) - thay
    assert not thieu, f"{code}: không tìm ra {thieu} (chỉ thấy {thay or 'không gì'})"


# ---------------------------------------------------------------------------
# Bộ soi — chiều thứ hai: có báo oan không
# ---------------------------------------------------------------------------

def test_khong_bao_oan_dong_sach(phat_hien):
    """
    Dòng sạch là dòng bình thường của một nhà phân phối: nhập đều, bán đều, giá
    nhích nhẹ. Gắn cờ chúng là dạy người dùng bỏ qua cảnh báo.
    """
    sach = [d.code for d in DONG if not d.loi_gieo]
    oan = {code: phat_hien[code] for code in sach if phat_hien.get(code)}
    assert not oan, f"báo oan trên dòng sạch: {oan}"


def test_khong_gan_them_co_ngoai_du_kien(phat_hien):
    """Dòng gieo lỗi cũng không được nhận thêm cờ nào ngoài lỗi đã gieo."""
    thua = {}
    for code, loi in LOI_GIEO.items():
        du = phat_hien.get(code, set()) - set(loi)
        if du:
            thua[code] = du
    assert not thua, f"phát hiện ngoài dự kiến: {thua}"


# ---------------------------------------------------------------------------
# Ghi file thật
# ---------------------------------------------------------------------------

def test_ghi_va_doc_lai_duoc_xlsx(tmp_path):
    """File .xlsx thật phải đọc lại được y như ma trận ô — đó là thứ sẽ tải lên."""
    from src.core.inventory_import import load_xlsx_bytes

    path = ghi_xlsx(tmp_path / "ton_kho_mau.xlsx")
    kq = load_xlsx_bytes(BytesIO(path.read_bytes()).getvalue())
    assert kq.ok, kq.checks
    assert {d.code for d in kq.lines} == {d.code for d in DONG}


# ---------------------------------------------------------------------------
# Kho cho phép giá trị 0 — chống báo oan
# ---------------------------------------------------------------------------

def test_kho_cho_phep_gia_tri_0_thi_thoi_bao_oan(ket_qua):
    """
    Chạy trên bản xuất MISA THẬT: kho KHUYẾN MẠI có 29/38 dòng bị gắn cờ "có số
    lượng nhưng không ghi nhận giá trị". Với kho mà giá trị 0 là trạng thái BÌNH
    THƯỜNG (hàng nhà cung cấp tặng kèm), đó là tiếng ồn, không phải phát hiện.

    Bộ soi kêu ca gần như mọi dòng thì người dùng tắt nó đi — và mất luôn những
    lỗi thật nằm cùng bảng.
    """
    thuong = audit_inventory(ket_qua.lines, period_start="2026-01-01",
                             period_end="2026-06-30")
    kho_km = audit_inventory(ket_qua.lines, period_start="2026-01-01",
                             period_end="2026-06-30", allow_zero_value=True)

    def loai(kq):
        return {f["kind"] for f in kq["findings"]}

    assert "zero_valued_stock" in loai(thuong)
    assert "zero_valued_stock" not in loai(kho_km)


def test_tat_gia_tri_0_KHONG_lam_mat_cac_phep_kiem_khac(ket_qua):
    """
    Kho khuyến mại được phép không có giá vốn, KHÔNG được phép sai số học.
    Chính kho đó trong dữ liệu thật có một ca tồn âm −115,2 lít.
    """
    thuong = audit_inventory(ket_qua.lines, period_start="2026-01-01",
                             period_end="2026-06-30")
    kho_km = audit_inventory(ket_qua.lines, period_start="2026-01-01",
                             period_end="2026-06-30", allow_zero_value=True)

    con_lai = {f["kind"] for f in thuong["findings"]} - {"zero_valued_stock"}
    assert con_lai <= {f["kind"] for f in kho_km["findings"]}, (
        "tắt phép kiểm giá-trị-0 đã nuốt mất phép kiểm khác"
    )
    # Cụ thể: tồn âm và lệch cân đối vẫn phải còn.
    assert {"negative_stock", "balance_mismatch"} <= {f["kind"] for f in kho_km["findings"]}


def test_phuong_phap_tinh_gia_von_van_duoc_thu_thap(ket_qua):
    """
    Regression: bản đầu dùng `continue` để bỏ phép kiểm giá-trị-0, và bỏ luôn
    phần thu thập phương pháp tính giá vốn ngay dưới — `_check_method_consistency`
    mất dữ liệu mà không báo gì.
    """
    from src.core.inventory import _costing_method

    co_phuong_phap = any(_costing_method(d) for d in ket_qua.lines)
    if not co_phuong_phap:
        pytest.skip("bảng mẫu không có dòng nào suy ra được phương pháp tính giá vốn")

    kq = audit_inventory(ket_qua.lines, period_start="2026-01-01",
                         period_end="2026-06-30", allow_zero_value=True)
    assert kq["explain"]["costing_methods_detected"], (
        "mất dữ liệu phương pháp tính giá vốn khi tắt phép kiểm giá-trị-0"
    )


# ---------------------------------------------------------------------------
# Hai bản xuất CÙNG một kỳ — đề bài cho phép so (`core/period_diff.py`)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def so_hai_ban():
    truoc = parse_inventory_table(bang())
    sau = parse_inventory_table(bang(KY_DEN_SAU, DONG_BAN_SAU))
    return doi_chieu_hai_lan_xuat(truoc, sau)


def test_hai_ban_chi_bao_dung_ba_cho_sua_hoi_to(so_hai_ban):
    """Đáp án `LOI_HOI_TO`: thiếu một chỗ là phép so hỏng, thừa một chỗ là báo oan."""
    thuc_te = {f["code"]: f["kind"] for f in so_hai_ban["findings"]}
    assert thuc_te == LOI_HOI_TO
    assert so_hai_ban["summary"]["có_sửa_hồi_tố"] is True


def test_phieu_bi_doi_ma_duoc_nhan_ra_ma_nhan(so_hai_ban):
    """DN-SG-18 mất 40 can xuất; DN-TL-46 tăng đúng 40: bản so phải nêu mã nhận, vì đó là chỗ lỗi âm kho mọc lại."""
    f = next(x for x in so_hai_ban["findings"] if x["code"] == "DN-SG-18")
    assert f["evidence"]["mã_tăng_đúng_bằng_lượng_này"] == ["DN-TL-46"]


def test_phat_sinh_moi_hop_le_khong_bi_bao_oan(so_hai_ban):
    """Hai mã bán thêm trong 15 ngày mới (số luỹ kế chỉ tăng) là đối chứng: không được có phát hiện nào."""
    ma = {f["code"] for f in so_hai_ban["findings"]}
    assert not ma & {"LC-COOL-200", "KM-4T-08"}
    assert "DN-TL-46" not in ma, "mã nhận tăng hợp lệ, không bị gắn cờ riêng"


def test_so_nguoc_thu_tu_bi_tu_choi_khong_im_lang():
    """Đưa bản MUỘN làm bản trước: Brain nói rõ là nhầm thứ tự, không cho ra kết quả vô nghĩa."""
    truoc = parse_inventory_table(bang())
    sau = parse_inventory_table(bang(KY_DEN_SAU, DONG_BAN_SAU))
    kq = doi_chieu_hai_lan_xuat(sau, truoc)
    assert kq["summary"]["so_sánh_được"] is False and kq["findings"] == [] and kq["warnings"]


def test_ghi_va_doc_lai_duoc_xlsx_ban_sau(tmp_path):
    """Tệp .xlsx thật của bản sau, qua cùng bộ nạp, cho đúng kết quả như so trên ma trận ô."""
    from src.core.inventory_import import load_xlsx_bytes

    truoc = load_xlsx_bytes(ghi_xlsx(tmp_path / "truoc.xlsx").read_bytes())
    sau = load_xlsx_bytes(ghi_xlsx(tmp_path / "sau.xlsx", KY_DEN_SAU, DONG_BAN_SAU).read_bytes())
    assert truoc.ok and sau.ok
    kq = doi_chieu_hai_lan_xuat(truoc, sau)
    assert {f["code"]: f["kind"] for f in kq["findings"]} == LOI_HOI_TO


# ---------------------------------------------------------------------------
# Danh sách đối tác — đề bài cho soi công nợ (`core/receivables.py`)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("vai_tro", ["khách hàng", "nhà cung cấp"])
def test_soi_tung_file_doi_tac_ra_dung_dap_an_khong_hon_khong_kem(tmp_path, vai_tro):
    """Soi MỘT file, đúng cách màn "Dòng tiền" của Body gọi: đúng bộ (loại, mã) đã gieo, đối chứng sạch không bị gắn cờ."""
    from src.core.partner_import import NHA_CUNG_CAP, load_partners_xlsx_bytes
    from src.core.receivables import audit_partners

    doc = load_partners_xlsx_bytes(ghi_doi_tac(tmp_path / "dt.xlsx", vai_tro).read_bytes())
    assert doc.ok, doc.checks
    assert doc.role == vai_tro and len(doc.partners) == len(DOI_TAC[vai_tro])
    la_ncc = vai_tro == NHA_CUNG_CAP
    kq = audit_partners([] if la_ncc else doc.partners, doc.partners if la_ncc else [])
    thuc_te = sorted((f["kind"], f.get("code") or "") for f in kq["findings"])
    assert thuc_te == sorted(LOI_DOI_TAC[vai_tro])


def test_tong_phai_thu_va_phai_tra_cua_file_mau_khop_tinh_tay(tmp_path):
    from src.core.partner_import import load_partners_xlsx_bytes
    from src.core.receivables import audit_partners

    khach = load_partners_xlsx_bytes(ghi_doi_tac(tmp_path / "k.xlsx", "khách hàng").read_bytes()).partners
    ncc = load_partners_xlsx_bytes(ghi_doi_tac(tmp_path / "n.xlsx", "nhà cung cấp").read_bytes()).partners
    assert audit_partners(khach)["summary"]["tổng_phải_thu"] == 520_000_000
    assert audit_partners([], ncc)["summary"]["tổng_phải_trả"] == 150_000_000
