"""
offline_training/tong_hop_issue.py — gom các issue của Brain thành MỘT bảng việc ngắn cho cả đội đọc nhanh.

Ai làm gì, việc nào đang mở, việc nào vừa đóng, việc nào chưa có người. Sinh từ GitHub bằng `gh`, nên
không ai phải nhớ cập nhật tay (bảng chép tay là bảng nói dối sau một tuần).

    python offline_training/tong_hop_issue.py                      # in ra màn hình
    python offline_training/tong_hop_issue.py --out BANG_VIEC.md   # ghi file

Cần `gh` đã đăng nhập. Trạng thái trên bảng dự án (Todo, In Progress, Done) lấy từ project số 6 nếu đọc được;
không đọc được thì cột đó hiện "?" chứ không đoán.

Hàm `dinh_dang` là hàm thuần (nhận dữ liệu, trả chuỗi) để test được mà không cần mạng.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = "ANSER-Logistics/ANSER_AI_Logistics"
ORG, SO_BANG = "ANSER-Logistics", "6"
TEN_NGUOI = {          # tên thường gọi; không có trong bảng thì dùng tên tài khoản
    "tranthanh-riu": "Thành",
    "Dgsonn": "Sơn",
    "erichocolatte": "Phương",
    "wikiepeidia": "Minh",
    "PCBoiz": "Agent (PCBoiz)",
}
GIOI_HAN_TIEU_DE = 95
NGAY_DONG_GAN_DAY = 7


def _gh_json(args: list[str]) -> Any:
    kq = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", check=False)
    if kq.returncode != 0:
        raise RuntimeError(kq.stderr.strip()[:300])
    return json.loads(kq.stdout)


def lay_issue() -> list[dict[str, Any]]:
    return _gh_json(["issue", "list", "--repo", REPO, "--state", "all", "--limit", "300", "--json",
                     "number,title,state,assignees,updatedAt,closedAt,comments"])


def lay_trang_thai_bang() -> dict[int, str]:
    """Số issue -> trạng thái trên bảng dự án. Không đọc được thì trả rỗng (cột sẽ hiện '?')."""
    try:
        du_lieu = _gh_json(["project", "item-list", SO_BANG, "--owner", ORG, "--format", "json", "--limit", "300"])
    except (RuntimeError, OSError, json.JSONDecodeError):
        return {}
    out: dict[int, str] = {}
    for it in du_lieu.get("items", []):
        so = (it.get("content") or {}).get("number")
        if so and it.get("status"):
            out[int(so)] = it["status"]
    return out


def _ngay(iso: str | None) -> str:
    if not iso:
        return "?"
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=7))).strftime("%d/%m")


def _tieu_de(t: str) -> str:
    t = " ".join(t.split())
    return t if len(t) <= GIOI_HAN_TIEU_DE else t[: GIOI_HAN_TIEU_DE - 1].rstrip() + "…"


def _dong(i: dict[str, Any], trang_thai: dict[int, str]) -> str:
    n = i["number"]
    return (f"| [#{n}](https://github.com/{REPO}/issues/{n}) | {_tieu_de(i['title'])} | "
            f"{trang_thai.get(n, '?')} | {_ngay(i.get('updatedAt'))} | {len(i.get('comments') or [])} |")


_DAU_BANG = "| Việc | Nội dung | Trên bảng | Cập nhật | Bình luận |\n|---|---|---|---|---|"


def dinh_dang(issues: list[dict[str, Any]], trang_thai: dict[int, str], bay_gio: datetime) -> str:
    """Bảng việc dạng markdown. Hàm thuần: cùng đầu vào, cùng đầu ra."""
    mo = sorted((i for i in issues if i["state"] == "OPEN"), key=lambda i: i["number"])
    moc = bay_gio - timedelta(days=NGAY_DONG_GAN_DAY)
    dong_gan_day = sorted(
        (i for i in issues if i["state"] == "CLOSED" and i.get("closedAt")
         and datetime.fromisoformat(i["closedAt"].replace("Z", "+00:00")) >= moc),
        key=lambda i: i["closedAt"], reverse=True)

    theo_nguoi: dict[str, list[dict[str, Any]]] = {}
    chua_giao: list[dict[str, Any]] = []
    for i in mo:
        ds = [a["login"] for a in i.get("assignees") or []]
        if not ds:
            chua_giao.append(i)
        for login in ds:
            theo_nguoi.setdefault(login, []).append(i)

    ra = [
        "# Bảng việc của đội Brain",
        "",
        f"Sinh tự động từ GitHub lúc {bay_gio.astimezone(timezone(timedelta(hours=7))).strftime('%H:%M %d/%m/%Y')} "
        f"(giờ Việt Nam) bằng `python offline_training/tong_hop_issue.py`. Muốn bản mới thì chạy lại lệnh đó; "
        f"đừng sửa tay file này.",
        "",
        f"Đang mở: **{len(mo)}** việc, trong đó **{len(chua_giao)}** chưa giao ai. "
        f"Đã đóng trong {NGAY_DONG_GAN_DAY} ngày qua: **{len(dong_gan_day)}**. "
        "Cột \"Trên bảng\" là trạng thái ở [bảng dự án](https://github.com/orgs/ANSER-Logistics/projects/6); "
        "dấu ? nghĩa là việc chưa nằm trên bảng hoặc không đọc được bảng.",
        "",
        "Việc có hai người nhận hiện ở cả hai mục.",
        "",
    ]
    thu_tu = [k for k in TEN_NGUOI if k in theo_nguoi] + sorted(k for k in theo_nguoi if k not in TEN_NGUOI)
    for login in thu_tu:
        ra += [f"## {TEN_NGUOI.get(login, login)} ({len(theo_nguoi[login])})", "", _DAU_BANG]
        ra += [_dong(i, trang_thai) for i in theo_nguoi[login]]
        ra.append("")
    if chua_giao:
        ra += [f"## Chưa giao ai ({len(chua_giao)})", "", _DAU_BANG] + [_dong(i, trang_thai) for i in chua_giao] + [""]
    if dong_gan_day:
        ra += [f"## Đã đóng trong {NGAY_DONG_GAN_DAY} ngày qua ({len(dong_gan_day)})", "", _DAU_BANG]
        ra += [_dong(i, trang_thai) for i in dong_gan_day] + [""]
    return "\n".join(ra).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="", help="ghi ra file thay vì in")
    args = ap.parse_args()
    van_ban = dinh_dang(lay_issue(), lay_trang_thai_bang(), datetime.now(timezone.utc))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(van_ban)
        print(f"Đã ghi {args.out}")
    else:
        print(van_ban)


if __name__ == "__main__":
    main()
