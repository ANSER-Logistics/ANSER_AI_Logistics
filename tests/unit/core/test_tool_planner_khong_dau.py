"""
tests/unit/core/test_tool_planner_khong_dau.py — bộ chọn công cụ hiểu câu KHÔNG DẤU và số tiền viết tắt (16/11/2026).

Bộ đo nghiệp vụ cho thấy mọi câu không dấu đều trượt, và "3tr5" không được nhận là số tiền. Test dùng câu VIẾT
MỚI, không chép câu của bộ đề, vì sửa theo câu của bộ đề là tự lừa.

Nửa còn lại của test canh CÁI GIÁ: bỏ dấu làm "thuê" trùng "thuế", "vật" trùng "vat", "rà" trùng "ra". Mỗi bẫy
đã gặp có một test, và câu CÓ dấu phải giữ nguyên hành vi.
"""

from __future__ import annotations

import pytest

from src.core.tool_planner import _SO_TIEN, plan_tools

CHAY = [
    ("bao cao loi nhuan quy nay", ["report"]),
    ("cac khach hang nao dang no minh", ["partner_audit"]),
    ("soat ton kho giup toi, co mat hang ton am khong", ["inventory_audit"]),
    ("nen nhap them hang gi, sap het hang roi", ["forecast_reorder"]),
    ("tinh vat 10% cho don 4tr2", ["vat"]),
    ("so sanh cac nha xe cho chuyen ngay mai", ["carrier_selection"]),
]


@pytest.mark.parametrize("cau, mong", CHAY)
def test_cau_khong_dau_duoc_hieu(cau, mong):
    assert plan_tools(cau) == mong


@pytest.mark.parametrize("cau", ["3tr5", "mua 2tr", "gia 9tr5 chua thue", "ship 150k", "500 nghin", "3 trieu"])
def test_so_tien_viet_tat_la_so_tien(cau):
    assert _SO_TIEN.search(cau)


@pytest.mark.parametrize("cau", ["10 trong số", "có 5 trường", "mua 3 trai", "lop 12 tro len"])
def test_chu_tr_khong_phai_so_tien(cau):
    assert not _SO_TIEN.search(cau)


# --- cái giá của việc bỏ dấu -------------------------------------------------

@pytest.mark.parametrize("cau", [
    "thue xe tai 5 tan het 3tr",          # thuê (rent), không phải thuế
    "thue nha xe gia 12 trieu",
    "thue kho bai 8tr mot thang",
    "mua vat tu 3tr",                     # vật tư, không phải VAT
])
def test_khong_dau_thue_va_vat_tu_khong_bi_nham_thanh_tinh_thue(cau):
    assert "vat" not in plan_tools(cau), cau


def test_ra_kho_lay_hang_khong_phai_yeu_cau_soi_kho():
    assert "inventory_audit" not in plan_tools("ra kho lay hang giup toi")


def test_cau_co_dau_van_phan_biet_thue_va_thue():
    assert "vat" not in plan_tools("Thuê xe tải 5 tấn hết 3 triệu")      # "thuê" = rent
    assert "vat" in plan_tools("Thuế 10% của đơn 4 triệu 2 là bao nhiêu")


# --- câu tính thuế không phải câu soát danh mục hay công nợ -------------------

def test_cau_tinh_thue_co_ten_hang_va_phai_tra_chi_ra_vat():
    assert plan_tools("Mua dầu nhớt 3tr5 thuế 8% thì tổng phải trả bao nhiêu?") == ["vat"]


def test_yeu_cau_ro_ve_danh_muc_hoac_cong_no_van_duoc_giu():
    assert "vat_catalog_audit" in plan_tools("Đối chiếu danh mục hàng với thuế 8% cho đơn 4 triệu")
    assert "partner_audit" in plan_tools("Thuế 10% đơn 4 triệu, đồng thời công nợ khách tổng hợp giúp tôi")


# --- câu định nghĩa -----------------------------------------------------------

@pytest.mark.parametrize("cau", [
    "Giá vốn hàng bán là gì?",
    "Công nợ phải thu khác công nợ phải trả chỗ nào",
    "Lợi nhuận gộp nghĩa là gì",
])
def test_cau_dinh_nghia_khong_chay_cong_cu(cau):
    assert plan_tools(cau) == []


# --- lớp lỗi từ tập ngoài mẫu của Minh (#103), viết lại bằng câu mới -----------

@pytest.mark.parametrize("cau, mong", [
    ("so doanh thu quý 3 với quý 2 xem hơn bao nhiêu", ["report"]),
    ("mặt hàng nào bán nhiều nhất mà lỗ", ["report"]),
    ("tính xem khách còn phải trả mình bao nhiêu trừ phần mình còn phải trả nhà cung cấp", ["partner_audit"]),
])
def test_lop_loi_ngoai_mau_cua_minh(cau, mong):
    assert plan_tools(cau) == mong
