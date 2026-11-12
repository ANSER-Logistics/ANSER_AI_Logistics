"""
tests/test_tai_lieu_khop_ma.py — tài liệu chỉ dẫn cho agent/người mới không được tự lệch khỏi mã.

AGENTS.md §4.2 nói thẳng: tài liệu từng sai ở nhiều điểm quan trọng (ARCHITECTURE v1.0 dẫn
tới chọn model theo A100 trong khi code chạy L4; danh sách biến môi trường ghi ba cái tên
KHÔNG tồn tại trong code). "Sửa tài liệu cùng PR" là quy tắc cho con người — ở đây nó thành
phép kiểm máy, vì lệch pha tài liệu là loại lỗi không ai thấy tới lúc có người làm theo.

Hai phép kiểm, cả hai đều có chốt chống xanh suông (số mẫu tối thiểu), vì một biểu thức
chính quy hỏng sẽ lặp trên tập rỗng và xanh hết:

  1. Mọi liên kết tương đối trong *.md trỏ tới file/thư mục CÓ THẬT.
  2. Mọi biến môi trường AGENTS.md §R5 khai là "tên thật trong code" thì code ĐỌC nó.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_BO_QUA = {".git", ".venv", "venv", "node_modules", "_backups", "__pycache__"}

_LIEN_KET = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")


def _tat_ca_md() -> list[Path]:
    return sorted(
        p for p in ROOT.rglob("*.md")
        if not (_BO_QUA & set(p.relative_to(ROOT).parts))
    )


def _lien_ket_tuong_doi(p: Path):
    for m in _LIEN_KET.finditer(p.read_text(encoding="utf-8")):
        url = m.group(1)
        if re.match(r"(https?:|mailto:|#)", url):
            continue
        duong = url.split("#", 1)[0]
        if duong:
            yield url, duong


def test_chot_chong_xanh_suong_co_du_file_va_lien_ket():
    files = _tat_ca_md()
    assert len(files) >= 20, f"chỉ thấy {len(files)} file .md — sai ROOT?"
    assert sum(1 for f in files for _ in _lien_ket_tuong_doi(f)) >= 200


def test_moi_lien_ket_tuong_doi_trong_tai_lieu_tro_toi_noi_co_that():
    hong = [
        f"{f.relative_to(ROOT)}: ({url})"
        for f in _tat_ca_md()
        for url, duong in _lien_ket_tuong_doi(f)
        if not (f.parent / duong).exists()
    ]
    assert not hong, "liên kết trỏ tới nơi không tồn tại:\n  " + "\n  ".join(hong)


def _bien_agents_r5() -> list[str]:
    """Tên biến trong khối mã của mục R5 (đầu mỗi dòng, chữ HOA + gạch dưới)."""
    s = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    i = s.index("### R5")
    khoi = re.search(r"```python\n(.*?)```", s[i:], re.S)
    assert khoi, "không thấy khối mã trong mục R5 — đổi định dạng thì sửa test này"
    return re.findall(r"^([A-Z][A-Z0-9_]+)\b", khoi.group(1), re.M)


def test_chot_chong_xanh_suong_doc_du_bien_r5():
    ten = _bien_agents_r5()
    assert len(ten) >= 8, f"chỉ đọc được {ten}"


@pytest.mark.parametrize("ten", _bien_agents_r5())
def test_bien_moi_truong_agents_r5_duoc_code_doc_that(ten):
    """AGENTS từng ghi GPU_MEMORY_UTILIZATION / MAX_MODEL_LEN / QUANTIZATION — không có trong code."""
    mau = re.compile(rf"""(?:getenv|environ\.get|environ)\(?\[?\s*["']{ten}["']""")
    thay = [p for p in (ROOT / "src").rglob("*.py") if mau.search(p.read_text(encoding="utf-8"))]
    assert thay, f"AGENTS.md khai {ten} là tên thật trong code nhưng src/ không đọc nó"
