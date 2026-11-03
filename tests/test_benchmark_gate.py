"""
tests/test_benchmark_gate.py — ba mức kết luận của cổng đo chất lượng.

`benchmark_v3.py` là cổng chặn chất lượng của pipeline fine-tune. Nó phải phân
biệt được **ba** chuyện, không phải hai:

    ĐẠT               qua mọi ngưỡng, và đo đủ
    CHƯA ĐẠT          đo được, và dưới ngưỡng
    KHÔNG ĐỦ DỮ LIỆU  phần đo được thì qua, nhưng còn phần chưa đo

Gộp mức thứ ba vào "đạt" là loại lỗi tệ nhất mà dự án đang chống: một câu nghe
có vẻ đúng. Bản trước in `"✅ Qua mọi ngưỡng ĐO ĐƯỢC"` cho mức đó — đúng chữ,
nhưng người lướt qua chỉ thấy dấu tích xanh.

Soát 04/11/2026: 3 trong 4 tập đo không có (`eval_extraction`,
`eval_narration`, `eval_agent` — cả ba cần `DEEPSEEK_API_KEY` để sinh lại),
nên mức thứ ba là mức mà cổng này đang thực sự ở.
"""

from __future__ import annotations

import pytest

from offline_training.benchmark_v3 import (
    MUC_CHUA_DAT,
    MUC_DAT,
    MUC_KHONG_DU_DU_LIEU,
    ma_thoat_cua,
    nhan_cua_muc,
    xep_muc,
)

TRUOT = ["narration 62% < 80%"]
THIEU = ["narration — thiếu eval_narration.jsonl"]
IT_MAU = ["extraction — 3 ca, quá ít"]


# ---------------------------------------------------------------------------
# Ba mức, ba nghĩa
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "gate_fail, khong_do_duoc, mau_qua_it, muc",
    [
        ([], [], [], MUC_DAT),
        (TRUOT, [], [], MUC_CHUA_DAT),
        ([], THIEU, [], MUC_KHONG_DU_DU_LIEU),
        ([], [], IT_MAU, MUC_KHONG_DU_DU_LIEU),
    ],
)
def test_xep_dung_muc(gate_fail, khong_do_duoc, mau_qua_it, muc):
    assert xep_muc(gate_fail, khong_do_duoc, mau_qua_it) == muc


def test_chua_dat_thang_khong_du_du_lieu():
    """
    Vừa dưới ngưỡng vừa thiếu tập đo -> CHƯA ĐẠT.

    "Đo được phần này và nó trượt" là tin chắc chắn hơn "phần kia chưa đo", nên
    báo cái chắc chắn trước.
    """
    assert xep_muc(TRUOT, THIEU, IT_MAU) == MUC_CHUA_DAT


# ---------------------------------------------------------------------------
# Mức KHÔNG phụ thuộc cờ dòng lệnh
# ---------------------------------------------------------------------------

def test_xep_muc_khong_nhan_co():
    """
    `xep_muc` nói SỰ THẬT, cờ nói ta LÀM GÌ với sự thật đó.

    Gộp lại thì bật một cờ ở CI có thể âm thầm biến một lượt trượt thành một
    dòng xanh. Tách ra thì `--no-gate` đổi được mã thoát mà không đổi được kết
    luận.
    """
    import inspect

    tham_so = set(inspect.signature(xep_muc).parameters)
    assert "no_gate" not in tham_so
    assert "doi_du_tap_do" not in tham_so


# ---------------------------------------------------------------------------
# Nhãn in ra
# ---------------------------------------------------------------------------

def test_khong_du_du_lieu_KHONG_dung_dau_tich_xanh():
    """Người lướt qua chỉ nhìn biểu tượng đầu dòng."""
    nhan = nhan_cua_muc(MUC_KHONG_DU_DU_LIEU)
    assert "✅" not in nhan
    assert "KHÔNG" in nhan


def test_moi_muc_co_nhan_rieng():
    nhan = {nhan_cua_muc(m) for m in (MUC_DAT, MUC_CHUA_DAT, MUC_KHONG_DU_DU_LIEU)}
    assert len(nhan) == 3
    assert nhan_cua_muc(MUC_DAT).startswith("✅")
    assert nhan_cua_muc(MUC_CHUA_DAT).startswith("❌")


# ---------------------------------------------------------------------------
# Mã thoát suy ra TỪ mức
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "muc, no_gate, doi, ma",
    [
        (MUC_DAT,              False, False, 0),
        (MUC_DAT,              True,  True,  0),
        (MUC_CHUA_DAT,         False, False, 1),
        (MUC_CHUA_DAT,         False, True,  1),
        # `--no-gate` tha CHƯA ĐẠT — dùng lúc đo baseline model gốc.
        (MUC_CHUA_DAT,         True,  False, 0),
        # Mặc định TẮT: ci.yml chưa gọi file này, không ai dựa vào hành vi cũ.
        (MUC_KHONG_DU_DU_LIEU, False, False, 0),
        (MUC_KHONG_DU_DU_LIEU, False, True,  2),
    ],
)
def test_ma_thoat(muc, no_gate, doi, ma):
    assert ma_thoat_cua(muc, no_gate=no_gate, doi_du_tap_do=doi) == ma


def test_no_gate_KHONG_tha_viec_thieu_du_lieu():
    """
    `--no-gate` nói "tôi biết nó chưa đạt, đừng chặn". Nó không nói gì về việc
    thiếu dữ liệu.

    Để nó tha luôn cả hai thì bật `--no-gate` trong CI là tắt sạch cổng mà
    không ai nhận ra.
    """
    assert ma_thoat_cua(
        MUC_KHONG_DU_DU_LIEU, no_gate=True, doi_du_tap_do=True
    ) == 2
