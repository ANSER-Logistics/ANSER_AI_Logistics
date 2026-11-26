"""
tests/contracts/test_kho_van_ban_phap_luat_day_du.py — văn bản pháp luật trong `src/data/docs/` phải đủ, không cụt.

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

import hashlib
import html
import re
import zipfile
from pathlib import Path

import pytest

from src.core.doc_extract import extract

DOCS = Path(__file__).resolve().parents[2] / "src" / "data" / "docs"
# PDF trong thư mục này là báo cáo ngành, bài tạp chí (không phải văn bản pháp luật): không kiểm kiểu này.
DUOI = (".docx", ".md", ".txt")


def _tai_lieu() -> list[Path]:
    return sorted(p for p in DOCS.iterdir() if p.suffix.lower() in DUOI)


def _van_ban(p: Path) -> str:
    """
    Chữ của tài liệu. `.docx` đọc bằng `zipfile` thuần, KHÔNG qua `doc_extract.extract`: CI không cài `python-docx`
    (và test tự bỏ qua khi thiếu thư viện là đúng kiểu im lặng mà dự án cấm). Bài kiểm cụt chỉ cần chữ và
    thứ tự của chúng, không cần bố cục; bảng trong `.docx` vẫn nằm trong XML nên không bị bỏ sót.
    """
    if p.suffix.lower() == ".docx":
        with zipfile.ZipFile(p) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()
    return extract(p.read_bytes(), p.name).text.strip()


def _chu_chuan(p: Path) -> str:
    """Chữ để so hai tài liệu có CÙNG nội dung không: giải mã thực thể XML (`&#39;` là dấu `'`) và gộp khoảng trắng."""
    return " ".join(html.unescape(_van_ban(p)).split())


def test_chot_chong_xanh_suong_co_du_tai_lieu():
    assert len(_tai_lieu()) >= 5, f"chỉ thấy {len(_tai_lieu())} tài liệu trong {DOCS}"


def test_khong_con_ban_converted():
    """Mười tệp "(Converted - ...)" đã xoá: so từng từ thì giống hệt bản gốc (#141 chỉ chặn nạp trùng, không xoá tệp)."""
    con = sorted(p.name for p in DOCS.glob("*Converted*"))
    assert not con, f"còn bản Converted: {con}"


def test_khong_co_hai_van_ban_trung_noi_dung():
    """
    Hai tệp cùng chữ dưới hai tên là hai nguồn: một đoạn chiếm hai chỗ trong `top_k` và tên tệp xấu lọt vào chuỗi
    dẫn nguồn (#118). #141 chặn ở lúc nạp; test này chặn ở gốc, trong chính thư mục dữ liệu.
    """
    theo_ma: dict[str, list[str]] = {}
    for p in _tai_lieu():
        theo_ma.setdefault(hashlib.sha256(_chu_chuan(p).encode("utf-8")).hexdigest(), []).append(p.name)
    trung = [ten for ten in theo_ma.values() if len(ten) > 1]
    assert not trung, f"các tệp cùng nội dung: {trung}"


def test_dau_do_bat_duoc_hai_tep_trung_noi_dung():
    """Chứng minh test không câm: `&#39;` và `'` là cùng chữ, khoảng trắng khác nhau vẫn là cùng chữ."""
    a = " ".join(html.unescape("Nghị định&#39;  số 18").split())
    b = " ".join(html.unescape("Nghị định' số\n18").split())
    assert a == b


@pytest.mark.parametrize("p", _tai_lieu(), ids=lambda p: p.name)
def test_tai_lieu_khong_cut_giua_cau_hay_giua_cong_thuc(p):
    text = _van_ban(p)
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
