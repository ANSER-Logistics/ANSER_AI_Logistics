"""
tests/test_vat_thue_suat_so_luong.py — `vat`: thuế suất do NGƯỜI DÙNG chọn, số lượng không do model bịa (BR-30).

VÌ SAO CÓ FILE NÀY
------------------
Khi gọi `vat`, model tự điền `is_reduced_vat` (8% hay 10%) và `qty`. Câu người dùng thường không nói cả
hai. `vat` tính ĐÚNG trên đầu vào sai, và kết quả trông có nguồn: loại sai không ai thấy.

Thuế suất (chủ dự án chỉ đạo 15/11/2026: để người dùng chọn). Bảng tra `vat_catalog` do team viết, chưa có
kế toán soát, nên mã không tự đặt 8% và model cũng không được chọn:
  1. hàng bảng tra kết luận KHÔNG được giảm -> mã ép 10%;
  2. người dùng NÓI thuế suất -> MÃ đặt cờ theo lời đó, không để model đọc;
  3. người dùng không nói mà bảng tra nói "được giảm" -> HỎI LẠI "8% hay 10%?";
  4. còn lại -> gỡ lời model, tool dùng 10%.
Số lượng: `qty` khác 1 mà không có trong câu thì hỏi lại.
"""

from __future__ import annotations

import pytest

from src.core.doc_dau_vao import (
    MOC_HOI_THUE_SUAT,
    ap_thue_suat_tu_bang_tra,
    cau_hoi_thue_suat,
    chot_dau_vao,
    hang_duoc_giam,
    noi_thue_suat,
    noi_tra_loi_hoi_thue,
    so_luong_khong_co_trong_cau,
    thue_suat_nguoi_dung_da_noi,
)

HANG_MAU = "Hàng mẫu"          # bảng tra: chưa xác định
HANG_DUOC_GIAM = "Dầu nhớt Caltex"   # bảng tra: được giảm 8%


def _vat(items, cau, history=None, **kw):
    return chot_dau_vao("vat", {"items": items, **kw}, cau, history=history)


# ---------------------------------------------------------------------------
# Nhận ra thuế suất người dùng nói
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cau, muc", [
    ("áp giảm thuế 8% giúp tôi", "8"),
    ("giảm thuế GTGT", "8"),
    ("VAT 8%", "8"),
    ("thuế suất 10%", "10"),
    ("8%", "8"),
    ("giảm 8%", "8"),
    ("tính 10%", "10"),
    ("thuế suất 8", "8"),
    ("Dầu 500.000\nchưa gồm VAT\n8%", "8"),                 # trả lời ngắn nằm trên một dòng riêng
    ("chiết khấu 10% cho khách, chưa gồm VAT", None),      # 10% này không phải thuế suất
    ("thuế 8% hay 10% đây", None),                         # nói cả hai: mâu thuẫn
    ("không nói gì về thuế suất", None),
    ("", None),
])
def test_nhan_ra_thue_suat_nguoi_dung_noi(cau, muc):
    assert noi_thue_suat(cau) == muc


# ---------------------------------------------------------------------------
# Luật 4: không nói, bảng tra không biết -> 10%
# ---------------------------------------------------------------------------

def test_cau_khong_noi_thue_suat_va_bang_tra_khong_biet_thi_go_gia_tri_model():
    args, hoi, ly_do = _vat(
        [{"name": HANG_MAU, "price": 500_000, "qty": 1, "is_reduced_vat": True}],
        "Hàng mẫu 500.000, giá chưa gồm VAT, tính thuế giúp tôi",
    )
    assert ly_do == "ok" and hoi is None
    assert "is_reduced_vat" not in args["items"][0], "model tự chọn 8% mà câu không nói"


def test_default_is_reduced_do_model_dien_cung_bi_go():
    args, _, _ = _vat(
        [{"name": HANG_MAU, "price": 500_000, "qty": 1}], "Hàng mẫu 500.000, chưa gồm VAT",
        default_is_reduced=True,
    )
    assert "default_is_reduced" not in args


# ---------------------------------------------------------------------------
# Luật 2: người dùng nói -> MÃ đặt cờ
# ---------------------------------------------------------------------------

def test_nguoi_dung_noi_8_thi_ma_dat_co_ke_ca_khi_model_khong_dat():
    args, hoi, ly_do = _vat(
        [{"name": HANG_DUOC_GIAM, "price": 500_000, "qty": 1}],     # model KHÔNG điền cờ nào
        "Dầu nhớt Caltex 500.000, chưa gồm VAT, giảm thuế 8%",
    )
    assert ly_do == "ok" and hoi is None
    assert args["items"][0]["is_reduced_vat"] is True


def test_nguoi_dung_noi_10_thi_ma_dat_10_ke_ca_khi_model_chon_8():
    args, _, ly_do = _vat(
        [{"name": HANG_DUOC_GIAM, "price": 500_000, "qty": 1, "is_reduced_vat": True}],
        "Dầu nhớt Caltex 500.000, chưa gồm VAT, thuế suất 10%",
    )
    assert ly_do == "ok" and args["items"][0]["is_reduced_vat"] is False


# ---------------------------------------------------------------------------
# Luật 1: hàng loại trừ luôn 10%
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ten", ["Thép cuộn cán nóng", "Bia lon 330ml", "Cước internet cáp quang"])
@pytest.mark.parametrize("cau_them", ["", ", áp giảm thuế 8%"])
def test_hang_bang_tra_loai_tru_thi_ma_ep_10_phan_tram_ke_ca_khi_cau_noi_8(ten, cau_them):
    args, _, _ = _vat(
        [{"name": ten, "price": 1_000_000, "qty": 1, "is_reduced_vat": True}],
        f"{ten} 1.000.000, chưa gồm VAT{cau_them}",
    )
    assert args["items"][0]["is_reduced_vat"] is False


def test_chi_dong_loai_tru_bi_ep_dong_khac_theo_loi_nguoi_dung():
    args, _ = ap_thue_suat_tu_bang_tra(
        "Thép và dầu nhớt, áp giảm thuế 8%",
        {"items": [
            {"name": "Thép tấm", "price": 1, "qty": 1},
            {"name": "Dầu nhớt", "price": 1, "qty": 1},
        ]},
    )
    assert args["items"][0]["is_reduced_vat"] is False
    assert args["items"][1]["is_reduced_vat"] is True


def test_khong_co_items_thi_khong_no():
    assert ap_thue_suat_tu_bang_tra("x", {}) == ({}, [])


# ---------------------------------------------------------------------------
# Luật 3: bảng tra nói "được giảm", người dùng không nói -> HỎI LẠI
# ---------------------------------------------------------------------------

def test_hang_duoc_giam_ma_cau_khong_noi_thi_hoi_lai_8_hay_10():
    args, hoi, ly_do = _vat(
        [{"name": HANG_DUOC_GIAM, "price": 500_000, "qty": 1}],
        "Dầu nhớt Caltex 500.000, chưa gồm VAT, tính thuế giúp tôi",
    )
    assert ly_do == "thue_suat"
    assert hoi and "Dầu nhớt Caltex" in hoi and "8%" in hoi and "10%" in hoi
    assert "chưa có kế toán soát" in hoi, "câu hỏi phải nói rõ bảng tra chưa được soát"
    assert MOC_HOI_THUE_SUAT in hoi
    assert "is_reduced_vat" not in args["items"][0]


def test_hoi_gom_vat_truoc_roi_moi_hoi_thue_suat():
    from src.core.doc_dau_vao import CAU_HOI_THUE

    _, hoi, ly_do = _vat([{"name": HANG_DUOC_GIAM, "price": 500_000, "qty": 1}], "Dầu nhớt Caltex 500.000")
    assert ly_do == "thue" and hoi == CAU_HOI_THUE


def test_chi_hoi_khi_co_it_nhat_mot_dong_duoc_giam():
    _, hoi, ly_do = _vat(
        [{"name": HANG_MAU, "price": 500_000, "qty": 1}, {"name": "Thép tấm", "price": 1_000_000, "qty": 1}],
        "Hàng mẫu 500.000 và Thép tấm 1.000.000, chưa gồm VAT",
    )
    assert ly_do == "ok" and hoi is None


def test_cau_hoi_liet_ke_toi_da_ba_hang():
    ds = [(f"Dầu {i}", "căn cứ") for i in range(5)]
    h = cau_hoi_thue_suat(ds)
    assert h.count("\"Dầu ") == 3 and "…" in h


def test_hang_duoc_giam_doc_ten_va_can_cu():
    ds = hang_duoc_giam({"items": [{"name": "Dầu nhớt"}, {"name": HANG_MAU}, {"name": "Thép"}]})
    assert [t for t, _ in ds] == ["Dầu nhớt"] and ds[0][1]


# ---------------------------------------------------------------------------
# Đã chọn một lần thì giữ trong hội thoại
# ---------------------------------------------------------------------------

def test_da_chon_8_o_luot_truoc_thi_khong_hoi_lai_o_luot_sau():
    ls = [{"role": "user", "content": "hoá đơn trước"},
          {"role": "assistant", "content": cau_hoi_thue_suat([("x", "y")])},
          {"role": "user", "content": "8%"}]
    assert thue_suat_nguoi_dung_da_noi(ls) == "8"
    args, hoi, ly_do = _vat(
        [{"name": HANG_DUOC_GIAM, "price": 700_000, "qty": 1}],
        "Dầu nhớt Caltex 700.000, chưa gồm VAT", history=ls,
    )
    assert ly_do == "ok" and hoi is None and args["items"][0]["is_reduced_vat"] is True


def test_loi_o_luot_hien_tai_thang_lich_su():
    ls = [{"role": "user", "content": "giảm thuế 8%"}]
    args, _, _ = _vat([{"name": HANG_DUOC_GIAM, "price": 500_000, "qty": 1}],
                      "Dầu nhớt Caltex 500.000, chưa gồm VAT, thuế suất 10%", history=ls)
    assert args["items"][0]["is_reduced_vat"] is False


def test_chi_doc_tin_cua_nguoi_dung_khong_doc_cau_tro_ly():
    ls = [{"role": "assistant", "content": "Bạn muốn áp thuế GTGT 8% hay 10%? giảm thuế 8%"}]
    assert thue_suat_nguoi_dung_da_noi(ls) is None
    assert thue_suat_nguoi_dung_da_noi(None) is None


# ---------------------------------------------------------------------------
# Ghép câu trả lời với hoá đơn gốc
# ---------------------------------------------------------------------------

HOA_DON = "Dầu nhớt Caltex 500.000"


def test_tra_loi_thue_suat_o_luot_sau_duoc_ghep_voi_hoa_don():
    ls = [{"role": "user", "content": HOA_DON},
          {"role": "assistant", "content": cau_hoi_thue_suat([("Dầu nhớt Caltex", "căn cứ")])}]
    assert noi_tra_loi_hoi_thue("8%", ls) == f"{HOA_DON}\n8%"


def test_hai_cau_hoi_noi_nhau_van_ghep_ve_hoa_don_goc():
    from src.core.doc_dau_vao import CAU_HOI_THUE

    ls = [{"role": "user", "content": HOA_DON}, {"role": "assistant", "content": CAU_HOI_THUE},
          {"role": "user", "content": "chưa gồm VAT"},
          {"role": "assistant", "content": cau_hoi_thue_suat([("Dầu nhớt Caltex", "căn cứ")])}]
    assert noi_tra_loi_hoi_thue("giảm 8%", ls) == f"{HOA_DON}\nchưa gồm VAT\ngiảm 8%"


def test_tra_loi_sai_loai_cau_hoi_khong_duoc_ghep():
    from src.core.doc_dau_vao import CAU_HOI_THUE

    hoi_thue_suat = [{"role": "user", "content": HOA_DON},
                     {"role": "assistant", "content": cau_hoi_thue_suat([("x", "y")])}]
    assert noi_tra_loi_hoi_thue("chưa gồm VAT", hoi_thue_suat) is None       # trả lời "gồm VAT" cho câu hỏi thuế suất
    hoi_gom_vat = [{"role": "user", "content": HOA_DON}, {"role": "assistant", "content": CAU_HOI_THUE}]
    assert noi_tra_loi_hoi_thue("8%", hoi_gom_vat) is None                   # trả lời thuế suất cho câu hỏi "gồm VAT"
    assert noi_tra_loi_hoi_thue("xin chào", hoi_thue_suat) is None


def test_chuoi_ghep_chay_het_duong_ra_ket_qua_tinh_voi_8_phan_tram():
    ls = [{"role": "user", "content": HOA_DON}, {"role": "assistant", "content": "x " + MOC_HOI_THUE_SUAT}]
    gop = noi_tra_loi_hoi_thue("giảm 8%", ls)
    args, hoi, ly_do = chot_dau_vao(
        "vat", {"items": [{"name": HANG_DUOC_GIAM, "price": 500_000, "qty": 1}]},
        gop + ", chưa gồm VAT",
    )
    assert ly_do == "ok" and hoi is None and args["items"][0]["is_reduced_vat"] is True


# ---------------------------------------------------------------------------
# Số lượng
# ---------------------------------------------------------------------------

def test_so_luong_model_bia_thi_hoi_lai_khong_chay():
    args, hoi, ly_do = _vat(
        [{"name": HANG_MAU, "price": 500_000, "qty": 10}],
        "Hàng mẫu 500.000, chưa gồm VAT, tính thuế giúp tôi",
    )
    assert ly_do == "so_luong"
    assert hoi and "10" in hoi and "không tự thêm số" in hoi


@pytest.mark.parametrize("cau, qty", [
    ("Mua 10 thùng hàng mẫu giá 500.000, chưa gồm VAT", 10),
    ("Mua hai thùng hàng mẫu giá 500.000, chưa gồm VAT", 2),
    ("Mua 2,5 lít hàng mẫu giá 500.000, chưa gồm VAT", 2.5),
    ("Hàng mẫu 500.000, chưa gồm VAT", 1),          # 1 = "không ghi số lượng", luôn hợp lệ
])
def test_so_luong_co_trong_cau_thi_cho_qua(cau, qty):
    args, hoi, ly_do = _vat([{"name": HANG_MAU, "price": 500_000, "qty": qty}], cau)
    assert ly_do == "ok" and hoi is None
    assert args["items"][0]["qty"] == qty


def test_dong_do_ma_boc_tu_hoa_don_khong_bi_hoi_lai_so_luong():
    """Mã bóc dòng hàng và tự đặt qty = 1: số model điền không còn dùng."""
    cau = ('Kiểm tra hoá đơn: {"Cước vận chuyển": 5000000, "Phụ phí xăng dầu": 500000}, '
           "chưa gồm VAT, thuế suất 10%")
    args, hoi, ly_do = chot_dau_vao("vat", {"items": [{"name": "x", "price": 5_500_000, "qty": 7}]}, cau)
    assert ly_do == "ok" and hoi is None
    assert [i["qty"] for i in args["items"]] == [1, 1]


def test_so_luong_bool_va_khong_phai_so_bi_bo_qua():
    assert so_luong_khong_co_trong_cau("x", {"items": [{"qty": True}, {"qty": None}, {"qty": "ba"}]}) == []


def test_cac_tool_khac_khong_bi_dong_vao():
    args, hoi, ly_do = chot_dau_vao("quote", {"items": [{"qty": 99, "is_reduced_vat": True}]}, "báo giá")
    assert args["items"][0] == {"qty": 99, "is_reduced_vat": True} and ly_do != "so_luong"
