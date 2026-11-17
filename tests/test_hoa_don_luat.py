"""
tests/test_hoa_don_luat.py — phần thuần của hoá đơn hư cấu kiểu Việt Nam (`offline_training/hoa_don_luat.py`).

Phần dễ sai nhất và khó thấy bằng mắt là số tiền bằng chữ: "một triệu không trăm linh năm nghìn" khác "một triệu
năm trăm nghìn" chỉ ở một chữ. Nên ngoài các ví dụ chốt tay, test này đọc NGƯỢC chữ ra số bằng một bộ phân tích
riêng và đòi đi vòng khớp trên hàng nghìn số ngẫu nhiên. Bộ phân tích kiểm tính nhất quán của phần đọc, không
kiểm quy ước (quy ước kiểm bằng các ví dụ chốt tay).
"""

from __future__ import annotations

import random

import pytest

from offline_training import hoa_don_luat as h
from offline_training import vlm_hoadon as v
from src.core.tax_id import kiem_ma_so_thue

# ---------------------------------------------------------------------------
# Số tiền bằng chữ
# ---------------------------------------------------------------------------

VI_DU = {
    0: "Không đồng chẵn",
    1: "Một đồng chẵn",
    5: "Năm đồng chẵn",
    10: "Mười đồng chẵn",
    11: "Mười một đồng chẵn",
    14: "Mười bốn đồng chẵn",
    15: "Mười lăm đồng chẵn",
    20: "Hai mươi đồng chẵn",
    21: "Hai mươi mốt đồng chẵn",
    24: "Hai mươi tư đồng chẵn",
    25: "Hai mươi lăm đồng chẵn",
    100: "Một trăm đồng chẵn",
    101: "Một trăm linh một đồng chẵn",
    105: "Một trăm linh năm đồng chẵn",
    110: "Một trăm mười đồng chẵn",
    115: "Một trăm mười lăm đồng chẵn",
    1_000: "Một nghìn đồng chẵn",
    15_000: "Mười lăm nghìn đồng chẵn",
    1_480_000: "Một triệu bốn trăm tám mươi nghìn đồng chẵn",
    1_500_000: "Một triệu năm trăm nghìn đồng chẵn",
    1_005_000: "Một triệu không trăm linh năm nghìn đồng chẵn",
    1_020_000: "Một triệu không trăm hai mươi nghìn đồng chẵn",
    1_000_001: "Một triệu không trăm linh một đồng chẵn",
    2_345_678: "Hai triệu ba trăm bốn mươi lăm nghìn sáu trăm bảy mươi tám đồng chẵn",
    12_345_000: "Mười hai triệu ba trăm bốn mươi lăm nghìn đồng chẵn",
    1_000_000_000: "Một tỷ đồng chẵn",
    1_000_000_000_000: "Một nghìn tỷ đồng chẵn",
}


@pytest.mark.parametrize("so,chu", sorted(VI_DU.items()))
def test_vi_du_chot_tay(so, chu):
    assert h.bang_chu_tien(so) == chu


_GIA_TRI = {"không": 0, "một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8,
            "chín": 9, "mốt": 1, "tư": 4, "lăm": 5}
_BAC = {"nghìn": 1_000, "triệu": 1_000_000}


def _doc_nguoc(chu: str) -> int:
    """Bộ phân tích RIÊNG (không dùng lại bảng của h): chữ -> số, cho các số có tới bậc tỷ và nghìn tỷ."""
    s = chu.lower().removesuffix(" đồng chẵn")
    tong = nhom = cuoi = 0
    for t in s.split():
        if t in _GIA_TRI:
            cuoi = _GIA_TRI[t]
            nhom += cuoi
        elif t == "trăm":
            nhom += cuoi * 99
        elif t == "mươi":
            nhom += cuoi * 9
            cuoi = 0
        elif t == "mười":
            nhom += 10
            cuoi = 0
        elif t == "linh":
            pass
        elif t in _BAC:
            tong += nhom * _BAC[t]
            nhom = cuoi = 0
        elif t == "tỷ":
            if nhom == 0 and tong > 0:          # "nghìn tỷ": đã nhân nghìn, giờ nhân tỷ
                tong *= 1_000_000_000
            else:
                tong += nhom * 1_000_000_000
            nhom = cuoi = 0
        else:
            raise AssertionError(f"từ lạ {t!r} trong {chu!r}")
    return tong + nhom


def test_doc_di_roi_doc_nguoc_khop_tren_so_ngau_nhien():
    rng = random.Random(20261117)
    mau = [rng.randint(0, 10 ** 12 - 1) for _ in range(3000)]
    mau += [rng.randint(0, 999) for _ in range(500)]           # nhiều số nhỏ: chỗ "linh", "mốt", "lăm" dày nhất
    mau += [rng.randint(0, 999) * 1000 for _ in range(500)]    # tròn nghìn: nhóm giữa bằng không
    for n in mau:
        chu = h.bang_chu_tien(n)
        assert _doc_nguoc(chu) == n, (n, chu)


def test_so_cua_bo_sinh_cu_deu_doc_duoc():
    """Mọi tổng tiền mà bộ sinh hoá đơn hiện có tạo ra đều đọc thành chữ được và khớp ngược."""
    for ca in v.sinh_ca(60, seed=3):
        gt = ca["gt"]
        n = int(gt["total"])
        assert _doc_nguoc(h.bang_chu_tien(n)) == n


def test_dinh_dang_cau_chu():
    chu = h.bang_chu_tien(1_500_000)
    assert chu[0].isupper() and chu.endswith(" đồng chẵn") and "  " not in chu


def test_so_thuc_nguyen_nhan_nhung_so_le_la_loi():
    assert h.bang_chu_tien(1_500_000.0) == "Một triệu năm trăm nghìn đồng chẵn"
    with pytest.raises(ValueError, match="phần lẻ"):
        h.bang_chu_tien(1500.5)


def test_so_am_va_qua_lon_va_kieu_sai_bi_tu_choi():
    with pytest.raises(ValueError):
        h.bang_chu_tien(-1)
    with pytest.raises(ValueError):
        h.doc_so(10 ** 15)
    with pytest.raises(TypeError):
        h.doc_so("1000")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        h.doc_so(True)


# ---------------------------------------------------------------------------
# Ký hiệu, số, ngày
# ---------------------------------------------------------------------------

def test_ky_hieu_sau_ky_tu_dung_dang():
    rng = random.Random(1)
    for nam in (2025, 2026, 2027):
        for loai in h.LOAI_HOA_DON:
            for co_ma in (True, False):
                k = h.ky_hieu_hoa_don(rng, nam, co_ma_cqt=co_ma, loai=loai)
                assert len(k) == 6 and h.ky_hieu_hop_le(k), k
                assert k[0] == ("C" if co_ma else "K") and k[1:3] == f"{nam % 100:02d}" and k[3] == loai


def test_ky_hieu_day_du_la_mau_so_cong_ky_hieu():
    assert h.ky_hieu_day_du(1, "C26TAA") == "1C26TAA"
    assert h.ky_hieu_day_du(2, "K26MXY") == "2K26MXY"


@pytest.mark.parametrize("xau", ["", "C26TA", "C26TAAA", "X26TAA", "C26XAA", "c26taa", "1C26TAA", "C2TAA"])
def test_ky_hieu_sai_dang_bi_tu_choi(xau):
    assert not h.ky_hieu_hop_le(xau)


def test_ky_hieu_dau_vao_sai_la_loi():
    rng = random.Random(1)
    with pytest.raises(ValueError):
        h.ky_hieu_hoa_don(rng, 2026, loai="F")            # chữ cái mới từ 01/07/2026: ngoài tập con dùng được
    with pytest.raises(ValueError):
        h.ky_hieu_hoa_don(rng, 1999)
    with pytest.raises(ValueError):
        h.ky_hieu_day_du(0, "C26TAA")
    with pytest.raises(ValueError):
        h.ky_hieu_day_du(10, "C26TAA")
    with pytest.raises(ValueError):
        h.ky_hieu_day_du(1, "C26TA")


def test_so_hoa_don_toi_da_tam_chu_so_dem_so_khong():
    rng = random.Random(2)
    for _ in range(300):
        s = h.so_hoa_don(rng)
        assert len(s) == 8 and s.isdigit() and int(s) >= 1
    with pytest.raises(ValueError):
        h.so_hoa_don(rng, toi_da=10 ** 8)


def test_ngay_viet():
    assert h.ngay_viet("2026-11-05") == "Ngày 05 tháng 11 năm 2026"
    with pytest.raises(ValueError):
        h.ngay_viet("05/11/2026")


# ---------------------------------------------------------------------------
# Người bán, người mua, gói hoàn chỉnh
# ---------------------------------------------------------------------------

def test_mst_bia_dung_so_kiem_tra_cua_runtime():
    rng = random.Random(7)
    for _ in range(1000):
        m = h.mst_gia(rng)
        assert m.startswith("99") and len(m) == 10 and kiem_ma_so_thue(m).hop_le, m


def test_mot_dinh_nghia_mst_giua_hai_module():
    """R4: bộ sinh cũ dùng CHÍNH hàm này, không giữ bản sao."""
    assert v._mst_gia is h.mst_gia


def test_phan_chu_hoa_don_dat_quy_uoc_hu_cau_tren_nhieu_seed():
    for seed in range(1, 400):
        rng = random.Random(seed)
        tong = rng.randint(1, 5_000_000_000)
        p = h.phan_chu_hoa_don(rng, tong=tong, iso_ngay="2026-11-05",
                               ban_cho_nguoi_tieu_dung=(seed % 3 == 0), loai=rng.choice(h.LOAI_HOA_DON))
        assert h.kiem_gia_lap(p) == [], (seed, h.kiem_gia_lap(p))
        assert _doc_nguoc(p["bang_chu"]) == tong
        assert p["ngay"] == "Ngày 05 tháng 11 năm 2026"


def test_ban_cho_nguoi_tieu_dung_khong_co_mst_nguoi_mua():
    p = h.phan_chu_hoa_don(random.Random(1), tong=1_000_000, iso_ngay="2026-11-05", ban_cho_nguoi_tieu_dung=True)
    assert p["nguoi_mua"] == {"ten": "Bán cho người tiêu dùng", "mst": "", "dia_chi": ""}


def test_cung_seed_cung_goi_chu():
    a = h.phan_chu_hoa_don(random.Random(5), tong=2_000_000, iso_ngay="2026-03-01")
    b = h.phan_chu_hoa_don(random.Random(5), tong=2_000_000, iso_ngay="2026-03-01")
    assert a == b


def test_dau_do_kiem_gia_lap_bat_duoc_chu_trong_nhu_that():
    """Chứng minh phép kiểm không câm: đưa vào những thứ trông như doanh nghiệp thật thì phải báo."""
    p = h.phan_chu_hoa_don(random.Random(1), tong=1_000_000, iso_ngay="2026-11-05")
    assert h.kiem_gia_lap(p) == []

    def sua(khoa_ngoai, khoa_trong, gia_tri):
        q = {k: (dict(val) if isinstance(val, dict) else val) for k, val in p.items()}
        q[khoa_ngoai][khoa_trong] = gia_tri
        return h.kiem_gia_lap(q)

    assert sua("nguoi_ban", "ten", "Công ty TNHH Dầu Khí Việt")
    assert sua("nguoi_ban", "mst", "0100109106")
    assert sua("nguoi_ban", "dien_thoai", "024 3825 1234")
    assert sua("nguoi_ban", "tai_khoan", "1903 1234 5678")
    assert sua("nguoi_mua", "mst", "0301234567")
    q = dict(p)
    q["ky_hieu"] = "C26TA"
    assert h.kiem_gia_lap(q)
    q = dict(p)
    q["so"] = "123456789"
    assert h.kiem_gia_lap(q)
