"""
tests/offline_training/test_tong_hop_issue.py — bảng việc của đội sinh từ issue GitHub (`offline_training/tong_hop_issue.py`).

Chỉ test phần thuần `dinh_dang` (không mạng, không `gh`). Điều cần canh: việc đóng không lọt vào mục "đang mở",
việc chưa giao không biến mất, việc có hai người nhận hiện ở cả hai mục, và đầu ra tất định.
"""

from __future__ import annotations

from datetime import datetime, timezone

from offline_training.tong_hop_issue import dinh_dang

BAY_GIO = datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc)


def _i(n, state="OPEN", ai=(), tieu_de="Việc", updated="2026-11-15T10:00:00Z", closed=None, cmt=0):
    return {"number": n, "title": tieu_de, "state": state, "assignees": [{"login": a} for a in ai],
            "updatedAt": updated, "closedAt": closed, "comments": [{}] * cmt}


def test_viec_dong_khong_nam_trong_dang_mo_nhung_hien_o_muc_da_dong_gan_day():
    vb = dinh_dang([_i(1, "OPEN", ["Dgsonn"]), _i(2, "CLOSED", [], closed="2026-11-14T10:00:00Z")], {}, BAY_GIO)
    assert "Đang mở: **1**" in vb
    assert "Đã đóng trong 7 ngày qua: **1**" in vb
    muc_son = vb.split("## Sơn")[1].split("##")[0]
    assert "#1" in muc_son and "#2" not in muc_son


def test_viec_dong_qua_7_ngay_khong_hien():
    vb = dinh_dang([_i(2, "CLOSED", [], closed="2026-11-01T10:00:00Z")], {}, BAY_GIO)
    assert "Đã đóng trong 7 ngày qua: **0**" in vb and "#2" not in vb


def test_viec_chua_giao_khong_bien_mat():
    vb = dinh_dang([_i(5, "OPEN", [])], {}, BAY_GIO)
    assert "Chưa giao ai (1)" in vb and "#5" in vb


def test_viec_hai_nguoi_nhan_hien_o_ca_hai_muc():
    vb = dinh_dang([_i(98, "OPEN", ["Dgsonn", "tranthanh-riu"])], {}, BAY_GIO)
    assert "## Thành (1)" in vb and "## Sơn (1)" in vb and vb.count("#98") == 2


def test_cot_tren_bang_lay_tu_du_lieu_va_hien_dau_hoi_khi_khong_co():
    vb = dinh_dang([_i(1, "OPEN", ["Dgsonn"]), _i(2, "OPEN", ["Dgsonn"])], {1: "In Progress"}, BAY_GIO)
    assert "| In Progress |" in vb and "| ? |" in vb


def test_tieu_de_dai_bi_cat_va_xuong_dong_bi_gop():
    vb = dinh_dang([_i(1, "OPEN", ["Dgsonn"], tieu_de="a\nb " + "x" * 200)], {}, BAY_GIO)
    dong = next(d for d in vb.splitlines() if "#1]" in d)
    assert "…" in dong and "\n" not in dong.strip("|")


def test_ngay_tinh_theo_gio_viet_nam():
    # 17:30 UTC ngày 15/11 là 00:30 ngày 16/11 ở Việt Nam
    vb = dinh_dang([_i(1, "OPEN", ["Dgsonn"], updated="2026-11-15T17:30:00Z")], {}, BAY_GIO)
    assert "| 16/11 |" in vb


def test_ten_nguoi_la_khong_co_trong_bang_dung_ten_tai_khoan_va_dat_cuoi():
    vb = dinh_dang([_i(1, "OPEN", ["nguoi-la"]), _i(2, "OPEN", ["Dgsonn"])], {}, BAY_GIO)
    assert vb.index("## Sơn") < vb.index("## nguoi-la")


def test_tat_dinh():
    d = [_i(1, "OPEN", ["Dgsonn"]), _i(2, "OPEN", [])]
    assert dinh_dang(d, {}, BAY_GIO) == dinh_dang(list(d), {}, BAY_GIO)
