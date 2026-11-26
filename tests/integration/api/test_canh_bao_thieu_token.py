"""
tests/integration/api/test_canh_bao_thieu_token.py — Brain chạy như bản triển khai mà không có `API_AUTH_TOKEN` thì phải LỘ RA.

`require_api_token` bỏ qua mọi kiểm tra khi token rỗng, nên token trống = mọi route nghiệp vụ mở cho bất kỳ ai
tới được địa chỉ của Brain. Sự cố 13/08/2026: compose đặt sai TÊN biến, Brain chạy mở mà không ai thấy: nó không
làm gì lỗi. Từ đây: log CRITICAL lúc khởi động và `/health.degraded` (kèm `auth_missing_in_deployment`).

TỪ 20/11/2026 (chủ dự án chốt: "Có") Brain TỪ CHỐI KHỞI ĐỘNG khi thiếu token ở mọi ENV khác LOCAL. Trước đó chỉ cảnh báo. Log CRITICAL và
`/health.degraded` vẫn còn: lời gọi không qua lifespan (TestClient không dùng `with`) vẫn thấy chúng.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from src.api import dependencies as deps
from src.api.main import app


@pytest.mark.parametrize("env, token, mong_doi", [
    ("LOCAL", "", False),          # máy dev không token: chủ ý
    ("local", "", False),          # không phân biệt hoa thường
    ("LOCAL", "x", False),
    ("GPU", "", True),
    ("SERVER", "", True),
    ("COLAB", "", True),
    ("GPU", "x", False),
    ("", "", True),                # ENV rỗng: coi là triển khai (fail-closed, như BR-34)
    ("LOKAL", "", True),           # gõ sai: báo thừa còn hơn im lặng bỏ qua một cổng mở
])
def test_thieu_token_o_trien_khai(monkeypatch, env, token, mong_doi):
    monkeypatch.setenv("ENV", env)
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", token)
    assert deps.thieu_token_o_trien_khai() is mong_doi


def _health(monkeypatch, env, token):
    monkeypatch.setenv("ENV", env)
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", token)
    return TestClient(app).get("/health").json()


def test_health_thieu_token_o_trien_khai_keo_degraded_len(monkeypatch):
    j = _health(monkeypatch, "GPU", "")
    assert j["auth_missing_in_deployment"] is True and j["degraded"] is True


def test_health_co_token_thi_khong_bao(monkeypatch):
    j = _health(monkeypatch, "GPU", "mot-token")
    assert j["auth_missing_in_deployment"] is False
    assert j["degraded"] is False, "mọi thứ khác đều khoẻ trong test: chỉ token mới được kéo degraded"


def test_health_may_dev_khong_token_khong_bi_bao_oan(monkeypatch):
    j = _health(monkeypatch, "LOCAL", "")
    assert j["auth_missing_in_deployment"] is False and j["degraded"] is False


def test_health_van_con_nam_khoa_body_doc(monkeypatch):
    j = _health(monkeypatch, "GPU", "")
    for k in ("status", "degraded", "engine_ready", "vision_ready", "load", "auth_enabled"):
        assert k in j, f"khoá Body đọc đã mất: {k}"


@pytest.mark.parametrize("env", ["GPU", "SERVER", "COLAB", "", "LOKAL"])
def test_khoi_dong_tu_choi_khi_thieu_token_o_trien_khai(monkeypatch, caplog, env):
    monkeypatch.setenv("ENV", env)
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", "")
    caplog.set_level(logging.INFO, logger="projecta.api")
    with pytest.raises(RuntimeError, match="Từ chối khởi động"):
        with TestClient(app):                  # vào `with` mới chạy lifespan
            pass
    ban = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(ban) == 1 and "API_AUTH_TOKEN" in ban[0].getMessage()


@pytest.mark.parametrize("env, token", [("LOCAL", ""), ("local", ""), ("LOCAL", "x"), ("GPU", "mot-token"), ("SERVER", "mot-token")])
def test_khoi_dong_khong_log_critical_khi_khong_co_van_de(monkeypatch, caplog, env, token):
    monkeypatch.setenv("ENV", env)
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", token)
    caplog.set_level(logging.INFO, logger="projecta.api")
    with TestClient(app):
        pass
    assert not [r for r in caplog.records if r.levelno == logging.CRITICAL]


def test_co_token_o_trien_khai_thi_khoi_dong_va_route_van_chan_dung(monkeypatch):
    """Đối chứng của phép từ chối: có token thì khởi động bình thường, route nghiệp vụ đòi token, `/health` vẫn mở."""
    monkeypatch.setenv("ENV", "GPU")
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", "mot-token")
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/tools").status_code == 401
        assert c.get("/tools", headers={"X-API-Token": "mot-token"}).status_code == 200


def test_may_dev_local_khong_token_van_khoi_dong(monkeypatch):
    monkeypatch.setenv("ENV", "LOCAL")
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", "")
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/tools").status_code == 200
