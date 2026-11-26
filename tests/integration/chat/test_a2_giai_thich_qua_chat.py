"""
tests/integration/chat/test_a2_giai_thich_qua_chat.py — câu "vì sao ra con số đó" phải giải thích được kết quả engine vừa tính, và không bao giờ bịa (KH90 A2, brain#322).

VÌ SAO CÓ FILE NÀY
------------------
Nhánh EXPLAIN tìm khối JSON của engine trong lịch sử hội thoại, nhưng thứ Brain trả về và Body lưu lại là câu VĂN XUÔI do model diễn giải, không có khối JSON
nào trong đó. Nên dù Body gửi `history` đầy đủ, EXPLAIN luôn nhận "chưa có kết quả nào gần đây". `ket_qua_gan_nhat.py` giữ khối engine ở phía Brain theo (kho, người dùng).
Mỗi test dưới đây khoá một chỗ có thể sai: giải thích kết quả của người khác (rò dữ liệu khách), giải thích kết quả đã quá cũ, giải thích một kết quả mà người dùng
chưa từng thấy (bị chốt chặn), hay bịa khi không có gì để giải thích.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from src.api import dependencies as deps
from src.api.main import app
from src.api.routes import chat as chat_mod
from src.core.ket_qua_gan_nhat import KetQuaGanNhat, khoi_giai_thich

client = TestClient(app)
TTL = 1800.0
CAU_BAO_CAO = "báo cáo lợi nhuận quý này"
CAU_VI_SAO = "giải thích giúp tôi con số này"            # router xếp EXPLAIN, không khớp luật tool nào
CAU_LAI_GOP = "vì sao lãi gộp ra con số đó"             # router xếp EXPLAIN, NHƯNG khớp luật `report` của plan_tools
TRA_LOI_GIAI_THICH = "Lãi gộp lấy doanh thu trừ giá vốn của từng dòng bán."
KHONG_CO = "Tôi chưa có kết quả nào gần đây để giải thích"

DONG_BAN = [
    {"date": "2026-11-10", "revenue": 300_000.0, "product": "Dầu CF-4", "quantity": 2.0, "cogs": 200_000.0},
    {"date": "2026-11-11", "revenue": 100_000.0, "product": "Mỡ bò", "quantity": 1.0, "cogs": 60_000.0},
]


# ---------------------------------------------------------------------------
# Bộ nhớ kết quả gần nhất
# ---------------------------------------------------------------------------

class _DongHo:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _kho(dong_ho=None, muc=256, ky_tu=12_000):
    return KetQuaGanNhat(TTL, muc, ky_tu, dong_ho or _DongHo())


KHOI = {"explain": {"formula": "lãi_gộp = doanh_thu - giá_vốn"}, "periods": [{"period": "2026-Q4", "revenue": 400_000}]}


def test_luu_roi_lay_lai_dung_khoi():
    kho = _kho()
    khoa = kho.khoa(1, 7)
    assert kho.ghi(khoa, KHOI) is True
    assert json.loads(kho.lay(khoa)) == KHOI


def test_khach_khac_khong_thay_khoi_cua_khach_nay():
    kho = _kho()
    kho.ghi(kho.khoa(1, 7), KHOI)
    assert kho.lay(kho.khoa(1, 8)) is None, "cùng kho khác người dùng"
    assert kho.lay(kho.khoa(2, 7)) is None, "cùng người dùng khác kho"


def test_qua_han_thi_het_va_bi_xoa():
    dh = _DongHo()
    kho = _kho(dh)
    khoa = kho.khoa(1, 7)
    kho.ghi(khoa, KHOI)
    dh.t += TTL - 1
    assert kho.lay(khoa) is not None
    dh.t += 1
    assert kho.lay(khoa) is None
    assert len(kho) == 0


def test_day_thi_bo_muc_cu_nhat():
    kho = _kho(muc=2)
    for u in (1, 2, 3):
        kho.ghi(kho.khoa(1, u), KHOI)
    assert kho.lay(kho.khoa(1, 1)) is None and kho.lay(kho.khoa(1, 3)) is not None and len(kho) == 2


def test_khoi_qua_lon_khong_luu_va_bo_luon_khoi_cu():
    kho = _kho(ky_tu=200)
    khoa = kho.khoa(1, 7)
    assert kho.ghi(khoa, KHOI) is True
    to = {"explain": {"x": "a" * 500}}
    assert kho.ghi(khoa, to) is False
    assert kho.lay(khoa) is None, "giữ khối cũ thì 'vì sao' sẽ trả lời bằng số của kết quả khác với cái người dùng đang nhìn"


@pytest.mark.parametrize("ttl,muc,ky_tu", [(0, 1, 1), (-1, 1, 1), (1, 0, 1), (1, 1, 0)])
def test_tham_so_vo_ly_bi_tu_choi(ttl, muc, ky_tu):
    with pytest.raises(ValueError):
        KetQuaGanNhat(ttl, muc, ky_tu)


def test_khoi_giai_thich_tu_nhieu_dang_du_lieu_neo():
    ket_qua = {"periods": [], "explain": {}}
    assert khoi_giai_thich(json.dumps(ket_qua)) == ket_qua
    assert khoi_giai_thich(ket_qua) == ket_qua
    quan_sat = [
        {"tool": "vat", "result": {"vat": 1}},                       # không có khoá giải thích
        {"tool": "report", "result": ket_qua},
        {"tool": "quote", "result": {"error": "tham số không hợp lệ"}},   # lỗi không được lọt qua
    ]
    assert khoi_giai_thich(json.dumps(quan_sat)) == ket_qua
    nhieu = [{"tool": "a", "result": {"explain": {"v": 1}}}, {"tool": "b", "result": {"explain": {"v": 2}}}]
    assert khoi_giai_thich(nhieu) == {"explain": {"v": 2}}, "lấy khối GẦN NHẤT"


@pytest.mark.parametrize("du_lieu", ["", "   ", "không phải json", "[1, 2]", "{}", "[]", None, 5, '{"a": 1}'])
def test_khoi_giai_thich_khong_bia_ra_khoi(du_lieu):
    assert khoi_giai_thich(du_lieu) is None


# ---------------------------------------------------------------------------
# Qua /chat
# ---------------------------------------------------------------------------

class _SaasBaoCao:
    def __init__(self):
        self.lan_goi = 0

    def get_report_lines(self, workspace_id=1):
        self.lan_goi += 1
        return {"sales": [dict(d) for d in DONG_BAN], "expenses": []}


@pytest.fixture
def phien(moi_truong, monkeypatch):  # noqa: F811
    """Manager giả có `explain_result` (ghi lại ngữ cảnh nhận được), đồng hồ giả, kho gần nhất mới tinh, saas giả có dòng bán."""
    dh = _DongHo()
    kho = KetQuaGanNhat(TTL, 256, 12_000, dh)
    monkeypatch.setattr(chat_mod, "_KET_QUA", kho)
    saas = _SaasBaoCao()
    monkeypatch.setattr(chat_mod, "_get_saas", lambda: saas)
    monkeypatch.setattr(deps.runtime, "kb", None, raising=False)
    nhan: list[str] = []

    async def explain_result(question, context, history=None):
        nhan.append(context)
        return TRA_LOI_GIAI_THICH

    monkeypatch.setattr(moi_truong, "explain_result", explain_result, raising=False)

    class P:
        manager = moi_truong
        saas_gia = saas
        dong_ho = dh
        ngu_canh = nhan
        kho_gan_nhat = kho

    return P


def _hoi(cau, user_id=1, history=None):
    ai = {"X-User-Id": str(user_id), "X-Store-Id": "1"}
    body = {"user_id": user_id, "store_id": 1, "message": cau}
    if history is not None:
        body["history"] = history
    resp = client.post("/chat", headers=ai, json=body)
    assert resp.status_code == 200, resp.text
    kq = client.get(f"/api/v1/task/{resp.json()['task_id']}", headers=ai).json()
    assert kq["status"] == "completed", kq
    return kq["result"]["answer"]


def _bao_cao(p, user_id=1, tra_loi="Đây là báo cáo theo số liệu bên dưới."):
    p.manager.category = "REPORT"
    p.manager.decisions = [
        {"thought": "cần số liệu", "tool": "report", "arguments": {}},
        {"thought": "đủ số liệu", "answer": tra_loi},
    ]
    return _hoi(CAU_BAO_CAO, user_id=user_id)


def _vi_sao(p, user_id=1, history=None, cau=CAU_VI_SAO):
    p.manager.category = "EXPLAIN"
    return _hoi(cau, user_id=user_id, history=history)


def test_vi_sao_sau_bao_cao_duoc_giai_thich_bang_khoi_engine(phien):
    _bao_cao(phien)
    assert _vi_sao(phien) == TRA_LOI_GIAI_THICH
    assert len(phien.ngu_canh) == 1
    ctx = json.loads(phien.ngu_canh[0])
    q4 = next(k for k in ctx["periods"] if k["period"] == "2026-Q4")
    # Số trong ngữ cảnh là số engine TẤT ĐỊNH tính trên đúng các dòng bán, không phải số model nghĩ ra.
    assert q4["revenue"] == 400_000 and q4["cogs"] == 260_000 and q4["gross_profit"] == 140_000
    assert "explain" in ctx


def test_cau_vi_sao_khop_luat_tool_van_giai_thich_khong_tinh_lai(phien):
    """"Vì sao lãi gộp ra con số đó" khớp luật `report`: đã có kết quả để giải thích thì phải đi nhánh EXPLAIN, không chạy lại báo cáo."""
    _bao_cao(phien)
    assert phien.saas_gia.lan_goi == 1
    assert _vi_sao(phien, cau=CAU_LAI_GOP) == TRA_LOI_GIAI_THICH
    assert phien.saas_gia.lan_goi == 1, "đã tính lại báo cáo thay vì giải thích kết quả đang có"
    assert len(phien.ngu_canh) == 1


def test_cau_vi_sao_khop_luat_tool_ma_chua_co_gi_de_giai_thich_thi_tinh_roi_tra_loi(phien):
    phien.manager.decisions = [
        {"thought": "cần số liệu", "tool": "report", "arguments": {}},
        {"thought": "đủ số liệu", "answer": "Lãi gộp là doanh thu trừ giá vốn, theo số liệu bên dưới."},
    ]
    tra_loi = _vi_sao(phien, cau=CAU_LAI_GOP)
    assert tra_loi.startswith("Lãi gộp là doanh thu trừ giá vốn")
    assert phien.saas_gia.lan_goi == 1 and phien.ngu_canh == [], "tính mới rồi trả lời, không đi nhánh EXPLAIN"


def test_chua_co_ket_qua_nao_thi_noi_thang_khong_bia(phien):
    tra_loi = _vi_sao(phien)
    assert KHONG_CO in tra_loi
    assert phien.ngu_canh == [], "không có khối engine thì không được cho model giải thích"


def test_nguoi_dung_khac_khong_nhan_giai_thich_cua_nguoi_khac(phien):
    _bao_cao(phien, user_id=1)
    tra_loi = _vi_sao(phien, user_id=2)
    assert KHONG_CO in tra_loi
    assert phien.ngu_canh == [], "kết quả (giá vốn, lãi gộp) của khách này không được tới tay khách khác"


def test_qua_han_thi_khong_giai_thich_ket_qua_cu(phien):
    _bao_cao(phien)
    phien.dong_ho.t += TTL
    assert KHONG_CO in _vi_sao(phien)
    assert phien.ngu_canh == []


def test_hoi_vi_sao_nhieu_lan_khong_keo_dai_han_dung(phien):
    _bao_cao(phien)
    phien.dong_ho.t += 1000
    assert _vi_sao(phien) == TRA_LOI_GIAI_THICH
    phien.dong_ho.t += 800            # tổng 1800 kể từ lúc tính xong: hết hạn, dù mới hỏi "vì sao" 800 giây trước
    assert KHONG_CO in _vi_sao(phien)


def test_cau_tra_loi_bi_chot_chan_thi_khong_nho_khoi(phien):
    """Người dùng chưa từng thấy kết quả đó (bị thay bằng câu từ chối), nên không có gì để hỏi "vì sao"."""
    tra_loi = _bao_cao(phien, tra_loi="Doanh thu là 987.654.321 đồng.")
    assert "987.654.321" not in tra_loi, "chốt chặn neo số phải chặn con số bịa"
    assert KHONG_CO in _vi_sao(phien)
    assert phien.ngu_canh == []


def test_ket_qua_moi_thay_ket_qua_cu(phien):
    _bao_cao(phien)
    # Lượt báo cáo thứ hai trên dữ liệu khác.
    cu = _SaasBaoCao.get_report_lines
    try:
        _SaasBaoCao.get_report_lines = lambda self, workspace_id=1: {
            "sales": [{"date": "2026-11-12", "revenue": 900_000.0, "product": "X", "quantity": 1.0, "cogs": 100_000.0}],
            "expenses": [],
        }
        _bao_cao(phien)
    finally:
        _SaasBaoCao.get_report_lines = cu
    _vi_sao(phien)
    q4 = next(k for k in json.loads(phien.ngu_canh[0])["periods"] if k["period"] == "2026-Q4")
    assert q4["revenue"] == 900_000


def test_khoi_nam_trong_lich_su_do_body_gui_van_dung_duoc(phien):
    khoi = {"explain": {"formula": "lãi_gộp = doanh_thu - giá_vốn"}, "periods": [{"period": "2026-Q3", "revenue": 555_000}]}
    lich_su = [
        {"role": "user", "content": "báo cáo quý 3"},
        {"role": "assistant", "content": json.dumps(khoi, ensure_ascii=False)},
    ]
    assert _vi_sao(phien, history=lich_su) == TRA_LOI_GIAI_THICH
    assert json.loads(phien.ngu_canh[0]) == khoi


def test_khoi_trong_lich_su_bi_cat_o_gioi_han_thi_noi_chua_co(phien):
    """Body cắt mỗi tin ở 4000 ký tự: một khối JSON bị cắt giữa chừng không giải thích được, và không được đoán nốt phần còn lại."""
    khoi = {"explain": {"formula": "x"}, "periods": [{"period": f"p{i}", "revenue": i} for i in range(400)]}
    chuoi = json.dumps(khoi, ensure_ascii=False)
    assert len(chuoi) > 4196
    lich_su = [{"role": "assistant", "content": chuoi[:4196]}]
    assert KHONG_CO in _vi_sao(phien, history=lich_su)
    assert phien.ngu_canh == []


def test_ket_qua_vua_tinh_duoc_uu_tien_hon_khoi_cu_trong_lich_su(phien):
    _bao_cao(phien)
    cu = {"explain": {"formula": "CŨ"}, "periods": [{"period": "2025-Q1", "revenue": 1}]}
    lich_su = [{"role": "assistant", "content": json.dumps(cu)}]
    _vi_sao(phien, history=lich_su)
    ctx = json.loads(phien.ngu_canh[0])
    assert ctx.get("explain", {}).get("formula") != "CŨ"
    assert any(k["period"] == "2026-Q4" for k in ctx["periods"])
