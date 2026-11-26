"""
Phần thuần của `offline_training/do_tre_rag.py` (#119): phân vị, đếm vượt ngưỡng, tóm tắt bỏ lần đầu, và lớp
bọc bấm giờ. Phép đo thật nạp bge-m3 và ViRanker nên chạy trên Colab, không chạy ở đây.
"""

from __future__ import annotations

import pytest

from offline_training import do_tre_rag as d
from src.core import nguong_p95


def test_phan_vi_khop_nguong_p95_cua_health():
    # Một định nghĩa p95 cho cả /health và phép đo này (R4): khác nhau thì hai con số không so được.
    for n in (1, 2, 10, 20, 30, 101):
        mau = [float(i) for i in range(1, n + 1)]
        assert d.phan_vi(mau, 0.95) == nguong_p95.p95(mau)


def test_phan_vi_bien():
    assert d.phan_vi([], 0.5) is None
    assert d.phan_vi([3.0, 1.0, 2.0], 0.5) == 2.0
    assert d.phan_vi([5.0], 0.95) == 5.0
    with pytest.raises(ValueError):
        d.phan_vi([1.0], 0)


def test_tom_tat_bo_lan_dau_khoi_phan_vi():
    # Lần đầu gồm nạp model lười: chậm gấp trăm lần, không được kéo p95 lên.
    kq = d.tom_tat([9000.0] + [10.0] * 20)
    assert kq["lan_dau"] == 9000.0
    assert kq["n"] == 20 and kq["p95"] == 10.0 and kq["max"] == 10.0


def test_tom_tat_khong_bo_lan_dau_khi_bo_dau_0():
    kq = d.tom_tat([300.0, 100.0], bo_dau=0)
    assert kq["lan_dau"] is None and kq["n"] == 2 and kq["max"] == 300.0


def test_tom_tat_chi_co_lan_dau():
    kq = d.tom_tat([42.0])
    assert kq["n"] == 0 and kq["p50"] is None and kq["lan_dau"] == 42.0


def test_dem_vuot_bang_nguong_khong_tinh_la_vuot():
    kq = d.dem_vuot([100, 512, 513, 9000], 512)
    assert kq["vuot"] == 2 and kq["ti_le_pct"] == 50.0
    assert d.dem_vuot([], 512)["ti_le_pct"] is None


class _Gia:
    the_khac = "giu nguyen"

    def __init__(self):
        self.goi = []

    def predict(self, cap, **kwargs):
        self.goi.append(cap)
        return [0.0] * len(cap)

    def khac(self):
        return "khong bam gio"


def test_dogio_bam_gio_dung_phuong_thuc_va_chuyen_qua_phan_con_lai():
    so: dict[str, list[float]] = {"xep": []}
    da_thay = []
    goc = _Gia()
    boc = d.DoGio(goc, "predict", "xep", so, khi_goi=lambda cap, **_: da_thay.extend(cap))
    assert boc.predict([["q", "a"], ["q", "b"]], batch_size=8) == [0.0, 0.0]
    assert len(so["xep"]) == 1 and so["xep"][0] >= 0
    assert da_thay == [["q", "a"], ["q", "b"]] and goc.goi == [[["q", "a"], ["q", "b"]]]
    assert boc.khac() == "khong bam gio" and boc.the_khac == "giu nguyen"
    assert len(so["xep"]) == 1, "phương thức khác không được ghi giờ"


def test_dogio_van_ghi_gio_khi_phuong_thuc_nem_loi():
    class _Hong:
        def query(self, **_):
            raise RuntimeError("chroma hỏng")

    so: dict[str, list[float]] = {"chroma": []}
    with pytest.raises(RuntimeError):
        d.DoGio(_Hong(), "query", "chroma", so).query(n_results=10)
    assert len(so["chroma"]) == 1


def test_cau_hoi_du_20_va_khong_trung():
    # #119: "ghép với 20 câu hỏi bất kỳ".
    assert len(d.CAU_HOI) == 20 and len(set(d.CAU_HOI)) == 20


def test_chi_doc_van_ban_phap_luat_cong_khai():
    # R2: không nạp gì ngoài `src/data/docs/`, và chỉ đuôi của văn bản luật.
    assert d.DOCS.parts[-3:] == ("src", "data", "docs")
    assert set(d.DUOI_PHAP_LUAT) == {".docx", ".md"}


def test_main_tu_choi_lan_khong_hop_le():
    with pytest.raises(SystemExit):
        d.main(["--lan", "0"])
