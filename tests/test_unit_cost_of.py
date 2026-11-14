"""
tests/test_unit_cost_of.py — đơn giá vốn của một dòng tồn kho (issue #36).

VÌ SAO CÓ FILE NÀY
------------------
`inventory.unit_cost_of` trả `(đơn_giá, nguồn)` và Body ghi con số đó thành GIÁ
VỐN HÀNG BÁN. Giá vốn sai thì lãi gộp sai, mà báo cáo vẫn trông bình thường —
không có gì đỏ cho tới lúc quyết toán. Soát 12/11/2026: không test nào gọi tên
hàm này (`grep -rn unit_cost_of tests/` rỗng).

HÀNH VI ĐANG KIỂM (đọc từ code, không từ tài liệu)
------------------------------------------------
- Thử lần lượt ba nguồn: XUẤT -> TỒN CUỐI -> TỒN ĐẦU. Lấy nguồn đầu tiên có
  đơn giá khác None VÀ > 0.
- Đơn giá của một nguồn = giá trị / số lượng, nhưng là None khi giá trị None
  hoặc số lượng <= 0,01 (`_QTY_TOL`) — đó là chỗ chặn chia cho 0.
- Không nguồn nào dùng được -> `(None, "")`. KHÔNG phải 0: 0 là một giá vốn
  trông hợp lệ, và lãi gộp sẽ thành bằng doanh thu.

Mọi đáp án dưới đây tính tay, ghi ngay cạnh ca.
"""

from __future__ import annotations

import pytest

from src.core.inventory import InventoryLine, unit_cost_of


def _dong(**kw) -> InventoryLine:
    return InventoryLine(code="VT001", name="Dầu CF-4 18L", unit="Can", **kw)


# ---------------------------------------------------------------------------
# Thứ tự ưu tiên ba nguồn
# ---------------------------------------------------------------------------

def test_du_ca_ba_nguon_thi_chon_XUAT():
    """Xuất là giá vốn THẬT đã phát sinh — phải thắng dù hai nguồn kia có số."""
    line = _dong(
        opening_qty=10, opening_value=1_000_000,     # 100.000 / can
        out_qty=4, out_value=480_000,                # 120.000 / can  <- chọn
        closing_qty=5, closing_value=550_000,        # 110.000 / can
    )
    assert unit_cost_of(line) == (120_000, "xuất")


def test_khong_xuat_thi_lui_ve_TON_CUOI():
    line = _dong(
        opening_qty=10, opening_value=1_000_000,     # 100.000
        closing_qty=8, closing_value=880_000,        # 110.000  <- chọn
    )
    assert unit_cost_of(line) == (110_000, "tồn cuối")


def test_chi_con_TON_DAU():
    line = _dong(opening_qty=20, opening_value=1_500_000)   # 75.000
    assert unit_cost_of(line) == (75_000, "tồn đầu")


def test_don_gia_le_khong_bi_lam_tron():
    """Hàm trả số thực; làm tròn là việc của nơi hiển thị, không phải ở đây."""
    line = _dong(out_qty=3, out_value=100_000)
    gia, nguon = unit_cost_of(line)
    assert nguon == "xuất"
    assert gia == pytest.approx(33_333.333_333, rel=1e-9)


# ---------------------------------------------------------------------------
# Thiếu dữ liệu -> None, không phải 0
# ---------------------------------------------------------------------------

def test_khong_co_gia_tri_nao_thi_None_chu_khong_phai_0():
    """Số lượng có đủ, nhưng cả ba cột giá trị đều CHƯA BIẾT."""
    line = _dong(opening_qty=10, out_qty=4, closing_qty=6)
    gia, nguon = unit_cost_of(line)
    assert gia is None, f"thiếu dữ liệu mà trả {gia!r} — phải là None"
    assert nguon == ""


def test_dong_trong_hoan_toan():
    assert unit_cost_of(_dong()) == (None, "")


def test_nguon_xuat_thieu_gia_tri_thi_lui_tiep_chu_khong_dung_o_do():
    """Có xuất 4 can nhưng không ghi giá trị -> không đoán, sang nguồn sau."""
    line = _dong(out_qty=4, out_value=None, closing_qty=5, closing_value=500_000)
    assert unit_cost_of(line) == (100_000, "tồn cuối")


# ---------------------------------------------------------------------------
# Mẫu số bằng 0 / gần 0
# ---------------------------------------------------------------------------

def test_so_luong_0_ma_co_gia_tri_KHONG_chia_cho_0():
    """Dữ liệu bẩn kiểu MISA: giá trị xuất 500.000 nhưng số lượng xuất 0."""
    line = _dong(out_qty=0, out_value=500_000, closing_qty=2, closing_value=200_000)
    assert unit_cost_of(line) == (100_000, "tồn cuối")


def test_so_luong_0_o_ca_ba_nguon():
    line = _dong(opening_value=1, out_value=2, closing_value=3)
    assert unit_cost_of(line) == (None, "")


def test_so_luong_duoi_nguong_bi_coi_nhu_0():
    """0,005 can mà giá trị 500 đồng sẽ cho đơn giá 100.000 — trông hợp lý nhưng
    là nhiễu làm tròn. Ngưỡng 0,01 (`_QTY_TOL`) chặn nó."""
    line = _dong(out_qty=0.005, out_value=500, closing_qty=1, closing_value=90_000)
    assert unit_cost_of(line) == (90_000, "tồn cuối")


# ---------------------------------------------------------------------------
# Giá trị 0 hoặc âm — ghi lại HÀNH VI HIỆN TẠI
# ---------------------------------------------------------------------------
# Hai ca này không phải "đúng theo nghiệp vụ" đã được ai chốt: chúng chụp lại
# việc hàm đang làm (bỏ qua và lùi sang nguồn sau), để nếu ai đổi thì test đỏ
# và người đó phải nói ra vì sao.

def test_hang_khuyen_mai_gia_tri_0_bi_bo_qua():
    """Kho khuyến mại xuất có giá trị 0 THẬT. Hàm không lấy 0 làm giá vốn."""
    line = _dong(out_qty=10, out_value=0, opening_qty=10, opening_value=800_000)
    assert unit_cost_of(line) == (80_000, "tồn đầu")


def test_gia_tri_am_bi_bo_qua():
    """Giá trị âm (chứng từ điều chỉnh) cho đơn giá âm — không dùng làm giá vốn."""
    line = _dong(out_qty=2, out_value=-100_000, closing_qty=1, closing_value=60_000)
    assert unit_cost_of(line) == (60_000, "tồn cuối")
