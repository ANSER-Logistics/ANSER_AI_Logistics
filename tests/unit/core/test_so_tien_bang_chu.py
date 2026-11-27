"""
tests/unit/core/test_so_tien_bang_chu.py — số tiền VIẾT BẰNG CHỮ trong câu trả lời phải bị kiểm như số tiền viết bằng chữ số (R1).

VÌ SAO CÓ FILE NÀY
------------------
`grounding.narration_numbers_ok` bắt mọi con số trong câu trả lời bằng biểu thức chữ số, nên "ba trăm hai mươi
triệu đồng" không bị phép kiểm nào thấy: một con số model tự tính rồi viết thành chữ lọt qua nguyên vẹn, trong khi
"320.000.000" cùng nghĩa thì bị chặn. Bộ đọc chữ ra số đã có sẵn ở `doc_dau_vao` (đọc số tiền NGƯỜI DÙNG nói); nay
nằm ở `so_bang_chu.py` để cả hai nơi dùng một định nghĩa (R4).

Dùng lại bộ đọc cho một việc mới thì lỗi ngữ pháp của nó đổi nghĩa: trước đây đọc thiếu chỉ làm tham số sai bị lọt,
nay đọc thiếu sẽ CHẶN OAN câu trả lời đúng. Nên test chính là một vòng khứ hồi: viết số ra chữ bằng bộ viết ĐỘC LẬP
(`offline_training.hoa_don_luat.doc_so`, dựng hoá đơn hư cấu) rồi đọc lại. Lần đầu chạy nó bắt hai chỗ đọc sai thật
("không trăm" và "nghìn tỷ", 1.384 trên 3.900 mẫu từ 1.000 trở lên) và một chỗ đọc "2.005" thành "2.500".
"""

from __future__ import annotations

import random

import pytest

from offline_training.hoa_don_luat import doc_so
from src.core.grounding import guard_answer, narration_numbers_ok
from src.core.so_bang_chu import so_bang_chu


def _gia_tri(cau: str) -> list[int]:
    return [v for _, v in so_bang_chu(cau)]


# ---------------------------------------------------------------------------
# Bộ đọc: vòng khứ hồi với bộ viết độc lập
# ---------------------------------------------------------------------------

def _mo_ho_nhom_nghin_trong(n: int) -> bool:
    """
    Còn một nhập nhằng THẬT của tiếng Việt, không phải lỗi: "một triệu hai trăm mười chín" cho 1.000.219 (bỏ nhóm
    nghìn rỗng) trùng với cách nói tắt "một triệu hai trăm mười chín nghìn" = 1.219.000. Với TIỀN cách nói tắt
    là cách đọc đúng, nên bộ đọc chọn nó. Số có một nhóm ba chữ số rỗng nằm giữa hai nhóm khác rỗng thuộc loại này.
    """
    nhom = []
    while n:
        nhom.append(n % 1000)
        n //= 1000
    dau = max(i for i, g in enumerate(nhom) if g)
    cuoi = min(i for i, g in enumerate(nhom) if g)
    return any(nhom[i] == 0 for i in range(cuoi + 1, dau))


def test_khu_hoi_moi_so_tu_1000_den_duoi_1e15_doc_lai_dung():
    rng = random.Random(20261120)
    sai, da_kiem = [], 0
    for so_chu_so in range(4, 16):                       # từ 1.000 tới dưới 10^15
        for _ in range(250):
            n = rng.randrange(10 ** (so_chu_so - 1), 10 ** so_chu_so)
            if _mo_ho_nhom_nghin_trong(n):
                continue
            da_kiem += 1
            if _gia_tri(doc_so(n) + " đồng") != [n]:
                sai.append((n, doc_so(n), _gia_tri(doc_so(n))))
    assert da_kiem > 2500, "mẫu quá ít: vòng khứ hồi chưa chứng minh gì"
    assert not sai, f"{len(sai)}/{da_kiem} số đọc sai, ví dụ: {sai[:3]}"


def test_duoi_1000_khong_phai_tien_thi_khong_doc():
    """Chốt chống xanh suông ở chiều ngược: 'năm trăm' trơn không có đơn vị nghìn/triệu/tỷ, không phải tiền."""
    for n in (5, 12, 99, 100, 500, 999):
        assert _gia_tri(doc_so(n) + " khách") == []


@pytest.mark.parametrize("chu, mong", [
    # Hai chỗ đọc sai đã sửa (20/11/2026): trước đây cắt thành HAI số sai, hoặc thành số khác hẳn.
    ("một triệu không trăm năm mươi nghìn", [1_050_000]),            # trước: [1_000_000, 50_000]
    ("hai nghìn không trăm linh năm", [2_005]),                       # trước: [2_500]
    ("hai triệu không trăm năm mươi", [2_000_050]),
    ("một nghìn tỷ", [1_000_000_000_000]),                            # trước: [1_000]
    ("hai trăm nghìn tỷ", [200_000_000_000_000]),
    # Cách nói tắt GIỮ NGUYÊN: đây là cách người Việt nói tiền.
    ("năm triệu rưỡi", [5_500_000]),
    ("năm triệu hai", [5_200_000]),
    ("hai triệu năm trăm", [2_500_000]),
    ("hai trăm nghìn", [200_000]),
    ("ba trăm linh năm nghìn", [305_000]),
    ("một tỷ hai trăm triệu", [1_200_000_000]),
    # Nhập nhằng đã nêu ở docstring `_mo_ho_nhom_nghin_trong`: chọn cách nói tắt.
    ("một triệu hai trăm mười chín", [1_219_000]),
])
def test_cac_ca_ngu_phap_cu_the(chu, mong):
    assert _gia_tri(chu + " đồng") == mong


# ---------------------------------------------------------------------------
# Phép kiểm câu trả lời
# ---------------------------------------------------------------------------

CTX = '{"total_revenue": 300000000, "net_profit": 2480000, "debt": 1200000000, "gap": 250000}'


@pytest.mark.parametrize("cau", [
    "Doanh thu là ba trăm triệu đồng.",                       # khớp chính xác 300.000.000
    "Nợ phải thu một tỷ hai trăm triệu đồng.",                # 1.200.000.000
    "Chênh lệch hai trăm năm mươi nghìn đồng.",               # 250.000
    "Lãi ròng khoảng hai triệu rưỡi.",                        # 2.480.000 làm tròn tới 0,1 triệu = 2,5 triệu
    "Có năm trăm khách trong kỳ.",                            # không có đơn vị tiền: không bị kiểm
    "Doanh thu 300.000.000 đồng, tức ba trăm triệu.",         # chữ số và chữ cùng đúng
])
def test_so_chu_khop_context_thi_qua(cau):
    assert narration_numbers_ok(cau, CTX) == (True, None)


@pytest.mark.parametrize("cau, so_vi_pham", [
    ("Doanh thu là ba trăm hai mươi triệu đồng.", "320000000"),   # model tự cộng/đoán
    ("Lãi ròng khoảng ba triệu rưỡi.", "3500000"),                # xa 2.480.000 hơn nửa đơn vị đã nói
    ("Nợ phải thu một tỷ ba trăm triệu đồng.", "1300000000"),
    ("Giảm hai trăm nghìn so với hôm qua.", "200000"),            # số suy ra, không có trong dữ liệu
])
def test_so_chu_khong_co_trong_context_thi_chan(cau, so_vi_pham):
    ok, vi_pham = narration_numbers_ok(cau, CTX)
    assert ok is False and vi_pham == so_vi_pham


def test_cung_con_so_viet_bang_chu_so_va_bang_chu_deu_bi_chan_nhu_nhau():
    """Trước 20/11/2026 hai cách viết này khác nhau: chữ số bị chặn, chữ lọt. Giờ cùng kết quả."""
    bang_so = narration_numbers_ok("Doanh thu là 320.000.000 đồng.", CTX)
    bang_chu = narration_numbers_ok("Doanh thu là ba trăm hai mươi triệu đồng.", CTX)
    assert bang_so[0] is False and bang_chu[0] is False


def test_luat_do_dai_cu_khong_doi():
    """`chi_kiem_so_tien=False` là luật cũ giữ cho phép so sánh trước/sau: không có đường chạy nào dùng, không đổi."""
    assert narration_numbers_ok("Doanh thu là ba trăm hai mươi triệu đồng.", CTX, chi_kiem_so_tien=False) == (True, None)


def test_guard_answer_tu_choi_cau_so_chu_bia():
    kq = guard_answer("Doanh thu là ba trăm hai mươi triệu đồng.", CTX, for_customer=True)
    assert kq.ok is False
    kq_dung = guard_answer("Doanh thu là ba trăm triệu đồng.", CTX, for_customer=True)
    assert kq_dung.ok is True
