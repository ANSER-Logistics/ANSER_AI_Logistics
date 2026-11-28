"""
tests/offline_training/test_demo_mot_may.py — phần THUẦN của bộ demo một máy (`offline_training/demo_mot_may/`).

Bật cả chuỗi Body + database thì cần Node và repo Body nên không chạy trong CI; ở đây khoá những thứ làm buổi demo hỏng mà không cần chạy: dữ liệu gieo không bao giờ bán quá tồn (Body trả 409),
ngày lùi tháng đúng (kể cả qua năm), đáp án lãi gộp bỏ hàng chưa có giá vốn, hàng mẫu cần gỡ không trùng hàng gieo, và không script nào ghim đường dẫn máy của một người.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from offline_training.demo_mot_may import body_api
from offline_training.demo_mot_may import gieo_du_lieu_demo as g

THU_MUC = Path(__file__).resolve().parents[2] / "offline_training" / "demo_mot_may"


def test_khong_ban_qua_ton_nen_body_khong_tra_409():
    """Tồn ban đầu cộng phiếu nhập phải đủ cho mọi hoá đơn, theo đúng thứ tự gieo: phiếu nhập trước, rồi hoá đơn."""
    ton = [h[3] for h in g.HANG]
    for i, q, _, _ in g.NHAP:
        ton[i] += q
    tat_ca = [dong for lui in sorted(g.LICH, reverse=True) for _, dong in g.LICH[lui]] + [dong for _, _, dong in g.GAN_DAY]
    for dong in tat_ca:
        for i, q in dong:
            ton[i] -= q
            assert ton[i] >= 0, (g.HANG[i][0], ton[i])
    assert any(t < 20 for t in ton), "phải có một mặt hàng dưới ngưỡng 20 để trang chủ hiện cảnh báo sắp hết"


def test_co_hang_chua_biet_gia_von_va_hang_do_duoc_ban():
    """Báo cáo phải nói 'chưa đủ giá vốn': cần ít nhất một mặt hàng không có giá vốn và nó thật sự được bán."""
    chua_biet = {i for i, h in enumerate(g.HANG) if h[5] is None}
    assert chua_biet
    ban = {i for lui in g.LICH for _, dong in g.LICH[lui] for i, _ in dong}
    assert ban & chua_biet


def test_hang_mau_body_can_go_khong_trung_hang_gieo():
    assert not set(g.HANG_MAU_BODY) & {h[0] for h in g.HANG}


@pytest.mark.parametrize("hom_nay,lui,thang_mong", [
    (dt.date(2026, 11, 28), 1, (2026, 10)),
    (dt.date(2027, 1, 5), 1, (2026, 12)),
    (dt.date(2027, 2, 15), 5, (2026, 9)),
])
def test_ngay_lui_thang_dung_ke_ca_qua_nam(hom_nay, lui, thang_mong):
    for thu_tu in range(4):
        ngay = g.ngay_cua(lui, thu_tu, hom_nay)
        assert (ngay.year, ngay.month) == thang_mong and 1 <= ngay.day <= 27


def test_ban_gan_day_nam_trong_bay_ngay():
    """Các ô '7 ngày qua' của Body chỉ có số khi hoá đơn nằm trong 7 ngày gần nhất."""
    assert all(0 <= cach <= 6 for cach, _, _ in g.GAN_DAY) and all(0 <= cach <= 6 for *_, cach in g.NHAP)


def test_goc_demo_doc_tu_bien_moi_truong(monkeypatch, tmp_path):
    monkeypatch.setenv("ANSER_DEMO", str(tmp_path))
    assert body_api.thu_muc_demo() == tmp_path
    monkeypatch.delenv("ANSER_DEMO")
    assert body_api.thu_muc_demo() == Path.home() / "anser-demo"


def test_khong_script_nao_ghim_duong_dan_may_ca_nhan():
    for f in THU_MUC.iterdir():
        if f.is_file():
            noi_dung = f.read_text(encoding="utf-8-sig")
            assert "D:\\anser-demo" not in noi_dung and "D:/anser-demo" not in noi_dung and "sonkh" not in noi_dung, f.name


def test_file_powershell_co_bom_de_windows_powershell_doc_dung_tieng_viet():
    """Windows PowerShell 5.1 đọc tệp UTF-8 không BOM như ANSI: chuỗi tiếng Việt thành rác."""
    for f in THU_MUC.glob("*.ps1"):
        assert f.read_bytes().startswith(b"\xef\xbb\xbf"), f.name
