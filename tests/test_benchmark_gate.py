"""
tests/test_benchmark_gate.py — mã thoát của cổng đo chất lượng.

`benchmark_v3.py` là cổng chặn chất lượng của pipeline fine-tune. Phần chữ nó
in ra rất cẩn thận: "KHÔNG ĐO ĐƯỢC (thiếu dữ liệu, không phải model đạt)", và
câu kết luận có điều kiện.

Nhưng **mã thoát** mới là thứ máy đọc. Người nhìn màn hình thì hiểu đúng; một
job CI đọc `$?` chỉ thấy một con số. Nếu con số đó là 0 khi chưa đo được gì,
thì "CI xanh" trở thành một câu không có lần chạy nào chứng minh — đúng thứ
`BIEN_BAN_CHU_KY_01` đã ghi về 136 lượt Actions.

Soát 04/11/2026: 3 trong 4 tập đo không có (`eval_extraction`,
`eval_narration`, `eval_agent` — cả ba cần `DEEPSEEK_API_KEY` để sinh lại).
"""

from __future__ import annotations

import pytest

from offline_training.benchmark_v3 import quyet_ma_thoat


def _goi(gate_fail=(), khong_do_duoc=(), mau_qua_it=(), *, no_gate=False, doi=False):
    return quyet_ma_thoat(
        list(gate_fail), list(khong_do_duoc), list(mau_qua_it),
        no_gate=no_gate, doi_du_tap_do=doi,
    )


# ---------------------------------------------------------------------------
# Ba mã, ba nghĩa khác nhau
# ---------------------------------------------------------------------------

def test_do_du_va_qua_nguong_thi_0():
    assert _goi() == 0


def test_duoi_nguong_thi_1():
    """Đo được, và không đạt. Đây là nghĩa gốc của cổng."""
    assert _goi(gate_fail=["narration 62% < 80%"]) == 1


def test_thieu_tap_do_voi_co_thi_2():
    """
    Khác hẳn mã 1: không phải "model chưa đạt", mà là "chưa đo".

    Dùng mã riêng để người đọc `$?` phân biệt được hai chuyện đó.
    """
    assert _goi(khong_do_duoc=["narration — thiếu eval_narration.jsonl"], doi=True) == 2


# ---------------------------------------------------------------------------
# Hành vi mặc định KHÔNG đổi
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "khong_do_duoc, mau_qua_it",
    [
        (["narration — thiếu eval_narration.jsonl"], []),
        ([], ["extraction — 3 ca, quá ít"]),
        (["a", "b", "c"], ["d"]),
    ],
)
def test_thieu_tap_do_ma_khong_bat_co_thi_van_0(khong_do_duoc, mau_qua_it):
    """
    `ci.yml` chưa gọi file này, nên không ai đang dựa vào mã thoát hiện tại.
    Đổi mặc định là đổi hợp đồng của một công cụ mà mình không biết hết người
    dùng. Ai nối vào CI thì tự bật cờ.
    """
    assert _goi(khong_do_duoc=khong_do_duoc, mau_qua_it=mau_qua_it) == 0


# ---------------------------------------------------------------------------
# `--no-gate` tha đúng một chuyện
# ---------------------------------------------------------------------------

def test_no_gate_tha_viec_duoi_nguong():
    """Dùng khi đo baseline model gốc — biết trước là dưới ngưỡng."""
    assert _goi(gate_fail=["narration 62% < 80%"], no_gate=True) == 0


def test_no_gate_KHONG_tha_viec_thieu_tap_do():
    """
    Hai chuyện khác nhau: "đo rồi, chưa đạt" và "chưa đo".

    `--no-gate` nói "tôi biết nó chưa đạt, đừng chặn". Nó không nói gì về việc
    thiếu dữ liệu. Để nó tha luôn cả hai thì bật `--no-gate` trong CI là tắt
    sạch cổng mà không ai nhận ra.
    """
    assert _goi(
        khong_do_duoc=["narration — thiếu eval_narration.jsonl"],
        no_gate=True, doi=True,
    ) == 2


def test_duoi_nguong_thang_thieu_tap_do():
    """
    Vừa dưới ngưỡng vừa thiếu tập đo -> trả 1.

    "Đo được phần này và nó trượt" là tin chắc chắn hơn "phần kia chưa đo", nên
    báo cái chắc chắn trước. Mã 2 dành cho trường hợp KHÔNG có tin xấu nào chắc
    chắn mà vẫn không kết luận được.
    """
    assert _goi(
        gate_fail=["narration 62% < 80%"],
        khong_do_duoc=["extraction — thiếu eval_extraction.jsonl"],
        doi=True,
    ) == 1
