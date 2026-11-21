"""
offline_training/cham_lai_n8n.py — chấm lại n8n từ ĐẦU RA THÔ có sẵn, có và không có bước sửa liên kết `noOp` (#91, 20/11/2026).

    python offline_training/cham_lai_n8n.py v3_tho.jsonl v4_tho.jsonl v5_tho.jsonl
    python offline_training/cham_lai_n8n.py --json ket_qua.json v5_tho.jsonl

VÌ SAO CÓ
---------
Chủ dự án đồng ý (20/11) cho `/chat` bỏ liên kết tới node `noOp` không tồn tại trước khi kiểm (`workflow_schema.sua_lien_ket_noop`), và
`benchmark_v3` chấm theo cách đó từ nay. Nhưng bảng v3, v4, v5 cũ chấm TRƯỚC bước đó. So hai lần chấm khác cách là so không công bằng, và chạy
lại GPU chỉ để đổi cách chấm là phí. Đầu ra thô đã nằm ở `--tho` của mỗi lần chạy (`v3_tho.jsonl`...), nên chấm lại tại chỗ, không cần GPU.

Mỗi file in: số câu hợp lệ KHÔNG sửa (cách cũ), CÓ sửa (cách mới), danh sách câu được cứu, và danh sách câu còn hỏng kèm lý do. Đọc cả hai nhánh
`n8n` (lần đầu) và `n8n_thu_lai` nếu có (chỉ phần được sinh lại).

KHÔNG đo được: workflow sau khi sửa có ĐÚNG VIỆC không (xem `make_n8n_eval`: bộ đo chỉ đo cấu trúc). Chỉ cho biết bao nhiêu câu hỏng CHỈ vì liên kết noOp.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from offline_training.benchmark_v3 import score_n8n  # noqa: E402
from offline_training.make_n8n_pairs import _stage_catalog_dir  # noqa: E402
from src.core.workflow_schema import reload_catalog  # noqa: E402


def doc_tho(duong_dan: Path) -> dict[str, list[dict]]:
    """{nhánh: [dòng]} từ một file `--tho` của benchmark_v3. Dòng hỏng JSON làm ngoại lệ có tên file và số dòng (không nuốt lặng lẽ)."""
    ra: dict[str, list[dict]] = {}
    for i, dong in enumerate(duong_dan.read_text(encoding="utf-8").splitlines(), 1):
        if not dong.strip():
            continue
        try:
            d = json.loads(dong)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{duong_dan}:{i}: không đọc được JSON ({exc})") from exc
        ra.setdefault(d.get("nhanh", "?"), []).append(d)
    return ra


def cham_nhanh(dong: list[dict]) -> dict:
    rows = [{"_id": d["_id"]} for d in dong]
    outs = [d["output"] for d in dong]
    fins = [d.get("finish", "") for d in dong]
    cu = score_n8n(rows, outs, fins, sua_noop=False)
    moi = score_n8n(rows, outs, fins, sua_noop=True)
    cuu = [rows[k]["_id"] for k, (a, b) in enumerate(zip(cu["per_row"], moi["per_row"])) if b and not a]
    lam_hong = [rows[k]["_id"] for k, (a, b) in enumerate(zip(cu["per_row"], moi["per_row"])) if a and not b]
    return {"n": len(rows), "hop_le_cu": cu["n_valid"], "hop_le_moi": moi["n_valid"], "duoc_cuu": cuu,
            "bi_lam_hong": lam_hong, "con_hong": [(i, why) for i, why in moi["failures"]]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tho", nargs="+", help="một hay nhiều file --tho của benchmark_v3")
    ap.add_argument("--json", default="", help="ghi kết quả ra file JSON")
    a = ap.parse_args(argv)
    # Catalog node CÙNG nguồn với benchmark_v3 (workflow mẫu thật, có respondToWebhook, gmail...). Thiếu bước này thì
    # validate_workflow rơi về catalog dự phòng 12 node và chấm hỏng oan mọi câu dùng node ngoài danh sách đó: lần chạy
    # đầu ngày 20/11 ra v3 32/34 "cách cũ" trong khi benchmark đo 33/34 trên đúng đầu ra ấy (#175).
    _stage_catalog_dir()
    reload_catalog()
    tat_ca: dict[str, dict] = {}
    for f in a.tho:
        p = Path(f)
        if not p.is_file():
            print(f"Không thấy {p}", file=sys.stderr)
            return 2
        nhanh = doc_tho(p)
        ra: dict[str, dict] = {}
        for ten in ("n8n", "n8n_thu_lai"):
            if nhanh.get(ten):
                ra[ten] = cham_nhanh(nhanh[ten])
        if not ra:
            print(f"{p}: không có nhánh n8n nào", file=sys.stderr)
            return 2
        tat_ca[p.name] = ra
        for ten, kq in ra.items():
            print(f"{p.name} [{ten}] {kq['hop_le_cu']}/{kq['n']} (cách cũ) -> {kq['hop_le_moi']}/{kq['n']} (có sửa noOp)")
            if kq["duoc_cuu"]:
                print(f"    được cứu: {', '.join(kq['duoc_cuu'])}")
            if kq["bi_lam_hong"]:
                print(f"    BỊ LÀM HỎNG (không được xảy ra): {', '.join(kq['bi_lam_hong'])}")
            for i, why in kq["con_hong"]:
                print(f"    còn hỏng {i}: {why}")
    if a.json:
        Path(a.json).write_text(json.dumps(tat_ca, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
