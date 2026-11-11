"""
offline_training/dong_bo_n8n_body.py — workflow n8n THẬT của Body, cho Brain dùng.

    python offline_training/dong_bo_n8n_body.py tai              # -> deploy/n8n-body/
    python offline_training/dong_bo_n8n_body.py tai --dich DIR
    python offline_training/dong_bo_n8n_body.py kiem             # so với catalog dự phòng
    python offline_training/dong_bo_n8n_body.py kiem --thu-muc deploy/n8n-body

`kiem` trả mã thoát 1 khi lệch, 2 khi không tải được Body.

VÌ SAO CÓ FILE NÀY (#20)
------------------------
Brain sinh workflow n8n cho khách. `typeVersion` và tham số của từng node phụ
thuộc n8n instance của Body. Sai thì workflow vẫn hợp lệ về CẤU TRÚC —
`validate_workflow()` cho qua, CI xanh — rồi khách import vào n8n và nó không
chạy. Lỗi lộ ra ở đầu xa nhất của chuỗi, trên máy khách, không có log nào bên
Brain dẫn về nguyên nhân.

Đo 09/11/2026 (catalog dự phòng vs `frontend/n8n-workflows/` của Body):
httpRequest 4.2 vs 4.4, if 2 vs 1 (tham số mẫu lại là kiểu v1), webhook 2 vs 1;
Body gửi mail bằng `emailSend` (SMTP) mà Brain chỉ biết `gmail`.

HAI LỆNH, HAI VIỆC
------------------
`tai`  — tải mọi `*.json` trong thư mục workflow của Body về một thư mục KHÔNG
         commit (`deploy/n8n-body/`, đã .gitignore). Compose mount thư mục đó và
         trỏ `N8N_TEMPLATES_DIR` vào. Không tạo bản sao thứ hai trong repo (R4):
         bản tải về là bản dẫn xuất, tải lại lúc nào cũng được.
`kiem` — so typeVersion từng node: Body vs `DEFAULT_NODE_CATALOG` của Brain (và
         vs bản đã tải, nếu đưa `--thu-muc`). Body đổi workflow thì lệnh này đỏ —
         biết bằng lệnh, không bằng nhớ.

CHỈ ĐỌC, KHÔNG SỬA BODY
-----------------------
AGENTS.md §1: Body không được sửa. Script này chỉ `GET` file công khai của
chính dự án từ GitHub, không gửi gì ra ngoài (R2).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.workflow_schema import BLOCKED_NODE_TYPES, DEFAULT_NODE_CATALOG  # noqa: E402

# Đường dẫn repo Body đổi hai lần trong một tuần (xem doi_chieu_hop_dong_body.py),
# nên để ở hằng số, và khi 404 thì nói thẳng là có thể repo lại đổi chỗ.
REPO_BODY = "ANSER-Logistics/ANSER-logistics-body"
NHANH_BODY = "master"
THU_MUC_BODY = "frontend/n8n-workflows"
URL_DANH_SACH = (
    f"https://api.github.com/repos/{REPO_BODY}/contents/{THU_MUC_BODY}?ref={NHANH_BODY}"
)
DICH_MAC_DINH = ROOT / "deploy" / "n8n-body"


class KhongTaiDuoc(RuntimeError):
    """Không đọc được Body — mạng, giới hạn API, hoặc repo đã đổi chỗ."""


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "anser-brain-dong-bo-n8n"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as exc:
        goi_y = {
            403: "giới hạn API GitHub cho truy cập không đăng nhập (60 lượt/giờ) — thử lại sau",
            404: f"không thấy — repo Body có thể lại đổi chỗ, sửa REPO_BODY/THU_MUC_BODY ({URL_DANH_SACH})",
        }.get(exc.code, "")
        raise KhongTaiDuoc(f"HTTP {exc.code} tại {url}. {goi_y}") from exc
    except urllib.error.URLError as exc:
        raise KhongTaiDuoc(f"không kết nối được {url}: {exc.reason}") from exc


def tai_body() -> dict[str, dict[str, Any]]:
    """{tên file: workflow} — mọi `*.json` trong thư mục workflow của Body."""
    danh_sach = json.loads(_get(URL_DANH_SACH))
    if not isinstance(danh_sach, list):
        raise KhongTaiDuoc(f"{URL_DANH_SACH} không trả danh sách file")
    ra: dict[str, dict[str, Any]] = {}
    for muc in danh_sach:
        ten = muc.get("name", "")
        if muc.get("type") != "file" or not ten.endswith(".json"):
            continue
        wf = json.loads(_get(muc["download_url"]))
        if not isinstance(wf, dict) or not isinstance(wf.get("nodes"), list):
            raise KhongTaiDuoc(f"{ten} không phải workflow n8n (thiếu mảng `nodes`)")
        ra[ten] = wf
    if not ra:
        raise KhongTaiDuoc(f"{URL_DANH_SACH} không có file .json nào")
    return ra


def doc_thu_muc(thu_muc: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Workflow đã tải về đĩa — đúng những gì `N8N_TEMPLATES_DIR` sẽ đọc."""
    ra: dict[str, dict[str, Any]] = {}
    for p in sorted(thu_muc.glob("*.json")):
        ra[p.name] = json.loads(p.read_text(encoding="utf-8"))
    return ra


def phien_ban_theo_node(workflows: dict[str, dict[str, Any]]) -> dict[str, set[float]]:
    """{node type: tập typeVersion gặp được} qua mọi workflow."""
    ra: dict[str, set[float]] = defaultdict(set)
    for wf in workflows.values():
        for n in wf.get("nodes") or []:
            if not isinstance(n, dict):
                continue
            t, v = n.get("type"), n.get("typeVersion")
            if isinstance(t, str) and isinstance(v, (int, float)) and not isinstance(v, bool):
                ra[t].add(float(v))
    return dict(ra)


def so_sanh(body: dict[str, set[float]],
            catalog: dict[str, dict[str, Any]]) -> list[tuple[str, str, str, str]]:
    """
    [(node, bên Brain, bên Body, kết luận)]. Kết luận bắt đầu bằng "LỆCH" hoặc
    "THIẾU" là lỗi; còn lại chỉ để đọc.

    - LỆCH:   cả hai có, typeVersion khác nhau.
    - THIẾU:  Body dùng mà Brain không biết — model không thể sinh node đó đúng.
    - bị chặn có chủ đích: node trong BLOCKED_NODE_TYPES (vd `code`), Brain
      không bao giờ sinh, dù Body dùng.
    - Body không dùng: Brain có mà Body không — không sai, nhưng không có gì
      xác nhận version đó chạy được trên n8n của Body.
    """
    ra = []
    for t in sorted(set(body) | set(catalog)):
        b = catalog.get(t, {}).get("typeVersion")
        th = sorted(body.get(t, set()))
        ben_body = ", ".join(f"{v:g}" for v in th) or "—"
        ben_brain = "—" if b is None else f"{float(b):g}"
        if t in BLOCKED_NODE_TYPES:
            kl = "bị chặn có chủ đích"
        elif b is None:
            kl = "THIẾU bên Brain"
        elif not th:
            kl = "Body không dùng"
        elif any(float(b) != v for v in th):
            kl = "LỆCH"
        else:
            kl = "khớp"
        ra.append((t, ben_brain, ben_body, kl))
    return ra


def la_loi(ket_luan: str) -> bool:
    return ket_luan.startswith(("LỆCH", "THIẾU"))


def lenh_tai(dich: pathlib.Path) -> int:
    body = tai_body()
    dich.mkdir(parents=True, exist_ok=True)
    # Thư mục đích là của riêng script này: xoá file .json Body đã bỏ, để Brain
    # không học tiếp từ một workflow không còn tồn tại.
    for cu in dich.glob("*.json"):
        if cu.name not in body:
            cu.unlink()
            print(f"  - xoá {cu.name} (Body đã bỏ)")
    for ten, wf in body.items():
        (dich / ten).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  + {ten}: {len(wf['nodes'])} node")
    print(f"\nĐã tải {len(body)} workflow vào {dich}")
    print("Đặt N8N_TEMPLATES_DIR trỏ vào thư mục đó (compose đã mount sẵn ở /app/n8n-body).")
    return 0


def lenh_kiem(thu_muc: pathlib.Path | None) -> int:
    body = tai_body()
    bang = so_sanh(phien_ban_theo_node(body), DEFAULT_NODE_CATALOG)
    print(f"Body: {len(body)} workflow tại {REPO_BODY}/{THU_MUC_BODY} ({NHANH_BODY})\n")
    print("| Node | Brain (dự phòng) | Body | Kết luận |")
    print("|---|---|---|---|")
    for t, b, th, kl in bang:
        print(f"| `{t}` | {b} | {th} | {kl} |")
    loi = [r for r in bang if la_loi(r[3])]

    cu = 0
    if thu_muc is not None:
        da_tai = doc_thu_muc(thu_muc) if thu_muc.is_dir() else {}
        if da_tai != body:
            cu = 1
            thieu = sorted(set(body) - set(da_tai))
            thua = sorted(set(da_tai) - set(body))
            khac = sorted(k for k in set(body) & set(da_tai) if body[k] != da_tai[k])
            print(f"\n✗ Bản đã tải ở {thu_muc} KHÔNG khớp Body hiện tại — chạy lại `tai`.")
            for nhan, ds in (("thiếu", thieu), ("thừa", thua), ("khác nội dung", khac)):
                if ds:
                    print(f"    {nhan}: {', '.join(ds)}")
        else:
            print(f"\n✓ Bản đã tải ở {thu_muc} khớp Body hiện tại.")

    if loi:
        print(f"\n✗ {len(loi)} node lệch hoặc thiếu. Sửa DEFAULT_NODE_CATALOG trong "
              "src/core/workflow_schema.py cho khớp Body.")
    else:
        print("\n✓ Catalog dự phòng khớp mọi node Body dùng.")
    return 1 if (loi or cu) else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    con = ap.add_subparsers(dest="lenh", required=True)
    p_tai = con.add_parser("tai", help="tải workflow của Body về thư mục để mount")
    p_tai.add_argument("--dich", type=pathlib.Path, default=DICH_MAC_DINH)
    p_kiem = con.add_parser("kiem", help="so typeVersion Body vs catalog dự phòng")
    p_kiem.add_argument("--thu-muc", type=pathlib.Path, default=None,
                        help="thư mục đã tải (vd deploy/n8n-body) — kiểm thêm nó có cũ không")
    a = ap.parse_args(argv)
    try:
        return lenh_tai(a.dich) if a.lenh == "tai" else lenh_kiem(a.thu_muc)
    except KhongTaiDuoc as exc:
        print(f"✗ Không đọc được Body: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
