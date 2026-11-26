"""
tests/test_giu_tep_trong_ram_219.py — tệp tải lên tới các route hứa "KHÔNG ghi ra đĩa" thật sự không tạo tệp tạm (#219, R2).

Đếm mọi lần `tempfile` tạo tệp trên đĩa (`TemporaryFile`, `NamedTemporaryFile`, `mkstemp`; `SpooledTemporaryFile.rollover` đi qua
`TemporaryFile`) trong lúc xử lý request. Có ca đối chứng: hạ ngưỡng về 1 MiB như mặc định của Starlette thì bộ đếm PHẢI thấy tệp tạm,
nên phép đo không câm. Dữ liệu là byte ngẫu nhiên (hư cấu).
"""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from starlette.formparsers import MultiPartParser

from src.api import giu_tep_trong_ram
from src.api.gioi_han_than import TRAN_THAN_MAC_DINH
from src.api.main import app
from src.api.routes import knowledge
from src.core.config import MAX_UPLOAD_BYTES

client = TestClient(app, raise_server_exceptions=False)

# Sát trần tệp: chừa 64 KiB cho phần bao multipart để không chạm trần 413 của handler.
SAT_TRAN = MAX_UPLOAD_BYTES - 64 * 1024

ROUTE_KHONG_GHI_DIA = [
    ("/tools/inventory-import", {}),
    ("/tools/partner-import", {}),
    ("/tools/product-import", {}),
    ("/knowledge/documents", {"workspace_id": "khach-hu-cau"}),
]


@pytest.fixture
def dem_tep_tam(monkeypatch):
    """Số tệp tạm trên đĩa được tạo kể từ lúc fixture bắt đầu."""
    dem = {"n": 0}
    for ten in ("TemporaryFile", "NamedTemporaryFile", "mkstemp"):
        goc = getattr(tempfile, ten)

        def boc(*a, _goc=goc, **k):
            dem["n"] += 1
            return _goc(*a, **k)

        monkeypatch.setattr(tempfile, ten, boc)
    return dem


@pytest.fixture(autouse=True)
def _kb_khong_nap_model(monkeypatch):
    """Dừng /knowledge/documents ngay sau `file.read()`: phép đo là bước phân tích multipart, không cần model embedding."""
    def dung(*a, **k):
        raise ValueError("dừng sau khi đọc tệp")

    monkeypatch.setattr(knowledge.doc_extract, "extract", dung)


def _gui(path: str, form: dict, so_byte: int):
    return client.post(path, files={"file": ("tep_hu_cau.xlsx", os.urandom(so_byte))}, data=form)


@pytest.mark.parametrize("path,form", ROUTE_KHONG_GHI_DIA, ids=[p for p, _ in ROUTE_KHONG_GHI_DIA])
@pytest.mark.parametrize("so_byte", [2 * 1024 * 1024, SAT_TRAN], ids=["2MB", "sat-tran"])
def test_tep_lon_hon_1mb_khong_tao_tep_tam(dem_tep_tam, path, form, so_byte):
    r = _gui(path, form, so_byte)
    # Handler đã đọc tệp (422 vì byte ngẫu nhiên không phải .xlsx, hoặc vì bước bóc chữ bị dừng), không bị từ chối ở trần.
    assert r.status_code == 422, (r.status_code, r.text[:200])
    assert dem_tep_tam["n"] == 0, f"{path}: tệp {so_byte} byte tạo {dem_tep_tam['n']} tệp tạm trên đĩa"


def test_doi_chung_nguong_mac_dinh_cua_starlette_thi_co_tep_tam(dem_tep_tam, monkeypatch):
    """Chứng minh bộ đếm không câm: đúng ngưỡng 1 MiB cũ thì tệp 2 MB PHẢI chạm đĩa (đây là lỗi #219 trước khi sửa)."""
    monkeypatch.setattr(MultiPartParser, "spool_max_size", 1024 * 1024)
    _gui("/tools/inventory-import", {}, 2 * 1024 * 1024)
    assert dem_tep_tam["n"] >= 1


def test_nguong_giu_trong_ram_bang_tran_than_request():
    """Một phần tệp không thể lớn hơn trần thân (middleware cắt trước), nên ngưỡng >= trần là đủ để không bao giờ tràn ra đĩa."""
    assert MultiPartParser.spool_max_size >= TRAN_THAN_MAC_DINH


def test_khong_ha_nguong_da_cao_hon(monkeypatch):
    monkeypatch.setattr(MultiPartParser, "spool_max_size", TRAN_THAN_MAC_DINH * 2)
    giu_tep_trong_ram.giu_trong_ram()
    assert MultiPartParser.spool_max_size == TRAN_THAN_MAC_DINH * 2


def test_nang_nguong_thap(monkeypatch):
    monkeypatch.setattr(MultiPartParser, "spool_max_size", 1024 * 1024)
    giu_tep_trong_ram.giu_trong_ram()
    assert MultiPartParser.spool_max_size == TRAN_THAN_MAC_DINH


def test_starlette_khong_co_ca_hai_thuoc_tinh_thi_dung_khong_lang_le(monkeypatch):
    """Không thấy thuộc tính ngưỡng nào: không biết tệp có chạm đĩa không, nên phải ném lỗi chứ không chạy tiếp."""
    monkeypatch.delattr(MultiPartParser, "spool_max_size")
    assert not hasattr(MultiPartParser, "max_file_size")
    with pytest.raises(RuntimeError, match="spool_max_size.*max_file_size"):
        giu_tep_trong_ram.giu_trong_ram()


# --- Starlette 0.27–0.45 gọi ngưỡng là `max_file_size` (review của Minh trên PR #279) ----------------------------------
# FastAPI 0.115.8 + Starlette 0.45.3 thoả `fastapi<1`. CI cài bản mới, nên giả lập lớp parser cũ bằng cách đổi tên thuộc tính.


@pytest.fixture
def parser_starlette_cu(monkeypatch):
    """MultiPartParser kiểu 0.45.3: có `max_file_size` = 1 MiB, không có `spool_max_size`."""
    monkeypatch.delattr(MultiPartParser, "spool_max_size")
    monkeypatch.setattr(MultiPartParser, "max_file_size", 1024 * 1024, raising=False)


def test_starlette_cu_nang_max_file_size(parser_starlette_cu):
    assert giu_tep_trong_ram.giu_trong_ram() == "max_file_size"
    assert MultiPartParser.max_file_size == TRAN_THAN_MAC_DINH
    assert not hasattr(MultiPartParser, "spool_max_size")


def test_starlette_cu_khong_ha_nguong_da_cao_hon(parser_starlette_cu, monkeypatch):
    monkeypatch.setattr(MultiPartParser, "max_file_size", TRAN_THAN_MAC_DINH * 2)
    giu_tep_trong_ram.giu_trong_ram()
    assert MultiPartParser.max_file_size == TRAN_THAN_MAC_DINH * 2


def test_starlette_moi_dung_spool_max_size():
    assert giu_tep_trong_ram.giu_trong_ram() == "spool_max_size"


def test_co_ca_hai_ten_thi_uu_tien_ten_moi(monkeypatch):
    """Bản nào đó có cả hai: `spool_max_size` mới là cái đặt cỡ bản đệm, `max_file_size` có thể mang nghĩa khác."""
    monkeypatch.setattr(MultiPartParser, "spool_max_size", 1024 * 1024)
    monkeypatch.setattr(MultiPartParser, "max_file_size", 7, raising=False)
    assert giu_tep_trong_ram.giu_trong_ram() == "spool_max_size"
    assert MultiPartParser.spool_max_size == TRAN_THAN_MAC_DINH
    assert MultiPartParser.max_file_size == 7


@pytest.mark.parametrize("gia_tri", [None, True, "1048576", 1.5])
def test_thuoc_tinh_sai_kieu_thi_dung(monkeypatch, gia_tri):
    monkeypatch.setattr(MultiPartParser, "spool_max_size", gia_tri)
    with pytest.raises(RuntimeError):
        giu_tep_trong_ram.giu_trong_ram()
