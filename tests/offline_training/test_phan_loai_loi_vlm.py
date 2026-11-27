"""
tests/offline_training/test_phan_loai_loi_vlm.py — phân loại lỗi đọc số của model thị giác theo đáp án thật (#124).

Lỗi cần bắt nhất là lỗi lũy thừa của 10: Qwen3-VL-2B đọc `55.192.500` thành `55192` ở cả 18/18 ca sai tổng, và lớp kiểm nhất quán
của runtime KHÔNG bắt được vì giá từng dòng và tổng cùng lệch. Cái dễ sai ở đây là cái không báo lỗi: bộ phân loại bỏ sót đúng
ca đó, hoặc gọi oan một ca sai thường là "lệch lũy thừa" rồi chặn nhầm một model tốt. Nên test dựng đầu ra từ ĐÁP ÁN thật của
`sinh_ca` rồi bóp méo từng kiểu.
"""

from __future__ import annotations

import copy
import json

import pytest

from offline_training import phan_loai_loi_vlm as pl
from offline_training.phan_loai_loi_vlm import la_luy_thua_10, phan_loai, phan_loai_ca, so_sanh
from offline_training.vlm_hoadon import sinh_ca

CA = sinh_ca(28)
BAN_LE = next(c for c in CA if c["kind"] == "retail" and any(i["qty"] > 1 for i in c["gt"]["items"]))
CUOC_THUONG = next(c for c in CA if c["kind"] == "freight" and c["variant"] != "vat_hidden")
CUOC_AN_VAT = next(c for c in CA if c["kind"] == "freight" and c["variant"] == "vat_hidden")


def dung(ca):
    """Đầu ra hoàn hảo: đúng đáp án."""
    return copy.deepcopy(ca["gt"])


# ---------------------------------------------------------------------------
# so_sanh
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gt, out, mong", [
    (55192500, 55192500, "dung"),
    (55192500, 55192500.2, "dung"),
    (55192500, 55192, "x10^-3"),            # ca thật của Qwen3-VL-2B: cụt phần lẻ nên không chia hết đúng 1000
    (42580080, 42580.08, "x10^-3"),
    (1634000, 1634, "x10^-3"),
    (1000, 1000000, "x10^3"),
    (5000, 50000, "x10^1"),
    (5000, 4000, "sai_khac"),
    (5000, 5001, "sai_khac"),
    (5000, None, "khong_co_so"),
    (5000, "5000", "khong_co_so"),
    (5000, True, "khong_co_so"),
    (5000, 0, "sai_khac"),
    (None, None, "dung"),
    (None, 0, "dien_0"),
    (None, 0.0, "dien_0"),
    (None, 10, "dien_so"),
    (0, 0, "dung"),
])
def test_so_sanh(gt, out, mong):
    assert so_sanh(gt, out) == mong


def test_sai_khac_gan_luy_thua_nhung_khong_trong_dung_sai():
    """Gấp 10 nhưng lệch 5% không phải 'lệch lũy thừa': nó là sai thường, không được chặn như lỗi quy ước số."""
    assert so_sanh(1000, 10500) == "sai_khac"
    assert so_sanh(1000, 10050) == "x10^1"


def test_la_luy_thua_10_chi_tinh_truong_tien():
    assert la_luy_thua_10("total:x10^-3") and la_luy_thua_10("unit_price:x10^3") and la_luy_thua_10("price:x10^1")
    assert not la_luy_thua_10("vat_rate:x10^1"), "thuế suất 8 thành 80 là sai thường, không phải quy ước số tiền"
    assert not la_luy_thua_10("total:sai_khac") and not la_luy_thua_10("gia:la_thanh_tien")


# ---------------------------------------------------------------------------
# Hoá đơn bán lẻ
# ---------------------------------------------------------------------------

def test_ban_le_hoan_hao_khong_co_tag():
    assert phan_loai_ca(BAN_LE, dung(BAN_LE)) == []


def test_ban_le_tat_ca_so_lech_1000_lan_la_ca_cua_qwen3_vl_2b():
    out = dung(BAN_LE)
    out["total"] = out["total"] / 1000
    for i in out["items"]:
        i["price"] = i["price"] / 1000
    tags = phan_loai_ca(BAN_LE, out)
    assert "total:x10^-3" in tags and "price:x10^-3" in tags
    assert all(la_luy_thua_10(t) for t in tags)


def test_ban_le_price_la_thanh_tien_la_loi_nham_cot_cua_ban_3b():
    out = dung(BAN_LE)
    for i in out["items"]:
        i["price"] = i["price"] * i["qty"]
    tags = phan_loai_ca(BAN_LE, out)
    assert "gia:la_thanh_tien" in tags
    assert not any(la_luy_thua_10(t) for t in tags), "nhầm cột không phải lỗi quy ước số; không được vào danh sách chặn"


def test_ban_le_thieu_dong_va_sai_so_luong():
    out = dung(BAN_LE)
    out["items"] = out["items"][:-1]
    assert "dong:thieu_hoac_thua" in phan_loai_ca(BAN_LE, out)
    out2 = dung(BAN_LE)
    out2["items"][0]["qty"] += 1
    assert phan_loai_ca(BAN_LE, out2) == ["sl:sai"]


def test_ban_le_dong_thua_cung_la_thieu_hoac_thua():
    out = dung(BAN_LE)
    out["items"].append({"name": "Hàng không có", "price": 1000, "qty": 1})
    assert "dong:thieu_hoac_thua" in phan_loai_ca(BAN_LE, out)


def test_ten_dong_khac_dau_van_ghep_duoc():
    """Model viết không dấu hoặc khác hoa thường vẫn ghép đúng dòng, không bị tính là thiếu dòng."""
    from offline_training.vlm_hoadon import _chuan

    out = dung(BAN_LE)
    for i in out["items"]:
        i["name"] = _chuan(i["name"]).upper()
    assert phan_loai_ca(BAN_LE, out) == []


# ---------------------------------------------------------------------------
# Hoá đơn cước
# ---------------------------------------------------------------------------

def test_cuoc_hoan_hao_khong_co_tag():
    assert phan_loai_ca(CUOC_THUONG, dung(CUOC_THUONG)) == []


def test_cuoc_lech_1000_o_don_gia_tong_va_tien_thue():
    out = dung(CUOC_THUONG)
    for c in out["charges"]:
        c["unit_price"] /= 1000
    for k in ("total", "subtotal", "vat_amount"):
        out[k] = out[k] / 1000
    tags = phan_loai_ca(CUOC_THUONG, out)
    assert {"unit_price:x10^-3", "total:x10^-3", "subtotal:x10^-3", "vat_amount:x10^-3"} <= set(tags)
    assert all(la_luy_thua_10(t) for t in tags)


def test_cuoc_an_vat_model_dien_0_va_dien_so_la_hai_loi_khac_nhau():
    """Hai lỗi khác nhau: điền 0 (R1 cấm thẳng) và điền một số bịa (còn nguy hiểm hơn vì trông như thật)."""
    out0 = dung(CUOC_AN_VAT)
    out0["vat_rate"] = out0["vat_amount"] = out0["subtotal"] = 0
    t0 = phan_loai_ca(CUOC_AN_VAT, out0)
    assert {"vat_rate:dien_0", "vat_amount:dien_0", "subtotal:dien_0"} <= set(t0)

    out1 = dung(CUOC_AN_VAT)
    out1["vat_rate"] = 10.0
    assert phan_loai_ca(CUOC_AN_VAT, out1) == ["vat_rate:dien_so"]


def test_cuoc_an_vat_tra_dung_none_la_dung():
    assert phan_loai_ca(CUOC_AN_VAT, dung(CUOC_AN_VAT)) == []


def test_cuoc_thieu_khoan():
    out = dung(CUOC_THUONG)
    out["charges"] = out["charges"][:-1] if len(out["charges"]) > 1 else []
    assert "dong:thieu_hoac_thua" in phan_loai_ca(CUOC_THUONG, out)


# ---------------------------------------------------------------------------
# Đầu ra hỏng
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("out", [None, "chuỗi", [], {"error": "hết giờ"}])
def test_dau_ra_khong_doc_duoc(out):
    assert phan_loai_ca(BAN_LE, out) == ["khong_doc_duoc"]


def test_dau_ra_thieu_khoa_khong_lam_no():
    assert phan_loai_ca(BAN_LE, {}) and phan_loai_ca(CUOC_THUONG, {"charges": "hỏng"})


# ---------------------------------------------------------------------------
# Gom và dòng lệnh
# ---------------------------------------------------------------------------

def _rows(out_theo_id):
    return [{"id": i, "out": o} for i, o in out_theo_id.items()]


def test_gom_dem_dung_va_chi_ra_ca_luy_thua():
    sai = dung(BAN_LE)
    sai["total"] /= 1000
    rows = _rows({BAN_LE["id"]: sai, CUOC_THUONG["id"]: dung(CUOC_THUONG)})
    kq = phan_loai(CA, rows)
    assert kq["n"] == 2 and kq["khong_loi_tien"] == 1
    assert kq["LECH_LUY_THUA_10"] == [BAN_LE["id"]]


def test_dong_ket_qua_khong_co_trong_de_bi_bo_va_noi_ra():
    kq = phan_loai(CA, [{"id": "ZZZ", "out": {}}, {"id": CUOC_THUONG["id"], "out": dung(CUOC_THUONG)}])
    assert kq["khong_co_trong_de"] == ["ZZZ"] and kq["n"] == 1


def _ghi(tmp_path, ten, out_theo_id):
    p = tmp_path / ten
    p.write_text(json.dumps({"rows": _rows(out_theo_id)}), encoding="utf-8")
    return str(p)


def _de(tmp_path):
    p = tmp_path / "eval.jsonl"
    p.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in CA), encoding="utf-8")
    return str(p)


def test_main_chan_thoat_1_khi_co_luy_thua_va_0_khi_sach(tmp_path, capsys):
    sai = dung(BAN_LE)
    sai["total"] /= 1000
    tep_sai = _ghi(tmp_path, "sai.json", {BAN_LE["id"]: sai})
    tep_sach = _ghi(tmp_path, "sach.json", {BAN_LE["id"]: dung(BAN_LE)})
    de = _de(tmp_path)
    assert pl.main(["--de", de, "--ket-qua", tep_sach, "--chan"]) == 0
    assert "LECH_LUY_THUA_10: rỗng" in capsys.readouterr().out
    assert pl.main(["--de", de, "--ket-qua", tep_sach, "--ket-qua", tep_sai, "--chan"]) == 1
    assert "⛔ LECH_LUY_THUA_10" in capsys.readouterr().out
    assert pl.main(["--de", de, "--ket-qua", tep_sai]) == 0, "không có --chan thì chỉ báo, không đổi mã thoát"


def test_main_tep_khong_doc_duoc_thoat_2_khong_bao_sach(tmp_path):
    assert pl.main(["--de", str(tmp_path / "khong_co.jsonl"), "--ket-qua", "x.json", "--chan"]) == 2
    assert pl.main(["--de", _de(tmp_path), "--ket-qua", str(tmp_path / "khong_co.json"), "--chan"]) == 2
