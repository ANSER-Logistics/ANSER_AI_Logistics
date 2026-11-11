"""
tests/test_database_url.py — `DATABASE_URL` có đặt mà không nhận ra thì KHÔNG được
lùi im lặng về SQLite in-memory.

Đo 12/11/2026, bản cũ chỉ nhận đúng hai tiền tố viết thường (`postgres://`,
`postgresql://`) và mọi dạng khác rơi xuống `sqlite:///:memory:` không một dòng log:

    postgresql+psycopg2://…   <- dạng CHÍNH hàm này sinh ra ở hai nhánh kia
    "  postgres://…"          <- khoảng trắng đầu dòng khi copy-dán
    POSTGRES://…              <- chữ hoa
    postgresql+asyncpg://…
    sqlite:///file.db

Brain chạy "khoẻ" trên một DB rỗng: lịch sử chat và báo cáo trống, `/health` không
nói gì. Đúng hình dạng "cấu hình sai mà trông như chạy" mà R5 muốn chặn.
"""

from __future__ import annotations

import logging

import pytest

from src.core import config as config_mod
from src.core.config import Config
from src.core.memory import MemoryManager

MAT_KHAU = "MAT-KHAU-BI-MAT-9f3a"


@pytest.fixture(autouse=True)
def _don_dep(monkeypatch):
    """Mỗi test bắt đầu từ trạng thái sạch: không DATABASE_URL, chưa báo lỗi lần nào."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # getattr: để chạy được cả trên mã cũ (chưa có biến này) và thấy các assert đỏ ĐÚNG LÝ DO.
    getattr(config_mod, "_DA_BAO_LOI_DB", set()).clear()
    yield
    getattr(config_mod, "_DA_BAO_LOI_DB", set()).clear()


def _cau_hinh(monkeypatch, url: str) -> Config:
    monkeypatch.setenv("DATABASE_URL", url)
    return Config()


@pytest.mark.parametrize(
    "url, mong_doi",
    [
        ("postgres://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        ("postgresql://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        # Dạng SQLAlchemy đầy đủ: giữ nguyên. Bản cũ làm rơi.
        ("postgresql+psycopg2://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        ("postgresql+asyncpg://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        # Khoảng trắng và chữ hoa là lỗi gõ/dán, không phải lỗi cấu hình.
        ("  postgres://u:p@h/db  ", "postgresql+psycopg2://u:p@h/db"),
        ("POSTGRES://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        ("PostgreSQL://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        # SQLite có chủ ý (file) được tôn trọng thay vì bị ghi đè bằng in-memory.
        ("sqlite:///dev.db", "sqlite:///dev.db"),
    ],
)
def test_dang_url_hop_le_duoc_nhan_ra(monkeypatch, url, mong_doi):
    c = _cau_hinh(monkeypatch, url)
    assert c.DB_URL == mong_doi
    assert c.DB_URL_LOI is None, "URL hợp lệ mà vẫn bị báo lỗi cấu hình"


def test_khong_dat_bien_la_che_do_dev_co_chu_y_khong_bao_loi():
    c = Config()
    assert c.DB_URL == "sqlite:///:memory:"
    assert c.DB_URL_LOI is None, "chưa đặt DATABASE_URL là dev có chủ ý — báo oan sẽ làm lần báo thật bị bỏ qua"


@pytest.mark.parametrize("url", ["mysql://u:p@h/db", "oracle://u:p@h/db", "http://x", "garbage"])
def test_dat_ma_khong_nhan_ra_thi_noi_ro_chu_khong_lui_im_lang(monkeypatch, url):
    c = _cau_hinh(monkeypatch, url)
    assert c.DB_URL == "sqlite:///:memory:"          # vẫn khởi động được (Config() dựng mỗi request)
    assert c.DB_URL_LOI and "DATABASE_URL" in c.DB_URL_LOI
    assert "RỖNG" in c.DB_URL_LOI, "phải nói hậu quả, không chỉ nói là không nhận ra"


def test_thong_bao_loi_khong_chua_mat_khau(monkeypatch, caplog):
    """URL có mật khẩu, và log cũng là nơi nó nằm lại (R2b)."""
    caplog.set_level(logging.ERROR, logger="projecta.config")
    c = _cau_hinh(monkeypatch, f"mysql://nguoi:{MAT_KHAU}@host/db")
    chu = (c.DB_URL_LOI or "") + " " + " ".join(r.getMessage() for r in caplog.records)
    assert MAT_KHAU not in chu and "nguoi" not in chu and "host" not in chu
    assert "mysql" in chu                                   # chỉ phần scheme


def test_thieu_scheme_khong_lo_phan_nao_cua_url(monkeypatch, caplog):
    """`user:pass@host/db` không có `://` — không được trích bất kỳ đoạn nào."""
    caplog.set_level(logging.ERROR, logger="projecta.config")
    c = _cau_hinh(monkeypatch, f"nguoi:{MAT_KHAU}@host/db")
    chu = (c.DB_URL_LOI or "") + " " + " ".join(r.getMessage() for r in caplog.records)
    assert MAT_KHAU not in chu and "nguoi" not in chu and "host" not in chu


def test_log_loi_cau_hinh_chi_mot_lan_du_Config_dung_moi_request(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger="projecta.config")
    monkeypatch.setenv("DATABASE_URL", "mysql://u:p@h/db")
    for _ in range(5):
        Config()
    assert len([r for r in caplog.records if r.name == "projecta.config"]) == 1


# ---------------------------------------------------------------------------
# Nối tới /health qua memory.kiem_luoc_do (main.py đã tính nó vào `degraded`)
# ---------------------------------------------------------------------------

def test_kiem_luoc_do_bao_loi_cau_hinh_thay_vi_bao_khoe(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://u:p@h/db")
    mem = MemoryManager()
    loi = mem.kiem_luoc_do()
    assert loi and "DATABASE_URL" in loi, (
        "DB_URL đã lùi về sqlite nên nhánh 'sqlite = dev' trả None — báo khoẻ trong khi cấu hình sai"
    )


def test_kiem_luoc_do_van_khong_bao_oan_khi_chua_dat_bien():
    assert MemoryManager().kiem_luoc_do() is None
