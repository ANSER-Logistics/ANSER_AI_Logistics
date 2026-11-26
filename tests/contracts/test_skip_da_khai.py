"""
tests/contracts/test_skip_da_khai.py — kiểm chính cổng "skip phải được khai" (#29).

Cổng nằm trong `tests/conftest.py`. Một cổng không ai kiểm sẽ hỏng im lặng đúng
như thứ nó canh: hook không được gọi, mã thoát không đổi, và CI vẫn xanh.
"""

from __future__ import annotations

import pathlib

import pytest

from tests.conftest import SKIP_DA_KHAI, doi_chieu_skip

pytest_plugins = ["pytester"]

GOC = pathlib.Path(__file__).resolve().parents[2]
KHAI = {"tests/test_a.py": (2, "lý do")}


def test_khop_thi_khong_loi():
    assert doi_chieu_skip({"tests/test_a.py": 2}, {"tests/test_a.py"}, KHAI) == []


def test_skip_NHIEU_hon_khai_la_loi():
    loi = doi_chieu_skip({"tests/test_a.py": 3}, {"tests/test_a.py"}, KHAI)
    assert len(loi) == 1 and "ngừng chạy" in loi[0]


def test_skip_IT_hon_khai_cung_la_loi():
    """Lý do skip đã hết mà quên sửa con số thì danh sách thành sai."""
    loi = doi_chieu_skip({}, {"tests/test_a.py"}, KHAI)
    assert len(loi) == 1 and "đã hết" in loi[0]


def test_file_co_skip_ma_khong_khai_la_loi():
    loi = doi_chieu_skip({"tests/test_b.py": 1}, {"tests/test_b.py"}, KHAI)
    assert loi == ["tests/test_b.py: 1 ca skip, khai 0 — có test vừa ngừng chạy"]


def test_file_khong_nam_trong_lan_chay_thi_bo_qua():
    """`pytest tests/test_x.py` có bật cổng không được đỏ vì file khác."""
    assert doi_chieu_skip({}, {"tests/test_x.py"}, KHAI) == []


def test_moi_dong_khai_co_ly_do_va_file_ton_tai():
    assert SKIP_DA_KHAI, "danh sách khai rỗng thì cổng chỉ còn là 'cấm mọi skip'"
    for ten, (so, ly_do) in SKIP_DA_KHAI.items():
        assert so > 0, f"{ten}: khai 0 ca thì xoá dòng đó đi"
        assert ly_do.strip(), f"{ten}: phải kèm lý do"
        assert (GOC / ten).is_file(), f"{ten}: file không còn tồn tại"


# ---------------------------------------------------------------------------
# Chạy pytest THẬT để chứng minh mã thoát đổi. Hàm đối chiếu đúng mà hook không
# được gọi, hoặc gọi mà không đổi exitstatus, thì CI vẫn xanh.
# ---------------------------------------------------------------------------

_CONFTEST_CON = (
    "from tests.conftest import (  # noqa: F401\n"
    "    pytest_collectreport, pytest_runtest_logreport,\n"
    "    pytest_sessionfinish, pytest_terminal_summary,\n"
    ")\n"
)


@pytest.fixture
def chay_con(pytester, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(GOC))
    pytester.makeconftest(_CONFTEST_CON)
    return pytester


def test_skip_chua_khai_lam_pytest_DO(chay_con, monkeypatch):
    monkeypatch.setenv("KIEM_SKIP_DA_KHAI", "1")
    chay_con.makepyfile(test_a="""
        import pytest
        def test_chay(): pass
        @pytest.mark.skip(reason="chưa khai")
        def test_bo(): pass
    """)
    kq = chay_con.runpytest_subprocess("-p", "no:randomly")
    assert kq.ret == pytest.ExitCode.TESTS_FAILED
    # So phần ASCII: stdout của tiến trình con trên Windows có thể mã hoá khác.
    kq.stdout.fnmatch_lines(["*(#29)*", "*test_a.py: 1 ca skip, khai 0*"])


def test_skip_ca_module_cung_bi_dem(chay_con, monkeypatch):
    """`importorskip` đầu module bỏ cả file mà pytest chỉ báo một ca."""
    monkeypatch.setenv("KIEM_SKIP_DA_KHAI", "1")
    chay_con.makepyfile(test_a="""
        import pytest
        pytest.importorskip("goi_khong_ton_tai_29")
        def test_x(): pass
    """)
    kq = chay_con.runpytest_subprocess("-p", "no:randomly")
    assert kq.ret != pytest.ExitCode.OK
    kq.stdout.fnmatch_lines(["*test_a.py: 1 ca skip, khai 0*"])


def test_khong_bat_co_thi_khong_doi_ma_thoat(chay_con, monkeypatch):
    """Máy dev (không đặt KIEM_SKIP_DA_KHAI) không bị đỏ vì skip."""
    monkeypatch.delenv("KIEM_SKIP_DA_KHAI", raising=False)
    chay_con.makepyfile(test_a="""
        import pytest
        @pytest.mark.skip(reason="máy dev")
        def test_bo(): pass
    """)
    kq = chay_con.runpytest_subprocess("-p", "no:randomly")
    assert kq.ret == pytest.ExitCode.OK


def test_khong_skip_nao_thi_xanh(chay_con, monkeypatch):
    monkeypatch.setenv("KIEM_SKIP_DA_KHAI", "1")
    chay_con.makepyfile(test_a="def test_chay(): pass\n")
    kq = chay_con.runpytest_subprocess("-p", "no:randomly")
    assert kq.ret == pytest.ExitCode.OK
