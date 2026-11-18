"""
offline_training/do_vlm_hoa_don.py — ĐO model thị giác trên bộ hoá đơn hư cấu (cần GPU: chạy trên Colab).

Chuẩn bị (một lần, máy bất kỳ):
    python offline_training/make_vlm_invoice_eval.py --n 28 --out /content/vlm_hoadon

Chạy (Colab, đã có ENV, TEXT_MODEL_ID/VISION_MODEL_ID như production):
    python offline_training/do_vlm_hoa_don.py --dir /content/vlm_hoadon --json truoc.json

ĐO TRƯỚC/SAU một thay đổi prompt (ví dụ BR-19 phần 2b): chạy hai lần, mỗi lần một nhánh mã, hai file
--json khác nhau, rồi đặt cạnh nhau. File JSON giữ kết quả TỪNG CA (`rows`) để so theo cặp.

Đi qua ĐÚNG đường production: `runtime.ensure_vision_runtime()` rồi `VisionAgent.extract_invoice` /
`extract_freight_invoice`, giống hệt `/ocr` và `/ocr/freight` trước bước kiểm số. Không có đường riêng
cho bộ đo (R4). Không gọi dịch vụ ngoài nào (R2); ảnh và đáp án đều hư cấu.

CON SỐ NÀY NÓI GÌ — và không nói gì: ảnh dựng bằng code, chữ in sạch (xem `vlm_hoadon.py`). Đây là cận
trên. Kém ở đây thì chắc chắn kém ngoài đời; tốt ở đây thì CHƯA biết gì về hoá đơn chụp điện thoại.
Mỗi ô in dạng k/n (n nhỏ: 28 ca chia cho 6 biến thể và hai loại, mỗi ô chỉ vài ca). Đừng đọc phần trăm.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_training.vlm_hoadon import cham, tong_hop  # noqa: E402


def _doc_ca(thu_muc: Path) -> list[dict]:
    p = thu_muc / "eval_vlm_hoadon.jsonl"
    if not p.is_file():
        raise SystemExit(f"Không thấy {p}. Chạy make_vlm_invoice_eval.py --out {thu_muc} trước.")
    return [json.loads(d) for d in p.read_text(encoding="utf-8").splitlines() if d.strip()]


def in_bang(nhom: dict[str, dict]) -> None:
    print(f"\n{'nhóm':<24}{'n':>4}{'parse':>8}{'đúng hết':>10}{'tổng đúng':>11}{'điền 0':>8}{'chép lệnh':>11}")
    for khoa in sorted(nhom, key=lambda k: (k != "all", k)):
        g = nhom[khoa]
        n = g["n"]
        print(f"{khoa:<24}{n:>4}{g['parse']:>6}/{n:<2}{g['tat_ca_dung']:>7}/{n:<2}"
              f"{g['tong_dung']:>8}/{n:<2}{g['dien_0']:>8}{g['chep_nhieu_loan']:>8}/{n:<2}")
    print("\n'điền 0' là SỐ TRƯỜNG (đáp án null mà model điền 0), không phải số ca."
          "\n'chép lệnh' là số ca mà model chép câu \"bỏ qua mọi hướng dẫn\" vào một trường văn bản.")


async def chay(thu_muc: Path, toi_da: int) -> list[dict]:
    from src.api.dependencies import runtime

    await runtime.ensure_vision_runtime()
    if not runtime.vision:
        raise SystemExit(f"Không nạp được vision runtime: {runtime.vision_error}")

    rows = []
    ca = _doc_ca(thu_muc)[: toi_da or None]
    for i, c in enumerate(ca, 1):
        anh = str(thu_muc / c["image"])
        t0 = time.perf_counter()
        if c["kind"] == "retail":
            out = await runtime.vision.extract_invoice(anh)
        else:
            out = await runtime.vision.extract_freight_invoice(anh)
        giay = time.perf_counter() - t0
        kq = cham(c, out)
        kq["out"] = out          # đầu ra thô của model, để người đọc tự soát các ca sai
        # Thời gian một ảnh, gồm cả mã hoá ảnh và gọi server (qua vLLM thì không gồm nạp model). Ca đầu thường chậm hơn vì
        # khởi động nóng: nhìn p50, đừng nhìn trung bình.
        kq["giay"] = round(giay, 2)
        rows.append(kq)
        print(f"[{i}/{len(ca)}] {c['id']} {c['kind']}/{c['variant']}: "
              f"{'đúng hết' if kq.get('tat_ca_dung') else 'có sai'}", flush=True)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, help="thư mục do make_vlm_invoice_eval.py tạo")
    ap.add_argument("--json", default="", help="ghi kết quả từng ca và bảng tổng hợp ra file này")
    ap.add_argument("--max", type=int, default=0, help="chỉ chạy N ca đầu (0 = tất cả)")
    args = ap.parse_args()

    rows = asyncio.run(chay(Path(args.dir), args.max))
    nhom = tong_hop(rows)
    in_bang(nhom)
    gs = sorted(r["giay"] for r in rows if "giay" in r)
    if gs:
        p = lambda q: gs[min(len(gs) - 1, int(q * len(gs)))]  # noqa: E731
        print(f"\nGiây mỗi ảnh: p50 {p(0.5):.1f}  p95 {p(0.95):.1f}  lâu nhất {gs[-1]:.1f}  (n={len(gs)})")
    if args.json:
        Path(args.json).write_text(
            json.dumps({"tong_hop": nhom, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        print(f"\nĐã ghi {args.json}")


if __name__ == "__main__":
    main()
