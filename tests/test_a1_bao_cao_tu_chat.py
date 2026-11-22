"""
tests/test_a1_bao_cao_tu_chat.py — câu "báo cáo quý này" qua /chat phải ra số của `reporting.build_report` (KH90 A1, brain#321).

VÌ SAO CÓ FILE NÀY
------------------
`chat._fetch_report_lines` chờ sẵn `saas.get_report_lines` từ lâu mà hàm đó chưa tồn tại, nên nhánh REPORT luôn trả "chưa nối được". Giờ hàm có, mà nó đứng
ngay trước một con số tiền: chỗ nào sai (mất dòng của sản phẩm đã xoá, giá vốn trống bị coi là 0, ngày lệch múi giờ, kho khác lọt vào) đều ra báo cáo
nghe hợp lý mà sai. Mỗi test dưới đây khoá đúng một chỗ như vậy.

GIỚI HẠN: bảng SQLite dựng từ chính khối SCHEMA MAP, nên test chỉ chứng minh SQL khớp hằng số; hằng số khớp Body thật hay không do
`tests/test_doi_chieu_schema_body*` và `offline_training/doi_chieu_hop_dong_body.py` canh (đã đối chiếu `schema.ts` ngày 22/11/2026).
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from src.api import dependencies as deps
from src.api.main import app
from src.api.routes import chat as chat_mod
from src.core import reporting as rp
from src.core import saas_api, utils
from src.core.saas_api import (
    P_COST,
    P_NAME,
    P_PRICE,
    P_STOCK,
    P_WAREHOUSE,
    PRODUCTS_TABLE,
    S_DATE,
    S_WAREHOUSE,
    SALE_ITEMS_TABLE,
    SALES_TABLE,
    SaasAPI,
    _dau_ky_bao_cao,
)
from tests.test_chat_routing import moi_truong  # noqa: F401  (moi_truong là fixture)

client = TestClient(app)
AI = {"X-User-Id": "1", "X-Store-Id": "1"}

# 12:00 ngày 22/11/2026 giờ Việt Nam. Quý hiện tại là Q4, nên báo cáo lấy từ 01/01/2026 (đủ bốn quý, Q1 đến Q4).
BAY_GIO = datetime(2026, 11, 22, 5, 0, tzinfo=timezone.utc)
TU_NGAY = date(2026, 1, 1)


@pytest.fixture(autouse=True)
def _gio_co_dinh(monkeypatch):
    monkeypatch.setattr(utils, "_bay_gio_utc", lambda: BAY_GIO)


def _engine_trong():
    """SQLite trong bộ nhớ, MỘT kết nối dùng chung: truy vấn chạy ở luồng khác (`chay_ngoai_loop`) vẫn thấy cùng cơ sở dữ liệu."""
    return create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})


def _dung_db(hoa_don, dong, san_pham):
    engine = _engine_trong()
    with engine.begin() as conn:
        conn.execute(text(
            f"CREATE TABLE {PRODUCTS_TABLE} (id INTEGER PRIMARY KEY, {P_NAME} TEXT, {P_PRICE} REAL, {P_STOCK} REAL, "
            f"{P_WAREHOUSE} INTEGER, {P_COST} INTEGER)"))
        conn.execute(text(
            f"CREATE TABLE {SALES_TABLE} (id INTEGER PRIMARY KEY, total INTEGER, {S_DATE} TEXT, {S_WAREHOUSE} INTEGER)"))
        conn.execute(text(
            f"CREATE TABLE {SALE_ITEMS_TABLE} (id INTEGER PRIMARY KEY, invoice_id INTEGER, product_id INTEGER, "
            f"product_name TEXT, quantity REAL, unit_cost INTEGER, line_total INTEGER)"))
        for p in san_pham:
            conn.execute(text(f"INSERT INTO {PRODUCTS_TABLE} (id, {P_NAME}, {P_WAREHOUSE}, {P_COST}) VALUES (:i, :n, :w, :c)"),
                         {"i": p[0], "n": p[1], "w": p[2], "c": p[3]})
        for h in hoa_don:
            conn.execute(text(f"INSERT INTO {SALES_TABLE} (id, total, {S_DATE}, {S_WAREHOUSE}) VALUES (:i, 0, :d, :w)"),
                         {"i": h[0], "d": h[1], "w": h[2]})
        for d in dong:
            conn.execute(text(
                f"INSERT INTO {SALE_ITEMS_TABLE} (invoice_id, product_id, product_name, quantity, unit_cost, line_total) "
                f"VALUES (:h, :p, :n, :q, :c, :t)"), {"h": d[0], "p": d[1], "n": d[2], "q": d[3], "c": d[4], "t": d[5]})
    return engine


def _saas(engine) -> SaasAPI:
    s = SaasAPI.__new__(SaasAPI)
    s.engine = engine
    return s


# Kho 1 là khách đang hỏi. Từng dòng nhắm vào một chỗ dễ sai (xem cột cuối).
SAN_PHAM = [
    (1, "Dầu CF-4", 1, 40_000),
    (2, "Mỡ bò", 1, None),
    (3, "Hàng của khách khác", 2, 1),
]
HOA_DON = [
    (1, "2026-11-10T03:00:00+00:00", 1),
    (2, "2026-09-30T19:00:00+00:00", 1),   # 02:00 ngày 01/10 giờ VN: thuộc Q4, không phải Q3
    (3, "2026-11-10T03:00:00+00:00", 2),   # kho khác
    (4, "2026-11-11T03:00:00+00:00", None),   # hoá đơn cũ chưa có warehouse_id: tính theo kho của sản phẩm
    (5, "2025-12-31T16:59:00+00:00", 1),   # 23:59 ngày 31/12/2025 giờ VN: ngoài cửa sổ
    (6, "2025-12-31T17:00:00+00:00", 1),   # 00:00 ngày 01/01/2026 giờ VN: trong cửa sổ, Q1
    (7, "2026-02-01T03:00:00+00:00", 1),
]
DONG = [
    (1, 1, "Dầu CF-4", 2.5, 50_000, 300_000),       # giá vốn lúc bán thắng giá vốn hiện tại
    (1, 2, "Mỡ bò", 1, None, 100_000),              # cả hai giá vốn trống: None, không phải 0
    (2, 1, "Dầu CF-4", 1, None, 80_000),            # rơi về giá vốn hiện tại của sản phẩm
    (3, 3, "Hàng của khách khác", 1, None, 999_999),
    (4, 1, "Dầu CF-4", 2, None, 150_000),
    (5, 1, "Dầu CF-4", 1, None, 7_777),
    (6, 1, "Dầu CF-4", 1, 1_000, 55_555),
    (7, None, "Hàng đã xoá", 3, None, 90_000),      # sản phẩm đã xoá: dòng vẫn phải có
]
MONG_DOI = [
    {"date": "2026-01-01", "revenue": 55_555.0, "product": "Dầu CF-4", "quantity": 1.0, "cogs": 1_000.0},
    {"date": "2026-02-01", "revenue": 90_000.0, "product": "Hàng đã xoá", "quantity": 3.0, "cogs": None},
    {"date": "2026-10-01", "revenue": 80_000.0, "product": "Dầu CF-4", "quantity": 1.0, "cogs": 40_000.0},
    {"date": "2026-11-10", "revenue": 300_000.0, "product": "Dầu CF-4", "quantity": 2.5, "cogs": 125_000.0},
    {"date": "2026-11-10", "revenue": 100_000.0, "product": "Mỡ bò", "quantity": 1.0, "cogs": None},
    {"date": "2026-11-11", "revenue": 150_000.0, "product": "Dầu CF-4", "quantity": 2.0, "cogs": 80_000.0},
]


def _khoa(d):
    return (d["date"], d["product"], d["revenue"])


# ---------------------------------------------------------------------------
# get_report_lines
# ---------------------------------------------------------------------------

def test_dong_ban_dung_tung_truong_hop_de_sai():
    ra = _saas(_dung_db(HOA_DON, DONG, SAN_PHAM)).get_report_lines(workspace_id=1)
    assert sorted(ra["sales"], key=_khoa) == sorted(MONG_DOI, key=_khoa)
    assert ra["expenses"] == [], "chưa có bảng chi phí bên Body (Body#23): để trống, engine sẽ cảnh báo"


def test_gia_von_trong_la_none_khong_bao_gio_la_khong():
    ra = _saas(_dung_db(HOA_DON, DONG, SAN_PHAM)).get_report_lines(workspace_id=1)
    cogs = {d["product"]: d["cogs"] for d in ra["sales"] if d["product"] in ("Mỡ bò", "Hàng đã xoá")}
    assert cogs == {"Mỡ bò": None, "Hàng đã xoá": None}
    assert all(d["cogs"] != 0 for d in ra["sales"]), "giá vốn 0 làm lãi gộp bằng doanh thu"


def test_khach_khac_khong_lot_vao():
    ra = _saas(_dung_db(HOA_DON, DONG, SAN_PHAM)).get_report_lines(workspace_id=2)
    assert [d["revenue"] for d in ra["sales"]] == [999_999.0]


def test_cua_so_tinh_theo_gio_viet_nam_khong_theo_utc():
    ra = _saas(_dung_db(HOA_DON, DONG, SAN_PHAM)).get_report_lines(workspace_id=1)
    ngay = [d["date"] for d in ra["sales"]]
    assert "2026-01-01" in ngay, "00:00 ngày 01/01 giờ VN là 17:00 ngày 31/12 UTC: phải nằm trong cửa sổ"
    assert not any(n < TU_NGAY.isoformat() for n in ngay), "23:59 ngày 31/12 giờ VN phải nằm ngoài"
    assert "2026-10-01" in ngay and "2026-09-30" not in ngay, "02:00 ngày 01/10 giờ VN thuộc Q4"


@pytest.mark.parametrize("hom_nay,so_quy,ky_vong", [
    (date(2026, 11, 22), 4, date(2026, 1, 1)),
    (date(2026, 1, 1), 4, date(2025, 4, 1)),
    (date(2026, 3, 31), 1, date(2026, 1, 1)),
    (date(2026, 4, 1), 2, date(2026, 1, 1)),
    (date(2026, 12, 31), 4, date(2026, 1, 1)),
    (date(2026, 2, 15), 5, date(2025, 1, 1)),
])
def test_dau_ky_bao_cao_lay_tron_quy(hom_nay, so_quy, ky_vong):
    assert _dau_ky_bao_cao(hom_nay, so_quy) == ky_vong


def test_loi_db_duoc_nem_len_chu_khong_tra_danh_sach_rong():
    engine = create_engine("sqlite://")            # không có bảng nào
    with pytest.raises(Exception) as e:
        _saas(engine).get_report_lines(workspace_id=1)
    assert "sales_invoice" in str(e.value) or "no such table" in str(e.value)


def test_vuot_tran_so_dong_thi_bao_loi_khong_cat_im_lang(monkeypatch):
    monkeypatch.setattr(saas_api, "DONG_TOI_DA", 2)
    with pytest.raises(RuntimeError):
        _saas(_dung_db(HOA_DON, DONG, SAN_PHAM)).get_report_lines(workspace_id=1)


@pytest.mark.parametrize("so_quy", [0, -1, 41, 2.5, True, "4"])
def test_so_quy_vo_ly_bi_tu_choi(so_quy):
    with pytest.raises(ValueError):
        _saas(_dung_db([], [], [])).get_report_lines(workspace_id=1, so_quy=so_quy)


def test_ngay_hoa_don_dang_chuoi_cua_sqlite_cung_doc_duoc():
    hd = [(1, "2026-11-10 03:00:00", 1)]
    dong = [(1, 1, "Dầu CF-4", 1, 1_000, 5_000)]
    ra = _saas(_dung_db(hd, dong, SAN_PHAM)).get_report_lines(workspace_id=1)
    assert [d["date"] for d in ra["sales"]] == ["2026-11-10"]


# ---------------------------------------------------------------------------
# Qua /chat: nhánh REPORT
# ---------------------------------------------------------------------------

class _SaasThat:
    """Bọc `SaasAPI` thật trên SQLite; ghi lại luồng đã chạy truy vấn."""

    def __init__(self, engine):
        self._that = _saas(engine)
        self.luong = []

    def get_report_lines(self, workspace_id=1):
        self.luong.append(threading.get_ident())
        return self._that.get_report_lines(workspace_id=workspace_id)


def _hoi_report(cau="báo cáo lợi nhuận quý này"):
    resp = client.post("/chat", headers=AI, json={"user_id": 1, "store_id": 1, "message": cau})
    assert resp.status_code == 200
    kq = client.get(f"/api/v1/task/{resp.json()['task_id']}", headers=AI).json()
    assert kq["status"] == "completed", kq
    return kq["result"]["answer"]


def _gan_manager(moi_truong, monkeypatch):  # noqa: F811
    """
    Câu có kế hoạch tool (`report`) đi vào VÒNG AGENTIC chứ không vào nhánh `cat == "REPORT"` trơn
    (xem `tool_planner.vao_vong_agentic`), nên dựng đúng đường đó: lượt 1 model gọi `report`, lượt 2 kết luận.
    Ghi lại lời gọi tool thật (đối số do mã bơm vào, kết quả do engine tính). Câu trả lời không chứa con số nào,
    để khỏi phụ thuộc chốt chặn neo số.
    """
    from src.api.routes import tools as tools_mod

    moi_truong.category = "REPORT"
    moi_truong.decisions = [
        {"thought": "cần số liệu", "tool": "report", "arguments": {}},
        {"thought": "đủ số liệu", "answer": "Đây là báo cáo theo số liệu bên dưới."},
    ]
    goi = []
    goc = tools_mod.run_tool

    async def run_tool(ten, args, *a, **k):
        kq = await goc(ten, args, *a, **k)
        goi.append((ten, args, kq))
        return kq

    monkeypatch.setattr(tools_mod, "run_tool", run_tool)
    monkeypatch.setattr(deps.runtime, "kb", None, raising=False)
    return goi


def test_chat_bao_cao_ra_dung_so_cua_engine_tat_dinh(moi_truong, monkeypatch):  # noqa: F811
    goi = _gan_manager(moi_truong, monkeypatch)
    saas = _SaasThat(_dung_db(HOA_DON, DONG, SAN_PHAM))
    monkeypatch.setattr(chat_mod, "_get_saas", lambda: saas)

    tra_loi = _hoi_report()

    assert tra_loi == "Đây là báo cáo theo số liệu bên dưới."
    assert [g[0] for g in goi] == ["report"]
    _, args, ket_qua = goi[0]
    # Đối số do MÃ bơm từ DB (model điền `{}`), và khớp từng dòng với kỳ vọng.
    assert sorted(args["sales"], key=_khoa) == sorted(MONG_DOI, key=_khoa)
    ky_vong = rp.build_report(rp.ReportRequest(sales=[rp.SaleLine(**s) for s in MONG_DOI], expenses=[]))
    ra = json.loads(json.dumps(ket_qua, ensure_ascii=False, default=str))
    for khoa in ("granularity", "periods", "products", "explain", "warnings"):
        assert ra[khoa] == json.loads(json.dumps(ky_vong[khoa], ensure_ascii=False)), khoa
    q4 = next(k for k in ra["periods"] if k["period"] == "2026-Q4")
    assert q4["revenue"] == 300_000 + 100_000 + 80_000 + 150_000
    assert saas.luong and all(t != threading.get_ident() for t in saas.luong), "truy vấn DB phải chạy ngoài event loop"


def test_chat_bao_cao_giu_gia_von_thieu_la_thieu_khong_phai_khong(moi_truong, monkeypatch):  # noqa: F811
    goi = _gan_manager(moi_truong, monkeypatch)
    monkeypatch.setattr(chat_mod, "_get_saas", lambda: _SaasThat(_dung_db(HOA_DON, DONG, SAN_PHAM)))
    _hoi_report()
    ra = goi[0][2]
    # 190.000 trong 775.555 đồng doanh thu không có giá vốn (Mỡ bò, hàng đã xoá): engine phải nói thiếu.
    assert ra["explain"]["cogs_coverage_pct"] is not None and ra["explain"]["cogs_coverage_pct"] < 100
    q4 = next(k for k in ra["periods"] if k["period"] == "2026-Q4")
    assert q4["cogs_coverage_pct"] < 100, "giá vốn của Mỡ bò chưa biết: không được tính vào lãi gộp như số 0"
    assert ra["warnings"], "thiếu giá vốn và chưa có chi phí thì phải có cảnh báo"


def test_chat_bao_cao_db_hong_thi_noi_chua_lay_duoc_khong_chay_tool(moi_truong, monkeypatch):  # noqa: F811
    goi = _gan_manager(moi_truong, monkeypatch)
    monkeypatch.setattr(chat_mod, "_get_saas", lambda: _SaasThat(_engine_trong()))
    tra_loi = _hoi_report()
    assert "chưa lấy được số liệu" in tra_loi
    assert goi == [], "không có dữ liệu thì không được chạy tool trên số rỗng"


def test_chat_bao_cao_khong_co_dong_nao_thi_noi_chua_co(moi_truong, monkeypatch):  # noqa: F811
    goi = _gan_manager(moi_truong, monkeypatch)
    monkeypatch.setattr(chat_mod, "_get_saas", lambda: _SaasThat(_dung_db([], [], SAN_PHAM)))
    tra_loi = _hoi_report()
    assert "Chưa có dòng bán hàng" in tra_loi
    assert goi == []
