"""
tests/test_srs_khop_ma.py — `docs/SRS_BRAIN.md` không được tự lệch khỏi mã.

SRS này nêu con số và tên gọi (số route, tên module, tên biến môi trường) cho người mới đọc.
Chúng cũ đi âm thầm: không ai thấy tới lúc có người làm theo một tên không còn tồn tại.
Test đối chiếu ba loại với mã thật, và mỗi phép kiểm có chốt chống xanh suông (số mẫu tối
thiểu) vì một biểu thức chính quy hỏng sẽ lặp trên tập rỗng và xanh hết.

Đổi mã làm test này đỏ thì sửa SRS cùng PR (AGENTS.md §4.2); đừng xoá phép kiểm.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRS = (ROOT / "docs" / "SRS_BRAIN.md").read_text(encoding="utf-8")

_ROUTE_TU_SINH = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _muc(tieu_de: str) -> str:
    """Nội dung từ một tiêu đề `### ...` tới tiêu đề cùng cấp kế tiếp."""
    i = SRS.index(tieu_de)
    j = SRS.find("\n### ", i + 1)
    k = SRS.find("\n## ", i + 1)
    cuoi = min(x for x in (j, k, len(SRS)) if x > 0)
    return SRS[i:cuoi]


def _route_trong_srs() -> set[tuple[str, str]]:
    """{(phương thức, đường dẫn)} từ bảng §4.4.

    Ô đầu của mỗi dòng gồm các đoạn trong dấu huyền, ví dụ:
      `GET /health`
      `POST`, `GET`, `DELETE /knowledge/documents`      (nhiều phương thức, một đường)
      `POST /tools/inventory-audit`, `/tools/inventory-import`   (đường sau dùng lại phương thức trước)
    """
    ra: set[tuple[str, str]] = set()
    for dong in _muc("### 4.4. Các route").splitlines():
        if not dong.startswith("| `"):
            continue
        cho: list[str] = []      # phương thức đứng riêng, chờ gặp đường dẫn
        truoc: list[str] = []    # phương thức của đoạn có đường dẫn gần nhất
        for doan in re.findall(r"`([^`]+)`", dong.split("|")[1]):
            pt = re.findall(r"\b(GET|POST|PUT|DELETE)\b", doan)
            duong = re.findall(r"(/[A-Za-z0-9_\-{}./]+)", doan)
            if pt and not duong:
                cho += pt
            elif duong:
                dung = cho + pt if pt else truoc
                ra |= {(m, d) for m in dung for d in duong}
                if pt:
                    truoc = dung
                cho = []
    return ra


@pytest.fixture(scope="module")
def route_that():
    import os

    os.environ.setdefault("ENV", "LOCAL")
    from src.api.main import app

    return {
        (m, r.path)
        for r in app.routes
        if getattr(r, "methods", None) and r.path not in _ROUTE_TU_SINH
        for m in r.methods
        if m not in {"HEAD", "OPTIONS"}
    }


def test_chot_chong_xanh_suong_doc_du_route():
    assert len(_route_trong_srs()) >= 22, sorted(_route_trong_srs())


def test_moi_route_trong_srs_ton_tai_that(route_that):
    thieu = sorted(r for r in _route_trong_srs() if r not in route_that)
    assert not thieu, f"SRS §4.4 nêu route không có trong app: {thieu}"


def test_moi_route_nghiep_vu_co_trong_srs(route_that):
    thieu = sorted(r for r in route_that if r not in _route_trong_srs())
    assert not thieu, f"app có route mà SRS §4.4 chưa liệt kê: {thieu}"


def test_so_route_nghiep_vu_trong_srs_dung_voi_app(route_that):
    # SRS ghi "25 route nghiệp vụ"; một route có thể có nhiều phương thức nên đếm theo đường dẫn.
    so_duong_dan = len({p for _, p in route_that})
    m = re.search(r"(\d+) route nghiệp vụ", SRS)
    assert m, "SRS không còn câu nêu số route nghiệp vụ"
    so_muc = len(route_that)
    assert int(m.group(1)) in {so_duong_dan, so_muc}, (m.group(1), so_duong_dan, so_muc)


def test_module_va_file_nhac_trong_srs_ton_tai():
    ten = set(re.findall(r"`(src/(?:core|agents|api)/[A-Za-z0-9_/]+\.py)`", SRS))
    assert len(ten) >= 8, ten
    thieu = sorted(t for t in ten if not (ROOT / t).exists())
    assert not thieu, f"SRS nêu file không tồn tại: {thieu}"


def test_cac_module_core_trong_bang_4_5_co_that():
    bang = _muc("### 4.5. Các module `src/core/`")
    ten = set(re.findall(r"`([a-z0-9_]+)`", bang)) - {"src", "core"}
    so_that = {p.stem for p in (ROOT / "src" / "core").glob("*.py")}
    # chỉ kiểm các tên trông như module (có trong thư mục hoặc là từ đầu ô của bảng)
    dau_o = set(re.findall(r"^\| [^|]+ \| `([a-z0-9_]+)`", bang, re.M))
    dau_o |= set(re.findall(r", `([a-z0-9_]+)` \(", bang))
    ung_vien = {t for t in ten if t in so_that or t in dau_o}
    assert len(ung_vien & so_that) >= 30, sorted(ung_vien & so_that)
    chua_liet_ke = sorted(so_that - {"__init__"} - ten)
    assert not chua_liet_ke, f"module trong src/core chưa có trong SRS §4.5: {chua_liet_ke}"


def test_bien_moi_truong_o_phu_luc_a_duoc_code_doc_that():
    bang = SRS[SRS.index("## Phụ lục A"):SRS.index("## Phụ lục B")]
    ten = set(re.findall(r"`([A-Z][A-Z0-9_]{2,})`", bang))
    ten = {t for t in ten if not t.endswith("_")}          # bỏ mẫu `ANSER_TEXT_*`
    assert len(ten) >= 25, sorted(ten)
    ma = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "src").rglob("*.py"))
    thieu = sorted(t for t in ten if t not in ma)
    assert not thieu, f"Phụ lục A nêu biến mà src/ không nhắc tới: {thieu}"


def test_ma_yeu_cau_6_3_khong_trung_va_lien_tuc():
    ma = re.findall(r"^#### (BR-\d+)\.", SRS, re.M)
    assert len(ma) >= 12, ma
    assert len(ma) == len(set(ma)), "mã BR trùng trong §6.3"
    so = sorted(int(m.split("-")[1]) for m in ma)
    assert so == list(range(so[0], so[-1] + 1)), f"mã BR không liên tục: {so}"
