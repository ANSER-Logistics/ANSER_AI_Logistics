"""
offline_training/do_nghiep_vu.py — BACKTEST tầng chọn việc của Brain trên câu hỏi nghiệp vụ.

Không GPU, không model, vài chục MB bộ nhớ: chạy ở máy dev và ở CI.

ĐO GÌ
-----
`tool_planner.plan_tools(câu)` cùng bộ định tuyến (router) quyết định câu hỏi của người dùng cần công cụ nào (VAT, báo cáo, soát kho,
công nợ, báo giá, chọn nhà xe, dự báo nhập hàng) hay không cần công cụ nào (tra luật, chào hỏi, câu nằm ngoài
nghiệp vụ). Chọn sai công cụ là sai nghiệp vụ ngay từ bước đầu: hỏi công nợ mà nhận báo cáo doanh thu.
Bảng luật này là tầng TẤT ĐỊNH, nên đo được mà không cần model.

BỘ ĐỀ: `generated/eval_nghiep_vu.jsonl`, câu hư cấu viết theo cách người dùng thật hay gõ (có dấu, không dấu,
viết tắt, số kiểu "3tr5", nhiều ý trong một câu) và các CÂU BẪY (có chữ "kho", "nợ", "báo cáo" nhưng không
phải yêu cầu dùng công cụ). Chia hai tập:
  dev      : tập được phép nhìn lỗi để sửa luật.
  holdout  : KHÔNG được nhìn lỗi để sửa luật. Con số trên tập này là con số thật; sửa luật theo nó là tự lừa.

GIỚI HẠN — đọc trước khi tin con số
-----------------------------------
Câu do một AI viết, không phải câu của khách thật (R2: không có câu thật nào trong repo). Một AI viết câu hỏi
vẫn viết theo cách một AI hình dung. Con số này là CẬN TRÊN của chất lượng ngoài đời. Thước đo thật là câu của
khách (BR-32, và chế độ chạy song song với việc làm tay của khách). Mỗi nhóm chỉ vài câu: đọc k/n, không đọc %.

CHẠY
    python offline_training/do_nghiep_vu.py                 # in bảng
    python offline_training/do_nghiep_vu.py --loi           # kèm từng câu sai
    python offline_training/do_nghiep_vu.py --json kq.json  # để theo dõi qua các lần đo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_training.dgen_common import GENERATED_DIR  # noqa: E402
from src.agents.manager import SemanticRouter  # noqa: E402
from src.api.routes.tools import get_tool_defs  # noqa: E402
from src.core.tool_planner import plan_tools, vao_vong_agentic  # noqa: E402

BO_DE = GENERATED_DIR / "eval_nghiep_vu.jsonl"


def doc_bo_de(duong_dan: Path = BO_DE) -> list[dict[str, Any]]:
    return [json.loads(d) for d in duong_dan.read_text(encoding="utf-8").splitlines() if d.strip()]


def duong_di(router: SemanticRouter, cau: str, ten_tool: list[str]) -> tuple[str, list[str]]:
    """
    Đường đi THẬT của một câu ở cửa trước: `(nhánh do router chọn, công cụ thực sự được chạy)`.

    Dùng đúng `plan_tools` và `vao_vong_agentic` mà `chat.py` dùng, và router ở CHẾ ĐỘ TỪ KHOÁ (lớp 1; không
    nạp embedder, vì nạp nó ở máy dev từng làm tiến trình chết vì hết bộ nhớ). Hệ quả: câu không khớp luật từ
    khoá rơi về GENERAL, trong khi production còn thêm lớp cosine. Đo ở đây là phần TẤT ĐỊNH của cửa trước.
    "Công cụ thực sự được chạy" rỗng nghĩa là câu đi luồng riêng của nhánh (n8n, workflow, tra tài liệu, chat).
    """
    cat = router.route_with_score(cau)["route"]
    plan = plan_tools(cau, ten_tool)
    return cat, (sorted(plan) if vao_vong_agentic(cat, plan, cau) else [])


def cham_mot(ca: dict[str, Any], cat: str, chay: list[str]) -> dict[str, Any]:
    """
    So công cụ được chạy với kỳ vọng như TẬP HỢP (thứ tự do `_PIPELINE` quyết, không phải đối tượng đo).
    Nếu câu có `nhanh` (LOGISTICS, TECHNICAL: nhánh xác định được bằng từ khoá) thì nhánh cũng phải khớp.
    """
    mong, co = set(ca["tool"]), set(chay)
    sai_nhanh = bool(ca.get("nhanh")) and cat != ca["nhanh"]
    return {
        "id": ca["id"], "nhom": ca["nhom"], "tap": ca["tap"], "cau": ca["cau"],
        "mo_ho": bool(ca.get("mo_ho")), "nguon": ca.get("nguon", ""),
        "mong": sorted(mong), "co": sorted(co), "nhanh": cat, "nhanh_mong": ca.get("nhanh"),
        "dung": mong == co and not sai_nhanh,
        "thieu": sorted(mong - co),           # cần công cụ mà không chọn: người dùng nhận câu "không làm được"
        "thua": sorted(co - mong),            # chọn công cụ không ai hỏi: người dùng nhận kết quả lạc đề
    }


def chay(bo_de: list[dict[str, Any]]) -> list[dict[str, Any]]:
    router = SemanticRouter(tu_nap_embedder=False)
    ten_tool = [t["name"] for t in get_tool_defs()]
    return [cham_mot(ca, *duong_di(router, ca["cau"], ten_tool)) for ca in bo_de]


def tong_hop(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Gom theo `tap/nhom`, `tap/all` và `all`. Mỗi ô là SỐ ĐẾM: n, đúng, thiếu, thừa."""
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        # Ca MƠ HỒ (nhãn của người viết không ánh xạ 1-1 sang công cụ của Brain) không tính vào con số chính;
        # báo riêng ở nhóm "mo_ho/<tập>" để không ai đọc nhầm một ca tranh cãi thành lỗi của Brain.
        khoa_nhom = (f"mo_ho/{r['tap']}",) if r.get("mo_ho") else (f"{r['tap']}/{r['nhom']}", f"{r['tap']}/all", "all")
        for khoa in khoa_nhom:
            g = out.setdefault(khoa, {"n": 0, "dung": 0, "thieu": 0, "thua": 0})
            g["n"] += 1
            g["dung"] += r["dung"]
            g["thieu"] += bool(r["thieu"])
            g["thua"] += bool(r["thua"])
    return out


def in_bang(nhom: dict[str, dict[str, int]]) -> None:
    print(f"\n{'nhóm':<26}{'n':>4}{'đúng':>8}{'thiếu':>8}{'thừa':>7}")
    for tap in ("holdout", "dev", "mo_ho"):
        for khoa in sorted(k for k in nhom if k.startswith(tap + "/")):
            g = nhom[khoa]
            print(f"{khoa:<26}{g['n']:>4}{g['dung']:>5}/{g['n']:<2}{g['thieu']:>8}{g['thua']:>7}")
        print()
    g = nhom.get("all", {"n": 0, "dung": 0, "thieu": 0, "thua": 0})
    print(f"{'TẤT CẢ (không tính mơ hồ)':<26}{g['n']:>4}{g['dung']:>5}/{g['n']:<2}{g['thieu']:>8}{g['thua']:>7}")
    print("\n'thiếu' = số câu cần công cụ mà không chọn; 'thừa' = số câu bị chọn công cụ không ai hỏi."
          "\nCon số trên tập holdout là con số thật. Câu do AI viết nên đây là CẬN TRÊN so với câu của khách.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--loi", action="store_true", help="in từng câu sai")
    ap.add_argument("--json", default="", help="ghi kết quả từng câu và bảng tổng hợp")
    ap.add_argument("--tap", choices=["dev", "holdout"], default="", help="chỉ in lỗi của một tập")
    args = ap.parse_args()

    bo_de = doc_bo_de()
    rows = chay(bo_de)
    nhom = tong_hop(rows)
    in_bang(nhom)
    if not any(c["tap"] == "holdout" for c in bo_de):
        print("\n!! CHƯA CÓ TẬP HOLDOUT. Mọi con số ở trên là TRONG MẪU: luật đã được sửa theo chính các câu này."
              "\n   Tập holdout đầu tiên (31/49 -> 33/49 trước khi nhìn lỗi) đã bị dùng ngày 16/11/2026."
              "\n   Cần một tập mới do NGƯỜI KHÁC viết, đánh dấu \"tap\": \"holdout\" (xem issue về bộ câu nghiệp vụ).")
    if args.loi:
        print("\nCÂU SAI:")
        for r in rows:
            if not r["dung"] and (not args.tap or r["tap"] == args.tap):
                print(f"  [{r['tap']}] {r['id']} {r['nhom']}: {r['cau'][:70]}\n"
                      f"      mong {r['mong']}  chạy {r['co']}  nhánh {r['nhanh']}"
                      + (f" (mong {r['nhanh_mong']})" if r["nhanh_mong"] else ""))
    if args.json:
        Path(args.json).write_text(json.dumps({"tong_hop": nhom, "rows": rows}, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"\nĐã ghi {args.json}")


if __name__ == "__main__":
    main()
