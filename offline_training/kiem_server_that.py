"""
offline_training/kiem_server_that.py — bật Brain THẬT bằng uvicorn rồi gọi vài đường có đáp án tất định (không GPU, không model).

    python offline_training/kiem_server_that.py            # in bảng, thoát 0 nếu đạt, 1 nếu hỏng
    python offline_training/kiem_server_that.py --json     # kết quả máy đọc được, cho CI và agent

VÌ SAO CÓ FILE NÀY
------------------
Hơn hai nghìn test của repo chạy bằng `TestClient`: app nằm CÙNG tiến trình với test, nên không có gì kiểm việc `uvicorn src.api.main:app` thật
sự KHỞI ĐỘNG được và trả lời qua socket thật. Việc đó trở nên quan trọng khi phụ thuộc không còn ghim chặt (`fastapi<1` từ #30): một bản
FastAPI hay starlette mới làm app không lên được thì mọi test vẫn xanh. Bài học của Lauren Tan (Cursor, Grok): "build the lever" — cho agent một
công cụ kiểm thật, lệnh gọn, kết quả JSON, mã thoát rõ — thay vì chỉ dặn bằng văn xuôi rằng hãy kiểm.

Chỉ kiểm thứ TẤT ĐỊNH (R1): `/health` có mặt, VAT và báo giá ra đúng con số tính tay, và lược đồ OpenAPI có đủ route. KHÔNG kiểm chat hay model.
Con số báo giá (1.139.000) là ví dụ của tài liệu người mới, tính tay: giá nhà xe 1.000.000, dầu 25.000 lên 27.500 (+10%), hệ số 0,35 thành +3,5%,
biên 10%, làm tròn tới nghìn.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

VAT_VAO = {"items": [{"name": "Hàng A", "price": 1_000_000, "qty": 2, "is_reduced_vat": False}],
           "prices_include_vat": False, "stated_total": 2_200_000}
QUOTE_VAO = {"carrier_cost": 1_000_000, "current_fuel_price": 27_500,
             "pricing_rule": {"base_margin_pct": 10, "fuel_baseline_price": 25_000}}
SO_ROUTE_TOI_THIEU = 20


def cong_trong() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def goi(port: int, duong: str, than: dict | None = None, han: float = 15.0) -> tuple[int, Any]:
    url = f"http://127.0.0.1:{port}{duong}"
    req = urllib.request.Request(url, data=json.dumps(than).encode() if than is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if than is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=han) as r:  # noqa: S310 (chỉ gọi 127.0.0.1)
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]


def danh_gia(health: Any, vat: Any, quote: Any, openapi: Any) -> list[dict[str, Any]]:
    """Hàm THUẦN: nhận bốn phản hồi (đã giải mã) và trả danh sách kiểm. Tách ra để test được không cần bật server."""
    ra: list[dict[str, Any]] = []

    def them(ten: str, ok: bool, chi_tiet: str) -> None:
        ra.append({"ten": ten, "ok": bool(ok), "chi_tiet": chi_tiet})

    them("health", isinstance(health, dict) and health.get("status") == "ok", f"status={getattr(health, 'get', lambda k: None)('status')}")
    them("vat_2_trieu_thue_10", isinstance(vat, dict) and vat.get("calculated_total") == 2_200_000 and vat.get("is_valid") is True,
         f"calculated_total={vat.get('calculated_total') if isinstance(vat, dict) else vat}")
    gia = quote.get("quote", {}).get("quoted_price") if isinstance(quote, dict) else None
    them("bao_gia_1_139_000", gia == 1_139_000, f"quoted_price={gia}")
    paths = openapi.get("paths", {}) if isinstance(openapi, dict) else {}
    them("openapi_du_route", len(paths) >= SO_ROUTE_TOI_THIEU - 2 and "/tools/vat" in paths, f"{len(paths)} đường dẫn")
    return ra


def chay(han_khoi_dong: float = 60.0) -> dict[str, Any]:
    port = cong_trong()
    moi_truong = {**os.environ, "ENV": "LOCAL", "PYTHONUTF8": "1"}
    log = Path(tempfile.gettempdir()) / "anser_kiem_server_that.log"   # ngoài repo: không bao giờ bị commit
    with open(log, "w", encoding="utf-8") as f:
        p = subprocess.Popen([sys.executable, "-m", "uvicorn", "src.api.main:app", "--port", str(port), "--log-level", "warning"],
                             cwd=ROOT, env=moi_truong, stdout=f, stderr=subprocess.STDOUT)
        try:
            t0 = time.perf_counter()
            health: Any = None
            while time.perf_counter() - t0 < han_khoi_dong:
                if p.poll() is not None:
                    break
                try:
                    ma, health = goi(port, "/health", han=3.0)
                    if ma == 200:
                        break
                except (urllib.error.URLError, OSError, ValueError):
                    time.sleep(0.5)
            else:
                health = None
            khoi_dong_s = round(time.perf_counter() - t0, 1)
            if not isinstance(health, dict):
                return {"ok": False, "khoi_dong_s": khoi_dong_s, "loi": "server không lên hoặc /health không trả JSON", "log": str(log),
                        "kiem": [{"ten": "khoi_dong", "ok": False, "chi_tiet": f"quá {han_khoi_dong:g}s hoặc tiến trình thoát"}]}
            _, vat = goi(port, "/tools/vat", VAT_VAO)
            _, quote = goi(port, "/tools/quote", QUOTE_VAO)
            _, openapi = goi(port, "/openapi.json")
            kiem = danh_gia(health, vat, quote, openapi)
            return {"ok": all(k["ok"] for k in kiem), "khoi_dong_s": khoi_dong_s, "kiem": kiem, "log": str(log)}
        finally:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="in kết quả dạng JSON")
    ap.add_argument("--han-khoi-dong", type=float, default=60.0, help="số giây chờ server lên (mặc định 60)")
    a = ap.parse_args(argv)
    kq = chay(a.han_khoi_dong)
    if a.json:
        print(json.dumps(kq, ensure_ascii=False, indent=1))
    else:
        print(f"Khởi động: {kq.get('khoi_dong_s')}s | log: {kq.get('log')}")
        for k in kq.get("kiem", []):
            print(f"  {'OK ' if k['ok'] else 'HỎNG'}  {k['ten']}: {k['chi_tiet']}")
        print("ĐẠT" if kq["ok"] else "KHÔNG ĐẠT")
    return 0 if kq["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
