"""Gọi API của Body như trình duyệt: đăng nhập MỘT lần (Body giới hạn 10 lần/15 phút, tính cả lần đúng), tự giữ cookie (cookie `Secure` của bản production không gửi qua http bằng CookieJar)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Optional

# Route đọc ảnh hoá đơn của Body từ chối kiểu không phải ảnh; tệp khác gửi như trình duyệt gửi tệp lạ.
_KIEU_ANH = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def kieu_noi_dung(ten_tep: str) -> str:
    return _KIEU_ANH.get(Path(ten_tep).suffix.lower(), "application/octet-stream")


def thu_muc_demo() -> Path:
    """Gốc của bộ demo cục bộ (Body clone, database, log): biến `ANSER_DEMO`, mặc định `~/anser-demo`. Nằm NGOÀI mọi repo."""
    return Path(os.environ.get("ANSER_DEMO") or Path.home() / "anser-demo")


# Tài khoản demo công khai, có sẵn trên trang đăng nhập của Body (chỉ tồn tại khi ENABLE_STARTUP_SEED=true, dữ liệu hư cấu).
DEMO_EMAIL, DEMO_PASSWORD = "demo@anser.dev", "demo1234"


class Body:
    def __init__(self, url: str):
        self.url, self.cookie = url.rstrip("/"), ""

    def goi(self, method: str, duong: str, than: Any = None, *, files: Optional[dict[str, tuple[str, bytes]]] = None, han: float = 60.0) -> tuple[int, Any]:
        dau: dict[str, str] = {}
        byte: Optional[bytes] = None
        if files:
            bien = "----anserdemo" + uuid.uuid4().hex
            phan = [
                f'--{bien}\r\nContent-Disposition: form-data; name="{ten}"; filename="{ten_tep}"\r\nContent-Type: {kieu_noi_dung(ten_tep)}\r\n\r\n'.encode() + nd + b"\r\n"
                for ten, (ten_tep, nd) in files.items()
            ]
            byte = b"".join(phan) + f"--{bien}--\r\n".encode()
            dau["Content-Type"] = f"multipart/form-data; boundary={bien}"
        elif than is not None:
            byte = json.dumps(than).encode()
            dau["Content-Type"] = "application/json"
        if self.cookie:
            dau["Cookie"] = self.cookie
        req = urllib.request.Request(self.url + duong, data=byte, headers=dau, method=method)
        try:
            with urllib.request.urlopen(req, timeout=han) as r:  # noqa: S310 (chỉ gọi máy cục bộ)
                sc = r.headers.get("Set-Cookie")
                if sc:
                    self.cookie = sc.split(";")[0]
                tho = r.read().decode("utf-8", "replace")
                try:
                    return r.status, json.loads(tho)
                except ValueError:
                    return r.status, tho
        except urllib.error.HTTPError as e:
            tho = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(tho)
            except ValueError:
                return e.code, tho[:200]
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            return 0, f"{type(e).__name__}: {e}"[:200]

    def dang_nhap(self) -> None:
        ma, r = self.goi("POST", "/api/auth/login", {"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        if ma != 200 or not self.cookie:
            raise SystemExit(f"Đăng nhập demo hỏng: http={ma} {r}")
