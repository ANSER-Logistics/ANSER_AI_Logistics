"""
tests/integration/api/test_grounding_doi_khang_100.py — chốt neo số liệu trên 100+ ca đối kháng sinh bằng mã (A13, #198).

Tiêu chí của #198: "0 vi phạm trên ≥ 100 ca đối kháng". Hai chiều:
- `bia`: câu trả lời có con số KHÔNG có trong ngữ cảnh (đổi chữ số, nhân 10 hoặc 1000, đổi dấu lãi/lỗ, đơn vị sai): PHẢI bị chặn.
- `that`: cùng con số viết đúng bằng các cách người Việt viết (có/không dấu chấm, "triệu", "tỷ", làm tròn đúng): PHẢI qua (không chặn oan).
Ca nào chốt chặn chưa bắt được thì ghi `xfail(strict=True)` kèm lý do, để sửa chốt chặn là test tự đỏ và buộc người sửa gỡ xfail.
"""

from __future__ import annotations

import json

import pytest

from src.core.grounding import guard_answer

GIA_TRI = [120_000_000, 45_500_000, 3_250_000_000, 987_654_321, 15_000_000, 72_300_000, 8_400_000, 560_000_000,
           230_000_000, 64_000_000, 1_750_000_000, 91_800_000, 5_600_000, 340_000_000, 27_000_000, 812_345_678]


def _ctx(v: int, am: bool = False) -> str:
    # doanh thu KHÁC độ lớn của lãi ròng: nếu bằng nhau thì con số "đúng" nằm sẵn trong ngữ cảnh với dấu dương và phép kiểm dấu vô nghĩa
    return json.dumps({"revenue": v * 3 + 1_234_567, "net_profit": -v if am else v // 5, "orders": 37}, ensure_ascii=False)


def _cach_viet(v: int) -> list[str]:
    dem = f"{v:,}".replace(",", ".")
    ra = [f"{dem} đồng", f"{dem}đ"]
    if v % 1_000_000 == 0:
        ra.append(f"{v // 1_000_000} triệu đồng")
    if v % 1_000_000_000 == 0:
        ra.append(f"{v // 1_000_000_000} tỷ đồng")
    return ra


def _bia(v: int) -> list[tuple[str, str]]:
    """(mô tả, số bịa)"""
    dem = lambda x: f"{x:,}".replace(",", ".")      # noqa: E731
    s = str(v)
    doi_chu_so = str(int(s[0]) % 9 + 1) + s[1:]
    ra = [
        ("doi_chu_so_dau", f"{dem(int(doi_chu_so))} đồng"),
        ("nhan_10", f"{dem(v * 10)} đồng"),
        ("nhan_1000", f"{dem(v * 1000)} đồng"),
        ("chia_10", f"{dem(v // 10)} đồng"),
        ("lech_nhe_1_phan_tram", f"{dem(int(v * 1.01) + 7)} đồng"),
    ]
    return ra


CAC_CA_BIA = [(v, mo_ta, so) for v in GIA_TRI for mo_ta, so in _bia(v)]
CAC_CA_THAT = [(v, c) for v in GIA_TRI for c in _cach_viet(v)]


def test_so_ca_dat_chi_tieu_100():
    assert len(CAC_CA_BIA) + len(CAC_CA_THAT) >= 100


@pytest.mark.parametrize("v,mo_ta,so", CAC_CA_BIA, ids=[f"{m}-{v}" for v, m, _ in CAC_CA_BIA])
def test_so_bia_bi_chan(v, mo_ta, so):
    kq = guard_answer(f"Doanh thu kỳ này là {so}.", json.dumps({"revenue": v, "orders": 37}))
    assert kq.blocked, f"số bịa lọt qua chốt chặn: {so} (ngữ cảnh có {v})"


@pytest.mark.parametrize("v,viet", CAC_CA_THAT, ids=[f"{viet}" for v, viet in CAC_CA_THAT])
def test_so_dung_khong_bi_chan_oan(v, viet):
    kq = guard_answer(f"Doanh thu kỳ này là {viet}.", json.dumps({"revenue": v, "orders": 37}))
    assert not kq.blocked, f"chặn oan số đúng: {viet} ({kq.reason})"


@pytest.mark.parametrize("v", GIA_TRI)
def test_lo_noi_thanh_lai_bi_chan(v):
    """Ngữ cảnh lãi ròng ÂM, câu trả lời nói lãi dương cùng độ lớn."""
    kq = guard_answer(f"Lãi ròng là {v:,} đồng.".replace(",", "."), _ctx(v, am=True))
    assert kq.blocked, "đổi dấu lỗ thành lãi lọt qua chốt chặn"


def test_bo_dem_chan_o_health(monkeypatch):
    """Số lượt bị chặn theo lý do hiện ở /health.guard; lý do chỉ là nhóm ngắn, không chứa nội dung câu trả lời."""
    from fastapi.testclient import TestClient

    from src.api.main import app
    from src.core import metrics

    metrics.dat_lai_cua_so_p95()
    monkeypatch.setattr(metrics, "METRICS_PATH", "")
    metrics.record(metrics.TurnMetric(request_id="r1", route="GENERAL", ok=True, latency_ms=10, blocked_reason="số liệu không có trong dữ liệu: 99.999.999"))
    metrics.record(metrics.TurnMetric(request_id="r2", route="GENERAL", ok=True, latency_ms=10))
    g = TestClient(app).get("/health").json()["guard"]
    assert g["turns"] == 2 and g["blocked"] == 1
    assert list(g["by_reason"]) == ["số liệu không có trong dữ liệu"] and "99" not in str(g)
    metrics.dat_lai_cua_so_p95()
