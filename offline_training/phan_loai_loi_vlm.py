"""
offline_training/phan_loai_loi_vlm.py — phân loại lỗi đọc số của model thị giác THEO ĐÁP ÁN THẬT (không theo model khác).

VÌ SAO CÓ FILE NÀY (#124, 19/11/2026)
-------------------------------------
Khi mổ xẻ số đo 5 model thị giác của Thành, mình phải lấy đầu ra của bản 7B làm "chuẩn thay thế" để thấy rằng cả 18 ca sai
tổng của Qwen3-VL-2B đều lệch đúng 1.000 lần (đọc `55.192.500` thành `55192`: dấu chấm hàng nghìn bị coi là thập phân), và rằng
bản mốc 3B nhầm cột (trả thành tiền của dòng vào `price`). Đó là cách làm tạm, và nó sai khi bản làm chuẩn cũng sai.
Công cụ này chấm trực tiếp với `gt` trong `eval_vlm_hoadon.jsonl`.

LỖI LŨY THỪA CỦA 10 LÀ CỔNG R1, KHÔNG PHẢI MỘT CỘT TRONG BẢNG
-------------------------------------------------------------
Hoá đơn 55 triệu đồng ghi thành 55 nghìn đồng mà MỌI số lệch cùng lúc thì `validate_invoice_total` vẫn báo hợp lệ (giá từng dòng và
tổng cùng lệch nên vẫn khớp nhau). Không lớp kiểm nhất quán nào bắt được; chỉ đáp án mới bắt được. Nên bất kỳ ca nào có tag `x10^k`
(k khác 0) ở trường tiền đều bị gom riêng vào danh sách `LECH_LUY_THUA_10`; điều kiện nhận một model là danh sách đó RỖNG.

CÁC TAG (mỗi ca trả một danh sách; rỗng nghĩa là mọi trường tiền đều đúng)
  <trường>:x10^k         sai đúng một lũy thừa của 10 (sai số 1%), ví dụ `total:x10^-3` là đọc nhỏ đi 1.000 lần
  <trường>:sai_khac      sai mà không phải lũy thừa của 10
  <trường>:khong_co_so   đáp án có số nhưng model trả None hoặc không phải số
  <trường>:dien_0        đáp án null mà model điền 0 (đúng thứ AGENTS R1 cấm)
  <trường>:dien_so       đáp án null mà model điền một số khác 0
  gia:la_thanh_tien      `price` của dòng bằng đơn giá nhân số lượng (nhầm cột Thành tiền thành Đơn giá)
  dong:thieu_hoac_thua   số dòng hàng/khoản khác đáp án, hoặc không ghép được dòng theo tên
  sl:sai                 số lượng khác đáp án
  khong_doc_duoc         đầu ra không phải object hoặc có `error`
Tổng tiền hoá đơn bán lẻ là trường `total`; dòng hàng là `price`; hoá đơn cước là `unit_price` của từng khoản, `subtotal`,
`vat_amount`, `total`, `vat_rate`.

CHẠY (không cần GPU, không cần mạng)
    python -m offline_training.phan_loai_loi_vlm --de /content/vlm_hoadon/eval_vlm_hoadon.jsonl \\
        --ket-qua 3b.json --ket-qua q25vl7b.json --chan
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from offline_training.vlm_hoadon import _chuan  # noqa: E402

# Tolerance khi coi hai số là "cùng một con số lệch lũy thừa của 10": 55192 so với 55192500 lệch 0,0009% vì cụt phần lẻ.
DUNG_SAI_LUY_THUA = 0.01
TRUONG_TIEN = ("total", "subtotal", "vat_amount", "price", "unit_price")


def _so(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x)


def so_sanh(gt: Any, out: Any) -> str:
    """Một tag cho một cặp (đáp án, đầu ra): `dung`, `x10^k`, `sai_khac`, `khong_co_so`, `dien_0`, `dien_so`."""
    if gt is None:
        o = _so(out)
        if out is None:
            return "dung"
        if o == 0.0:
            return "dien_0"
        return "dien_so"
    g, o = _so(gt), _so(out)
    if g is None:
        return "dung" if out == gt else "sai_khac"
    if o is None:
        return "khong_co_so"
    if abs(g - o) < 0.5:
        return "dung"
    if g == 0 or o <= 0 or g < 0:
        return "sai_khac"
    r = o / g
    k = round(math.log10(r))
    if k != 0 and abs(r / (10 ** k) - 1) < DUNG_SAI_LUY_THUA:
        return f"x10^{k}"
    return "sai_khac"


def _tag(truong: str, kq: str) -> str | None:
    return None if kq == "dung" else f"{truong}:{kq}"


def _ghep_theo_ten(gt_items: list[dict], out_items: list[Any]) -> tuple[list[tuple[dict, dict]], bool]:
    """Ghép dòng đáp án với dòng đầu ra theo tên đã chuẩn hoá (trùng tên thì theo thứ tự). Trả (cặp, có dòng thiếu/thừa)."""
    con = [i for i in out_items if isinstance(i, dict)]
    tu: Counter = Counter()
    chua: dict[str, list[dict]] = {}
    for i in con:
        chua.setdefault(_chuan(i.get("name")), []).append(i)
    cap: list[tuple[dict, dict]] = []
    thieu = False
    for g in gt_items:
        ten = _chuan(g["name"])
        ds = chua.get(ten, [])
        if tu[ten] < len(ds):
            cap.append((g, ds[tu[ten]]))
            tu[ten] += 1
        else:
            thieu = True
    thua = len(con) != len(cap)
    return cap, thieu or thua


def phan_loai_ca(ca: dict[str, Any], out: Any) -> list[str]:
    """Danh sách tag cho MỘT ca. Rỗng nghĩa là mọi trường tiền đều đúng."""
    if not isinstance(out, dict) or "error" in out:
        return ["khong_doc_duoc"]
    gt = ca["gt"]
    tags: list[str] = []

    def them(t: str | None) -> None:
        if t and t not in tags:
            tags.append(t)

    if ca["kind"] == "retail":
        them(_tag("total", so_sanh(gt["total"], out.get("total"))))
        raw: list[Any] = out["items"] if isinstance(out.get("items"), list) else []
        cap, lech_dong = _ghep_theo_ten(gt["items"], raw)
        if lech_dong:
            them("dong:thieu_hoac_thua")
        for g, o in cap:
            kq = so_sanh(g["price"], o.get("price"))
            if kq != "dung":
                p = _so(o.get("price"))
                if kq == "sai_khac" and g["qty"] != 1 and p is not None and abs(p - g["price"] * g["qty"]) < 0.5:
                    them("gia:la_thanh_tien")
                else:
                    them(_tag("price", kq))
            if _so(o.get("qty", 1.0)) != float(g["qty"]):
                them("sl:sai")
    else:
        for truong in ("total", "subtotal", "vat_amount", "vat_rate"):
            them(_tag(truong, so_sanh(gt.get(truong), out.get(truong))))
        raw = out["charges"] if isinstance(out.get("charges"), list) else []
        con = [c for c in raw if isinstance(c, dict)]
        gt_ch = gt["charges"]
        if len(con) != len(gt_ch):
            them("dong:thieu_hoac_thua")
        theo_loai: dict[Any, list[dict]] = {}
        for c in con:
            theo_loai.setdefault(c.get("kind"), []).append(c)
        da: Counter = Counter()
        for g in gt_ch:
            ds = theo_loai.get(g["kind"], [])
            if da[g["kind"]] < len(ds):
                o = ds[da[g["kind"]]]
                da[g["kind"]] += 1
                kq = so_sanh(g["unit_price"], o.get("unit_price"))
                if kq != "dung":
                    p = _so(o.get("unit_price"))
                    if kq == "sai_khac" and g["quantity"] != 1 and p is not None and abs(p - g["unit_price"] * g["quantity"]) < 0.5:
                        them("gia:la_thanh_tien")
                    else:
                        them(_tag("unit_price", kq))
                if _so(o.get("quantity", 1.0)) != float(g["quantity"]):
                    them("sl:sai")
            else:
                them("dong:thieu_hoac_thua")
    return tags


def la_luy_thua_10(tag: str) -> bool:
    truong, _, loai = tag.partition(":")
    return truong in TRUONG_TIEN and loai.startswith("x10^")


def phan_loai(ca_list: list[dict], rows: list[dict]) -> dict[str, Any]:
    """Gom theo tag cho một lần chạy. `rows` là `rows` trong file `--json` của `do_vlm_hoa_don.py` (mỗi dòng có `id` và `out`)."""
    theo_id = {c["id"]: c for c in ca_list}
    dem: Counter = Counter()
    ma_theo_tag: dict[str, list[str]] = {}
    luy_thua: list[str] = []
    bo_qua: list[str] = []
    sach = 0
    for r in rows:
        ca = theo_id.get(r.get("id"))
        if ca is None:
            bo_qua.append(str(r.get("id")))
            continue
        tags = phan_loai_ca(ca, r.get("out"))
        if not tags:
            sach += 1
        for t in tags:
            dem[t] += 1
            ma_theo_tag.setdefault(t, []).append(ca["id"])
        if any(la_luy_thua_10(t) for t in tags):
            luy_thua.append(ca["id"])
    return {"n": len(rows) - len(bo_qua), "khong_loi_tien": sach, "dem": dict(dem), "ma": ma_theo_tag,
            "LECH_LUY_THUA_10": luy_thua, "khong_co_trong_de": bo_qua}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--de", required=True, help="eval_vlm_hoadon.jsonl (có `gt` của từng ca)")
    p.add_argument("--ket-qua", action="append", required=True, help="file --json của do_vlm_hoa_don.py (lặp lại)")
    p.add_argument("--chan", action="store_true", help="thoát mã 1 nếu BẤT KỲ lần chạy nào có ca lệch lũy thừa của 10")
    p.add_argument("--json", dest="json_out", default="")
    a = p.parse_args(argv)

    try:
        ca_list = [json.loads(d) for d in Path(a.de).read_text(encoding="utf-8").splitlines() if d.strip()]
    except FileNotFoundError:
        print(f"Không có {a.de}", file=sys.stderr)
        return 2
    tong: dict[str, Any] = {}
    co_luy_thua = False
    for tep in a.ket_qua:
        try:
            rows = json.loads(Path(tep).read_text(encoding="utf-8")).get("rows") or []
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            print(f"Không đọc được {tep}: {exc}", file=sys.stderr)
            return 2
        kq = phan_loai(ca_list, rows)
        tong[tep] = kq
        print(f"\n[{Path(tep).name}] {kq['n']} ca, {kq['khong_loi_tien']} ca không có lỗi tiền")
        for t, n in sorted(kq["dem"].items(), key=lambda x: (-x[1], x[0])):
            ma = ", ".join(kq["ma"][t][:6]) + (" …" if n > 6 else "")
            print(f"  {n:3d}  {t:<24} {ma}")
        if kq["khong_co_trong_de"]:
            print(f"  ⚠ {len(kq['khong_co_trong_de'])} dòng kết quả không có trong bộ đề (bỏ qua): {kq['khong_co_trong_de'][:5]}")
        if kq["LECH_LUY_THUA_10"]:
            co_luy_thua = True
            print(f"  ⛔ LECH_LUY_THUA_10 ({len(kq['LECH_LUY_THUA_10'])}): {', '.join(kq['LECH_LUY_THUA_10'])}"
                  "  — tiền sai cả nghìn lần mà lớp kiểm nhất quán không bắt được")
        else:
            print("  ✓ LECH_LUY_THUA_10: rỗng")
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(tong, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if (a.chan and co_luy_thua) else 0


if __name__ == "__main__":
    sys.exit(main())
