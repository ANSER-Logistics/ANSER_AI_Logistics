"""
tests/test_vat_thue_suat_so_luong.py — `vat`: thuế suất không do model đoán, số lượng không do model bịa (BR-30).

VÌ SAO CÓ FILE NÀY
------------------
Khi gọi `vat`, model tự điền `is_reduced_vat` (8% hay 10%) và `qty`. Câu người dùng thường không
nói cả hai. `vat` tính ĐÚNG trên đầu vào sai, và kết quả trông có nguồn: loại sai không ai thấy.

Thuế suất: mặt hàng bảng tra kết luận KHÔNG được giảm thì mã ép 10%; câu không nói thuế suất thì
gỡ giá trị model điền (tool dùng 10%); câu có nói thì giữ. Mã KHÔNG tự đặt 8% theo bảng tra: đó
là đổi mặc định, việc của chủ dự án (xem khối chú thích ở `doc_dau_vao.ap_thue_suat_tu_bang_tra`).
Số lượng: `qty` khác 1 mà không có trong câu thì hỏi lại.
"""

from __future__ import annotations

import pytest

from src.core.doc_dau_vao import (
    ap_thue_suat_tu_bang_tra,
    chot_dau_vao,
    so_luong_khong_co_trong_cau,
)


def _vat(items, cau, **kw):
    return chot_dau_vao("vat", {"items": items, **kw}, cau)


# ---------------------------------------------------------------------------
# Thuế suất
# ---------------------------------------------------------------------------

def test_cau_khong_noi_thue_suat_thi_go_gia_tri_model_dien():
    args, hoi, ly_do = _vat(
        [{"name": "Dầu nhớt Caltex", "price": 500_000, "qty": 1, "is_reduced_vat": True}],
        "Dầu nhớt Caltex 500.000, giá chưa gồm VAT, tính thuế giúp tôi",
    )
    assert ly_do == "ok" and hoi is None
    assert "is_reduced_vat" not in args["items"][0], "model tự chọn 8% mà câu không nói"


def test_default_is_reduced_do_model_dien_cung_bi_go_khi_cau_khong_noi():
    args, _, _ = _vat(
        [{"name": "Dầu nhớt", "price": 500_000, "qty": 1}],
        "Dầu nhớt 500.000, chưa gồm VAT, tính thuế",
        default_is_reduced=True,
    )
    assert "default_is_reduced" not in args


def test_cau_co_noi_thue_suat_thi_giu_gia_tri_model():
    args, _, _ = _vat(
        [{"name": "Dầu nhớt", "price": 500_000, "qty": 1, "is_reduced_vat": True}],
        "Dầu nhớt 500.000, chưa gồm VAT, áp giảm thuế 8% giúp tôi",
    )
    assert args["items"][0]["is_reduced_vat"] is True


@pytest.mark.parametrize("ten", ["Thép cuộn cán nóng", "Bia lon 330ml", "Cước internet cáp quang"])
@pytest.mark.parametrize("cau_them", ["", ", áp giảm thuế 8%"])
def test_hang_bang_tra_loai_tru_thi_ma_ep_10_phan_tram_ke_ca_khi_cau_noi_8(ten, cau_them):
    """Hàng loại trừ không được giảm. Câu hay model nói 8% cũng không đè được."""
    args, _, _ = _vat(
        [{"name": ten, "price": 1_000_000, "qty": 1, "is_reduced_vat": True}],
        f"{ten} 1.000.000, chưa gồm VAT{cau_them}",
    )
    assert args["items"][0]["is_reduced_vat"] is False


def test_hang_duoc_giam_theo_bang_tra_van_la_10_phan_tram_khi_cau_khong_noi():
    """CỐ Ý: mã không tự đặt 8% chỉ vì bảng tra nói "được giảm". Đó là đổi mặc định (chủ dự án quyết)."""
    args, _, _ = _vat(
        [{"name": "Cước vận chuyển HN-HP", "price": 5_000_000, "qty": 1}],
        "Cước vận chuyển HN-HP 5.000.000, chưa gồm VAT",
    )
    assert "is_reduced_vat" not in args["items"][0]   # tool dùng 10%


def test_chi_dong_loai_tru_bi_ep_dong_khac_giu_nguyen():
    args, _ = ap_thue_suat_tu_bang_tra(
        "Thép và dầu nhớt, áp giảm thuế 8%",
        {"items": [
            {"name": "Thép tấm", "price": 1, "qty": 1, "is_reduced_vat": True},
            {"name": "Dầu nhớt", "price": 1, "qty": 1, "is_reduced_vat": True},
        ]},
    )
    assert args["items"][0]["is_reduced_vat"] is False
    assert args["items"][1]["is_reduced_vat"] is True


def test_khong_co_items_thi_khong_no():
    assert ap_thue_suat_tu_bang_tra("x", {}) == ({}, [])


# ---------------------------------------------------------------------------
# Số lượng
# ---------------------------------------------------------------------------

def test_so_luong_model_bia_thi_hoi_lai_khong_chay():
    args, hoi, ly_do = _vat(
        [{"name": "Dầu nhớt", "price": 500_000, "qty": 10}],
        "Dầu nhớt 500.000, chưa gồm VAT, tính thuế giúp tôi",
    )
    assert ly_do == "so_luong"
    assert hoi and "10" in hoi and "không tự thêm số" in hoi


@pytest.mark.parametrize("cau, qty", [
    ("Mua 10 thùng dầu nhớt giá 500.000, chưa gồm VAT", 10),
    ("Mua hai thùng dầu nhớt giá 500.000, chưa gồm VAT", 2),
    ("Mua 2,5 lít dầu nhớt giá 500.000, chưa gồm VAT", 2.5),
    ("Dầu nhớt 500.000, chưa gồm VAT", 1),          # 1 = "không ghi số lượng", luôn hợp lệ
])
def test_so_luong_co_trong_cau_thi_cho_qua(cau, qty):
    args, hoi, ly_do = _vat([{"name": "Dầu nhớt", "price": 500_000, "qty": qty}], cau)
    assert ly_do == "ok" and hoi is None
    assert args["items"][0]["qty"] == qty


def test_dong_do_ma_boc_tu_hoa_don_khong_bi_hoi_lai_so_luong():
    """Mã bóc dòng hàng và tự đặt qty = 1: số model điền không còn dùng."""
    cau = 'Kiểm tra hoá đơn: {"Cước vận chuyển": 5000000, "Phụ phí xăng dầu": 500000}, chưa gồm VAT'
    args, hoi, ly_do = chot_dau_vao("vat", {"items": [{"name": "x", "price": 5_500_000, "qty": 7}]}, cau)
    assert ly_do == "ok" and hoi is None
    assert [i["qty"] for i in args["items"]] == [1, 1]


def test_so_luong_bool_va_khong_phai_so_bi_bo_qua():
    assert so_luong_khong_co_trong_cau("x", {"items": [{"qty": True}, {"qty": None}, {"qty": "ba"}]}) == []


def test_cac_tool_khac_khong_bi_dong_vao():
    args, hoi, ly_do = chot_dau_vao("quote", {"items": [{"qty": 99, "is_reduced_vat": True}]}, "báo giá")
    assert args["items"][0] == {"qty": 99, "is_reduced_vat": True} and ly_do != "so_luong"
