"""
tests/test_p95_health.py — ngưỡng p95 trên /health (#9, NFR-03).

Chủ dự án chốt 12/11/2026: cửa sổ 200 lượt gần nhất, tối thiểu 30 mẫu ms/token,
dưới đó "không đủ dữ liệu" (không báo đạt). CHỈ ms/token "chưa đạt" hạ
`degraded`; tổng ms chỉ báo cáo. Lượt không biết số token bị bỏ khỏi ms/token.

Dữ liệu ở đây là lượt giả, không có nội dung khách nào (R2).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import runtime
from src.api.main import app
from src.core import metrics, nguong_p95
from src.core.metrics import TurnMetric

client = TestClient(app)


def _luot(latency_ms: int, *, tokens: int | None = 100, model_ms: int | None = None) -> None:
    metrics.record(TurnMetric(
        request_id="t", route="CHAT", ok=True, latency_ms=latency_ms,
        completion_tokens=tokens,
        model_ms=latency_ms if model_ms is None else model_ms,
    ))


# ---------------------------------------------------------------------------
# Hàm thuần
# ---------------------------------------------------------------------------

def test_p95_nearest_rank():
    assert nguong_p95.p95([]) is None
    assert nguong_p95.p95([7.0]) == 7.0
    # n=20: ceil(19)-1 = 18 -> phần tử thứ 19 (int(20×0,95)=19 sẽ ra max)
    assert nguong_p95.p95([float(i) for i in range(1, 21)]) == 19.0
    # n=30: ceil(28,5)-1 = 28 -> phần tử thứ 29
    assert nguong_p95.p95([float(i) for i in range(1, 31)]) == 29.0
    # n=10: ceil(9,5)-1 = 9 -> max
    assert nguong_p95.p95([float(i) for i in range(1, 11)]) == 10.0


def test_duoi_mau_toi_thieu_la_khong_du_du_lieu_ke_ca_khi_rat_cham():
    kl = nguong_p95.ket_luan([999.0] * 29, [99999.0] * 29, so_luot=29)
    assert kl["muc"] == nguong_p95.KHONG_DU
    assert kl["ms_moi_token"] == 999.0, "vẫn trả số để đọc, chỉ không kết luận"


def test_du_mau_dat_va_chua_dat():
    assert nguong_p95.ket_luan([40.0] * 30, [8000.0] * 30, 30)["muc"] == nguong_p95.DAT
    assert nguong_p95.ket_luan([61.0] * 30, [100.0] * 30, 30)["muc"] == nguong_p95.CHUA_DAT


def test_tong_ms_vuot_khong_lam_chua_dat():
    kl = nguong_p95.ket_luan([40.0] * 30, [9000.0] * 30, 30)
    assert kl["muc"] == nguong_p95.DAT
    assert kl["tong_dat"] is False, "tổng ms chỉ báo cáo"


def test_nguong_doc_tu_env(monkeypatch):
    monkeypatch.setenv("P95_MS_MOI_TOKEN", "30")
    monkeypatch.setenv("P95_MAU_TOI_THIEU", "5")
    kl = nguong_p95.ket_luan([40.0] * 5, [1.0] * 5, 5)
    assert kl["muc"] == nguong_p95.CHUA_DAT and kl["nguong_ms_moi_token"] == 30.0


@pytest.mark.parametrize("ten,gia_tri", [
    ("P95_CUA_SO", "abc"), ("P95_CUA_SO", "0"), ("P95_MAU_TOI_THIEU", "-1"),
])
def test_cua_so_env_hong_thi_bao_loi(monkeypatch, ten, gia_tri):
    monkeypatch.setenv(ten, gia_tri)
    with pytest.raises(ValueError):
        nguong_p95.doc_cua_so()


def test_mau_toi_thieu_lon_hon_cua_so_thi_bao_loi(monkeypatch):
    monkeypatch.setenv("P95_CUA_SO", "10")
    monkeypatch.setenv("P95_MAU_TOI_THIEU", "11")
    with pytest.raises(ValueError, match="không bao giờ đủ mẫu"):
        nguong_p95.doc_cua_so()


# ---------------------------------------------------------------------------
# Cửa sổ trong metrics
# ---------------------------------------------------------------------------

def test_luot_khong_biet_token_bi_bo_khoi_ms_moi_token():
    for _ in range(40):
        _luot(5000, tokens=None)
    kl = metrics.p95_gan_day()
    assert kl["so_luot"] == 40 and kl["so_mau_ms_moi_token"] == 0
    assert kl["muc"] == nguong_p95.KHONG_DU, "không biết token thì không kết luận, không đoán"
    assert kl["tong_ms"] == 5000


def test_token_bang_0_hoac_thieu_model_ms_bi_bo():
    _luot(100, tokens=0)
    metrics.record(TurnMetric(request_id="t", route="CHAT", ok=True, latency_ms=100,
                              completion_tokens=50, model_ms=None))
    assert metrics.p95_gan_day()["so_mau_ms_moi_token"] == 0


def test_ms_moi_token_chia_tren_model_ms_khong_phai_latency():
    # latency gồm cả tool/RAG; chia trên nó là đổ lỗi cho server
    for _ in range(30):
        _luot(9000, tokens=100, model_ms=4000)
    kl = metrics.p95_gan_day()
    assert kl["ms_moi_token"] == 40.0 and kl["muc"] == nguong_p95.DAT


def test_cua_so_chi_giu_luot_gan_nhat(monkeypatch):
    monkeypatch.setenv("P95_CUA_SO", "30")
    metrics.dat_lai_cua_so_p95()
    for _ in range(30):
        _luot(9000, tokens=100)          # 90 ms/token: chưa đạt
    assert metrics.p95_gan_day()["muc"] == nguong_p95.CHUA_DAT
    for _ in range(30):
        _luot(4000, tokens=100)          # 40 ms/token đẩy hết lượt cũ ra
    kl = metrics.p95_gan_day()
    assert kl["so_luot"] == 30 and kl["muc"] == nguong_p95.DAT


def test_tat_ghi_file_van_cap_nhat_cua_so(monkeypatch):
    monkeypatch.setattr(metrics, "METRICS_PATH", "")
    _luot(100)
    assert metrics.p95_gan_day()["so_luot"] == 1


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@pytest.fixture
def health(monkeypatch):
    monkeypatch.setenv("ENV", "LOCAL")
    monkeypatch.setattr(runtime, "memory", None, raising=False)
    return lambda: client.get("/health").json()


def test_health_vua_khoi_dong_khong_du_du_lieu_khong_ha_degraded(health):
    goc = health()
    assert goc["p95"]["muc"] == nguong_p95.KHONG_DU
    assert goc["p95"]["so_luot"] == 0 and goc["p95"]["ms_moi_token"] is None
    for _ in range(29):
        _luot(9000)                       # chậm nhưng mới 29 mẫu
    j = health()
    assert j["p95"]["muc"] == nguong_p95.KHONG_DU and j["degraded"] == goc["degraded"]


def test_health_ms_moi_token_chua_dat_ha_degraded(health):
    for _ in range(30):
        _luot(9000)                       # 90 ms/token > 60
    j = health()
    assert j["p95"]["muc"] == nguong_p95.CHUA_DAT
    assert j["degraded"] is True


def test_health_chi_tong_ms_vuot_khong_ha_degraded(health):
    goc = health()["degraded"]
    for _ in range(30):
        _luot(9000, tokens=300)           # 30 ms/token, tổng 9 giây
    j = health()
    assert j["p95"]["muc"] == nguong_p95.DAT and j["p95"]["tong_dat"] is False
    assert j["degraded"] == goc, "câu trả lời dài không phải sự cố"


def test_health_giu_khoa_body_doc(health):
    _luot(100)
    j = health()
    for k in ("status", "degraded", "engine_ready", "vision_ready", "load"):
        assert k in j
