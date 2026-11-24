"""
offline_training/chay_nhu_ci.py — chạy ĐÚNG các bước của `ci.yml` trên máy dev bằng một lệnh, cộng thêm phần CI không chạy được.

    python offline_training/chay_nhu_ci.py              # ruff, mypy, pytest (có Redis, có Body), server thật
    python offline_training/chay_nhu_ci.py -- -x -k vat  # mọi thứ sau `--` chuyển nguyên cho pytest

VÌ SAO CÓ FILE NÀY
------------------
Trên máy dev, `pytest` trần bỏ qua những test cần Redis thật (`REDIS_TEST_URL`) và test hợp đồng Body (`ANSER_BODY_DIR`), nên "xanh ở máy
mình" chạy ít hơn CI, và test Body thì CI không chạy bao giờ. Script này:

- Redis: dùng `REDIS_TEST_URL` nếu đã đặt; không thì dựng container `redis:7` (cùng ảnh CI) tên `anser-redis-test` ở cổng 6380, KHÔNG phải
  6379, để không đụng Redis riêng của ai đang chạy. Container để chạy tiếp cho lần sau; tắt bằng `docker rm -f anser-redis-test`.
  Không có Docker thì nói rõ và chạy tiếp, các test Redis sẽ skip.
- Body: tìm repo Body nằm cạnh repo này (thư mục có `frontend/src/server/brain.ts`), hoặc dùng `ANSER_BODY_DIR` nếu đã đặt.
- Không bật cổng `KIEM_SKIP_DA_KHAI`: cổng đó so số skip với môi trường CI; ở đây chạy NHIỀU test hơn CI nên số skip khác là đúng.

Mã thoát 1 nếu bất kỳ bước nào hỏng; bước sau vẫn chạy để thấy hết lỗi trong một lần.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REDIS_TEN = "anser-redis-test"
REDIS_CONG = 6380


def _redis_song(url: str) -> bool:
    try:
        import redis
    except ImportError:
        return False
    try:
        return bool(redis.Redis.from_url(url, socket_connect_timeout=1).ping())
    except redis.RedisError:
        return False


def chuan_bi_redis() -> str | None:
    """URL Redis cho test, hoặc None (kèm lời giải thích đã in) khi không dựng được."""
    if url := os.getenv("REDIS_TEST_URL", "").strip():
        return url
    url = f"redis://localhost:{REDIS_CONG}/15"
    if _redis_song(url):
        return url
    docker = shutil.which("docker")
    if docker is None or subprocess.run([docker, "info"], capture_output=True).returncode != 0:
        print("⚠ Không có Docker đang chạy (mở Docker Desktop) và chưa đặt REDIS_TEST_URL: các test Redis sẽ skip.")
        return None
    subprocess.run([docker, "rm", "-f", REDIS_TEN], capture_output=True)
    r = subprocess.run([docker, "run", "-d", "--rm", "--name", REDIS_TEN, "-p", f"{REDIS_CONG}:6379", "redis:7"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"⚠ Không dựng được container Redis: {r.stderr.strip()}")
        return None
    for _ in range(30):
        if _redis_song(url):
            print(f"✓ Redis chạy trong container {REDIS_TEN} ({url})")
            return url
        time.sleep(0.5)
    print("⚠ Container Redis đã chạy nhưng không trả lời ping sau 15 giây.")
    return None


def tim_body() -> Path | None:
    if dat_san := os.getenv("ANSER_BODY_DIR", "").strip():
        return Path(dat_san)
    for d in sorted(ROOT.parent.iterdir()):
        if d != ROOT and (d / "frontend" / "src" / "server" / "brain.ts").is_file():
            return d
    return None


def main(argv: list[str]) -> int:
    them_pytest = argv[argv.index("--") + 1:] if "--" in argv else []
    env = {**os.environ, "ENV": "LOCAL"}
    if url := chuan_bi_redis():
        env["REDIS_TEST_URL"] = url
    if body := tim_body():
        env["ANSER_BODY_DIR"] = str(body)
        print(f"✓ Repo Body: {body}")
    else:
        print("⚠ Không thấy repo Body cạnh repo này: test hợp đồng Body sẽ skip.")

    py = sys.executable
    buoc = [  # cùng thứ tự và phạm vi với ci.yml
        ("ruff", [py, "-m", "ruff", "check", "src", "tests", "offline_training", "launch_demo.py",
                  "execute_backup_and_push.py"]),
        ("mypy", [py, "-m", "mypy", "src", "offline_training"]),
        ("pytest", [py, "-m", "pytest", "-q", "-rs", *them_pytest]),
        ("server thật", [py, "offline_training/kiem_server_that.py"]),
    ]
    ket_qua = []
    for ten, lenh in buoc:
        print(f"\n=== {ten} ===", flush=True)
        ket_qua.append((ten, subprocess.run(lenh, cwd=ROOT, env=env).returncode))

    print("\n=== Tóm tắt ===")
    for ten, ma in ket_qua:
        print(f"{'✓' if ma == 0 else '✗'} {ten}" + ("" if ma == 0 else f" (mã {ma})"))
    return 0 if all(ma == 0 for _, ma in ket_qua) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
