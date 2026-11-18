"""
offline_training/bang_nhieu_lan_chay.py — đặt NHIỀU lần chạy `benchmark_v3` cạnh nhau (v3, v4, Claude, DeepSeek...).

VÌ SAO CÓ FILE NÀY
------------------
`compare_runs.py` so đúng HAI lần chạy. Câu hỏi của #91 không dừng ở hai: v4 làm hỏng 14 câu n8n mà v3 làm đúng, nhưng
14 câu đó hỏng vì model, hay vì đề bài vốn mơ hồ hoặc cấu trúc kiểm không công bằng? Một model mạnh (Claude, DeepSeek)
chạy trên CÙNG bộ đề trả lời được đúng câu hỏi đó:

  - cả bốn bản đều sai một câu  -> nghi ĐỀ BÀI hay bộ kiểm, không nghi model: đọc nguyên văn câu đó trước khi kết tội ai;
  - mốc tham chiếu đúng, mọi bản local sai -> khoảng cách THẬT của model, đáng sửa bằng dữ liệu;
  - bản local đúng, mốc tham chiếu sai   -> ca lạ, soát: thường là ràng buộc JSON hai bên khác nhau (`rang_buoc`).

Mốc tham chiếu KHÔNG phải đáp án. Điểm của nó là một cận để biết bộ đề có làm được hay không, và không thay cho cổng
của `benchmark_v3`. Lần chạy qua API ngoài chỉ hợp lệ trên bộ đề hoàn toàn hư cấu (R2, xem `providers.py`).

Đọc file JSON của `benchmark_v3 --json`. Không chạy model, không cần GPU, không cần mạng.

DÙNG
----
    python -m offline_training.bang_nhieu_lan_chay \\
        --lan v3=v3.json --lan v4=v4.json --lan claude=claude.json --lan deepseek=deepseek.json \\
        --tham-chieu claude,deepseek [--sau-thu-lai]

`--sau-thu-lai`: với lần chạy có mục `thu_lai` (cờ `--thu-lai-n8n`), dùng kết quả SAU MỘT LẦN THỬ LẠI cho nhánh n8n, như `/chat`.
Lần chạy không có mục đó giữ kết quả lần đầu và bảng nói thẳng điều đó.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from offline_training.stats import wilson  # noqa: E402

TOI_DA_MA_IN = 14


@dataclass(frozen=True)
class LanChay:
    nhan: str
    model: str
    rang_buoc: str
    sections: dict


def doc_lan_chay(nhan: str, duong: str) -> LanChay:
    try:
        d = json.loads(Path(duong).read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"Không có file {duong} (nhãn {nhan!r}). Chạy benchmark_v3.py với --json trước.")
    except json.JSONDecodeError as exc:
        sys.exit(f"{duong} không phải JSON hợp lệ: {exc}")
    return LanChay(nhan, str(d.get("model", "?")), str(d.get("rang_buoc", "?")), d.get("sections") or {})


def _theo_ma(muc: dict, sau_thu_lai: bool) -> tuple[dict[str, bool], bool]:
    """
    `{mã câu: đúng/sai}` của một nhánh, và cờ "đã dùng kết quả sau thử lại".
    Mã và kết quả ghép THEO `row_ids`, không theo vị trí (xem `compare_runs._khop_theo_id`).
    """
    ids = muc.get("row_ids") or []
    per_row = muc.get("per_row") or []
    dung_thu_lai = False
    if sau_thu_lai and muc.get("thu_lai") and muc["thu_lai"].get("per_row"):
        per_row = muc["thu_lai"]["per_row"]
        dung_thu_lai = True
    if len(ids) != len(per_row):
        raise ValueError(f"row_ids {len(ids)} phần tử nhưng per_row {len(per_row)}: file hỏng hoặc đến từ hai lần chấm")
    return dict(zip(ids, (bool(x) for x in per_row))), dung_thu_lai


def _ma(ds: list[str]) -> str:
    if not ds:
        return "(không có)"
    s = ", ".join(ds[:TOI_DA_MA_IN])
    return s + (f" … (+{len(ds) - TOI_DA_MA_IN})" if len(ds) > TOI_DA_MA_IN else "")


def doc_bo_ma(duong: str) -> dict[str, str]:
    """
    Tệp danh sách câu BỎ KHỎI ĐIỂM, mỗi dòng `MÃ  # lý do`. Bắt buộc có lý do: bỏ một câu mà không ghi vì sao là chỉnh điểm
    trong im lặng. Dòng trống và dòng bắt đầu bằng `#` bỏ qua.
    """
    ra: dict[str, str] = {}
    try:
        dong = Path(duong).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        sys.exit(f"Không có tệp {duong} (--bo-ma-tep).")
    for i, d in enumerate(dong, 1):
        d = d.strip()
        if not d or d.startswith("#"):
            continue
        ma, _, ly_do = d.partition("#")
        if not ma.strip() or not ly_do.strip():
            sys.exit(f"{duong}:{i}: dòng phải có dạng `MÃ  # lý do` (thiếu lý do thì không được bỏ câu): {d!r}")
        ra[ma.strip()] = ly_do.strip()
    return ra


def bang(lan_chay: list[LanChay], tham_chieu: set[str], sau_thu_lai: bool = False,
         bo_ma: dict[str, str] | None = None) -> str:
    """
    `bo_ma`: `{mã câu: lý do}` bỏ khỏi MỌI lần chạy trước khi tính. Dùng khi một câu đề đã biết là nhãn sai (ví dụ EX0034,
    EX0110 ở #91): bỏ khi ĐỌC kết quả nên không phải đo lại model cũ và không sửa nhãn tại chỗ. Bảng in rõ đã bỏ câu nào.
    """
    bo_ma = bo_ma or {}
    nhan_co = {lc.nhan for lc in lan_chay}
    la = tham_chieu - nhan_co
    if la:
        raise ValueError(f"--tham-chieu nêu nhãn không có trong --lan: {sorted(la)}")

    out: list[str] = []
    ten_muc = sorted({m for lc in lan_chay for m in lc.sections})
    for muc in ten_muc:
        co: list[tuple[LanChay, dict[str, bool], bool]] = []
        thieu: list[str] = []
        for lc in lan_chay:
            if muc not in lc.sections:
                thieu.append(lc.nhan)
                continue
            theo_ma, thu_lai = _theo_ma(lc.sections[muc], sau_thu_lai)
            theo_ma = {k: v for k, v in theo_ma.items() if k not in bo_ma}
            co.append((lc, theo_ma, thu_lai))
        if len(co) < 2:
            out.append(f"\n[{muc}] chỉ {len(co)} lần chạy có nhánh này — không so được")
            continue

        chung = set.intersection(*(set(t) for _, t, _ in co))
        ma_chung = sorted(chung)
        out.append(f"\n{'─' * 70}\n[{muc}]  {len(ma_chung)} câu chung cho {len(co)} lần chạy")
        if thieu:
            out.append(f"  (thiếu nhánh này: {', '.join(thieu)})")
        da_bo = sorted(k for k in bo_ma if any(k in lc.sections[muc].get("row_ids", []) for lc, _, _ in co))
        if da_bo:
            out.append("  đã BỎ khỏi điểm: " + "; ".join(f"{k} ({bo_ma[k]})" for k in da_bo))
        if not ma_chung:
            out.append("  không có câu nào chung — hai bộ đề khác nhau?")
            continue
        lech = {lc.nhan: len(t) - len(chung) for lc, t, _ in co if len(t) != len(chung)}
        if lech:
            out.append(f"  ⚠ có lần chạy mang câu riêng, đã bỏ: {lech}")

        rb = {lc.rang_buoc for lc, _, _ in co}
        if len(rb) > 1:
            out.append(f"  ⚠ ràng buộc JSON KHÁC NHAU giữa các lần chạy: "
                       f"{ {lc.nhan: lc.rang_buoc for lc, _, _ in co} } — phần chênh lệch lẫn cả cơ chế, không thuần năng lực")

        for lc, t, thu_lai in co:
            k = sum(t[m] for m in ma_chung)
            kt = wilson(k, len(ma_chung))
            gc = ""
            if sau_thu_lai and muc == "n8n":
                gc = "  (sau một lần thử lại)" if thu_lai else "  (lần thử đầu: lần chạy này không có mục thu_lai)"
            vai = "  [mốc tham chiếu]" if lc.nhan in tham_chieu else ""
            out.append(f"  {lc.nhan:<12} {k:>3}/{len(ma_chung):<3} {kt}{vai}{gc}")

        kq = {lc.nhan: t for lc, t, _ in co}
        local = [lc.nhan for lc, _, _ in co if lc.nhan not in tham_chieu]
        ref = [lc.nhan for lc, _, _ in co if lc.nhan in tham_chieu]

        ai_cung_sai = [m for m in ma_chung if not any(kq[n][m] for n in kq)]
        out.append(f"\n  Mọi lần chạy đều SAI ({len(ai_cung_sai)}): {_ma(ai_cung_sai)}")
        if ai_cung_sai:
            out.append("    -> nghi đề bài hoặc bộ kiểm, chưa phải model: đọc nguyên văn từng câu (`--tho`) trước khi kết luận")

        if ref and local:
            gap = [m for m in ma_chung if any(kq[r][m] for r in ref) and not any(kq[n][m] for n in local)]
            lech2 = [m for m in ma_chung if any(kq[n][m] for n in local) and not any(kq[r][m] for r in ref)]
            out.append(f"  Mốc tham chiếu đúng, MỌI bản local sai ({len(gap)}): {_ma(gap)}")
            out.append("    -> khoảng cách thật của model so với một bản mạnh: ứng viên cho dữ liệu huấn luyện")
            out.append(f"  Có bản local đúng, MỌI mốc tham chiếu sai ({len(lech2)}): {_ma(lech2)}")
            if lech2:
                out.append("    -> ca lạ: soát ràng buộc JSON hai bên và nguyên văn đầu ra trước khi tin")

        if len(local) >= 2:
            goc = local[0]
            for khac in local[1:]:
                hong = [m for m in ma_chung if kq[goc][m] and not kq[khac][m]]
                sua = [m for m in ma_chung if not kq[goc][m] and kq[khac][m]]
                out.append(f"\n  {khac} so với {goc}:  sửa được {len(sua)}, LÀM HỎNG {len(hong)}")
                if hong:
                    out.append(f"    {khac} làm hỏng: {_ma(hong)}")
                    if ref:
                        ref_dung = [m for m in hong if any(kq[r][m] for r in ref)]
                        out.append(f"    trong đó mốc tham chiếu làm được: {len(ref_dung)}/{len(hong)} "
                                   f"({_ma(ref_dung)}) — phần còn lại nghi đề bài")
                if sua:
                    out.append(f"    {khac} sửa được: {_ma(sua)}")
    return "\n".join(out)


def _tach_lan(s: str) -> tuple[str, str]:
    if "=" not in s:
        raise argparse.ArgumentTypeError(f"--lan phải dạng nhan=duong_dan.json, nhận {s!r}")
    nhan, duong = s.split("=", 1)
    if not nhan or not duong:
        raise argparse.ArgumentTypeError(f"--lan có nhãn hoặc đường dẫn rỗng: {s!r}")
    return nhan, duong


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lan", action="append", type=_tach_lan, required=True, help="nhan=file.json (lặp lại)")
    p.add_argument("--tham-chieu", default="", help="các nhãn là mốc tham chiếu, cách nhau bằng dấu phẩy")
    p.add_argument("--sau-thu-lai", action="store_true")
    p.add_argument("--bo-ma-tep", default="",
                   help="tệp các câu bỏ khỏi điểm, mỗi dòng `MÃ  # lý do` (bắt buộc có lý do)")
    a = p.parse_args(argv)

    nhan = [n for n, _ in a.lan]
    if len(set(nhan)) != len(nhan):
        sys.exit(f"Nhãn trùng nhau: {nhan}")
    lan_chay = [doc_lan_chay(n, d) for n, d in a.lan]
    tham_chieu = {x.strip() for x in a.tham_chieu.split(",") if x.strip()}

    print("=" * 70)
    print("  NHIỀU LẦN CHẠY CẠNH NHAU")
    for lc in lan_chay:
        vai = " [mốc tham chiếu]" if lc.nhan in tham_chieu else ""
        print(f"  {lc.nhan:<12} {lc.model}   (ràng buộc: {lc.rang_buoc}){vai}")
    print("=" * 70)
    try:
        print(bang(lan_chay, tham_chieu, a.sau_thu_lai, doc_bo_ma(a.bo_ma_tep) if a.bo_ma_tep else None))
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"\n{'=' * 70}")
    print("Mốc tham chiếu là cận để biết bộ đề có làm được không, không phải đáp án và không thay cổng của benchmark_v3.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
