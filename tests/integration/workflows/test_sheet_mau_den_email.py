"""
tests/integration/workflows/test_sheet_mau_den_email.py — Google Sheet MẪU mà khách nhập chạy được hết luồng báo giá, tới email khách cuối.

VÌ SAO CÓ FILE NÀY
------------------
`data/sheet_templates/*.csv` là thứ khách pilot import làm Google Sheet (README cùng thư mục). Trước file này không test
nào đọc chúng, nên một cột đổi tên ở CSV, ở đoạn JS của workflow n8n, hay ở schema `/tools/*` (`extra="forbid"`) chỉ lộ ra
khi khách bấm báo giá thật. Ở đây cả chuỗi chạy bằng mã thật: CSV -> JS "Ghép dữ liệu" -> `/tools/carrier-selection`
-> JS "Lấy hãng đầu bảng" -> `/tools/quote` -> JS "Dựng nháp + embed" (dòng ghi vào sheet QuoteDrafts) -> JS duyệt
"Dựng email từ phần công khai". Node "Dựng email..." trước đây chưa test nào chạy, mà nó là chốt cuối của P2: giá gốc
nhà xe và biên không bao giờ vào email khách.
"""

from __future__ import annotations

import csv
import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core import pricing
from tests.support.n8n import NODE, ROOT, chay_code_node, code_node

pytestmark = pytest.mark.skipif(NODE is None, reason="cần Node để chạy đoạn JS thật của workflow n8n (CI có sẵn Node)")

YEU_CAU = "workflows/logistics/logistics_quote_request.json"
DUYET = "workflows/logistics/logistics_quote_approve.json"
NHAC_NO = "workflows/logistics/logistics_debt_reminder.json"
# Ngày dữ liệu mẫu được viết: mọi giá chào trong CarrierQuotes.csv còn hiệu lực, giá dầu mới 1 ngày.
NOW = "2026-07-27T03:00:00Z"  # 10:00 giờ Việt Nam
HOM_NAY = date(2026, 7, 27)

REQ = {"origin": "Hữu Nghị", "destination": "Hải Phòng", "vehicle_type": "5T", "cargo_type": "Hàng lạnh",
       "customer_name": "Khách hư cấu", "customer_email": "khach@example.com"}


def _bang(ten: str) -> list[dict]:
    """Như node Google Sheets trả: mỗi dòng một dict, mọi ô là chuỗi (trường hợp xấu nhất cho phép đổi kiểu)."""
    with open(ROOT / "data" / "sheet_templates" / f"{ten}.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _cot(ten: str) -> list[str]:
    with open(ROOT / "data" / "sheet_templates" / f"{ten}.csv", encoding="utf-8-sig", newline="") as f:
        return next(csv.reader(f))


def _ok(ket_qua: dict) -> dict:
    assert "ok" in ket_qua, ket_qua
    return ket_qua["ok"]


def _vn(n) -> str:
    """Như `Intl.NumberFormat('vi-VN')` cho số nguyên: dấu chấm ngăn nghìn."""
    return f"{int(n):,}".replace(",", ".")


@pytest.fixture
def luong(monkeypatch):
    """Chạy cả chuỗi một lần; trả mọi bước để từng test kiểm một chỗ nối."""
    monkeypatch.setattr(pricing, "hom_nay_vn", lambda: HOM_NAY)
    client = TestClient(app)

    ghep = _ok(chay_code_node(code_node(YEU_CAU, "Ghép dữ liệu"), now=NOW, nodes={
        "Nhận yêu cầu báo giá": {"body": REQ},
        "Đọc Carriers": _bang("Carriers"),
        "Đọc CarrierQuotes": _bang("CarrierQuotes"),
        "Đọc PricingRules": _bang("PricingRules"),
        "Đọc FuelIndex": _bang("FuelIndex"),
        "Đọc Routes": _bang("Routes"),
    }))
    r_chon = client.post("/tools/carrier-selection", json=ghep["payloadSelection"])
    assert r_chon.status_code == 200, r_chon.text

    pick = _ok(chay_code_node(code_node(YEU_CAU, "Lấy hãng đầu bảng"), now=NOW,
                              nodes={"Ghép dữ liệu": ghep}, input=[r_chon.json()]))
    r_gia = client.post("/tools/quote", json=pick["quotePayload"])
    assert r_gia.status_code == 200, r_gia.text

    nhap = _ok(chay_code_node(code_node(YEU_CAU, "Dựng nháp + embed"), now=NOW,
                              nodes={"Ghép dữ liệu": ghep, "Lấy hãng đầu bảng": pick}, input=[r_gia.json()]))
    return {"ghep": ghep, "chon": r_chon.json(), "gia": r_gia.json(), "nhap": nhap}


def test_du_lieu_mau_sach_khong_canh_bao_va_dung_tuyen(luong):
    ghep = luong["ghep"]
    assert ghep["canh_bao_du_lieu"] == [], "sheet mẫu mà còn cảnh báo thì khách copy mẫu là có lỗi ngay"
    assert ghep["route_id"] == "R001"
    assert ghep["fuel_price_as_of"] == "2026-07-27", "lấy giá dầu MỚI NHẤT (AGENTS §3.1c)"
    assert ghep["current_fuel_price"] == 27100
    assert {o["carrier_id"] for o in ghep["payloadSelection"]["offers"]} == {"C001", "C002"}


def test_brain_chon_hang_re_hon_va_bao_gia_khop_gia_chao(luong):
    assert luong["chon"]["ranked"], luong["chon"]
    gia = luong["gia"]
    assert gia["internal"]["carrier_cost"] == luong["chon"]["ranked"][0]["offer_price"]
    assert gia["quote"]["quoted_price"] > gia["internal"]["carrier_cost"]
    assert [s["name"] for s in gia["quote"]["surcharges"]] == ["Phụ phí hàng lạnh"]


def test_dong_nhap_khop_dung_cot_sheet_quotedrafts(luong):
    """Node 'Lưu nháp vào Sheet' ghi `draftRow` theo tên cột; khoá lệch cột là mất dữ liệu im lặng."""
    assert sorted(luong["nhap"]["draftRow"]) == sorted(_cot("QuoteDrafts"))


def test_email_duyet_chi_co_phan_cong_khai(luong):
    dong = luong["nhap"]["draftRow"]
    email = _ok(chay_code_node(code_node(DUYET, "Dựng email từ phần công khai"), now=NOW,
                               nodes={"Nhận lệnh duyệt": {"query": {"draft_id": dong["id"]}}}, input=[dong]))
    gia, noi_bo = luong["gia"]["quote"], luong["gia"]["internal"]
    assert email["already"] is False and email["to"] == REQ["customer_email"]
    assert _vn(gia["quoted_price"]) in email["body"]
    assert "Phụ phí hàng lạnh: " + _vn(gia["surcharges"][0]["value"]) in email["body"]
    thu = email["body"] + email["subject"]
    for bi_mat in ("carrier_cost", "margin", "fuel_adjustment"):
        v = noi_bo[bi_mat]
        assert v, f"{bi_mat} = 0 thì phép kiểm dưới vô nghĩa"
        for dang in (_vn(v), str(int(v))):  # số đã định dạng (văn) hoặc số thô (JSON dán nhầm)
            assert dang not in thu, f"{bi_mat} = {dang} lọt vào email khách (P2)"
    assert "Hùng Phát" not in thu and "Thành Đạt" not in thu, "tên nhà xe là thông tin nội bộ"


# ---------------------------------------------------------------------------
# Node duyệt: các ca biên
# ---------------------------------------------------------------------------

def _email(dong: dict, draft_id="QD-1") -> dict:
    return chay_code_node(code_node(DUYET, "Dựng email từ phần công khai"), now=NOW,
                          nodes={"Nhận lệnh duyệt": {"query": {"draft_id": draft_id}}}, input=[dong])


_DONG = {"id": "QD-1", "status": "pending", "customer_email": "k@example.com", "origin": "A", "destination": "B",
         "vehicle_type": "5T", "quoted_price": 4550000, "surcharges_json": "[]", "internal_json": "{}"}


def test_bam_link_lan_hai_khong_gui_lai():
    assert _ok(_email(_DONG | {"status": "sent"})) == {"already": True, "status": "sent", "draft_id": "QD-1"}


def test_id_so_tu_sheet_van_khop_draft_id_chuoi():
    assert _ok(_email(_DONG | {"id": 7}, draft_id="7"))["to"] == "k@example.com"


@pytest.mark.parametrize("dong, draft_id, loi", [
    (_DONG, "", "Thiếu draft_id"),
    (_DONG, "QD-KHAC", "Không tìm thấy nháp"),
    (_DONG | {"customer_email": ""}, "QD-1", "thiếu email khách"),
])
def test_thieu_du_lieu_thi_dung_khong_gui(dong, draft_id, loi):
    assert loi in _email(dong, draft_id).get("error", "")


def test_phu_phi_hong_van_gui_duoc_gia_tong():
    out = _ok(_email(_DONG | {"surcharges_json": "{hỏng"}))
    assert "4.550.000" in out["body"] and "Phụ phí" not in out["body"]


# ---------------------------------------------------------------------------
# Nhắc nợ đọc sheet Receivables mẫu
# ---------------------------------------------------------------------------

def _nhac_no(rows: list[dict]) -> dict:
    return _ok(chay_code_node(code_node(NHAC_NO, "Lọc quá hạn"), now=NOW, input=rows))


def test_nhac_no_tren_sheet_mau_chi_bao_khoan_qua_han_con_no():
    out = _nhac_no(_bang("Receivables"))
    assert out["has_overdue"] is True
    mo_ta = json.loads(out["discord_body"])["embeds"][0]["description"]
    assert "RC-001" not in mo_ta and "QD-20260727-001" not in mo_ta, "RC-001 hạn 10/08: chưa quá hạn"
    assert "4.200.000" in mo_ta and "quá hạn 7 ngày" in mo_ta, "RC-002: 7.200.000 - 3.000.000, hạn 20/07"


@pytest.mark.xfail(strict=True, reason="brain#265: so ngày bằng chuỗi thô, ô không đọc được bị bỏ im lặng")
@pytest.mark.parametrize("han, so_tien", [
    ("15/07/2999", "1000000"),   # hôm nay: báo "quá hạn NaN ngày" cho khoản còn 973 năm mới tới hạn
    ("31/12/2000", "1000000"),   # hôm nay: quá hạn 26 năm mà KHÔNG được báo
    ("2026-07-20", "4.550.000"),  # hôm nay: số kiểu Việt Nam -> NaN -> khoản nợ biến mất khỏi báo cáo
])
def test_nhac_no_o_khong_doc_duoc_thi_noi_ra_khong_im_lang(han, so_tien):
    """
    Cùng lỗi 'Ghép dữ liệu' đã sửa (so chuỗi thô): Google Sheets locale Việt Nam trả DD/MM/YYYY và 4.550.000.
    Không bắt node phải đoán DD/MM; chỉ bắt nó không im lặng và không in NaN: chủ DN phải thấy dòng này.
    """
    dong = {"id": "RC-9", "customer_name": "Khách K9", "quote_id": "Q", "amount": so_tien, "paid_amount": "0",
            "status": "open", "due_date": han}
    out = _nhac_no([dong])
    assert "Khách K9" in out.get("discord_body", ""), "dòng nợ không đọc được mà bị bỏ im lặng"
    assert "NaN" not in out["discord_body"]
