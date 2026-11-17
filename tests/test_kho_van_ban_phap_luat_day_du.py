"""
tests/test_kho_van_ban_phap_luat_day_du.py — văn bản pháp luật trong `src/data/docs/` phải đủ, không cụt.

VÌ SAO CÓ FILE NÀY
------------------
Tệp `67-2025-QH15-580594.docx` (Luật Thuế thu nhập doanh nghiệp, ngày 14/06/2025) trong kho RAG chỉ có 11.766
ký tự và dừng GIỮA CÔNG THỨC ở Điều 7 ("Thu nhập tính thuế ="): mới khoảng một phần tư luật. Hai bản "(Converted ...)"
của nó giống hệt, cụt y như vậy. Không bước nào lúc nạp phát hiện, nên hệ thống trả lời về thuế suất, ưu đãi, chuyển
lỗ... mà không có các Điều đó, và không nói gì. Nghiên cứu RAG 17/11/2026 tìm ra; thay bằng bản Công báo đầy đủ.

Bài kiểm này rẻ và chỉ bắt được loại lỗi đó (cụt giữa câu hoặc giữa công thức), không bắt được cụt đúng chỗ kết
thúc một câu. Nó là chốt tối thiểu, không thay cho việc đối chiếu với nguồn chính thống khi thêm văn bản mới.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.core.doc_extract import extract

DOCS = Path(__file__).resolve().parent.parent / "src" / "data" / "docs"
# PDF trong thư mục này là báo cáo ngành, bài tạp chí (không phải văn bản pháp luật): không kiểm kiểu này.
DUOI = (".docx", ".md", ".txt")


def _tai_lieu() -> list[Path]:
    return sorted(p for p in DOCS.iterdir() if p.suffix.lower() in DUOI)


def test_chot_chong_xanh_suong_co_du_tai_lieu():
    assert len(_tai_lieu()) >= 5, f"chỉ thấy {len(_tai_lieu())} tài liệu trong {DOCS}"


@pytest.mark.parametrize("p", _tai_lieu(), ids=lambda p: p.name)
def test_tai_lieu_khong_cut_giua_cau_hay_giua_cong_thuc(p):
    text = extract(p.read_bytes(), p.name).text.strip()
    assert len(text) > 2000, f"{p.name} chỉ có {len(text)} ký tự: nhiều khả năng cụt"
    cuoi = text[-1]
    assert cuoi not in "=:,;-(+*/", (
        f"{p.name} kết thúc bằng {cuoi!r} — dừng giữa câu hoặc giữa công thức, tức là cụt. "
        f"Đoạn cuối: {text[-80:]!r}"
    )


def test_khong_con_ban_cut_cua_luat_thue_tndn():
    """Ba tệp cụt (bản gốc và hai bản "Converted") đã thay bằng bản Công báo đầy đủ."""
    con = sorted(p.name for p in DOCS.glob("67-2025-QH15-580594*"))
    assert not con, f"còn bản cụt của Luật Thuế TNDN: {con}"


def test_luat_thue_tndn_day_du_20_dieu_va_co_khoi_ky():
    p = DOCS / "67-2025-QH15-Luat-Thue-TNDN.md"
    assert p.is_file(), "thiếu bản đầy đủ của Luật 67/2025/QH15"
    text = extract(p.read_bytes(), p.name).text
    dieu = [int(x) for x in re.findall(r"(?m)^### Điều (\d+)\.", text)]
    assert dieu == list(range(1, 21)), f"Luật 67/2025/QH15 có 20 Điều liên tục, tệp có {dieu}"
    assert text.rstrip().endswith("Trần Thanh Mẫn"), "thiếu khối ký ở cuối: tệp có thể cụt"
    assert "congbao.chinhphu.vn" in text, "phải ghi nguồn (Công báo) ở đầu tệp"


def test_luat_thue_tndn_co_dung_ba_muc_thue_suat_o_dieu_10():
    """Chốt nội dung có thật, không chỉ cấu trúc: Điều 10 (thuế suất) là Điều quan trọng nhất của luật."""
    text = (DOCS / "67-2025-QH15-Luat-Thue-TNDN.md").read_text(encoding="utf-8")
    m = re.search(r"### Điều 10\..*?(?=### Điều 11\.)", text, re.S)
    assert m, "không tìm thấy Điều 10"
    dieu10 = m.group(0)
    assert "20%" in dieu10 and "15%" in dieu10 and "17%" in dieu10
    assert "03 tỷ đồng" in dieu10 and "50 tỷ đồng" in dieu10


def test_dau_do_bat_duoc_van_ban_cut():
    """Chứng minh test không câm: đúng đoạn cuối của tệp cụt cũ phải bị bắt."""
    cut = "Điều 7. Xác định thu nhập tính thuế 1. Thu nhập tính thuế trong kỳ tính thuế được xác định như sau: Thu nhập tính thuế ="
    assert cut.strip()[-1] in "=:,;-(+*/"
