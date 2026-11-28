"""tests/test_sinh_khoa_hmac.py — công cụ sinh khoá HMAC: khoá đủ mạnh, khác nhau, được Brain nạp, không ghi đè."""

from __future__ import annotations

import re

from offline_training import sinh_khoa_hmac as sk
from src.api import hmac_auth as h


def test_hai_khoa_khac_nhau_va_du_dai():
    a, b = sk.sinh_khoa(), sk.sinh_khoa()
    assert set(a) == {"API_HMAC_KEY_BODY", "API_HMAC_KEY_N8N"}
    assert len(set(a.values())) == 2, "hai bên phải có khoá riêng để thu hồi từng bên"
    assert not (set(a.values()) & set(b.values())), "mỗi lần chạy phải ra khoá mới"
    for v in a.values():
        assert re.fullmatch(r"[0-9a-f]{64}", v) and len(v) >= h.KHOA_TOI_THIEU


def test_brain_nap_duoc_dung_key_id_va_kiem_cau_hinh_cho_qua(monkeypatch):
    for ten, v in sk.sinh_khoa().items():
        monkeypatch.setenv(ten, v)
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    assert set(h.nap_khoa()) >= {"body", "n8n"}
    h.kiem_cau_hinh()                      # không ném: tên và độ dài khoá hợp lệ


def test_in_ra_man_hinh_hai_dong_va_khong_ghi_log(capsys, caplog):
    assert sk.main([]) == 0
    ra = capsys.readouterr()
    dong = ra.out.strip().splitlines()
    assert len(dong) == 2 and all(re.fullmatch(r"API_HMAC_KEY_(BODY|N8N)=[0-9a-f]{64}", d) for d in dong)
    assert "API_HMAC_KEY" not in ra.err and not caplog.records


def test_ghi_tep_moi_va_tu_choi_ghi_de(tmp_path, capsys):
    t = tmp_path / "khoa.txt"
    assert sk.main(["--tep", str(t)]) == 0
    cu = t.read_text(encoding="utf-8")
    assert len(cu.splitlines()) == 2
    ra = capsys.readouterr()
    assert cu.split("=")[1][:16] not in ra.out + ra.err, "không in giá trị khoá khi ghi tệp"
    assert sk.main(["--tep", str(t)]) == 2
    assert t.read_text(encoding="utf-8") == cu, "tệp cũ không được bị ghi đè"
