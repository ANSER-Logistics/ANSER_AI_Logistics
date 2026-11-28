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

WF = Path(__file__).resolve().parents[3] / "workflows" / "logistics" / "logistics_debt_reminder.json"
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


def _no(ma="RC-1", ten="Khách A", han="2026-07-01", tien="1000000", tra="", st="open", id_=None):
    d = {"quote_id": ma, "customer_name": ten, "due_date": han, "amount": tien, "paid_amount": tra, "status": st}
    if id_ is not None:
        d["id"] = id_            # sheet Receivables thật có CẢ `id` (khoá của dòng) và `quote_id` (báo giá nguồn)
    return d


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
    assert "Khách Cũ" in mo_ta and "Khách Xa" in mo_ta, "chủ DN cần thấy KHÁCH nào để đi sửa ô"
    assert "31/12/2000" not in mo_ta and "15/07/2999" not in mo_ta, "nội dung ô ngày/tiền lạ không được đưa vào thông báo"


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


def test_ma_va_ten_la_chi_giu_ky_tu_an_toan_va_co_do_dai_toi_da():
    ra = _chay([_no(ma="RC-1 <script>\nđộc", ten="Khách *đậm* `mã` \n| x" + "y" * 100, han="xx")])
    mo_ta = _mo_ta(ra)
    assert "<" not in mo_ta and "\nđộc" not in mo_ta
    assert "*đậm*" not in mo_ta and "`" not in mo_ta and "yyyy" in mo_ta and "y" * 70 not in mo_ta
    ra = _chay([_no(ma=f"RC{i}", han="xx") for i in range(30)])
    assert "30 dòng không đọc được" in _mo_ta(ra) and "…" in _mo_ta(ra)


def test_if_node_doc_has_report_de_dong_chi_co_loi_van_gui_di():
    wf = json.loads(WF.read_text(encoding="utf-8"))
    if_node = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.if")
    assert if_node["parameters"]["conditions"]["boolean"][0]["value1"] == "={{ $json.has_report }}"


# --- review của wikiepeidia trên PR #276 -------------------------------------------------------------------------------------

def test_bao_cao_dai_van_giu_muc_loi_va_cat_theo_dong_khong_cat_giua_chung():
    """75 dòng quá hạn + 1 dòng sai ngày: `slice(0, 3800)` trên cả khối từng làm mất đúng mục lỗi, tiêu đề báo một lỗi mà không ai biết sửa dòng nào."""
    dong = [_no(f"QT-{i}", f"Khách số {i} có cái tên khá dài để báo cáo đầy", han="2026-07-01", tien=f"{1_000_000 + i}", id_=f"RC-{i}") for i in range(75)]
    dong.append(_no("QT-LOI", "Khách Sai Ngày", han="31/12/2000", id_="RC-LOI"))
    ra = _chay(dong)
    mo_ta = _mo_ta(ra)
    assert len(mo_ta) <= 4096, len(mo_ta)
    assert "1 dòng không đọc được" in mo_ta and "Khách Sai Ngày" in mo_ta and "RC-LOI" in mo_ta, "mục lỗi phải còn nguyên"
    assert "khách nữa" in mo_ta, "danh sách bị rút gọn thì phải nói còn bao nhiêu khách"
    con_lai = int(mo_ta.split("… và ")[1].split(" khách nữa")[0])
    hien = mo_ta.count("• **")
    assert hien + con_lai == 75, "dòng nào không hiện thì phải được đếm vào '… và N khách nữa'"
    assert "tổng" in json.loads(ra["discord_body"])["embeds"][0]["title"] and "75 khách" in json.loads(ra["discord_body"])["embeds"][0]["title"]


def test_nhieu_dong_loi_hien_toi_da_hai_muoi_va_noi_ro_con_bao_nhieu():
    ra = _chay([_no(f"QT-{i}", f"Khách lỗi {i}", han="31/12/2000", id_=f"RC-{i}") for i in range(60)])
    mo_ta = _mo_ta(ra)
    assert "60 dòng không đọc được" in mo_ta and "(+40 dòng nữa)" in mo_ta and len(mo_ta) <= 4096
    assert mo_ta.count("Khách lỗi") == 20


def test_dong_loi_hien_ma_khoan_phai_thu_va_ma_bao_gia_khi_co_ca_hai():
    """`id=RC-1, quote_id=QT-1` từng chỉ in `QT-1`: người vận hành không tra được dòng cần sửa trong sheet Receivables."""
    mo_ta = _mo_ta(_chay([_no("QT-1", "Khách Hai Mã", han="31/12/2000", id_="RC-1")]))
    assert "mã RC-1" in mo_ta and "báo giá QT-1" in mo_ta


def test_dong_loi_khong_co_cot_id_van_hien_ma_bao_gia():
    assert "mã QT-9" in _mo_ta(_chay([_no("QT-9", "Khách Cũ", han="31/12/2000")]))


def test_ten_khach_qua_dai_o_dong_qua_han_khong_lam_mat_muc_loi():
    ra = _chay([_no("QT-1", "K" * 5000, han="2026-07-01", id_="RC-1"), _no("QT-2", "Khách Sai", han="31/12/2000", id_="RC-2")])
    mo_ta = _mo_ta(ra)
    assert len(mo_ta) <= 4096 and "RC-2" in mo_ta and "Khách Sai" in mo_ta
