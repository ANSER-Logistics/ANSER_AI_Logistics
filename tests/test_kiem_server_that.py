"""
tests/test_kiem_server_that.py — phần THUẦN của `offline_training/kiem_server_that.py`.

Việc bật server thật chạy ở bước CI riêng (không ở pytest: bật tiến trình con trong bộ test làm chập chờn và tốn thời gian).
Ở đây chỉ khoá phép chấm: nó phải ĐỎ khi một phản hồi sai, không chỉ xanh khi mọi thứ đúng.
"""

from __future__ import annotations

from offline_training.kiem_server_that import danh_gia

TOT = (
    {"status": "ok"},
    {"calculated_total": 2_200_000, "is_valid": True},
    {"quote": {"quoted_price": 1_139_000}},
    {"paths": {f"/p{i}": {} for i in range(22)} | {"/tools/vat": {}}},
)


def _ok(*phan_hoi):
    return {k["ten"]: k["ok"] for k in danh_gia(*phan_hoi)}


def test_moi_phan_hoi_dung_thi_dat_het():
    assert all(_ok(*TOT).values()) and len(_ok(*TOT)) == 4


def test_tung_phan_hoi_sai_thi_dung_mot_kiem_do():
    sai = [
        ({"status": "degraded"}, *TOT[1:]),
        (TOT[0], {"calculated_total": 2_160_000, "is_valid": False}, *TOT[2:]),
        (*TOT[:2], {"quote": {"quoted_price": 1_138_500}}, TOT[3]),     # quên làm tròn tới nghìn
        (*TOT[:3], {"paths": {"/tools/vat": {}}}),                       # app mất gần hết route
    ]
    for phan_hoi in sai:
        ket_qua = _ok(*phan_hoi)
        assert sum(1 for v in ket_qua.values() if not v) == 1, (phan_hoi, ket_qua)


def test_phan_hoi_khong_phai_json_thi_do_khong_no():
    """Server trả chuỗi lỗi hay None: phép chấm phải báo hỏng chứ không ném ngoại lệ."""
    assert not any(_ok("Internal Server Error", None, "x", None).values())
