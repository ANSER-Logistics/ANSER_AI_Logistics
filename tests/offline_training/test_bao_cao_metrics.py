"""
tests/test_bao_cao_metrics.py — báo cáo tổng hợp ai_metrics_log: chỉ số đếm, không nội dung (R2), thiếu thì nói thiếu (R1).
"""

from __future__ import annotations

import json

from offline_training import bao_cao_metrics as bc
from src.core.metrics import TurnMetric

CANARY = "Cong ty Minh Long"


def _dong(**k) -> dict:
    goc = {"request_id": "r", "route": "GENERAL", "ok": True, "latency_ms": 1000, "ts": "2026-11-24T10:00:00+00:00"}
    return {**goc, **k}


def _ghi(tmp_path, dong, them: str = ""):
    p = tmp_path / "m.jsonl"
    p.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in dong) + them, encoding="utf-8")
    return p


def test_khong_in_noi_dung_o_bat_ky_truong_nao(tmp_path, capsys):
    dong = [
        _dong(message=CANARY, extra={"q": CANARY}, user_id=918273, store_id=564738, request_id=CANARY, tool_plan=CANARY + " " + "x" * 60,
              error=f"ValueError: khong doc duoc {CANARY}", blocked_reason=f"bịa số: {CANARY} 3.400.000"),
        _dong(route=f"{CANARY}\nxuong dong", ok=False, error=f"{CANARY} hong", blocked_reason=f"{CANARY} " + "y" * 80, router_method=f"{CANARY}\n"),
    ]
    p = _ghi(tmp_path, dong)
    for them in ([], ["--json"]):
        assert bc.main([str(p), *them]) == 0
        ra = capsys.readouterr().out
        for cam in ("Minh Long", "918273", "564738", "3.400.000", "xuong dong", "yyyy"):
            assert cam not in ra, (cam, ra)
        assert "ValueError" in ra and "bịa số" in ra and bc.KHAC in ra


def test_truong_cua_turnmetric_duoc_doc_dung_ten():
    """Đổi tên trường ở `TurnMetric` mà không đổi ở đây thì báo cáo lặng lẽ ra "không biết"."""
    ten = set(TurnMetric.__dataclass_fields__)
    for t in ("route", "ok", "latency_ms", "blocked_reason", "error", "asked_back", "workflow_valid", "workflow_retried", "web_fallback",
              "completion_tokens", "model_ms", "router_method", "tool_plan", "ts"):
        assert t in ten, t


def test_thieu_thi_noi_khong_biet_khong_tinh_la_0(tmp_path, capsys):
    p = _ghi(tmp_path, [_dong(latency_ms=None, ok=None)])
    assert bc.main([str(p), "--json"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["chung"]["p95_ms"] is None and r["chung"]["p95_ms_moi_token"] is None
    assert r["chung"]["dat"] == {"dung": 0, "biet": 0}
    assert bc.main([str(p)]) == 0
    md = capsys.readouterr().out
    assert "không biết" in md and "0%" not in md


def test_dem_dung_theo_nhanh_va_muc_dang_xem(tmp_path, capsys):
    dong = [_dong(route="TECHNICAL", ok=False, workflow_valid=False, workflow_retried=True, latency_ms=5000),
            _dong(route="TECHNICAL", ok=True, workflow_valid=True, workflow_retried=False, latency_ms=2000),
            _dong(blocked_reason="bịa số: 5", asked_back=True, completion_tokens=100, model_ms=3000)]
    p = _ghi(tmp_path, dong, them="khong phai json\n[1,2]\n")
    assert bc.main([str(p), "--json"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["dong_hong"] == 2 and r["chung"]["luot"] == 3
    t = r["theo_nhanh"]["TECHNICAL"]
    assert t["luot"] == 2 and t["dat"] == {"dung": 1, "biet": 2} and t["workflow_hop_le"] == {"dung": 1, "biet": 2} and t["p95_ms"] == 5000
    assert r["theo_nhanh"]["GENERAL"]["p95_ms_moi_token"] == 30.0
    assert r["ly_do_chan"] == {"bịa số": 1}
    xem = " | ".join(r["dang_xem"])
    assert "TECHNICAL: 1/2 lượt không đạt" in xem and "GENERAL: 1/1 lượt bị chốt chặn" in xem
    assert "không đủ mẫu" in xem and "2 dòng nhật ký không đọc được" in xem


def test_loc_theo_ngay(tmp_path, capsys):
    p = _ghi(tmp_path, [_dong(ts="2026-11-01T00:00:00+00:00"), _dong(ts="2026-11-24T00:00:00+00:00")])
    assert bc.main([str(p), "--tu", "2026-11-20", "--json"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["chung"]["luot"] == 1 and r["tu_ngay"] == "2026-11-24"


def test_khong_co_du_lieu_thi_ma_2_khong_bao_la_on(tmp_path, capsys):
    assert bc.main([str(tmp_path / "khong_co.jsonl")]) == 2
    assert bc.main([str(_ghi(tmp_path, []))]) == 2
    ra = capsys.readouterr()
    assert ra.out == "" and "CHƯA CÓ DỮ LIỆU" in ra.err


def test_dong_that_do_metrics_ghi_ra_doc_duoc(tmp_path, monkeypatch, capsys):
    from src.core import metrics

    p = tmp_path / "that.jsonl"
    monkeypatch.setattr(metrics, "METRICS_PATH", str(p))
    metrics.record(TurnMetric(request_id="a", route="GENERAL", ok=True, latency_ms=12))
    monkeypatch.setenv("AI_METRICS_PATH", str(p))
    assert bc.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["chung"]["luot"] == 1
