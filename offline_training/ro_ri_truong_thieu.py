"""
offline_training/ro_ri_truong_thieu.py — tin nhắn nhắc tới một trường mà nhãn ghi là `null` (thiếu).

VÌ SAO CÓ FILE NÀY
------------------
Bộ sinh dữ liệu trích xuất (`reverse_generate.py`) bảo DeepSeek viết một tin nhắn "TUYỆT ĐỐI KHÔNG nhắc đến điểm giao
hàng", rồi gán nhãn `destination: null`. Docstring của nó hứa tin nhắn được kiểm "trường thiếu không được nhắc tới".
Nhưng `verify_message` chỉ kiểm chiều thuận (trường CÓ nhãn phải xuất hiện), không kiểm chiều ngược. Seed chỉ giữ tên
trường bị bỏ chứ không giữ giá trị gốc, nên không so được theo giá trị: DeepSeek bịa ra "HP" hay "HN" thì vẫn qua.

Bằng chứng (Thành, #91, 18/11/2026, bốn câu mọi bản đều sai): EX0034 "ship về HP" mang nhãn `destination: null`, và EX0110
"giao nội thành HN" cũng vậy. Hệ quả không dừng ở bộ đo: cùng bộ sinh dựng cả tập huấn luyện, nơi tin nhắn có nơi đến
mà nhãn `null` dạy model bỏ sót thông tin có thật. Chưa biết tỷ lệ vì dữ liệu nằm trên Drive.

CÁCH LÀM, VÀ GIỚI HẠN
---------------------
Không có giá trị gốc để so, nên dò theo TẬP ĐỊA DANH ĐÃ BIẾT (chính các danh sách `ORIGINS`, `DESTINATIONS`,
`VEHICLE_PHRASES` mà bộ seed dùng, một định nghĩa, R4) cộng vài viết tắt. Hậu quả:

  - Bắt được: địa danh trong tập, "HP"/"HN", cụm trọng tải ("3 tấn", "5t", "1t5", "đầu kéo", "cont").
  - KHÔNG bắt được: địa danh DeepSeek tự bịa ngoài tập. Số bắt được là CẬN DƯỚI của số rò thật.
  - Có thể bắt oan: "HP" là mã lực của xe, "5 tấn" là khối lượng hàng chứ không phải loại xe. Với bộ sinh, bắt oan chỉ
    tốn một lần viết lại; với dữ liệu đã có, người đọc quyết (đọc nguyên văn các dòng bị dò).
  - Địa danh trùng với giá trị GỐC của trường khác không bị tính là rò: "KCN VSIP Bắc Ninh" là điểm lấy hàng, không phải
    "Bắc Ninh" là điểm giao.

CHẠY (không cần GPU, không cần mạng, không cần khoá)
----------------------------------------------------
    python -m offline_training.ro_ri_truong_thieu                       # cả train lẫn eval trong GENERATED_DIR
    python -m offline_training.ro_ri_truong_thieu a.jsonl b.jsonl --json ra.json
    python -m offline_training.ro_ri_truong_thieu --chan                # thoát 1 nếu có dòng nghi rò
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from offline_training.dgen_common import GENERATED_DIR, load_jsonl, strip_diacritics  # noqa: E402
from offline_training.make_extraction_seeds import (  # noqa: E402
    DESTINATIONS,
    ORIGINS,
    VEHICLE_PHRASES,
)

# Viết tắt hay gặp trong tin nhắn nhắn vội (chính `STYLES` của bộ seed nhắc 'HP'). Giữ ngắn và ít nhập nhằng: thêm một
# viết tắt hai chữ cái là thêm khả năng bắt oan ("DN", "BN", "TH" đều có nghĩa khác).
VIET_TAT_DIA_DANH = ("hp", "hn")

TRUONG_KIEM = ("origin", "destination", "vehicle_type")

_BIEN_TRAI = r"(?<![a-z0-9])"
_BIEN_PHAI = r"(?![a-z0-9])"
# "3 tấn", "3t", "3 t", "1t5", "1.5 tan". Không khớp "t3" (thứ 3) và "3 tháng" (sau chữ t còn chữ cái).
_TRONG_TAI = re.compile(r"(?<![a-z0-9])\d+(?:[.,]\d+)?\s*t(?:an)?(?![a-z])")
_TRONG_TAI_CHU = re.compile(r"(?<![a-z])(?:mot|hai|ba|bon|nam|sau|bay|tam|chin|muoi)\s+tan(?![a-z])")


def _chuan(s: str) -> str:
    return " ".join(strip_diacritics(s).lower().split())


def _tim_tu(van_ban: str, tu: str) -> bool:
    return re.search(_BIEN_TRAI + re.escape(tu) + _BIEN_PHAI, van_ban) is not None


def _bo_gia_tri_goc(van_ban: str, gt: dict[str, Any], *truong: str) -> str:
    """Xoá khỏi văn bản (đã chuẩn hoá) giá trị GỐC của các trường nêu tên, để nó không bị tính là rò của trường khác."""
    for t in truong:
        v = gt.get(t)
        if v:
            van_ban = van_ban.replace(_chuan(str(v)), " ")
    return van_ban


def truong_thieu_bi_nhac(message: str, gt: dict[str, Any]) -> list[tuple[str, str]]:
    """
    `[(trường, đoạn khớp), ...]` cho mỗi trường trong `origin`/`destination`/`vehicle_type` mà `gt` ghi thiếu (None hoặc
    rỗng) nhưng `message` lại nhắc tới. Rỗng nghĩa là KHÔNG thấy rò trong tập đã biết, không phải "chắc chắn sạch".
    """
    m = _chuan(message)
    ra: list[tuple[str, str]] = []

    if not gt.get("destination"):
        sach = _bo_gia_tri_goc(m, gt, "origin")
        for d in (*DESTINATIONS, *VIET_TAT_DIA_DANH):
            if _tim_tu(sach, _chuan(d)):
                ra.append(("destination", d))
                break

    if not gt.get("origin"):
        sach = _bo_gia_tri_goc(m, gt, "destination")
        for o in ORIGINS:
            if _tim_tu(sach, _chuan(o)):
                ra.append(("origin", o))
                break

    if not gt.get("vehicle_type"):
        khop = None
        for cum in (p for ds in VEHICLE_PHRASES.values() for p in ds):
            if _tim_tu(m, _chuan(cum)):
                khop = cum
                break
        if khop is None:
            mm = _TRONG_TAI.search(m) or _TRONG_TAI_CHU.search(m)
            khop = mm.group(0) if mm else None
        if khop is None:
            for tu in ("dau keo", "container", "cont"):
                if _tim_tu(m, tu):
                    khop = tu
                    break
        if khop:
            ra.append(("vehicle_type", khop))

    return ra


# ---------------------------------------------------------------------------
# Dò trên tệp dữ liệu đã sinh
# ---------------------------------------------------------------------------

_TIEN_TO_TIN_NHAN = "Tin nhắn: "


def tach_dong(row: dict) -> tuple[str, dict] | None:
    """
    `(tin nhắn, nhãn)` của một dòng MỘT LƯỢT, hoặc None. Hiểu hai định dạng bộ sinh ghi ra:
    eval (`message` + `ground_truth`) và train (`messages` = system, user, assistant).
    Dòng hai lượt bỏ qua: lượt 2 cố ý không nhắc lại điểm đi/đến nên không áp luật này.
    """
    if "messages" in row:
        ms = row["messages"]
        if len(ms) != 3:
            return None
        user, asst = ms[1].get("content", ""), ms[2].get("content", "")
        if _TIEN_TO_TIN_NHAN not in user:
            return None
        try:
            gt = json.loads(asst)
        except (TypeError, ValueError):
            return None
        return user.split(_TIEN_TO_TIN_NHAN, 1)[1], gt if isinstance(gt, dict) else {}
    if row.get("kind", "single") != "single" or "message" not in row:
        return None
    gt = row.get("ground_truth")
    return (str(row["message"]), gt) if isinstance(gt, dict) else None


def soat(rows: list[dict]) -> dict[str, Any]:
    """Đếm theo trường: bao nhiêu dòng có trường đó thiếu, và bao nhiêu trong số đó bị dò thấy nhắc tới."""
    quet = 0
    co_thieu = {t: 0 for t in TRUONG_KIEM}
    nghi: list[dict[str, str]] = []
    for row in rows:
        td = tach_dong(row)
        if td is None:
            continue
        quet += 1
        msg, gt = td
        for t in TRUONG_KIEM:
            if not gt.get(t):
                co_thieu[t] += 1
        for truong, khop in truong_thieu_bi_nhac(msg, gt):
            nghi.append({"id": str(row.get("_id", "?")), "truong": truong, "khop": khop, "tin_nhan": msg})
    theo_truong = {t: sum(1 for n in nghi if n["truong"] == t) for t in TRUONG_KIEM}
    return {"quet": quet, "co_truong_thieu": co_thieu, "nghi_ro": nghi, "nghi_theo_truong": theo_truong}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tep", nargs="*", help="tệp .jsonl; mặc định train_extraction và eval_extraction trong GENERATED_DIR")
    p.add_argument("--json", dest="json_out", default="", help="ghi kết quả đầy đủ ra tệp JSON")
    p.add_argument("--chan", action="store_true", help="thoát mã 1 nếu có dòng nghi rò")
    p.add_argument("--in-toi-da", type=int, default=15)
    a = p.parse_args(argv)

    duong = [Path(x) for x in a.tep] or [GENERATED_DIR / "train_extraction.jsonl", GENERATED_DIR / "eval_extraction.jsonl"]
    tong_nghi = 0
    khong_do_duoc = 0
    ket_qua: dict[str, Any] = {}
    for d in duong:
        rows = load_jsonl(d) if d.exists() else []
        if not rows:
            print(f"\n[{d.name}] KHÔNG ĐỌC ĐƯỢC hoặc rỗng — không dò được ({d})")
            ket_qua[d.name] = None
            khong_do_duoc += 1
            continue
        r = soat(rows)
        ket_qua[d.name] = r
        tong_nghi += len(r["nghi_ro"])
        print(f"\n[{d.name}] quét {r['quet']} dòng một lượt (bỏ qua dòng hai lượt)")
        for t in TRUONG_KIEM:
            thieu, nghi = r["co_truong_thieu"][t], r["nghi_theo_truong"][t]
            ty_le = f"{nghi / thieu * 100:.1f}%" if thieu else "—"
            print(f"  {t:<13} nhãn thiếu {thieu:>4}   trong đó tin nhắn nhắc tới {nghi:>3}  ({ty_le})")
        for n in r["nghi_ro"][: a.in_toi_da]:
            print(f"  ? {n['id']} [{n['truong']}={n['khop']!r}] {n['tin_nhan'][:110]!r}")
        if len(r["nghi_ro"]) > a.in_toi_da:
            print(f"  … còn {len(r['nghi_ro']) - a.in_toi_da} dòng (xem --json)")
    print("\nĐây là CẬN DƯỚI: chỉ bắt địa danh/viết tắt trong tập đã biết; địa danh tự bịa ngoài tập không bị dò. "
          "Đọc nguyên văn các dòng nghi trước khi kết luận (có thể bắt oan, ví dụ 'HP' là mã lực).")
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(ket_qua, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.chan:
        # Không dò được KHÔNG phải là sạch: mã 2 riêng, khác mã 1 (có dòng nghi rò), như `benchmark_v3 --doi-du-tap-do`.
        if khong_do_duoc:
            return 2
        return 1 if tong_nghi else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
