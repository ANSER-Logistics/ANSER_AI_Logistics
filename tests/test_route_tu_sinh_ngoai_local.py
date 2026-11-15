"""
tests/test_route_tu_sinh_ngoai_local.py — `/docs`, `/redoc`, `/openapi.json` chỉ có ở ENV=LOCAL (BR-34, R2).

Ba route do FastAPI tự sinh không đi qua `auth_guard`. Có `API_AUTH_TOKEN` rồi mà chúng vẫn trả 200,
và `/openapi.json` lộ toàn bộ lược đồ đầu vào của mọi route cho người không có token. `tests/test_auth_bao_phu.py`
cố ý bỏ ba route này khỏi bảng quét (chúng ở `MO_CO_Y`), nên không test nào thấy.

`app` được dựng lúc import, nên mỗi ca chạy trong một tiến trình con với `ENV` riêng; đổi `ENV` rồi `reload`
trong tiến trình test sẽ để lại module đã nạp ở trạng thái lẫn lộn cho các test sau.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parent.parent
TOKEN = "token-thu-nghiem"

_MA = """
import json
from fastapi.testclient import TestClient
from src.api.main import app
c = TestClient(app)
kq = {p: c.get(p).status_code for p in ("/health", "/docs", "/redoc", "/openapi.json")}
kq["tools_khong_token"] = c.post("/tools/vat", json={}).status_code
print(json.dumps(kq))
"""


def _chay(env: str) -> dict[str, int]:
    import os

    moi = {**os.environ, "ENV": env, "API_AUTH_TOKEN": TOKEN}
    if env == "SERVER":
        moi["VLLM_BASE_URL"] = "http://vllm-text:8001"
    r = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(GOC)!r})\n" + _MA],
                       cwd=GOC, env=moi, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("env", ["SERVER", "GPU", "COLAB", "", "lcoal"])
def test_ngoai_local_ba_route_tu_sinh_bi_tat_va_health_van_song(env):
    kq = _chay(env)
    for duong in ("/docs", "/redoc", "/openapi.json"):
        assert kq[duong] in (401, 404), f"ENV={env!r}: {duong} -> {kq[duong]} (lộ lược đồ khi có token)"
    assert kq["/health"] == 200, kq
    assert kq["tools_khong_token"] == 401, "đường bảo vệ thật phải còn nguyên"


def test_local_van_giu_trang_tai_lieu_cho_may_dev():
    kq = _chay("LOCAL")
    assert kq["/openapi.json"] == 200 and kq["/docs"] == 200 and kq["/redoc"] == 200
