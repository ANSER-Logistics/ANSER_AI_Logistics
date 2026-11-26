"""
tests/integration/chat/test_a3_tra_hang_theo_tu_khoa.py — câu hỏi tự nhiên về hàng hoá phải tìm ra đúng hàng (KH90 A3, brain#323).

VÌ SAO CÓ FILE NÀY
------------------
`lookup_product` từng đưa NGUYÊN câu hỏi vào `LIKE '%câu hỏi%'`, nên "còn bao nhiêu thùng dầu động cơ CF-4 15W40" không khớp tên hàng nào (tên hàng không chứa nguyên
câu), và gõ "thuy luc" không thấy "thuỷ lực". Nhánh DATA_INTERNAL vì thế gần như luôn trả "không tìm thấy" cho câu người thật hỏi.

GIỚI HẠN CỦA BỘ ĐO (đọc trước khi tin con số): danh mục và hai mươi câu dưới đây do chính người viết luật (agent) bịa ra, theo kiểu khách pilot (phân phối dầu nhớt), KHÔNG có dữ
liệu khách thật. Người viết luật cũng là người viết câu hỏi nên con số 18/20 là cận trên lạc quan; con số đáng tin hơn là kết quả chạy chế độ bóng trên câu hỏi thật (A6, #208).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from src.api import dependencies as deps
from src.api.main import app
from src.api.routes import chat as chat_mod
from src.core import saas_api
from src.core.saas_api import (
    P_NAME,
    P_PRICE,
    P_STOCK,
    P_WAREHOUSE,
    PRODUCTS_TABLE,
    S_DATE,
    S_WAREHOUSE,
    SALES_TABLE,
    SaasAPI,
    diem_khop_hang,
    tu_khoa_tim_hang,
)

client = TestClient(app)

DANH_MUC = {
    1: "Dầu động cơ CF-4 15W40 thùng 18 lít",
    2: "Dầu động cơ CI-4 20W50 phuy 209 lít",
    3: "Dầu thuỷ lực AW46 thùng 18 lít",
    4: "Dầu thuỷ lực AW68 phuy 209 lít",
    5: "Mỡ bò EP2 xô 15kg",
    6: "Mỡ chịu nhiệt EP3 xô 15kg",
    7: "Dầu hộp số 80W90 can 5 lít",
    8: "Dầu nhớt xe máy 4T 10W40 chai 1 lít",
    9: "Nước làm mát xanh can 4 lít",
    10: "Dầu phanh DOT 4 chai 500ml",
    11: "Dầu cầu 85W140 can 5 lít",
    12: "Dầu máy nén khí VG100 thùng 18 lít",
    13: "Dầu biến thế 25 thùng 20 lít",
    14: "Nhớt tổng hợp 5W30 chai 4 lít",
    15: "Mỡ bôi trơn đa dụng NLGI2 hộp 1kg",
}
KHO_KHAC = {101: "Dầu động cơ CF-4 15W40 thùng 18 lít"}      # cùng tên, khách khác: không được lọt vào

# (câu hỏi, các id PHẢI có trong kết quả, số hàng tối đa được trả). Rỗng = phải trả "không tìm thấy".
HAI_MUOI_CAU = [
    ("còn bao nhiêu thùng dầu động cơ CF-4 15W40?", {1}, 3),
    ("giá dầu thủy lực AW46 là bao nhiêu", {3}, 3),
    ("cho mình hỏi dầu thuy luc aw 68 con hang khong", {4}, 3),
    ("mỡ bò EP2 tồn bao nhiêu xô", {5}, 3),
    ("tồn kho mỡ chịu nhiệt EP3", {6}, 3),
    ("dầu hộp số 80W90 giá sao", {7}, 3),
    ("có nhớt xe máy 10W40 không", {8}, 3),
    ("nước làm mát còn không", {9}, 3),
    ("dầu phanh DOT4 giá bao nhiêu", {10}, 3),
    ("dầu cầu 85W140 còn mấy can", {11}, 3),
    ("giá dầu máy nén khí VG100", {12}, 3),
    ("dầu biến thế 25 có không", {13}, 3),
    ("nhớt tổng hợp 5W30 bao nhiêu 1 chai", {14}, 3),
    ("mỡ đa dụng NLGI2", {15}, 3),
    ("kiểm tra giúp tôi tồn kho dầu động cơ CI-4", {2}, 3),
    ("phuy dầu thủy lực 68 giá bao nhiêu", {4}, 4),
    ("mình cần biết giá và tồn của dầu động cơ", {1, 2}, 4),
    ("anh ơi bên mình có bán dầu hộp số không", {7}, 4),
    ("lốp xe tải còn không", set(), 0),
    ("doanh số tháng này thế nào", set(), 0),
]


def _engine(danh_muc, kho_khac=None):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text(
            f"CREATE TABLE {PRODUCTS_TABLE} (id INTEGER PRIMARY KEY, {P_NAME} TEXT, {P_PRICE} REAL, {P_STOCK} REAL, {P_WAREHOUSE} INTEGER)"))
        conn.execute(text(
            f"CREATE TABLE {SALES_TABLE} (id INTEGER PRIMARY KEY, total INTEGER, {S_DATE} TEXT, {S_WAREHOUSE} INTEGER)"))
        for i, ten in danh_muc.items():
            conn.execute(text(f"INSERT INTO {PRODUCTS_TABLE} (id, {P_NAME}, {P_PRICE}, {P_STOCK}, {P_WAREHOUSE}) VALUES (:i, :n, :g, :t, 1)"),
                         {"i": i, "n": ten, "g": 1_000_000 + i, "t": 10 + i})
        for i, ten in (kho_khac or {}).items():
            conn.execute(text(f"INSERT INTO {PRODUCTS_TABLE} (id, {P_NAME}, {P_PRICE}, {P_STOCK}, {P_WAREHOUSE}) VALUES (:i, :n, 9999999, 5, 2)"),
                         {"i": i, "n": ten})
    return engine


def _saas(engine) -> SaasAPI:
    s = SaasAPI.__new__(SaasAPI)
    s.engine = engine
    return s


def _tra(saas, cau):
    """(danh sách id, thông báo). Đúng một trong hai."""
    kq = saas.lookup_product(cau, workspace_id=1)
    try:
        return [h["id"] for h in json.loads(kq)], None
    except ValueError:
        return [], kq


@pytest.fixture
def saas():
    return _saas(_engine(DANH_MUC, KHO_KHAC))


# ---------------------------------------------------------------------------
# Bộ hai mươi câu
# ---------------------------------------------------------------------------

def _dung(saas, cau, can, toi_da):
    ids, thong_bao = _tra(saas, cau)
    if not can:
        return not ids and thong_bao is not None
    return can <= set(ids) and len(ids) <= toi_da


def test_hai_muoi_cau_tu_nhien_tim_dung_it_nhat_muc_nghiem_thu(saas):
    """Nghiệm thu A3: tìm đúng ít nhất 18/20. In từng câu sai để biết sửa chỗ nào, không chỉ con số."""
    sai = [(c, _tra(saas, c)[0]) for c, can, toi_da in HAI_MUOI_CAU if not _dung(saas, c, can, toi_da)]
    dung = len(HAI_MUOI_CAU) - len(sai)
    assert dung >= 18, f"{dung}/20; sai: {sai}"


@pytest.mark.parametrize("cau,can,toi_da", HAI_MUOI_CAU, ids=[c for c, _, _ in HAI_MUOI_CAU])
def test_tung_cau(saas, cau, can, toi_da):
    """Mỗi câu một test để thấy rõ câu nào còn sai. Hiện mong đợi đúng cả 20; hạ ngưỡng ở test tổng, không ở đây."""
    assert _dung(saas, cau, can, toi_da), (cau, _tra(saas, cau))


def test_khach_khac_khong_lot_vao(saas):
    ids, _ = _tra(saas, "dầu động cơ CF-4 15W40")
    assert 101 not in ids and 1 in ids


# ---------------------------------------------------------------------------
# Từ khoá và độ phủ
# ---------------------------------------------------------------------------

def test_cau_chi_hoi_doanh_so_khong_co_tu_khoa_hang():
    assert not tu_khoa_tim_hang("doanh số tháng này thế nào")
    assert not tu_khoa_tim_hang("còn hàng không")


def test_ma_hang_noi_lien_ke_ca_khi_viet_tach_hoac_gach_noi():
    for cau in ("CF-4", "cf 4", "CF4"):
        assert "cf4" in tu_khoa_tim_hang(cau).hien_thi(), cau
    assert "aw68" in tu_khoa_tim_hang("AW 68").hien_thi()
    assert "dot4" in tu_khoa_tim_hang("DOT 4").hien_thi()


def test_khong_noi_qua_tu_thua():
    """"dầu 68 giá cf 4": hai từ thừa ở giữa không được tạo ra mã nối rác như "68cf" làm tụt độ phủ."""
    assert set(tu_khoa_tim_hang("68 gia cf 4").noi) == {"cf4"}
    assert not tu_khoa_tim_hang("aw 68 con hang").noi.keys() - {"aw68"}


def test_ma_noi_khong_khop_thi_khong_bi_tru_diem():
    """"dầu 18 lít" sinh mã nối "dau18"; tên hàng "Dầu động cơ 18 lít" không có mã đó nhưng vẫn phải khớp trọn."""
    assert diem_khop_hang(tu_khoa_tim_hang("dầu 18 lít"), "Dầu động cơ thùng 18 lít") == 1.0


def test_bo_dau_hai_chieu():
    assert diem_khop_hang(tu_khoa_tim_hang("thuy luc"), "Dầu thuỷ lực AW46") > 0.9
    assert diem_khop_hang(tu_khoa_tim_hang("thuỷ lực"), "Dau thuy luc AW46") > 0.9


def test_tu_trung_ngau_nhien_khong_du_de_khop():
    """"xe" trùng giữa "lốp xe tải" và "nhớt xe máy": độ phủ thấp hơn ngưỡng nên không được trả."""
    assert diem_khop_hang(tu_khoa_tim_hang("lốp xe tải"), "Dầu nhớt xe máy 4T 10W40") < saas_api._NGUONG_PHU


def test_xep_hang_khop_nhat_len_truoc(saas):
    ids, _ = _tra(saas, "dầu thuỷ lực AW68")
    assert ids[0] == 4


def test_khong_tra_qua_toi_da_hang(monkeypatch):
    danh_muc = {i: f"Dầu loại số {i}" for i in range(1, 60)}
    ids, _ = _tra(_saas(_engine(danh_muc)), "dầu loại số")
    assert len(ids) == saas_api.TOI_DA_HANG_TRA


def test_kho_qua_lon_lui_ve_like_theo_tu_khoa_dai_nhat(monkeypatch):
    monkeypatch.setattr(saas_api, "TOI_DA_HANG_DOC", 5)
    danh_muc = {i: f"Dầu động cơ mã {i}" for i in range(1, 10)} | {50: "Mỡ bò EP2 xô 15kg"}
    ids, thong_bao = _tra(_saas(_engine(danh_muc)), "cho tôi hỏi mỡ bò")
    assert 50 in ids, thong_bao


def test_chuoi_doc_hai_khong_vao_sql(saas):
    ids, thong_bao = _tra(saas, "'; DROP TABLE products; --")
    assert ids == [] and thong_bao and "Không tìm thấy" in thong_bao
    with saas.engine.connect() as conn:
        assert conn.execute(text(f"SELECT COUNT(*) FROM {PRODUCTS_TABLE}")).scalar() >= len(DANH_MUC)


def test_thong_bao_khong_tim_thay_cat_ngan_cau_hoi_dai(saas):
    kq = saas.lookup_product("lốp " + "x" * 500, workspace_id=1)
    assert "Không tìm thấy" in kq and len(kq) < 250


# ---------------------------------------------------------------------------
# Qua /chat: nhánh DATA_INTERNAL
# ---------------------------------------------------------------------------

def test_chat_hoi_ton_kho_tu_nhien_dua_dung_hang_vao_ngu_canh(moi_truong, monkeypatch):  # noqa: F811
    thuc = SaasAPI.__new__(SaasAPI)
    thuc.engine = _engine(DANH_MUC, KHO_KHAC)
    monkeypatch.setattr(chat_mod, "_get_saas", lambda: thuc)
    monkeypatch.setattr(deps.runtime, "kb", None, raising=False)
    moi_truong.category = "DATA_INTERNAL"

    ai = {"X-User-Id": "1", "X-Store-Id": "1"}
    resp = client.post("/chat", headers=ai, json={"user_id": 1, "store_id": 1, "message": "còn bao nhiêu thùng dầu động cơ CF-4 15W40 vậy"})
    assert resp.status_code == 200
    kq = client.get(f"/api/v1/task/{resp.json()['task_id']}", headers=ai).json()
    assert kq["status"] == "completed", kq

    ctx = moi_truong.contexts[-1]
    assert "Dầu động cơ CF-4 15W40 thùng 18 lít" in ctx
    assert "9,999,999" not in ctx and "9.999.999" not in ctx, "hàng của khách khác lọt vào ngữ cảnh"


# ---------------------------------------------------------------------------
# Bộ thứ hai, viết SAU khi luật đã xong và không dùng để chỉnh luật. Mỗi câu thử một cơ chế khác: gạch nối trong mã, đơn vị dính ("18l"),
# không dấu, mã đứng một mình, nhắc tới nhóm hàng chung, câu có hai hàng cùng khớp.
# ---------------------------------------------------------------------------

BO_THU_HAI = [
    ("nhớt 10W40 cho xe máy còn không", {8}, 4),
    ("dầu động cơ 15w-40", {1}, 4),
    ("dầu CF4 thùng 18l", {1}, 4),
    ("dau hop so 80w90 gia bao nhieu", {7}, 4),
    ("dầu thắng DOT 4", {10}, 4),
    ("EP3", {6}, 4),
    ("cho hỏi 85W140", {11}, 4),
    ("phuy 209 lít dầu gì còn", {2, 4}, 4),
    ("nhớt", {8, 14}, 4),
    ("còn xô mỡ chịu nhiệt không", {6}, 4),
]


@pytest.mark.parametrize("cau,can,toi_da", BO_THU_HAI, ids=[c for c, _, _ in BO_THU_HAI])
def test_bo_thu_hai(saas, cau, can, toi_da):
    assert _dung(saas, cau, can, toi_da), (cau, _tra(saas, cau))


def test_gioi_han_da_biet_dong_nghia_chua_xu():
    """
    Nói thẳng cái chưa làm. "Thắng" (phương ngữ) và "phanh" là một, luật so chữ không biết điều đó: "dầu thắng xe" KHÔNG ra dầu phanh, và "dầu thắng" ra cả
    loạt dầu (mọi hàng chứa "dầu"), dầu phanh chỉ nằm lẫn trong đó. Khi thêm bảng đồng nghĩa thì sửa test này, đừng xoá nó.
    """
    saas = _saas(_engine(DANH_MUC))
    ids, _ = _tra(saas, "dầu thắng xe")
    assert 10 not in ids
    ids, _ = _tra(saas, "dầu thắng")
    assert 10 in ids and len(ids) > 5, "rộng, không nhắm đúng hàng"


def test_go_sai_mot_chu_nhung_con_ma_hang_van_tim_ra():
    ids, _ = _tra(_saas(_engine(DANH_MUC)), "daauf thuy luc aw46")
    assert ids == [3]
