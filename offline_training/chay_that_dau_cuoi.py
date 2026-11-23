"""
offline_training/chay_that_dau_cuoi.py — MỘT LẦN CHẠY THẬT đầu cuối trên Colab, ra một bảng đạt/trượt (A7, brain#325).

VÌ SAO CÓ
---------
"Một lần chạy thật" là điều kiện của mọi mục "B, chạy thật" trên bảng 23 năng lực (#213) và của AGENTS §6.0 ("tiêu chí cho `main` là bảy mục ở §7 cộng với một lần chạy thật"), mà chưa từng có định nghĩa: ai
chạy gì, theo thứ tự nào, đạt khi nào. Bốn script đã có sẵn, mỗi cái kiểm một lớp; file này chỉ gọi chúng theo một thứ tự cố định, đọc kết quả bằng đúng tiêu chí của từng cái, và ghi MỘT bảng.

THỨ TỰ (mỗi bước có tiêu chí đạt ghi sẵn; không bước nào tự nới)
    1. kiem_server_that   uvicorn THẬT khởi động, HMAC enforce (ký đúng thì vào, không ký 401, token cũ không vào), VAT và báo giá ra đúng con số tính tay. Không cần GPU hay Brain đang chạy.
    2. suc_khoe_truoc     GET /health của Brain đang chạy: status "ok", không degraded.
    3. chay_thu_live      ba câu qua đúng đường Body đi: route và tool_plan THẬT đọc từ `ai_metrics.jsonl`, không đoán qua câu trả lời.
    4. benchmark_tich_hop sáu ca nội dung qua HTTP (định tuyến, công cụ tất định, model, chốt chặn neo số) và độ trễ.
    5. suc_khoe_sau_tai   GET /health lần nữa SAU tải: Brain vẫn "ok" (không tụt degraded vì mạch ngắt, hàng đợi hay VRAM).

KHÔNG CHẠY KHÔNG PHẢI ĐẠT
-------------------------
Bước không chạy được (thiếu URL, Brain không lên, bị `--bo-qua`) ghi là "KHÔNG CHẠY"/"BỎ QUA" và KHÔNG tính là đạt: mã thoát 2 (chưa đủ). Có bước TRƯỢT thì mã thoát 1. Chỉ khi cả năm bước ĐẠT mới thoát 0.

CHẠY (Brain đã lên bằng `bat_lai_brain.py` ở ô riêng, xem RUNBOOK §11):
    BRAIN_URL=https://xxx.ngrok-free.dev BRAIN_API_TOKEN=... AI_METRICS_PATH=/content/ai_metrics.jsonl \\
        python offline_training/chay_that_dau_cuoi.py --json ket_qua_chay_that.json
    python offline_training/chay_that_dau_cuoi.py --chi kiem_server_that          # chỉ bước không cần GPU
    python offline_training/chay_that_dau_cuoi.py --bo-qua benchmark_tich_hop     # bỏ qua có chủ ý (mã thoát 2)

Bảng và JSON KHÔNG chứa token. URL chỉ in tên máy.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse

GOC = Path(__file__).resolve().parent.parent
DAT, TRUOT, KHONG_CHAY, BO_QUA = "dat", "truot", "khong_chay", "bo_qua"


@dataclass
class Buoc:
    khoa: str
    ten: str
    tieu_chi: str
    can_brain: bool
    han_giay: int
    lenh: Optional[list[str]] = None          # None = kiểm /health bằng HTTP
    phan_tich: Callable[[int, str], tuple[bool, str]] = field(default=lambda ma, ra: (ma == 0, f"mã thoát {ma}"))


@dataclass
class KetQua:
    khoa: str
    ten: str
    tieu_chi: str
    trang_thai: str
    chi_tiet: str
    giay: float = 0.0


def _phan_tich_kiem_server(ma: int, ra: str) -> tuple[bool, str]:
    try:
        kq = json.loads(ra)
    except ValueError:
        return False, f"không đọc được JSON (mã thoát {ma})"
    kiem = kq.get("kiem") or []
    dat = [k for k in kiem if k.get("ok")]
    hong = [k.get("ten") for k in kiem if not k.get("ok")]
    chi_tiet = f"{len(dat)}/{len(kiem)} kiểm đạt" + (f"; hỏng: {', '.join(map(str, hong[:4]))}" if hong else "")
    return bool(kq.get("ok")) and ma == 0 and bool(kiem), chi_tiet


def _phan_tich_tich_hop(ma: int, ra: str) -> tuple[bool, str]:
    ca = re.search(r"Ca đạt hoàn toàn\s*:\s*(\d+)\s*/\s*(\d+)", ra)
    p95 = re.search(r"Độ trễ phân vị 95:\s*([\d.]+)s", ra)
    chi_tiet = (f"{ca.group(1)}/{ca.group(2)} ca đạt hoàn toàn" if ca else f"mã thoát {ma}") + (f"; p95 {p95.group(1)}s" if p95 else "")
    return ma == 0, chi_tiet


def _phan_tich_chay_thu(ma: int, ra: str) -> tuple[bool, str]:
    sai = re.search(r"=> (\d+) MỤC SAI", ra)
    return ma == 0, ("đường đi đúng" if ma == 0 else (f"{sai.group(1)} mục sai" if sai else f"mã thoát {ma}"))


def cac_buoc() -> list[Buoc]:
    py = sys.executable
    dau = str(GOC / "offline_training")
    return [
        Buoc("kiem_server_that", "uvicorn thật + HMAC enforce", "mọi kiểm đạt, ok=true", False, 180,
             [py, f"{dau}/kiem_server_that.py", "--json", "--hmac"], _phan_tich_kiem_server),
        Buoc("suc_khoe_truoc", "/health trước tải", 'status "ok", degraded=false', True, 30),
        Buoc("chay_thu_live", "ba câu qua đúng đường Body đi", "route và tool_plan đúng, tool đã chạy", True, 900,
             [py, f"{dau}/chay_thu_live.py"], _phan_tich_chay_thu),
        Buoc("benchmark_tich_hop", "sáu ca nội dung đầu cuối", "đạt ngưỡng ca của chính script (mã thoát 0)", True, 3600,
             [py, f"{dau}/benchmark_integration.py"], _phan_tich_tich_hop),
        Buoc("suc_khoe_sau_tai", "/health sau tải", 'status "ok", degraded=false', True, 30),
    ]


def doc_health(url: str, token: Optional[str], http_get: Callable[..., tuple[int, str]]) -> tuple[bool, str]:
    head = {"X-Api-Token": token} if token else {}
    try:
        ma, than = http_get(url.rstrip("/") + "/health", head)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        return False, f"không gọi được /health ({type(e).__name__})"
    try:
        body = json.loads(than)
    except ValueError:
        return False, f"/health http={ma} không phải JSON"
    ok = ma == 200 and body.get("status") == "ok" and not body.get("degraded")
    return ok, f"http={ma} status={body.get('status')!r} degraded={body.get('degraded')!r} engine_ready={body.get('engine_ready')!r}"


def _http_get_that(url: str, head: dict) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={**head, "ngrok-skip-browser-warning": "1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - URL do người vận hành đặt
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def chay(
    buoc_ds: list[Buoc],
    url: Optional[str],
    token: Optional[str],
    bo_qua: frozenset[str] = frozenset(),
    chi: Optional[frozenset[str]] = None,
    runner: Callable[..., Any] = subprocess.run,
    http_get: Callable[..., tuple[int, str]] = _http_get_that,
    dong_ho: Callable[[], float] = time.monotonic,
) -> list[KetQua]:
    ra: list[KetQua] = []
    brain_len: Optional[bool] = None       # None = chưa thử; False = đã thử và Brain không lên
    for b in buoc_ds:
        if chi is not None and b.khoa not in chi:
            ra.append(KetQua(b.khoa, b.ten, b.tieu_chi, BO_QUA, "ngoài --chi"))
            continue
        if b.khoa in bo_qua:
            ra.append(KetQua(b.khoa, b.ten, b.tieu_chi, BO_QUA, "bỏ qua có chủ ý (--bo-qua)"))
            continue
        if b.can_brain and not url:
            ra.append(KetQua(b.khoa, b.ten, b.tieu_chi, KHONG_CHAY, "chưa có BRAIN_URL"))
            continue
        if b.can_brain and brain_len is False and b.lenh is not None:
            ra.append(KetQua(b.khoa, b.ten, b.tieu_chi, KHONG_CHAY, "/health trước tải không đạt: Brain chưa lên"))
            continue
        t0 = dong_ho()
        if b.lenh is None:
            dat, chi_tiet = doc_health(url or "", token, http_get)
            if b.khoa == "suc_khoe_truoc":
                brain_len = dat
        else:
            env = dict(os.environ)
            if url:
                env["BRAIN_URL"] = url
            if token:
                env["BRAIN_API_TOKEN"] = token
            try:
                p = runner(b.lenh, capture_output=True, text=True, timeout=b.han_giay, env=env, cwd=str(GOC), encoding="utf-8", errors="replace")
                dat, chi_tiet = b.phan_tich(p.returncode, p.stdout or "")
            except subprocess.TimeoutExpired:
                dat, chi_tiet = False, f"quá {b.han_giay}s"
            except OSError as e:
                dat, chi_tiet = False, f"không chạy được ({type(e).__name__})"
        ra.append(KetQua(b.khoa, b.ten, b.tieu_chi, DAT if dat else TRUOT, chi_tiet, round(dong_ho() - t0, 1)))
    return ra


def ma_thoat(kq: list[KetQua]) -> int:
    if any(k.trang_thai == TRUOT for k in kq):
        return 1
    if all(k.trang_thai == DAT for k in kq):
        return 0
    return 2


_NHAN = {DAT: "ĐẠT", TRUOT: "TRƯỢT", KHONG_CHAY: "KHÔNG CHẠY", BO_QUA: "BỎ QUA"}


def bang(kq: list[KetQua]) -> str:
    d = ["| Bước | Tiêu chí đạt | Kết quả | Chi tiết | Giây |", "|---|---|---|---|---|"]
    for k in kq:
        d.append(f"| {k.ten} | {k.tieu_chi} | **{_NHAN[k.trang_thai]}** | {k.chi_tiet} | {k.giay:g} |")
    ma = ma_thoat(kq)
    n_dat = sum(1 for k in kq if k.trang_thai == DAT)
    ket = {0: "ĐẠT: một lần chạy thật hoàn chỉnh.", 1: "TRƯỢT: có bước không đạt; gửi nguyên bảng này về, đừng sửa gì thêm.",
           2: "CHƯA ĐỦ: có bước không chạy hoặc bị bỏ qua; KHÔNG tính là một lần chạy thật."}[ma]
    d += ["", f"**{n_dat}/{len(kq)} bước đạt.** {ket}"]
    return "\n".join(d)


def commit_ngan() -> Optional[str]:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=str(GOC), timeout=10)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def main(argv: Optional[list[str]] = None) -> int:
    buoc_ds = cac_buoc()
    khoa = [b.khoa for b in buoc_ds]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("BRAIN_URL"), help="Brain đang chạy (mặc định $BRAIN_URL)")
    ap.add_argument("--json", metavar="TỆP", help="ghi kết quả máy đọc được (không chứa token)")
    ap.add_argument("--chi", help=f"chỉ chạy các bước này, cách nhau dấu phẩy: {', '.join(khoa)}")
    ap.add_argument("--bo-qua", help="bỏ qua các bước này (mã thoát 2: chưa đủ)")
    a = ap.parse_args(argv)
    chi = frozenset(a.chi.split(",")) if a.chi else None
    bo = frozenset(a.bo_qua.split(",")) if a.bo_qua else frozenset()
    for ten in (chi or frozenset()) | bo:
        if ten not in khoa:
            ap.error(f"bước lạ: {ten!r}; có: {', '.join(khoa)}")
    token = os.environ.get("BRAIN_API_TOKEN") or os.environ.get("API_AUTH_TOKEN")
    kq = chay(buoc_ds, a.url, token, bo, chi)
    print(bang(kq))
    if a.json:
        Path(a.json).write_text(json.dumps({
            "commit": commit_ngan(), "may_chu": urlparse(a.url).hostname if a.url else None,
            "ma_thoat": ma_thoat(kq), "buoc": [k.__dict__ for k in kq],
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nĐã ghi {a.json}")
    return ma_thoat(kq)


if __name__ == "__main__":
    sys.exit(main())
