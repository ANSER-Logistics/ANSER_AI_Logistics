"""
tests/unit/core/test_ro_ri_truong_thieu.py — tin nhắn nhắc tới trường mà nhãn ghi `null` (#91, EX0034 và EX0110).

Cái dễ sai là cái không báo lỗi: bộ dò quá rộng thì loại oan những dòng đúng (và âm thầm đổi phân phối dữ liệu), quá hẹp thì
không bắt được chính hai ca đã biết. Nên test khoá cả hai phía: hai tin nhắn thật của #91 PHẢI bị bắt, và các cách nói
bình thường của một trường CÓ nhãn KHÔNG được bị bắt.
"""

from __future__ import annotations

import json

import pytest

from offline_training import ro_ri_truong_thieu as r
from offline_training.reverse_generate import verify_message
from offline_training.ro_ri_truong_thieu import soat, tach_dong, truong_thieu_bi_nhac

DAY_DU = {"origin": "Hữu Nghị", "destination": "Hải Phòng", "vehicle_type": "3T",
          "cargo_type": None, "pickup_date": None, "customer_name": None, "customer_email": None}


def gt(**kw):
    d = dict(DAY_DU)
    d.update(kw)
    return d


# ---------------------------------------------------------------------------
# Hai ca thật của #91 phải bị bắt
# ---------------------------------------------------------------------------

def test_EX0034_ship_ve_HP_nhan_destination_null_bi_bat():
    ra = truong_thieu_bi_nhac("lấy hàng tại KCN Tân Trường, ship về HP cho tôi", gt(origin="KCN Tân Trường", destination=None))
    assert ra == [("destination", "hp")]


def test_EX0110_giao_noi_thanh_HN_bi_bat():
    ra = truong_thieu_bi_nhac("lay hang o Huu Nghi, giao nội thành HN, co chở nhanh t3 dc ko?",
                              gt(origin="Hữu Nghị", destination=None, vehicle_type="3T"))
    assert ra and ra[0][0] == "destination"


@pytest.mark.parametrize("msg", [
    "giao về Hải Phòng nhé",
    "giao ve hai phong nhe",          # không dấu
    "GIAO VỀ HẢI PHÒNG",
    "đi Hà Nội",
    "chở lên Lạng Sơn",
])
def test_dia_danh_trong_tap_bi_bat_ke_ca_khong_dau_va_viet_hoa(msg):
    assert truong_thieu_bi_nhac(msg, gt(destination=None))


# ---------------------------------------------------------------------------
# Không được bắt oan
# ---------------------------------------------------------------------------

def test_truong_co_nhan_thi_khong_kiem():
    assert truong_thieu_bi_nhac("từ Hữu Nghị về Hải Phòng xe 3 tấn", gt()) == []


def test_dia_danh_la_gia_tri_goc_cua_truong_khac_khong_tinh_la_ro():
    """'KCN VSIP Bắc Ninh' là điểm LẤY HÀNG; 'Bắc Ninh' trong đó không phải điểm giao."""
    g = gt(origin="KCN VSIP Bắc Ninh", destination=None)
    assert truong_thieu_bi_nhac("lấy hàng ở KCN VSIP Bắc Ninh, cần xe 3 tấn", g) == []
    # nhưng nếu còn nhắc thêm một điểm giao thật thì vẫn bị bắt
    assert truong_thieu_bi_nhac("từ KCN VSIP Bắc Ninh đi Hải Phòng", g) == [("destination", "Hải Phòng")]


@pytest.mark.parametrize("msg", [
    "báo giá giúp mình với",
    "cần xe gấp trong tuần này",
    "hàng dễ vỡ, lấy ở Hữu Nghị",
    "xe tải HPC",                       # 'hp' là tiền tố của một từ khác: biên từ phải chặn
    "t3 lấy được không",                # 'thứ 3', không phải trọng tải
    "ngày 3 tháng sau",                 # '3 t' + 'háng'
])
def test_cau_binh_thuong_khong_bi_bat_oan(msg):
    assert truong_thieu_bi_nhac(msg, gt(destination=None, vehicle_type=None, origin="Hữu Nghị")) == []


# ---------------------------------------------------------------------------
# Điểm lấy hàng và loại xe
# ---------------------------------------------------------------------------

def test_diem_lay_hang_thieu_ma_nhac_den_bi_bat():
    assert truong_thieu_bi_nhac("lấy ở Gia Lâm đi Hải Phòng", gt(origin=None))[0][0] == "origin"


@pytest.mark.parametrize("msg", ["cần xe 3 tấn", "xe 5t được không", "xe 1t5", "xe 1.5 tan", "xe ba tấn",
                                 "cần đầu kéo", "xe container 40", "dung xe cont"])
def test_loai_xe_thieu_ma_nhac_den_bi_bat(msg):
    assert ("vehicle_type" in {t for t, _ in truong_thieu_bi_nhac(msg, gt(vehicle_type=None))}), msg


def test_nhieu_truong_cung_ro_thi_tra_du():
    ra = truong_thieu_bi_nhac("xe 5 tấn từ Gia Lâm về Hải Phòng", gt(origin=None, destination=None, vehicle_type=None))
    assert {t for t, _ in ra} == {"origin", "destination", "vehicle_type"}


# ---------------------------------------------------------------------------
# Nối vào bộ sinh: verify_message
# ---------------------------------------------------------------------------

def _seed(**kw):
    return {"ground_truth": gt(origin="KCN Tân Trường", **kw)}


def test_verify_message_tu_choi_tin_nhan_ro_trong_khi_truoc_do_cho_qua():
    seed = _seed(destination=None)
    msg = "lấy hàng tại KCN Tân Trường, ship về HP cho tôi, xe 3 tấn"
    ly_do = verify_message(msg, seed)
    assert ly_do and "điểm giao hàng" in ly_do and "'hp'" in ly_do


def test_verify_message_van_cho_qua_tin_nhan_dung():
    assert verify_message("cần xe 3 tấn lấy hàng tại KCN Tân Trường, giá bao nhiêu?", _seed(destination=None)) is None


def test_verify_message_van_kiem_chieu_thuan():
    ly_do = verify_message("cần xe 3 tấn đi Hải Phòng", _seed(destination="Hải Phòng"))
    assert ly_do and "thiếu thông tin bắt buộc" in ly_do


# ---------------------------------------------------------------------------
# Dò trên tệp đã sinh
# ---------------------------------------------------------------------------

def _eval_row(i, msg, **gtkw):
    return {"_id": i, "today": "2026-03-04", "kind": "single", "message": msg, "ground_truth": gt(**gtkw)}


def _train_row(i, msg, **gtkw):
    return {"_id": i, "_source": "logistics_extract", "messages": [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "Hôm nay là thứ Tư, ngày 2026-03-04.\nTin nhắn: " + msg},
        {"role": "assistant", "content": json.dumps(gt(**gtkw), ensure_ascii=False)}]}


def test_tach_dong_hieu_ca_hai_dinh_dang_va_bo_qua_dong_hai_luot():
    assert tach_dong(_eval_row("a", "xin chào"))[0] == "xin chào"
    assert tach_dong(_train_row("b", "chào bạn"))[0] == "chào bạn"
    assert tach_dong({"_id": "c", "kind": "followup", "message": "x", "ground_truth": {}}) is None
    nam = {"messages": [{}, {}, {}, {}, {}]}
    assert tach_dong(nam) is None
    assert tach_dong({"messages": [{}, {"content": "không có tiền tố"}, {"content": "{}"}]}) is None
    assert tach_dong(_eval_row("d", "x") | {"ground_truth": "hỏng"}) is None


def test_soat_dem_dung_mau_so_va_tu_so():
    rows = [
        _eval_row("EX0034", "ship về HP", destination=None),                       # thiếu + nhắc -> nghi
        _eval_row("EX0111", "giá bao nhiêu vậy", destination=None),               # thiếu, sạch
        _eval_row("EX0112", "đi Hải Phòng", destination="Hải Phòng"),             # có nhãn: không kiểm
        _train_row("EX0200", "lấy ở Gia Lâm", origin=None, destination=None, vehicle_type=None),  # origin nghi
        {"_id": "FU1", "kind": "followup", "message": "đổi xe", "ground_truth": {}},  # bỏ qua
    ]
    kq = soat(rows)
    assert kq["quet"] == 4
    assert kq["co_truong_thieu"]["destination"] == 3
    assert kq["nghi_theo_truong"]["destination"] == 1
    assert kq["nghi_theo_truong"]["origin"] == 1
    assert {n["id"] for n in kq["nghi_ro"]} == {"EX0034", "EX0200"}


def test_main_in_ty_le_noi_la_can_duoi_va_chan_khi_duoc_yeu_cau(tmp_path, capsys):
    p = tmp_path / "eval.jsonl"
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in [
        _eval_row("EX0034", "ship về HP", destination=None), _eval_row("OK1", "giá nhé", destination=None)]),
        encoding="utf-8")
    assert r.main([str(p)]) == 0
    out = capsys.readouterr().out
    assert "EX0034" in out and "CẬN DƯỚI" in out and "50.0%" in out
    assert r.main([str(p), "--chan"]) == 1


def test_main_tep_khong_doc_duoc_thi_noi_ro_va_chan_thoat_2_khong_phai_sach(tmp_path, capsys):
    khong_co = str(tmp_path / "khong_co.jsonl")
    assert r.main([khong_co]) == 0                       # không bật --chan: chỉ báo
    assert "KHÔNG ĐỌC ĐƯỢC" in capsys.readouterr().out
    assert r.main([khong_co, "--chan"]) == 2             # bật --chan: không dò được không phải là sạch


# ---------------------------------------------------------------------------
# Thuộc tính trên seed thật của bộ sinh (cùng `make_seed` mà bộ sinh dùng)
# ---------------------------------------------------------------------------

def _seeds(n=1500):
    import random

    from offline_training.make_extraction_seeds import make_seed

    rng = random.Random(20261119)
    return [make_seed(i, rng) for i in range(n)]


def test_khong_bat_oan_tin_nhan_dung_tu_facts():
    """Tin nhắn ghép từ `facts` KHÔNG chứa trường thiếu theo cách dựng, nên mọi báo động ở đây là bắt oan. Đo ngày
    19/11/2026 trên 5.000 seed (2.260 có trường thiếu): 0 báo động."""
    seeds = _seeds()
    assert sum(1 for s in seeds if s["must_not_mention"]) > 400, "chốt chống xanh suông: phải có đủ seed thiếu trường"
    oan = []
    for s in seeds:
        msg = " ".join(str(v) for v in s["facts"].values())
        ra = truong_thieu_bi_nhac(msg, s["ground_truth"])
        if ra:
            oan.append((s["_id"], ra, msg))
    assert not oan, oan[:3]


def test_chen_dia_danh_vao_truong_thieu_thi_luon_bi_bat():
    """Chiều ngược: seed thiếu điểm giao, chèn BẤT KỲ địa danh nào trong tập (hoặc viết tắt) thì phải bị bắt."""
    from offline_training.make_extraction_seeds import DESTINATIONS

    n = 0
    for s in _seeds():
        if "destination" not in s["must_not_mention"]:
            continue
        base = " ".join(str(v) for v in s["facts"].values())
        for d in (*DESTINATIONS, "HP", "HN"):
            ra = truong_thieu_bi_nhac(f"{base}, ship về {d}", s["ground_truth"])
            assert ("destination" in {t for t, _ in ra}), (s["_id"], d, base)
            n += 1
    assert n > 1000


# ---------------------------------------------------------------------------
# Lọc ở bước dựng dataset (build_dataset_v3)
# ---------------------------------------------------------------------------

def test_loc_dong_ro_ri_loai_dung_dong_nhan_sai_va_giu_phan_con_lai():
    from offline_training.ro_ri_truong_thieu import loc_dong_ro_ri

    rows = [
        _train_row("EX0034", "ship về HP", destination=None),                   # nhãn sai: loại
        _train_row("EX0111", "giá bao nhiêu vậy", destination=None),            # nhãn thiếu, tin nhắn sạch: giữ
        _train_row("EX0112", "đi Hải Phòng", destination="Hải Phòng"),          # có nhãn: giữ
        {"_id": "FU1", "_source": "logistics_extract_multiturn", "messages": [{}, {}, {}, {}, {}]},  # hai lượt: giữ
        {"_id": "X", "messages": "hỏng"},                                       # không đọc được: giữ, không nổ
    ]
    giu, loai = loc_dong_ro_ri(rows)
    assert [r["_id"] for r in giu] == ["EX0111", "EX0112", "FU1", "X"]
    assert loai == [{"id": "EX0034", "truong": "destination", "khop": "hp"}]


def test_build_dataset_v3_goi_bo_loc_cho_train_extraction():
    """Dựng dataset là chỗ bộ lọc có tác dụng thật; hàm đúng mà không ai gọi thì nhãn sai vẫn vào tập train."""
    from pathlib import Path

    nguon = (Path(__file__).resolve().parents[3] / "offline_training" / "build_dataset_v3.py").read_text(encoding="utf-8")
    assert "loc_dong_ro_ri(rows)" in nguon and 'name == "train_extraction.jsonl"' in nguon
