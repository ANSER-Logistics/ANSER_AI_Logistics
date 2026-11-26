"""tests/offline_training/test_chay_nhu_ci.py — script chạy-như-CI tìm đúng repo Body và không đụng Redis khi đã có URL."""

from __future__ import annotations

from offline_training import chay_nhu_ci as c


def test_tim_body_uu_tien_bien_moi_truong(monkeypatch, tmp_path):
    monkeypatch.setenv("ANSER_BODY_DIR", str(tmp_path / "noi-khac"))
    assert c.tim_body() == tmp_path / "noi-khac"


def test_tim_body_nhan_repo_canh_ben_theo_brain_ts_khong_theo_ten(monkeypatch, tmp_path):
    monkeypatch.delenv("ANSER_BODY_DIR", raising=False)
    brain = tmp_path / "brain"
    brain.mkdir()
    (tmp_path / "repo-khac").mkdir()
    body = tmp_path / "ten-bat-ky"
    (body / "frontend" / "src" / "server").mkdir(parents=True)
    (body / "frontend" / "src" / "server" / "brain.ts").write_text("", encoding="utf-8")
    monkeypatch.setattr(c, "ROOT", brain)
    assert c.tim_body() == body
    (body / "frontend" / "src" / "server" / "brain.ts").unlink()
    assert c.tim_body() is None


def test_redis_test_url_da_dat_thi_dung_nguyen_khong_goi_docker(monkeypatch):
    monkeypatch.setenv("REDIS_TEST_URL", "redis://may-khac:6379/15")
    monkeypatch.setattr(c.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("không được gọi docker")))
    assert c.chuan_bi_redis() == "redis://may-khac:6379/15"
