"""
tests/test_gio_viet_nam.py — mọi chỗ trong Brain cần "hôm nay" phải dùng giờ Việt Nam (BR-22).

VÌ SAO CÓ FILE NÀY
------------------
Container chạy UTC. Từ 00:00 đến 07:00 sáng ở Việt Nam, `date.today()` và `CURRENT_DATE` của DB
còn là HÔM QUA, nên báo cáo "hôm nay", ngày hiệu lực của bảng giá và ngày bơm vào prompt trích
yêu cầu báo giá lệch một ngày. `pricing` và ba workflow n8n đã sửa từ PR #54; file này canh bốn
chỗ còn lại và canh luôn việc không ai viết lại một định nghĩa thứ hai (R4).

Đồng hồ giả đặt MỘT chỗ (`utils._bay_gio_utc`), mọi nơi gọi `hom_nay_vn()` đều đọc qua đó.
Giờ chọn 20:00 UTC ngày 12/11 = 03:00 ngày 13/11 giờ Việt Nam: lúc UTC và Việt Nam khác ngày.
"""

from __future__ import annotations

import ast
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.core import pricing, saas_api, utils
from src.core.knowledge import KnowledgeBase
from src.core.prompts import Prompts
from tests.test_knowledge import FakeCollection, FakeEmbedder, FakeReranker

HAI_GIO_SANG_VN = datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc)   # 03:00 ngày 13/11 ở Việt Nam
HOM_NAY_VN = date(2026, 11, 13)
HOM_NAY_UTC = date(2026, 11, 12)


@pytest.fixture
def luc_ba_gio_sang_vn(monkeypatch):
    monkeypatch.setattr(utils, "_bay_gio_utc", lambda: HAI_GIO_SANG_VN)


def test_dinh_nghia_duy_nhat_tra_ngay_viet_nam(luc_ba_gio_sang_vn):
    assert utils.hom_nay_vn() == HOM_NAY_VN
    assert utils.hom_nay_vn() != HOM_NAY_UTC, "đồng hồ giả không tách được UTC khỏi giờ Việt Nam"


def test_ranh_gioi_17_gio_utc():
    assert utils.hom_nay_vn(datetime(2026, 11, 12, 16, 59, tzinfo=timezone.utc)) == date(2026, 11, 12)
    assert utils.hom_nay_vn(datetime(2026, 11, 12, 17, 0, tzinfo=timezone.utc)) == date(2026, 11, 13)


def test_pricing_dung_chung_mot_ham():
    """`pricing.hom_nay_vn` còn dùng được (test cũ gọi nó), và là CÙNG hàm, không phải bản chép."""
    assert pricing.hom_nay_vn is utils.hom_nay_vn


def test_prompt_trich_bao_gia_bom_ngay_viet_nam(luc_ba_gio_sang_vn):
    """Model chỉ đổi "ngày mai" ra YYYY-MM-DD đúng khi biết hôm nay là ngày nào."""
    out = Prompts.format_extraction_user("giao hàng ngày mai")
    assert "ngày 2026-11-13" in out
    assert "2026-11-12" not in out
    assert "thứ Sáu" in out      # 13/11/2026 là thứ Sáu


def test_prompt_trich_van_nhan_ngay_tuong_minh():
    """Dữ liệu fine-tune sinh bằng hàm này với ngày cố định: tham số `today` phải còn hiệu lực."""
    out = Prompts.format_extraction_user("x", today=date(2026, 1, 5))
    assert "ngày 2026-01-05" in out


def test_kho_tri_thuc_hieu_luc_theo_ngay_viet_nam(luc_ba_gio_sang_vn):
    """Bảng giá có hiệu lực từ 13/11: lúc 03:00 sáng 13/11 giờ Việt Nam nó đã phải là bảng đang dùng."""
    kb = KnowledgeBase(embedder=FakeEmbedder(), reranker=FakeReranker(), collection=FakeCollection())
    kb.add_document("khach", "BẢNG GIÁ MỚI\nHà Nội\tĐà Nẵng\t12.000.000\n", source="gia_moi.txt",
                    effective_from="2026-11-13")
    kq = kb.search("khach", "giá cước Hà Nội Đà Nẵng", top_k=5)
    assert [p.source for p in kq] == ["gia_moi.txt"], "dùng ngày UTC nên bảng giá có hiệu lực hôm nay bị loại"


def test_loc_ky_sql_dung_ngay_viet_nam(luc_ba_gio_sang_vn):
    for ky in ("today", "week", "month"):
        dk = saas_api._period_filter(ky)
        assert "2026-11-13" in dk, f"{ky}: {dk}"
        assert "2026-11-12" not in dk, f"{ky}: {dk}"
        assert "CURRENT_DATE" not in dk, f"{ky}: dùng ngày của phiên DB: {dk}"


def test_loc_ky_hom_nay_chay_duoc_tren_sqlite(luc_ba_gio_sang_vn):
    """Dev chạy SQLite: điều kiện 'today' phải là chuỗi ISO trần (`CAST(... AS date)` ra số 2026 trên SQLite)."""
    import sqlalchemy as sa

    eng = sa.create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE t (d TEXT)"))
        c.execute(sa.text("INSERT INTO t VALUES ('2026-11-13'), ('2026-11-12')"))
        dk = saas_api._period_filter("today").replace(saas_api.S_DATE, "d")
        n = c.execute(sa.text(f"SELECT COUNT(*) FROM t WHERE {dk}")).scalar()
    assert n == 1


# ---------------------------------------------------------------------------
# Không ai viết lại một định nghĩa thứ hai
# ---------------------------------------------------------------------------

_SRC = Path(__file__).resolve().parent.parent / "src"


def _mã_không_docstring(tree: ast.AST):
    """Mọi nút trừ chuỗi docstring (docstring được phép NÓI về `date.today()`)."""
    doc = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = n.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant):
                doc.add(id(b[0].value))
    for n in ast.walk(tree):
        if id(n) not in doc:
            yield n


def test_khong_con_date_today_hay_current_date_trong_ma():
    """Nghiệm thu BR-22: không `date.today()`, không `CURRENT_DATE` trong chuỗi SQL, ngoài định nghĩa."""
    files = sorted(_SRC.rglob("*.py"))
    assert len(files) > 30, "không quét được file nào — test này sẽ xanh giả"
    loi = []
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in _mã_không_docstring(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "today"):
                loi.append(f"{f.relative_to(_SRC)}:{n.lineno} gọi .today()")
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and "CURRENT_DATE" in n.value:
                loi.append(f"{f.relative_to(_SRC)}:{n.lineno} chuỗi chứa CURRENT_DATE")
    assert not loi, "dùng múi giờ của máy/DB thay vì `utils.hom_nay_vn()`:\n  " + "\n  ".join(loi)
