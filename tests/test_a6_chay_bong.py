"""
tests/test_a6_chay_bong.py — công cụ chế độ bóng (`offline_training/chay_bong.py`, KH90 A6, brain#324).

Hai điều phải giữ: (1) nhật ký và phiếu đọc KHÔNG chứa nội dung của tệp (tên hàng, mã hàng, tên công ty), kể cả khi chạy nhiều tệp và khi có lỗi (R2); (2) mỗi bất biến tự động bắt đúng thứ nó
tên là, và một lần chạy sạch không báo oan. Chốt chống xanh suông: đối chứng dương, nội dung CÓ đến được công cụ (`--tra-cuu` in ra nó), nên "không thấy canary" thật sự là không ghi.
"""

from __future__ import annotations

import csv
import json
import logging
import secrets

import pytest

from offline_training import chay_bong as cb

CANARY = "cnr" + secrets.token_hex(6)


# ---------------------------------------------------------------------------
# Một lần chạy hư cấu đầy đủ
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def lan_chay(tmp_path_factory):
    """12 tệp hư cấu x 40 dòng, chạy trong tiến trình. Dùng chung cho các test chỉ đọc kết quả (mỗi lần chạy mất vài giây)."""
    thu_muc = tmp_path_factory.mktemp("tep")
    ra = tmp_path_factory.mktemp("ra")
    cb.sinh_hu_cau(thu_muc, 12)
    dong = cb.chay_thu_muc(cb.KetNoi(), thu_muc)
    cb.ghi_ket_qua(dong, ra)
    return dong, ra, thu_muc


def test_sinh_hu_cau_ra_it_nhat_100_ca_va_khong_vi_pham_bat_bien(lan_chay):
    dong, _, _ = lan_chay
    tep = [d for d in dong if d["loai_ban_ghi"] == "tep"]
    ca = [d for d in dong if d["loai_ban_ghi"] == "phat_hien"]
    assert len(tep) == 12 and all(t["http"] == 200 and t["doc_duoc"] for t in tep), "mọi tệp hư cấu phải đọc được (bộ sinh nhất quán đơn giá)"
    assert len(ca) >= 100, f"nghiệm thu A6: ít nhất 100 ca, được {len(ca)}"
    assert all(not t["vi_pham"] for t in tep), [t["vi_pham"] for t in tep]
    assert len({c["ca"] for c in ca}) == len(ca), "mã ca phải là duy nhất"


def test_moi_ca_co_dang_khong_noi_dung(lan_chay):
    dong, _, _ = lan_chay
    cho_phep = {"loai_ban_ghi", "ca", "tep", "tool", "kind", "muc", "co_tien", "co_bang_chung", "co_goi_y"}
    for c in (d for d in dong if d["loai_ban_ghi"] == "phat_hien"):
        assert set(c) == cho_phep
        assert isinstance(c["co_tien"], bool) and isinstance(c["co_bang_chung"], bool) and isinstance(c["co_goi_y"], bool)
        assert len(c["tep"]) == 12 and len(c["ca"]) == 10


def test_phieu_doc_co_cot_nguoi_doc_de_trong(lan_chay):
    dong, ra, _ = lan_chay
    phieu = cb.doc_phieu(ra)
    assert len(phieu) == sum(1 for d in dong if d["loai_ban_ghi"] == "phat_hien")
    assert list(phieu[0].keys()) == cb.COT_PHIEU
    assert all(p["nguoi_doc"] == "" and p["ket_luan"] == "" for p in phieu)


def test_chay_hai_lan_ra_cung_ma_ca(lan_chay, tmp_path):
    dong, _, thu_muc = lan_chay
    lai = cb.chay_thu_muc(cb.KetNoi(), thu_muc)
    ca = lambda ds: sorted(d["ca"] for d in ds if d["loai_ban_ghi"] == "phat_hien")      # noqa: E731
    assert ca(dong) == ca(lai), "mã ca phải ổn định giữa các lần chạy để người đọc tra lại được"


def test_sinh_hu_cau_cung_seed_ra_cung_noi_dung(tmp_path):
    a = cb.sinh_hu_cau(tmp_path / "a", 1)[0].read_bytes()
    b = cb.sinh_hu_cau(tmp_path / "b", 1)[0].read_bytes()
    from src.core import inventory_import as ii
    la, lb = ii.load_xlsx_bytes(a).lines, ii.load_xlsx_bytes(b).lines
    assert [(x.code, x.closing_qty) for x in la] == [(x.code, x.closing_qty) for x in lb]


# ---------------------------------------------------------------------------
# Không nội dung trong nhật ký (R2), kèm đối chứng dương
# ---------------------------------------------------------------------------

def _tep_canary(thu_muc):
    import random
    cb.sinh_ton_kho(thu_muc / "ton_kho_canary.xlsx", 30, random.Random(7), tien_to=CANARY.upper(), ten_cong_ty=CANARY, ten_nhom=CANARY)


def test_canary_khong_vao_ca_phieu_man_hinh_hay_log(tmp_path, capfd, caplog):
    tep = tmp_path / "tep"
    tep.mkdir()
    _tep_canary(tep)
    ra = tmp_path / "ra"
    caplog.set_level(logging.DEBUG)
    assert cb.main(["--thu-muc", str(tep), "--ra", str(ra)]) == 0
    out, err = capfd.readouterr()
    log = "\n".join(f"{r.getMessage()}\n{r.exc_text or ''}" for r in caplog.records if not r.name.startswith(("httpx", "httpcore")))
    noi_dung = (ra / "ca.jsonl").read_text(encoding="utf-8") + (ra / "phieu_doc.csv").read_text(encoding="utf-8-sig") + out + err + log
    assert (ra / "ca.jsonl").stat().st_size > 0 and "phat_hien" in noi_dung, "không có ca nào: phép kiểm vô nghĩa"
    for dang in (CANARY, CANARY.upper(), CANARY.lower()):
        assert dang not in noi_dung, f"nội dung của tệp lọt vào nhật ký/phiếu/màn hình: {dang}"


def test_doi_chung_duong_tra_cuu_in_ra_noi_dung_that(tmp_path, capfd):
    """Canary CÓ đến được công cụ: `--tra-cuu` (chỉ ra màn hình) phải in nó. Nếu không, test trên xanh vì công cụ không thấy nội dung, không phải vì nó không ghi."""
    tep = tmp_path / "tep"
    tep.mkdir()
    _tep_canary(tep)
    ra = tmp_path / "ra"
    cb.main(["--thu-muc", str(tep), "--ra", str(ra)])
    ca_id = next(d["ca"] for d in cb.doc_ca(ra) if d["loai_ban_ghi"] == "phat_hien")
    capfd.readouterr()
    assert cb.main(["--tra-cuu", ca_id, "--thu-muc", str(tep)]) == 0
    out, _ = capfd.readouterr()
    assert CANARY in out or CANARY.upper() in out
    assert "ton_kho_canary.xlsx" in out
    assert not list(tep.glob("*.json")) and not list(tmp_path.glob("**/*tra_cuu*")), "--tra-cuu không được ghi tệp nào"


def test_tra_cuu_ca_khong_ton_tai_noi_ro(tmp_path, capfd):
    tep = tmp_path / "tep"
    tep.mkdir()
    _tep_canary(tep)
    cb.main(["--tra-cuu", "khongcoca00", "--thu-muc", str(tep)])
    assert "Không thấy ca khongcoca00" in capfd.readouterr()[0]


# ---------------------------------------------------------------------------
# Từng bất biến
# ---------------------------------------------------------------------------

def _f(**kw):
    ban = {"kind": "negative_stock", "severity": "cao", "code": "A-1", "title": "t", "evidence": {"x": 1}, "suggestion": "s", "money_impact": 1000}
    ban.update(kw)
    return ban


def _p(findings, ok=True, **thêm):
    return {"import": {"ok": ok, "lines": [{"code": "A-1"}, {"code": "A-2"}]}, "audit": {"findings": findings}, "unit_costs": [], **thêm}


def kiem(payload, lan_hai=None, ma_khac=frozenset()):
    return cb.kiem_bat_bien(payload, lan_hai, "lines", set(ma_khac))


def test_sach_thi_khong_bao_oan():
    assert kiem(_p([_f()]), _p([_f()])) == []
    assert kiem(_p([_f(money_impact=None)])) == [], "None là 'chưa quy ra tiền được', hợp lệ"
    assert kiem(_p([_f(money_impact=0)])) == []


def test_doc_hong_ma_van_co_audit_hoac_gia_von():
    hong = _p([_f()], ok=False)
    assert kiem(hong) == ["doc_hong_nhung_co_audit"]
    hong2 = {"import": {"ok": False, "lines": []}, "audit": None, "unit_costs": [{"code": "A", "unit_cost": 1}]}
    assert kiem(hong2) == ["doc_hong_nhung_co_audit"]
    dung = {"import": {"ok": False, "lines": []}, "audit": None, "unit_costs": []}
    assert kiem(dung) == []


@pytest.mark.parametrize("sua", [{"title": ""}, {"evidence": {}}, {"suggestion": ""}, {"severity": "khẩn"}, {"title": None}])
def test_phat_hien_thieu_truong(sua):
    assert kiem(_p([_f(**sua)])) == ["thieu_truong_phat_hien"]


@pytest.mark.parametrize("tien", [float("nan"), float("inf"), "1000", True, [1]])
def test_tien_khong_huu_han(tien):
    assert kiem(_p([_f(money_impact=tien)])) == ["tien_khong_huu_han"]


def test_khong_tat_dinh():
    assert kiem(_p([_f()]), _p([_f(money_impact=2000)])) == ["khong_tat_dinh"]
    assert kiem(_p([_f()]), None) == []


def test_ro_cheo_tep():
    assert kiem(_p([_f(code="B-9")]), ma_khac={"B-9"}) == ["ro_cheo_tep"]
    assert kiem(_p([_f(code="A-1")]), ma_khac={"A-1"}) == [], "mã có ở cả hai tệp (cùng danh mục hàng) không phải rò"
    assert kiem(_p([_f(code="Z-0")]), ma_khac={"B-9"}) == [], "mã lạ không có ở tệp nào khác thì không phải rò chéo"


def test_nhieu_bat_bien_cung_luc_va_khong_lap():
    kq = kiem(_p([_f(title=""), _f(evidence={})], ok=False), _p([_f()]))
    assert kq == ["doc_hong_nhung_co_audit", "thieu_truong_phat_hien", "khong_tat_dinh"]


# ---------------------------------------------------------------------------
# Chạy tệp với kết nối giả
# ---------------------------------------------------------------------------

class KetNoiGia:
    def __init__(self, kq_theo_lan):
        self.kq = list(kq_theo_lan)
        self.goi_ra = []

    def goi(self, route, ten, du_lieu):
        self.goi_ra.append((route, ten))
        return self.kq.pop(0) if self.kq else (200, {})


def test_loi_may_chu_duoc_ghi_va_lam_thoat_1(tmp_path):
    (tmp_path / "ton_kho_x.xlsx").write_bytes(b"x")
    dong = cb.chay_thu_muc(KetNoiGia([(500, {}), (500, {})]), tmp_path)
    assert dong[0]["http"] == 500 and "loi_may_chu" in dong[0]["vi_pham"]
    cb.ghi_ket_qua(dong, tmp_path / "ra")
    assert cb.main(["--tong-hop", str(tmp_path / "ra")]) == 1


def test_khong_tat_dinh_trong_chay_that_lam_thoat_1(tmp_path):
    (tmp_path / "ton_kho_x.xlsx").write_bytes(b"x")
    # Vòng một (lấy mã), lần chạy 1, lần chạy 2: lần hai khác lần một.
    kn = KetNoiGia([(200, _p([_f()])), (200, _p([_f()])), (200, _p([_f(money_impact=5)]))])
    dong = cb.chay_thu_muc(kn, tmp_path)
    assert dong[0]["vi_pham"] == ["khong_tat_dinh"]


def test_tep_khong_nhan_ra_loai_thi_bo_qua_va_noi_ro(tmp_path):
    (tmp_path / "bao_cao_khac.xlsx").write_bytes(b"x")
    kn = KetNoiGia([])
    dong = cb.chay_thu_muc(kn, tmp_path)
    assert dong[0]["bo_qua"] and dong[0]["tool"] is None and kn.goi_ra == []


@pytest.mark.parametrize("ten,route", [
    ("Ton_kho_thang_6.xlsx", "/tools/inventory-import"),
    ("Tồn kho tháng 6.xlsx", "/tools/inventory-import"),
    ("BC_NXT_Q2.xlsx", "/tools/inventory-import"),
    ("Danh sách khách hàng.xlsx", "/tools/partner-import"),
    ("nha_cung_cap_2026.xlsx", "/tools/partner-import"),
    ("Danh mục hàng hóa.xlsx", "/tools/product-import"),
])
def test_nhan_ra_loai_tep_theo_ten(ten, route):
    assert cb.loai_cua_tep(ten)[0] == route


# ---------------------------------------------------------------------------
# Tổng hợp và phiếu đã điền
# ---------------------------------------------------------------------------

def _ghi_phieu(ra, ket_luan_moi_dong):
    phieu = cb.doc_phieu(ra)
    for p, kl in zip(phieu, ket_luan_moi_dong):
        p["nguoi_doc"] = "son" if kl else ""
        p["ket_luan"] = kl
    with open(ra / "phieu_doc.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cb.COT_PHIEU)
        w.writeheader()
        w.writerows(phieu)
    return len(phieu)


def test_tong_hop_dem_dung_oan_thieu_va_doi_du_nguoi_doc(lan_chay, tmp_path):
    _, ra0, _ = lan_chay
    ra = tmp_path / "ra"
    ra.mkdir()
    for ten in ("ca.jsonl", "phieu_doc.csv"):
        (ra / ten).write_bytes((ra0 / ten).read_bytes())
    n = _ghi_phieu(ra, ["dung", "dung", "oan", "thieu"] + [""] * 3)
    bang, thoat = cb.tong_hop(ra, doi_du_nguoi_doc=False)
    assert thoat == 0 and "Đã có người đọc: 4/" in bang and "dung=2, oan=1, thieu=1" in bang and "báo oan trên ca đã đọc: 25%" in bang
    _, thoat = cb.tong_hop(ra, doi_du_nguoi_doc=True)
    assert thoat == 1, "còn ca chưa đọc thì không đạt"
    _ghi_phieu(ra, ["dung"] * n)
    bang, thoat = cb.tong_hop(ra, doi_du_nguoi_doc=True)
    assert thoat == 0 and f"{n}/{n}" in bang


def test_ket_luan_ngoai_danh_sach_khong_tinh_la_da_doc(lan_chay, tmp_path):
    _, ra0, _ = lan_chay
    ra = tmp_path / "ra"
    ra.mkdir()
    for ten in ("ca.jsonl", "phieu_doc.csv"):
        (ra / ten).write_bytes((ra0 / ten).read_bytes())
    _ghi_phieu(ra, ["có lẽ đúng", "ok"])
    bang, thoat = cb.tong_hop(ra, doi_du_nguoi_doc=True)
    assert "Đã có người đọc: 0/" in bang and "CẢNH BÁO: 2 ca" in bang and thoat == 1


def test_tong_hop_in_nhan_gioi_han_cua_chinh_no(lan_chay):
    _, ra, _ = lan_chay
    bang, _ = cb.tong_hop(ra)
    assert "không biết phát hiện nào đúng nghiệp vụ" in bang


def test_ca_jsonl_la_json_hop_le_moi_dong(lan_chay):
    _, ra, _ = lan_chay
    for dong in (ra / "ca.jsonl").read_text(encoding="utf-8").splitlines():
        assert isinstance(json.loads(dong), dict)
