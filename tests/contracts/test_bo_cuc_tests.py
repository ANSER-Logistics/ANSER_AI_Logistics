"""
tests/contracts/test_bo_cuc_tests.py — không có file test nào ở gốc `tests/` (đề xuất của Thành ở #266).

Từ #266 mỗi test nằm trong một nhóm theo phạm vi. pytest vẫn thu một file đặt ở gốc nên CI vẫn xanh, và bố cục lặng lẽ
trôi lại như cũ. Gốc chỉ được giữ `__init__.py` và `conftest.py`.
"""

from __future__ import annotations

from pathlib import Path

GOC = Path(__file__).resolve().parents[1]


def test_khong_co_file_test_o_goc_tests():
    lac = sorted(p.name for p in [*GOC.glob("test_*.py"), *GOC.glob("*_test.py")])
    assert not lac, (
        f"File test ở gốc tests/: {lac}. Chuyển vào tests/unit/, tests/integration/, tests/contracts/ "
        "hoặc tests/offline_training/ theo phạm vi."
    )
