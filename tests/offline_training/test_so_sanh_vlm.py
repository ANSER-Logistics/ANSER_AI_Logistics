"""
tests/offline_training/test_so_sanh_vlm.py — công cụ đặt các lần đo model thị giác cạnh nhau (`offline_training/so_sanh_vlm.py`).

Phần thuần là toán (Wilson, McNemar chính xác) và luật "không so hai lần đo khác bộ đề". Toán kiểm bằng số tính
tay; luật kiểm bằng cách đưa vào đúng tình huống đã xảy ra: hai lần đo trên bộ ảnh khác nhau (trước và sau PR #107).
"""

from __future__ import annotations

import json
from math import comb

import pytest

from offline_training import so_sanh_vlm as s


def _rows(dung: list[bool], *, tien_to: str = "VH") -> list[dict]:
    return [{"id": f"{tien_to}{i:04d}", "tat_ca_dung": d, "tong_dung": d, "dien_0": 0, "parse": True}
            for i, d in enumerate(dung)]


# ---------------------------------------------------------------------------
# Wilson
# ---------------------------------------------------------------------------

def test_wilson_15_tren_28_khop_con_so_36_den_70():
    lo, hi = s.wilson(15, 28)
    assert 0.355 < lo < 0.362 and 0.700 < hi < 0.710, (lo, hi)


def test_wilson_bien_hai_dau_khong_ra_ngoai_0_1():
    lo, hi = s.wilson(0, 28)
    assert 0.0 <= lo < 1e-9 and 0.10 < hi < 0.14
    lo, hi = s.wilson(28, 28)
    assert 1.0 - 1e-9 < hi <= 1.0 and 0.86 < lo < 0.90


def test_wilson_n_bang_khong_la_chua_biet_gi():
    assert s.wilson(0, 0) == (0.0, 1.0)


def test_wilson_k_ngoai_khoang_la_loi():
    with pytest.raises(ValueError):
        s.wilson(5, 4)


def test_wilson_hep_dan_khi_n_tang():
    r28 = s.wilson(20, 28)
    r280 = s.wilson(200, 280)
    assert (r280[1] - r280[0]) < (r28[1] - r28[0]) / 2


# ---------------------------------------------------------------------------
# McNemar chính xác
# ---------------------------------------------------------------------------

def test_mcnemar_khong_co_ca_bat_dong_thi_p_bang_1():
    assert s.mcnemar_chinh_xac(0, 0) == 1.0


def test_mcnemar_b_bang_c_thi_p_bang_1():
    assert s.mcnemar_chinh_xac(4, 4) == 1.0


@pytest.mark.parametrize("b,c,mong", [
    (7, 1, 2 * (comb(8, 0) + comb(8, 1)) / 2 ** 8),       # 0,0703
    (10, 0, 2 / 2 ** 10),                                   # 0,00195
    (0, 10, 2 / 2 ** 10),                                   # đối xứng
    (6, 2, 2 * (1 + 8 + 28) / 2 ** 8),                      # 0,289
])
def test_mcnemar_gia_tri_tinh_tay(b, c, mong):
    assert s.mcnemar_chinh_xac(b, c) == pytest.approx(mong)


def test_mcnemar_doi_xung_va_khong_vuot_1():
    for b in range(0, 12):
        for c in range(0, 12):
            p = s.mcnemar_chinh_xac(b, c)
            assert 0.0 < p <= 1.0
            assert p == s.mcnemar_chinh_xac(c, b)


def test_mcnemar_am_la_loi():
    with pytest.raises(ValueError):
        s.mcnemar_chinh_xac(-1, 3)


# ---------------------------------------------------------------------------
# so_sanh
# ---------------------------------------------------------------------------

def test_so_voi_chinh_minh_thi_khong_khac():
    rows = _rows([True] * 15 + [False] * 13)
    kq = s.so_sanh({"moc": rows, "ban_sao": [dict(r) for r in rows]}, "moc")
    g = kq["bang"]["ban_sao"]
    assert (g["b"], g["c"], g["p"]) == (0, 0, 1.0)
    assert g["k"] == 15 and g["n"] == 28


def test_dem_dung_b_va_c_theo_cap():
    moc = _rows([True, True, True, False, False, False, True, True])
    mo = _rows([True, False, False, True, True, False, True, True])
    kq = s.so_sanh({"moc": moc, "mo": mo}, "moc")
    g = kq["bang"]["mo"]
    assert g["b"] == 2 and g["c"] == 2 and g["p"] == 1.0           # (1,2) mốc đúng model sai; (3,4) ngược lại


def test_model_hon_ro_rang_cho_p_nho():
    moc = _rows([False] * 20 + [True] * 8)
    tot = _rows([True] * 20 + [True] * 8)           # đúng hết: 20 ca mốc sai mà model đúng
    kq = s.so_sanh({"moc": moc, "tot": tot}, "moc")
    assert kq["bang"]["tot"]["c"] == 20 and kq["bang"]["tot"]["b"] == 0
    assert kq["bang"]["tot"]["p"] < 0.001


def test_thu_tu_ca_khong_anh_huong_ket_qua():
    moc = _rows([True, False, True, False, True, True, False, False])
    mo = _rows([True, True, False, False, True, False, True, False])
    thuan = s.so_sanh({"moc": moc, "mo": mo}, "moc")
    dao = s.so_sanh({"moc": list(reversed(moc)), "mo": mo}, "moc")
    assert thuan == dao


def test_tu_choi_so_hai_bo_de_khac_nhau():
    """Đúng tình huống đã xảy ra: ảnh đổi sau PR #107, số hai lần đo không so được."""
    truoc = _rows([True] * 10, tien_to="VH")
    sau = _rows([True] * 10, tien_to="VK")
    with pytest.raises(ValueError, match="KHÔNG cùng bộ đề"):
        s.so_sanh({"moc": truoc, "sau": sau}, "moc")


def test_tu_choi_khi_thieu_ca_o_mot_ben():
    a = _rows([True] * 10)
    b = _rows([True] * 9)
    with pytest.raises(ValueError, match="KHÔNG cùng bộ đề"):
        s.so_sanh({"moc": a, "b": b}, "moc")


def test_id_trung_la_loi():
    rows = _rows([True, True])
    rows[1]["id"] = rows[0]["id"]
    with pytest.raises(ValueError, match="hai lần"):
        s.so_sanh({"moc": rows}, "moc")


def test_moc_khong_ton_tai_la_loi():
    with pytest.raises(ValueError, match="mốc"):
        s.so_sanh({"a": _rows([True])}, "khong_co")


def test_dem_dien_0_chep_lenh_va_khong_parse():
    rows = _rows([False, False, True])
    rows[0]["dien_0"] = 2
    rows[1]["chep_nhieu_loan"] = True
    rows[1]["parse"] = False
    g = s.so_sanh({"m": rows}, "m")["bang"]["m"]
    assert g["dien_0"] == 2 and g["chep_lenh"] == 1 and g["khong_parse"] == 1


# ---------------------------------------------------------------------------
# Đọc file và dòng lệnh
# ---------------------------------------------------------------------------

def _ghi(duong, rows):
    duong.write_text(json.dumps({"tong_hop": {}, "rows": rows}, ensure_ascii=False), encoding="utf-8")
    return str(duong)


def test_doc_ket_qua_bao_ro_file_khong_phai_dau_ra_cua_bo_do(tmp_path):
    p = tmp_path / "xau.json"
    p.write_text(json.dumps({"khac": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="rows"):
        s.doc_ket_qua(p)


def test_doc_ket_qua_bao_ro_ca_thieu_truong(tmp_path):
    p = tmp_path / "thieu.json"
    p.write_text(json.dumps({"rows": [{"id": "VH0000"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="tat_ca_dung"):
        s.doc_ket_qua(p)


def test_dong_lenh_in_bang_va_thoat_0(tmp_path, capsys):
    a = _ghi(tmp_path / "a.json", _rows([True] * 15 + [False] * 13))
    b = _ghi(tmp_path / "b.json", _rows([True] * 18 + [False] * 10))
    ma = s.main([f"moc={a}", f"hai={b}"])
    ra = capsys.readouterr().out
    assert ma == 0 and "15/28" in ra and "18/28" in ra and "McNemar" in ra and "(mốc)" in ra


def test_dong_lenh_thoat_2_khi_khac_bo_de(tmp_path, capsys):
    a = _ghi(tmp_path / "a.json", _rows([True] * 4, tien_to="VH"))
    b = _ghi(tmp_path / "b.json", _rows([True] * 4, tien_to="VK"))
    ma = s.main([f"moc={a}", f"hai={b}"])
    assert ma == 2 and "không so được" in capsys.readouterr().err


def test_dong_lenh_cho_phep_lap_moc_cung_file(tmp_path, capsys):
    a = _ghi(tmp_path / "a.json", _rows([True, False, True, False]))
    assert s.main([f"moc={a}", f"moc={a}"]) == 0
    capsys.readouterr()


def test_dong_lenh_tu_choi_cung_ten_hai_file_khac_nhau(tmp_path):
    a = _ghi(tmp_path / "a.json", _rows([True, False]))
    b = _ghi(tmp_path / "b.json", _rows([False, True]))
    with pytest.raises(SystemExit):
        s.main([f"moc={a}", f"moc={b}"])
