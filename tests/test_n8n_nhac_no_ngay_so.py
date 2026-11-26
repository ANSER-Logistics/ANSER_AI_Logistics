"""
tests/test_n8n_nhac_no_ngay_so.py — workflow nhắc nợ phải đọc ngày và số tiền kiểu Google Sheets locale Việt Nam, không bỏ im lặng khoản nợ nào (#265, R1).

Bản trước so ngày bằng chuỗi thô và đổi tiền bằng `Number()`: "31/12/2000" không được báo (quá hạn 26 năm), "15/07/2999" báo "quá hạn NaN ngày", "4.550.000" ra NaN
và khoản nợ biến mất khỏi báo cáo. Chạy ĐOẠN JS THẬT trong Node, đồng hồ cố định 2026-07-27T03:00:00Z (10:00 sáng VN). Dữ liệu hư cấu.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WF = Path(__file__).resolve().parent.parent / "workflows" / "logistics" / "logistics_debt_reminder.json"
NOW = "2026-07-27T03:00:00Z"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="cần Node để chạy đoạn JS thật của workflow n8n (CI có sẵn Node)")

_HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const t0 = Date.parse(input.now);
Date.now = () => t0;
const rows = r => ({ all: () => r.map(json => ({ json })), first: () => ({ json: r[0] }) });
const fn = new Function('$input', input.code);
const out = fn(rows(input.input));
process.stdout.write(JSON.stringify(out));
"""


def _code() -> str:
    wf = json.loads(WF.read_text(encoding="utf-8"))
    return next(n for n in wf["nodes"] if n["name"] == "Lọc quá hạn")["parameters"]["jsCode"]


def _chay(rows: list[dict]) -> dict:
    r = subprocess.run(["node", "-e", _HARNESS], input=json.dumps({"code": _code(), "now": NOW, "input": rows}), capture_output=True, text=True,
                       encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr[:600]
    return json.loads(r.stdout)[0]["json"]


def _no(ma="RC-1", ten="Khách A", han="2026-07-01", tien="1000000", tra="", st="open"):
    return {"quote_id": ma, "customer_name": ten, "due_date": han, "amount": tien, "paid_amount": tra, "status": st}


def _mo_ta(ra: dict) -> str:
    return json.loads(ra["discord_body"])["embeds"][0]["description"]


def test_ba_ca_cua_issue_265():
    ra = _chay([
        _no("RC-OLD", "Khách Cũ", han="31/12/2000"),            # DD/MM/YYYY: không đọc được, KHÔNG được bỏ im lặng
        _no("RC-FUT", "Khách Xa", han="15/07/2999"),            # không được in "NaN"
        _no("RC-TIEN", "Khách Tiền", han="2026-07-01", tien="4.550.000"),
    ])
    mo_ta = _mo_ta(ra)
    assert ra["has_report"] is True and ra["has_overdue"] is True
    assert "Khách Tiền" in mo_ta and "4.550.000" in mo_ta and "quá hạn 26 ngày" in mo_ta
    assert "NaN" not in mo_ta and "NaN" not in ra["discord_body"]
    assert "2 dòng không đọc được" in mo_ta and "RC-OLD" in mo_ta and "RC-FUT" in mo_ta
    assert "Khách Cũ" not in mo_ta and "Khách Xa" not in mo_ta, "dòng không đọc được chỉ hiện MÃ, không hiện nội dung ô lạ"


def test_chi_co_dong_khong_doc_duoc_van_bao_khong_im_lang():
    ra = _chay([_no("RC-X", han="31/12/2000")])
    assert ra["has_report"] is True and ra["has_overdue"] is False
    assert "1 dòng không đọc được" in _mo_ta(ra) and "RC-X" in _mo_ta(ra)


def test_khong_co_gi_de_bao_thi_im_la_dung():
    ra = _chay([_no(han="2026-08-01"), _no(st="paid", han="2020-01-01"), _no(tien="500000", tra="500000")])
    assert ra == {"has_overdue": False, "has_report": False}


@pytest.mark.parametrize("tien,ky_vong", [("4.550.000", 4_550_000), ("4550000", 4_550_000), (4550000, 4_550_000), ("4.550.000 đ", 4_550_000),
                                          ("4.550.000 VND", 4_550_000), ("999", 999)])
def test_so_tien_doc_duoc(tien, ky_vong):
    ra = _chay([_no(tien=tien)])
    assert "còn nợ **" in _mo_ta(ra) and f"{ky_vong:,}".replace(",", ".") in _mo_ta(ra)


@pytest.mark.parametrize("tien", ["4,55", "1e6", "bốn triệu", "-100", "4.55.0", "1.2345", "0x10", ""])
def test_so_tien_khong_doc_duoc_thi_dua_vao_muc_rieng_khong_NaN(tien):
    ra = _chay([_no(ma="RC-T", tien=tien)])
    assert "NaN" not in ra["discord_body"] and "RC-T" in _mo_ta(ra) and "1 dòng không đọc được" in _mo_ta(ra)


def test_da_tra_het_hoac_tra_nhieu_hon_thi_khong_bao_va_paid_hong_thi_noi():
    assert _chay([_no(tien="1.000.000", tra="1.000.000")])["has_report"] is False
    assert _chay([_no(tien="1.000.000", tra="1.200.000")])["has_report"] is False
    ra = _chay([_no(ma="RC-P", tien="1.000.000", tra="abc")])
    assert "RC-P" in _mo_ta(ra) and "1 dòng không đọc được" in _mo_ta(ra)
    ra = _chay([_no(tien="1.000.000", tra="400.000")])
    assert "còn nợ **600.000 đ**" in _mo_ta(ra)


def test_han_dung_hom_nay_chua_qua_han_va_hom_qua_la_mot_ngay():
    assert _chay([_no(han="2026-07-27")])["has_report"] is False
    assert "quá hạn 1 ngày" in _mo_ta(_chay([_no(han="2026-07-26")]))


def test_khong_co_han_thi_khong_tinh_la_giu_hanh_vi_cu():
    assert _chay([_no(han="")])["has_report"] is False


def test_ma_la_chi_giu_ky_tu_an_toan_va_co_do_dai_toi_da():
    ra = _chay([_no(ma="RC-1 <script>\nđộc", han="xx")])
    mo_ta = _mo_ta(ra)
    assert "<" not in mo_ta and "\nđộc" not in mo_ta
    ra = _chay([_no(ma=f"RC{i}", han="xx") for i in range(30)])
    assert "30 dòng không đọc được" in _mo_ta(ra) and "…" in _mo_ta(ra)


def test_if_node_doc_has_report_de_dong_chi_co_loi_van_gui_di():
    wf = json.loads(WF.read_text(encoding="utf-8"))
    if_node = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.if")
    assert if_node["parameters"]["conditions"]["boolean"][0]["value1"] == "={{ $json.has_report }}"
