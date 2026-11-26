"""
offline_training/bao_cao_metrics.py — báo cáo tổng hợp từ `ai_metrics_log` (S4: nhật ký ghi từ lâu mà chưa ai đọc).

    python offline_training/bao_cao_metrics.py [tệp.jsonl ...] [--tu YYYY-MM-DD] [--json]

Mặc định đọc `AI_METRICS_PATH` (hay `src/data/ai_metrics_log.jsonl`). In: mỗi nhánh bao nhiêu lượt, tỷ lệ đạt, bị chốt chặn vì gì, lỗi loại nào,
hỏi lại, workflow, p95 độ trễ và ms/token, kèm mục "đáng xem".

R2: CHỈ đọc một danh sách trường cho phép và CHỈ in số đếm cùng nhãn ngắn do mã đặt. Không in câu hỏi, câu trả lời, `extra`, mã người dùng hay mã cửa hàng.
Nhãn lạ (dài, có xuống dòng, trông như nội dung) bị gộp vào "(khác)".
R1: thiếu dữ liệu thì nói "không biết", không đếm là 0; tỷ lệ chỉ chia trên số lượt có trường đó. Không có lượt nào thì mã thoát 2, không phải "không có vấn đề".
p95 và ngưỡng dùng lại `nguong_p95` (một định nghĩa với /health).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, cast

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from src.core import nguong_p95  # noqa: E402
from src.core.metrics import METRICS_PATH, TurnMetric, _ms_moi_token  # noqa: E402

KHAC = "(khác)"
# Nhãn mã (nhánh, cách định tuyến, kế hoạch tool): định danh ASCII liền, không dấu cách. Nhãn lý do chặn: cụm chữ THƯỜNG ngắn, không chữ số.
_NHAN = re.compile(r"[A-Za-z0-9_.+,\-]{1,40}")
_LY_DO = re.compile(r"[^\W\d_A-Z]+(?: [^\W\d_A-Z]+){0,5}")
_LOAI_LOI = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,59}(?:Error|Exception|Timeout|Unavailable|Truncated|Overloaded)")


def nhan(gia_tri: Any) -> str:
    """Nhãn định danh an toàn để in (nhánh, cách định tuyến, kế hoạch tool); không đúng khuôn là "(khác)"."""
    return gia_tri if isinstance(gia_tri, str) and _NHAN.fullmatch(gia_tri) else KHAC


def ly_do(gia_tri: Any) -> str:
    """Lý do chặn: phần trước dấu ':' (như `/health`), chỉ khi là cụm chữ thường ngắn do mã đặt; chữ hoa hay chữ số là "(khác)"."""
    if not isinstance(gia_tri, str):
        return KHAC
    dau = gia_tri.split(":")[0].strip()
    return dau if len(dau) <= 30 and dau == dau.lower() and _LY_DO.fullmatch(dau) else KHAC


def loai_loi_ghi(gia_tri: Any) -> str:
    """Chỉ TÊN LỚP lỗi đứng đầu chuỗi; thông điệp lỗi có thể chứa nội dung nên không bao giờ in."""
    if isinstance(gia_tri, str):
        m = _LOAI_LOI.match(gia_tri.strip())
        if m:
            return m.group(0)
    return KHAC


def doc(duong: Iterable[Path], tu: str = "") -> tuple[list[dict], int]:
    """Các dòng đọc được (từ ngày `tu`, so tiền tố ISO của `ts`) và số dòng hỏng."""
    dong, hong = [], 0
    for p in duong:
        with open(p, encoding="utf-8", errors="replace") as f:
            for tho in f:
                if not tho.strip():
                    continue
                try:
                    o = json.loads(tho)
                except ValueError:
                    hong += 1
                    continue
                if not isinstance(o, dict) or "route" not in o:
                    hong += 1
                    continue
                if tu and str(o.get("ts") or "")[:10] < tu:
                    continue
                dong.append(o)
    return dong, hong


def _so(v: Any) -> float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None


def _co(dong: list[dict], truong: str) -> dict[str, int]:
    """Đếm cờ ba trạng thái: đúng, sai, và số lượt BIẾT."""
    biet = [d[truong] for d in dong if isinstance(d.get(truong), bool)]
    return {"dung": sum(biet), "biet": len(biet)}


def tom_tat_nhom(dong: list[dict]) -> dict:
    tre = [v for d in dong if (v := _so(d.get("latency_ms"))) is not None]
    tok = [v for d in dong if (v := _ms_moi_token(cast(TurnMetric, SimpleNamespace(
        completion_tokens=_so(d.get("completion_tokens")), model_ms=_so(d.get("model_ms")))))) is not None]
    return {
        "luot": len(dong),
        "dat": _co(dong, "ok"),
        "bi_chan": sum(1 for d in dong if d.get("blocked_reason")),
        "loi": sum(1 for d in dong if d.get("error")),
        "hoi_lai": _co(dong, "asked_back"),
        "workflow_hop_le": _co(dong, "workflow_valid"),
        "workflow_thu_lai": _co(dong, "workflow_retried"),
        "tra_web": _co(dong, "web_fallback"),
        "p95_ms": nguong_p95.p95(tre),
        "p95_ms_moi_token": None if not tok else round(nguong_p95.p95(tok) or 0, 1),
        "so_mau_ms_moi_token": len(tok),
    }


def bao_cao(dong: list[dict], hong: int = 0) -> dict:
    theo_nhanh: dict[str, list[dict]] = {}
    for d in dong:
        theo_nhanh.setdefault(nhan(d.get("route")), []).append(d)
    ngay = sorted(ng for d in dong if (ng := str(d.get("ts") or "")[:10]) and re.fullmatch(r"\d{4}-\d\d-\d\d", ng))
    chung = tom_tat_nhom(dong)
    nguong_ms, nguong_tok = nguong_p95.doc_nguong()
    _, toi_thieu = nguong_p95.doc_cua_so()

    xem: list[str] = []
    for ten, ds in sorted(theo_nhanh.items()):
        t = tom_tat_nhom(ds)
        truot = t["dat"]["biet"] - t["dat"]["dung"]
        if truot:
            xem.append(f"{ten}: {truot}/{t['dat']['biet']} lượt không đạt")
        if t["bi_chan"]:
            xem.append(f"{ten}: {t['bi_chan']}/{t['luot']} lượt bị chốt chặn câu trả lời")
    if chung["so_mau_ms_moi_token"] < toi_thieu:
        xem.append(f"ms/token: không đủ mẫu để kết luận ({chung['so_mau_ms_moi_token']}/{toi_thieu})")
    elif chung["p95_ms_moi_token"] > nguong_tok:
        xem.append(f"ms/token p95 {chung['p95_ms_moi_token']} vượt ngưỡng {nguong_tok}")
    if hong:
        xem.append(f"{hong} dòng nhật ký không đọc được")

    return {
        "tu_ngay": ngay[0] if ngay else None,
        "den_ngay": ngay[-1] if ngay else None,
        "dong_hong": hong,
        "chung": chung,
        "theo_nhanh": {k: tom_tat_nhom(v) for k, v in sorted(theo_nhanh.items())},
        "ly_do_chan": dict(Counter(ly_do(d["blocked_reason"]) for d in dong if d.get("blocked_reason")).most_common()),
        "loai_loi": dict(Counter(loai_loi_ghi(d["error"]) for d in dong if d.get("error")).most_common()),
        "cach_dinh_tuyen": dict(Counter(nhan(d["router_method"]) for d in dong if d.get("router_method")).most_common()),
        "ke_hoach_tool": dict(Counter(nhan(d["tool_plan"]) for d in dong if d.get("tool_plan")).most_common()),
        "nguong": {"tong_ms": nguong_ms, "ms_moi_token": nguong_tok},
        "dang_xem": xem,
    }


def _ty_le(c: dict) -> str:
    return "không biết" if not c["biet"] else f"{c['dung']}/{c['biet']} ({100 * c['dung'] / c['biet']:.0f}%)"


def _gia(v: Any) -> str:
    return "không biết" if v is None else f"{v:g}"


def in_markdown(r: dict) -> str:
    ra = [f"# Báo cáo nhật ký Brain: {r['tu_ngay'] or '?'} đến {r['den_ngay'] or '?'} ({r['chung']['luot']} lượt)", "", "## Đáng xem"]
    ra += [f"- {x}" for x in r["dang_xem"]] or ["- không có mục nào vượt ngưỡng trên dữ liệu này"]
    ra += ["", "## Theo nhánh", "", "| Nhánh | Lượt | Đạt | Bị chặn | Lỗi | Hỏi lại | p95 ms | p95 ms/token |", "|---|---:|---|---:|---:|---|---:|---:|"]
    for ten, t in [*r["theo_nhanh"].items(), ("Tất cả", r["chung"])]:
        ra.append(f"| {ten} | {t['luot']} | {_ty_le(t['dat'])} | {t['bi_chan']} | {t['loi']} | {_ty_le(t['hoi_lai'])} | "
                  f"{_gia(t['p95_ms'])} | {_gia(t['p95_ms_moi_token'])} |")
    c = r["chung"]
    ra += ["", f"Workflow hợp lệ: {_ty_le(c['workflow_hop_le'])}; phải thử lại: {_ty_le(c['workflow_thu_lai'])}; được tra web: {_ty_le(c['tra_web'])}."]
    for tieu_de, khoa in (("Lý do chặn", "ly_do_chan"), ("Loại lỗi", "loai_loi"), ("Cách định tuyến", "cach_dinh_tuyen"), ("Kế hoạch tool", "ke_hoach_tool")):
        if r[khoa]:
            ra += ["", f"## {tieu_de}", ""] + [f"- {k}: {v}" for k, v in r[khoa].items()]
    return "\n".join(ra)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Báo cáo tổng hợp ai_metrics_log (không in nội dung).")
    ap.add_argument("tep", nargs="*", help="tệp JSONL; bỏ trống thì dùng AI_METRICS_PATH")
    ap.add_argument("--tu", default="", help="chỉ tính từ ngày YYYY-MM-DD (UTC)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.tu and not re.fullmatch(r"\d{4}-\d\d-\d\d", a.tu):
        ap.error("--tu phải theo dạng YYYY-MM-DD")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    duong = [Path(t) for t in a.tep] or [Path(os.getenv("AI_METRICS_PATH") or METRICS_PATH or "")]
    thieu = [p for p in duong if not p.is_file()]
    if thieu:
        print(f"CHƯA CÓ DỮ LIỆU: không thấy tệp {', '.join(str(p) for p in thieu)}.", file=sys.stderr)
        return 2
    dong, hong = doc(duong, a.tu)
    if not dong:
        print(f"CHƯA CÓ DỮ LIỆU: 0 lượt đọc được ({hong} dòng hỏng). Đây không phải kết luận 'không có vấn đề'.", file=sys.stderr)
        return 2
    r = bao_cao(dong, hong)
    print(json.dumps(r, ensure_ascii=False, indent=2) if a.json else in_markdown(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
