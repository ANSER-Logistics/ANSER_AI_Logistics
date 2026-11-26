"""
offline_training/ve_duong_cong_vlm.py — Vẽ đồ thị đường cong điểm VLM theo mức độ hỏng hóc (#113).

CHẠY
    python offline_training/ve_duong_cong_vlm.py --json ket_qua_curve.json --out duong_cong_vlm.png
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from offline_training.vlm_hoadon import BIEN_THE_CHUP, MUC_HONG, phan_tich_duong_cong  # noqa: E402

_TEN_HIEN_THI = {
    "perspective": "Méo phối cảnh + xoay",
    "shadow": "Bóng đổ / sáng không đều",
    "jpeg_lowres": "Nén JPEG + giảm phân giải",
    "stamp_over_num": "Dấu mộc đỏ / chữ ký đè số",
    "paper_crumple": "Giấy ngả vàng + nếp gấp",
    "crop_edge": "Cắt lẹm mép",
}


def in_bang_duong_cong(phan_tich: dict) -> None:
    print(f"\nĐiểm mốc ảnh sạch (clean): {phan_tich['diem_clean']:.3f}")
    print(f"\n{'Loại hỏng hóc':<30}{'clean':>8}{'nhẹ':>8}{'vừa':>8}{'nặng':>8}{'tụt TB':>10}")
    print("-" * 72)
    for bien in BIEN_THE_CHUP:
        d = phan_tich["theo_loai"][bien]
        tut = phan_tich["do_tut_trung_binh"][bien]
        print(
            f"{_TEN_HIEN_THI.get(bien, bien):<30}"
            f"{d['clean']:>8.3f}{d['nhe']:>8.3f}{d['vua']:>8.3f}{d['nang']:>8.3f}{tut:>+10.3f}"
        )
    nhanh_nhat = phan_tich["loai_tut_nhanh_nhat"]
    if nhanh_nhat:
        print(f"\nLoại hỏng làm model tụt điểm nhanh nhất: {_TEN_HIEN_THI.get(nhanh_nhat, nhanh_nhat)} ({nhanh_nhat})")


def ve_bieu_do(phan_tich: dict, out_png: Path) -> None:
    import matplotlib.pyplot as plt

    truc_x = ["clean", *MUC_HONG]
    nhan_x = ["Sạch (clean)", "Nhẹ", "Vừa", "Nặng"]

    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150)
    for bien in BIEN_THE_CHUP:
        d = phan_tich["theo_loai"][bien]
        y = [d[k] for k in truc_x]
        ax.plot(nhan_x, y, marker="o", linewidth=2, label=_TEN_HIEN_THI.get(bien, bien))

    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("Mức độ hỏng hóc ảnh chụp")
    ax.set_ylabel("Tỷ lệ đọc đúng hết (tat_ca_dung)")
    ax.set_title("Đường cong điểm VLM theo loại và mức độ hỏng hóc ảnh hoá đơn (#113)")
    ax.grid(True, linestyle="--", alpha=0.45)
    ax.legend(loc="lower left", fontsize=9)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)
    print(f"Đã lưu đồ thị đường cong tại: {out_png}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", required=True, help="File JSON xuất từ do_vlm_hoa_don.py")
    ap.add_argument("--out", default="duong_cong_vlm.png", help="Đường dẫn file ảnh biểu đồ đầu ra")
    args = ap.parse_args()

    data = json.loads(Path(args.json).read_text(encoding="utf-8"))
    rows = data["rows"] if isinstance(data, dict) and "rows" in data else data
    pt = phan_tich_duong_cong(rows)
    in_bang_duong_cong(pt)
    ve_bieu_do(pt, Path(args.out))


if __name__ == "__main__":
    main()
