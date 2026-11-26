"""
tests/offline_training/test_a7_chay_that_dau_cuoi.py — "một lần chạy thật" có định nghĩa: năm bước, tiêu chí ghi sẵn, bước không chạy KHÔNG tính là đạt (KH90 A7, brain#325).

Các bước thật (uvicorn, Brain đang chạy trên Colab, vLLM) không chạy được ở đây, nên test dùng bộ chạy và bộ gọi HTTP giả. Giữ ba điều: (1) thứ tự và tiêu chí đạt không bị nới lặng lẽ; (2) KHÔNG CHẠY và
BỎ QUA không bao giờ thành ĐẠT (mã thoát 2, khác TRƯỢT mã 1); (3) bảng và JSON không chứa token. Chỗ đọc kết quả từng script dựa trên chữ chúng in ra: test dùng mẫu chữ lấy từ chính script.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from offline_training import chay_that_dau_cuoi as ct

TOKEN = "tok-bi-mat-1234567890"
URL = "https://abc-123.ngrok-free.dev"

KIEM_SERVER_DAT = json.dumps({"ok": True, "kiem": [{"ten": "health", "ok": True, "chi_tiet": ""}, {"ten": "vat", "ok": True, "chi_tiet": ""}]})
KIEM_SERVER_HONG = json.dumps({"ok": False, "kiem": [{"ten": "health", "ok": True}, {"ten": "hmac_khong_ky_la_401", "ok": False}]})
TICH_HOP_DAT = "  Ca đạt hoàn toàn : 6/6\n  Tiêu chí đạt     : 18/18 (100%)\n  Độ trễ phân vị 95: 41.2s  ✓\n  ✅ ĐẠT TOÀN BỘ"
TICH_HOP_MOT_PHAN = "  Ca đạt hoàn toàn : 5/6\n  Độ trễ phân vị 95: 58.0s  ✓"
CHAY_THU_DAT = "  => ĐƯỜNG ĐI ĐÚNG. Soát hoá đơn vào vòng agentic, báo giá giữ luồng n8n."
CHAY_THU_SAI = "  => 2 MỤC SAI — gửi nguyên bảng này về, đừng sửa gì thêm."


class Gia:
    """Bộ chạy giả theo tên script: trả (mã thoát, đầu ra) đã dặn."""

    def __init__(self, **kq):
        self.kq = {"kiem_server_that": (0, KIEM_SERVER_DAT), "chay_thu_live": (0, CHAY_THU_DAT), "benchmark_integration": (0, TICH_HOP_DAT)}
        self.kq.update(kq)
        self.da_goi: list[str] = []
        self.env_nhan: list[dict] = []

    def __call__(self, lenh, **kw):
        ten = Path(lenh[1]).stem
        self.da_goi.append(ten)
        self.env_nhan.append(kw.get("env", {}))
        ma, ra = self.kq[ten]
        if isinstance(ma, Exception):
            raise ma
        return SimpleNamespace(returncode=ma, stdout=ra)


def health_ok(url, head):
    return 200, json.dumps({"status": "ok", "degraded": False, "engine_ready": True})


def chay(runner=None, http=health_ok, url=URL, **kw):
    return ct.chay(ct.cac_buoc(), url, TOKEN, runner=runner or Gia(), http_get=http, **kw)


def trang_thai(kq):
    return {k.khoa: k.trang_thai for k in kq}


# ---------------------------------------------------------------------------
# Định nghĩa
# ---------------------------------------------------------------------------

def test_nam_buoc_dung_thu_tu():
    assert [b.khoa for b in ct.cac_buoc()] == ["kiem_server_that", "suc_khoe_truoc", "chay_thu_live", "benchmark_tich_hop", "suc_khoe_sau_tai"]


def test_moi_buoc_co_tieu_chi_ghi_san():
    assert all(b.tieu_chi.strip() for b in ct.cac_buoc())


def test_script_ma_cac_buoc_goi_deu_ton_tai_va_dung_python_dang_chay():
    for b in ct.cac_buoc():
        if b.lenh:
            assert b.lenh[0] == sys.executable
            assert Path(b.lenh[1]).is_file(), f"{b.lenh[1]} không còn: đổi tên script thì phải sửa chay_that_dau_cuoi.py"


def test_kiem_server_la_buoc_duy_nhat_khong_can_brain():
    assert [b.khoa for b in ct.cac_buoc() if not b.can_brain] == ["kiem_server_that"]


# ---------------------------------------------------------------------------
# Đạt, trượt, không chạy, bỏ qua
# ---------------------------------------------------------------------------

def test_tat_ca_dat_thi_ma_thoat_0():
    kq = chay()
    assert set(trang_thai(kq).values()) == {ct.DAT}
    assert ct.ma_thoat(kq) == 0
    assert "5/5 bước đạt" in ct.bang(kq) and "ĐẠT: một lần chạy thật hoàn chỉnh" in ct.bang(kq)


def test_mot_buoc_truot_thi_ma_thoat_1_va_bang_noi_ro():
    kq = chay(Gia(chay_thu_live=(1, CHAY_THU_SAI)))
    assert trang_thai(kq)["chay_thu_live"] == ct.TRUOT and ct.ma_thoat(kq) == 1
    b = ct.bang(kq)
    assert "2 mục sai" in b and "TRƯỢT" in b and "4/5 bước đạt" in b and "đừng sửa gì thêm" in b


def test_thieu_url_thi_cac_buoc_can_brain_khong_chay_va_ma_thoat_2():
    runner = Gia()
    kq = chay(runner, url=None)
    assert trang_thai(kq) == {"kiem_server_that": ct.DAT, "suc_khoe_truoc": ct.KHONG_CHAY, "chay_thu_live": ct.KHONG_CHAY,
                              "benchmark_tich_hop": ct.KHONG_CHAY, "suc_khoe_sau_tai": ct.KHONG_CHAY}
    assert runner.da_goi == ["kiem_server_that"], "không có URL thì không được chạy script nào cần Brain"
    assert ct.ma_thoat(kq) == 2 and "CHƯA ĐỦ" in ct.bang(kq)


def test_khong_chay_khong_bao_gio_thanh_dat():
    kq = chay(url=None)
    assert ct.ma_thoat(kq) != 0 and all(k.trang_thai != ct.DAT for k in kq if k.khoa != "kiem_server_that")


def test_bo_qua_co_chu_dich_la_chua_du_khong_phai_dat():
    kq = chay(bo_qua=frozenset({"benchmark_tich_hop"}))
    assert trang_thai(kq)["benchmark_tich_hop"] == ct.BO_QUA and ct.ma_thoat(kq) == 2


def test_chi_chay_mot_buoc_thi_cac_buoc_con_lai_la_bo_qua_va_van_chua_du():
    runner = Gia()
    kq = chay(runner, chi=frozenset({"kiem_server_that"}))
    assert runner.da_goi == ["kiem_server_that"] and ct.ma_thoat(kq) == 2


def test_truot_thang_bo_qua_ve_ma_thoat():
    kq = chay(Gia(chay_thu_live=(1, CHAY_THU_SAI)), bo_qua=frozenset({"benchmark_tich_hop"}))
    assert ct.ma_thoat(kq) == 1, "có bước trượt thì 1, dù có bước khác bị bỏ qua"


def test_health_truoc_hong_thi_khong_chay_script_can_brain():
    runner = Gia()
    kq = chay(runner, http=lambda u, h: (200, json.dumps({"status": "degraded", "degraded": True})))
    t = trang_thai(kq)
    assert t["suc_khoe_truoc"] == ct.TRUOT
    assert t["chay_thu_live"] == ct.KHONG_CHAY and t["benchmark_tich_hop"] == ct.KHONG_CHAY
    assert runner.da_goi == ["kiem_server_that"]
    assert ct.ma_thoat(kq) == 1


def test_health_sau_tai_tut_xuong_degraded_thi_truot():
    lan = {"n": 0}

    def http(url, head):
        lan["n"] += 1
        return 200, json.dumps({"status": "ok" if lan["n"] == 1 else "degraded", "degraded": lan["n"] > 1})

    kq = chay(http=http)
    t = trang_thai(kq)
    assert t["suc_khoe_truoc"] == ct.DAT and t["suc_khoe_sau_tai"] == ct.TRUOT and ct.ma_thoat(kq) == 1


def test_timeout_va_loi_he_dieu_hanh_la_truot_khong_nem_ra_ngoai():
    kq = chay(Gia(benchmark_integration=(subprocess.TimeoutExpired("x", 1), ""), chay_thu_live=(OSError("x"), "")))
    t = trang_thai(kq)
    assert t["benchmark_tich_hop"] == ct.TRUOT and t["chay_thu_live"] == ct.TRUOT
    chi_tiet = {k.khoa: k.chi_tiet for k in kq}
    assert "quá" in chi_tiet["benchmark_tich_hop"] and "OSError" in chi_tiet["chay_thu_live"]


# ---------------------------------------------------------------------------
# Đọc kết quả từng bước
# ---------------------------------------------------------------------------

def test_doc_kiem_server():
    assert ct._phan_tich_kiem_server(0, KIEM_SERVER_DAT) == (True, "2/2 kiểm đạt")
    dat, ct_ = ct._phan_tich_kiem_server(1, KIEM_SERVER_HONG)
    assert dat is False and "hmac_khong_ky_la_401" in ct_
    assert ct._phan_tich_kiem_server(0, "không phải json")[0] is False
    assert ct._phan_tich_kiem_server(0, json.dumps({"ok": True, "kiem": []}))[0] is False, "ok mà không kiểm gì thì không đạt"
    assert ct._phan_tich_kiem_server(1, KIEM_SERVER_DAT)[0] is False, "mã thoát khác 0 thì không đạt, dù JSON nói ok"


def test_doc_benchmark_tich_hop():
    assert ct._phan_tich_tich_hop(0, TICH_HOP_DAT) == (True, "6/6 ca đạt hoàn toàn; p95 41.2s")
    dat, chi_tiet = ct._phan_tich_tich_hop(0, TICH_HOP_MOT_PHAN)
    assert dat is True and "5/6" in chi_tiet, "5/6 là ngưỡng ca của chính script; con số hiện trong bảng để người đọc thấy"
    assert ct._phan_tich_tich_hop(1, "  Chỉ đạt 3/6")[0] is False


def test_doc_chay_thu_live():
    assert ct._phan_tich_chay_thu(0, CHAY_THU_DAT) == (True, "đường đi đúng")
    assert ct._phan_tich_chay_thu(1, CHAY_THU_SAI) == (False, "2 mục sai")


@pytest.mark.parametrize("ma,body,ky_vong", [
    (200, {"status": "ok", "degraded": False}, True),
    (200, {"status": "ok", "degraded": True}, False),
    (200, {"status": "degraded"}, False),
    (503, {"status": "ok", "degraded": False}, False),
    (200, {}, False),
])
def test_doc_health(ma, body, ky_vong):
    assert ct.doc_health(URL, TOKEN, lambda u, h: (ma, json.dumps(body)))[0] is ky_vong


def test_doc_health_loi_mang_va_khong_phai_json():
    def hong(u, h):
        raise urllib.error.URLError("x")

    dat, chi_tiet = ct.doc_health(URL, TOKEN, hong)
    assert dat is False and "URLError" in chi_tiet
    assert ct.doc_health(URL, TOKEN, lambda u, h: (200, "<html>"))[0] is False


def test_health_gui_token_trong_header_va_khong_ghi_vao_chi_tiet():
    nhan = {}

    def http(url, head):
        nhan.update(head, url=url)
        return 200, json.dumps({"status": "ok", "degraded": False})

    _, chi_tiet = ct.doc_health(URL + "/", TOKEN, http)
    assert nhan["X-Api-Token"] == TOKEN and nhan["url"] == URL + "/health"
    assert TOKEN not in chi_tiet


# ---------------------------------------------------------------------------
# Token và đầu ra
# ---------------------------------------------------------------------------

def test_token_chuyen_cho_script_con_qua_moi_truong_khong_qua_dong_lenh():
    runner = Gia()
    chay(runner)
    live = [e for e in runner.env_nhan if e.get("BRAIN_URL")]
    assert live and all(e["BRAIN_API_TOKEN"] == TOKEN and e["BRAIN_URL"] == URL for e in live)
    for b in ct.cac_buoc():
        assert TOKEN not in " ".join(b.lenh or [])


def test_bang_va_json_khong_chua_token_va_chi_in_ten_may(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BRAIN_API_TOKEN", TOKEN)
    kq = chay()                                        # chạy thật hàm của module TRƯỚC khi thay nó
    monkeypatch.setattr(ct, "chay", lambda *a, **k: kq)
    ra = tmp_path / "kq.json"
    assert ct.main(["--url", URL, "--json", str(ra)]) == 0
    out = capsys.readouterr().out
    noi_dung = ra.read_text(encoding="utf-8")
    assert TOKEN not in out and TOKEN not in noi_dung
    d = json.loads(noi_dung)
    assert d["may_chu"] == "abc-123.ngrok-free.dev" and "https://" not in noi_dung
    assert d["ma_thoat"] == 0 and len(d["buoc"]) == 5 and {"khoa", "trang_thai", "chi_tiet", "giay"} <= set(d["buoc"][0])


def test_buoc_la_bi_tu_choi():
    with pytest.raises(SystemExit) as e:
        ct.main(["--chi", "khong_co_buoc_nay"])
    assert e.value.code == 2


def test_thoi_gian_moi_buoc_do_bang_dong_ho_duoc_tiem_vao():
    dh = iter(x * 2.0 for x in range(100))
    kq = ct.chay(ct.cac_buoc(), URL, TOKEN, runner=Gia(), http_get=health_ok, dong_ho=lambda: next(dh))
    assert all(k.giay == 2.0 for k in kq)
