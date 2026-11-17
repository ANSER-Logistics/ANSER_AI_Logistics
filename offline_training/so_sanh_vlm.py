"""
offline_training/so_sanh_vlm.py — đặt nhiều lần đo model thị giác cạnh nhau và nói thật chênh lệch nào đáng tin.

VÌ SAO CÓ FILE NÀY
------------------
Chủ dự án không xin được giấy phép Qwen2.5-VL-3B nên phải chọn model thay (17/11/2026). Mỗi ứng viên chạy
`do_vlm_hoa_don.py` ra một file `--json`. Đặt hai bảng k/n cạnh nhau bằng mắt rất dễ đọc nhiễu thành khác biệt:
28 ca, mỗi ô chỉ vài ca, một ca đổi chiều là 3,6 điểm phần trăm. Công cụ này làm hai việc mà mắt không làm được:

  1. Khoảng tin cậy Wilson 95% cho từng model (15/28 là khoảng 36 đến 70%, không phải "54%").
  2. So THEO CẶP từng ca với mốc bằng kiểm định McNemar chính xác. Hai model cùng đọc cùng 28 tờ, nên chỉ những
     ca hai bên khác nhau (b: mốc đúng, model sai; c: mốc sai, model đúng) mới mang thông tin.

TỪ CHỐI so hai lần đo khác bộ đề: các file phải có cùng tập `id` ca. Hai lần đo trên bộ ảnh khác nhau (ví dụ
trước và sau PR #107 sửa lỗi bộ đo) không so được với nhau, và công cụ báo lỗi thay vì in một con số vô nghĩa.

CHẠY
    python offline_training/so_sanh_vlm.py 3b=truoc_3b.json q3vl2b=q3vl2b.json q3vl4b=q3vl4b.json

Mốc là lần đo ĐẦU TIÊN trong dòng lệnh, hoặc đặt `--moc TÊN` (một tên đã có, không phải tên=file). Không GPU,
không mạng, không dữ liệu khách (R2): chỉ đọc file `--json`.

CON SỐ NÀY NÓI GÌ: ảnh hư cấu, chữ in sạch, n nhỏ. So sánh TƯƠNG ĐỐI giữa các model trên cùng bộ ảnh là việc
dữ liệu tổng hợp làm được; nói "model này đọc đúng X% hoá đơn thật" thì không.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Thống kê thuần
# ---------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Khoảng tin cậy Wilson cho tỷ lệ k/n. n = 0 thì (0, 1): chưa biết gì."""
    if n <= 0:
        return 0.0, 1.0
    if not 0 <= k <= n:
        raise ValueError(f"k={k} ngoài 0..n={n}")
    p = k / n
    mau = 1 + z * z / n
    tam = (p + z * z / (2 * n)) / mau
    nua = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / mau
    return max(0.0, tam - nua), min(1.0, tam + nua)


def mcnemar_chinh_xac(b: int, c: int) -> float:
    """
    p hai phía của kiểm định McNemar chính xác (nhị thức, p = 1/2) trên b + c ca bất đồng.
    b = mốc đúng mà model sai; c = mốc sai mà model đúng. Không có ca bất đồng nào thì p = 1.
    """
    if b < 0 or c < 0:
        raise ValueError("b và c không âm")
    n = b + c
    if n == 0:
        return 1.0
    nho = min(b, c)
    duoi = sum(math.comb(n, i) for i in range(nho + 1)) / (2 ** n)
    return min(1.0, 2 * duoi)


# ---------------------------------------------------------------------------
# Đọc và so
# ---------------------------------------------------------------------------

_TRUONG = ("id", "tat_ca_dung")


def doc_ket_qua(duong_dan: str | Path) -> list[dict[str, Any]]:
    """Đọc `rows` từ file `--json` của do_vlm_hoa_don.py; báo rõ nếu thiếu trường cần."""
    du_lieu = json.loads(Path(duong_dan).read_text(encoding="utf-8"))
    rows = du_lieu.get("rows") if isinstance(du_lieu, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{duong_dan}: không có `rows` (file này không phải đầu ra của do_vlm_hoa_don.py --json?)")
    for r in rows:
        thieu = [t for t in _TRUONG if t not in r]
        if thieu:
            raise ValueError(f"{duong_dan}: ca {r.get('id')!r} thiếu trường {thieu}")
    return rows


def _theo_id(rows: list[dict[str, Any]], ten: str) -> dict[str, dict[str, Any]]:
    ra: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r["id"] in ra:
            raise ValueError(f"{ten}: id ca {r['id']!r} xuất hiện hai lần")
        ra[r["id"]] = r
    return ra


def so_sanh(ket_qua: dict[str, list[dict[str, Any]]], moc: str) -> dict[str, Any]:
    """
    `ket_qua`: tên lần đo -> rows. Trả bảng từng model: k/n, Wilson, và so theo cặp với `moc`.
    Ném ValueError nếu các lần đo không cùng tập id ca (không so được).
    """
    if moc not in ket_qua:
        raise ValueError(f"mốc {moc!r} không có trong {sorted(ket_qua)}")
    theo_id = {ten: _theo_id(rows, ten) for ten, rows in ket_qua.items()}
    tap_moc = set(theo_id[moc])
    for ten, d in theo_id.items():
        if set(d) != tap_moc:
            khac = sorted(set(d) ^ tap_moc)
            raise ValueError(
                f"{ten} và mốc {moc} KHÔNG cùng bộ đề ({len(khac)} id khác nhau, ví dụ {khac[:3]}): "
                "không so được. Chạy lại cả hai trên cùng bộ ảnh."
            )
    ids = sorted(tap_moc)
    bang: dict[str, dict[str, Any]] = {}
    for ten, d in theo_id.items():
        n = len(ids)
        k = sum(bool(d[i].get("tat_ca_dung")) for i in ids)
        k_tong = sum(bool(d[i].get("tong_dung")) for i in ids)
        lo, hi = wilson(k, n)
        dong: dict[str, Any] = {
            "n": n, "k": k, "ti_le": k / n, "wilson": (lo, hi), "k_tong": k_tong,
            "dien_0": sum(int(d[i].get("dien_0", 0)) for i in ids),
            "chep_lenh": sum(bool(d[i].get("chep_nhieu_loan")) for i in ids),
            "khong_parse": sum(not d[i].get("parse", True) for i in ids),
        }
        if ten != moc:
            b = sum(bool(theo_id[moc][i].get("tat_ca_dung")) and not d[i].get("tat_ca_dung") for i in ids)
            c = sum((not theo_id[moc][i].get("tat_ca_dung")) and bool(d[i].get("tat_ca_dung")) for i in ids)
            dong.update(b=b, c=c, p=mcnemar_chinh_xac(b, c))
        bang[ten] = dong
    return {"moc": moc, "n": len(ids), "bang": bang}


def in_bang(kq: dict[str, Any]) -> str:
    moc = kq["moc"]
    dong = [
        f"Mốc: {moc}. n = {kq['n']} ca, cùng một bộ đề. 'đúng hết' = mọi trường đúng.",
        "",
        f"{'model':<18}{'đúng hết':>10}{'Wilson 95%':>16}{'tổng đúng':>11}{'điền 0':>8}{'chép lệnh':>11}"
        f"{'b':>4}{'c':>4}{'p (McNemar)':>14}",
    ]
    for ten, g in kq["bang"].items():
        lo, hi = g["wilson"]
        co_cap = "p" in g
        khoang = f"{lo * 100:.0f}-{hi * 100:.0f}%"
        dong.append(
            f"{ten:<18}{g['k']:>6}/{g['n']:<3}{khoang:>13}{g['k_tong']:>8}/{g['n']:<2}"
            f"{g['dien_0']:>8}{g['chep_lenh']:>8}/{g['n']:<2}"
            + (f"{g['b']:>4}{g['c']:>4}{g['p']:>14.3f}" if co_cap else f"{'(mốc)':>22}")
        )
    dong += [
        "",
        "b = ca mốc đúng mà model sai; c = ca mốc sai mà model đúng. p nhỏ hơn 0,05 mới đáng tin là khác thật.",
        "Với 28 ca, mỗi ca đổi chiều là 3,6 điểm phần trăm: chênh dưới khoảng 20 điểm gần như luôn là nhiễu.",
        "'điền 0' là số TRƯỜNG (đáp án null mà model điền 0). So nhiều model với một mốc thì mỗi p cần hiệu chỉnh "
        "(nhân với số model, Bonferroni).",
    ]
    return "\n".join(dong)


def _doc_doi(xau: str) -> tuple[str, str]:
    if "=" not in xau:
        raise argparse.ArgumentTypeError(f"cần dạng TÊN=file.json, nhận {xau!r}")
    ten, _, duong = xau.partition("=")
    if not ten or not duong:
        raise argparse.ArgumentTypeError(f"cần dạng TÊN=file.json, nhận {xau!r}")
    return ten, duong


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("lan_do", nargs="+", type=_doc_doi, metavar="TÊN=file.json",
                    help="các lần đo; tên đầu tiên là mốc trừ khi có --moc")
    ap.add_argument("--moc", default="", help="tên lần đo làm mốc")
    args = ap.parse_args(argv)
    ten_ds = [t for t, _ in args.lan_do]
    if len(set(ten_ds)) != len(ten_ds):
        # cùng tên hai lần: giữ một (cho phép lặp mốc trong dòng lệnh cho tiện) nếu cùng file
        gom: dict[str, str] = {}
        for t, p in args.lan_do:
            if t in gom and gom[t] != p:
                raise SystemExit(f"tên {t!r} trỏ tới hai file khác nhau: {gom[t]} và {p}")
            gom[t] = p
        args.lan_do = list(gom.items())
        ten_ds = list(gom)
    ket_qua = {t: doc_ket_qua(p) for t, p in args.lan_do}
    try:
        kq = so_sanh(ket_qua, args.moc or ten_ds[0])
    except ValueError as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return 2
    print(in_bang(kq))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
