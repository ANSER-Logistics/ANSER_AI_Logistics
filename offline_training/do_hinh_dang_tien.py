# -*- coding: utf-8 -*-
"""
do_hinh_dang_tien.py — brain#42: đo hai luật phân loại con số của chốt neo số liệu.

VÌ SAO CÓ FILE NÀY
------------------
`narration_numbers_ok` chặn con số không có trong dữ liệu. Nó phân loại bằng ĐỘ
DÀI: từ 4 chữ số trở lên thì kiểm. Ngưỡng đó gộp tiền với năm, số hiệu văn bản,
mã đơn — và đồng thời bỏ sót "45 triệu" vì chuẩn hoá ra hai chữ số.

`la_hinh_dang_tien` phân loại bằng HÌNH DẠNG thay vì độ dài. Nó CHƯA được bật
mặc định, vì bật lên là đổi hành vi của một lớp an toàn hướng ra khách: siết sai
thì hệ thống từ chối một câu trả lời đúng ngay trước mặt khách hàng.

Script này cho ra con số để quyết định, chạy lại được bất cứ lúc nào:

    python offline_training/do_hinh_dang_tien.py

Hai phép đo, và phép thứ hai quan trọng hơn phép thứ nhất:

  1. BẢNG CA SOẠN TAY — 14 ca, mỗi ca có đáp án mong đợi. Đo được "luật nào trả
     lời đúng nhiều hơn".

  2. VĂN BẢN THẬT — toàn bộ tài liệu tiếng Việt của dự án. KHÔNG có đáp án mong
     đợi, chỉ liệt kê con số mà mỗi luật đánh dấu. Dùng để thấy luật mới đánh
     dấu THÊM những gì — tức là chặn oan thêm những gì.

Phép đo 1 từng cho 14/14 cho một phiên bản luật mà phép đo 2 chỉ ra là sai: dấu
hiệu "có dấu chấm hoặc dấu phẩy" đánh dấu thêm 747 con số, phần lớn là số mục
(`5.1.`), số phiên bản (`2.5`), phần trăm (`15,8%`). Bảng tự soạn không bắt được
lỗi đó vì nó chỉ chứa những ca người soạn đã nghĩ ra.

GIỚI HẠN, nói thẳng: tài liệu dự án KHÔNG phải câu trả lời gửi khách. Nó nhiều
thuật ngữ kỹ thuật hơn và ít tiền hơn. Tập đúng để đo là `eval_narration.jsonl`,
và tập đó chưa sinh được (brain#45: thiếu `DEEPSEEK_API_KEY`). Dùng tài liệu dự
án vì nó là văn bản tiếng Việt thật duy nhất trong repo có đủ bốn loại số cần
phân biệt: tiền, năm, số hiệu văn bản, số đo.
"""

from __future__ import annotations

import collections
import glob
import io
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from src.core.grounding import (  # noqa: E402
    _SO_KEM_THANG,
    MIN_DIGITS,
    la_hinh_dang_tien,
    narration_numbers_ok,
)

CTX_TRONG = ""
CTX = '{"doanh_thu": 45000000, "lai_gop": 11500000}'

# (nhãn, câu trả lời, ngữ cảnh, có PHẢI cho qua không)
CA = [
    # --- phải CHO QUA. Chặn oan ở đây là hệ thống tự bịt miệng mình -------
    ("năm", "Hôm nay là ngày 4 tháng 11 năm 2026.", CTX_TRONG, True),
    ("số hiệu văn bản", "Nghị định 72/2024/NĐ-CP quy định rõ điều này.", CTX_TRONG, True),
    ("thông tư", "Theo Thông tư 18/2025/TT-BTC thì hoá đơn phải có mã.", CTX_TRONG, True),
    ("số đếm", "Có 3 chuyến trong tuần này.", CTX_TRONG, True),
    ("ngày trong tháng", "Giao hàng vào ngày 15.", CTX_TRONG, True),
    ("mã đơn", "Đơn hàng 4821 đã được giao.", CTX_TRONG, True),
    ("tiền có trong dữ liệu", "Lãi gộp là 11.500.000 đồng.", CTX, True),
    ("tiền viết ngắn, có dữ liệu", "Doanh thu 45 triệu.", CTX, True),
    # --- phải CHẶN. Cho qua ở đây là con số bịa đi ra màn hình ------------
    ("bịa tiền đầy đủ", "Lãi là 11.500.000 đồng.", CTX_TRONG, False),
    ("bịa tiền viết ngắn", "Doanh thu khoảng 45 triệu.", CTX_TRONG, False),
    ("bịa tiền kèm đơn vị", "Tổng cộng 18500000đ.", CTX_TRONG, False),
    ("bịa tiền trần 8 chữ số", "Chi phí là 50000000.", CTX_TRONG, False),
    ("model tự cộng", "8 triệu cộng 3 triệu là 11 triệu.", CTX_TRONG, False),
    ("tiền lệch dữ liệu", "Lãi gộp là 12.000.000 đồng.", CTX, False),
]


def do_bang_ca() -> None:
    print("=" * 74)
    print("PHÉP ĐO 1 — bảng ca soạn tay")
    print("=" * 74)
    for che_do, nhan in ((False, f"HIỆN TẠI (>= {MIN_DIGITS} chữ số)"),
                         (True, "ĐỀ XUẤT (hình dạng tiền)")):
        dung = 0
        dong = []
        for ten, ans, ctx, mong in CA:
            ok, bad = narration_numbers_ok(ans, ctx, chi_kiem_so_tien=che_do)
            khop = ok == mong
            dung += khop
            dong.append((ten, "cho qua" if ok else f"chặn ({bad})", "✓" if khop else "✗"))
        print(f"\n  {nhan}: {dung}/{len(CA)}")
        for ten, kq, dau in dong:
            print(f"    {dau} {ten:28s} → {kq}")


def _quet_van_ban() -> tuple[list[str], list[str], int]:
    files = sorted(glob.glob(os.path.join(REPO, "docs", "**", "*.md"), recursive=True))
    files += sorted(glob.glob(os.path.join(REPO, "*.md")))
    cu: list[str] = []
    moi: list[str] = []
    for p in files:
        t = io.open(p, encoding="utf-8", errors="replace").read()
        for m in _SO_KEM_THANG.finditer(t):
            tho, hau_to = m.group(1), m.group(2)
            sau = t[m.end():m.end() + 8]
            nhan = (m.group(0).strip() + sau[:2].rstrip()).replace("\n", " ")
            if len(tho.replace(".", "").replace(",", "")) >= MIN_DIGITS:
                cu.append(nhan)
            if la_hinh_dang_tien(tho, hau_to, sau):
                moi.append(nhan)
    return cu, moi, len(files)


def do_van_ban_that(n_mau: int = 15) -> None:
    cu, moi, n_file = _quet_van_ban()
    print()
    print("=" * 74)
    print(f"PHÉP ĐO 2 — văn bản tiếng Việt thật ({n_file} file .md)")
    print("=" * 74)
    print(f"\n  Luật hiện tại đánh dấu {len(cu)} con số")
    print(f"  Luật đề xuất đánh dấu  {len(moi)} con số")

    chi_cu = collections.Counter(cu) - collections.Counter(moi)
    chi_moi = collections.Counter(moi) - collections.Counter(cu)

    print(f"\n  CHỈ luật cũ đánh dấu — luật mới THA ({sum(chi_cu.values())} lượt).")
    print("  Đây là phần chặn oan mà luật mới gỡ được:")
    for v, c in chi_cu.most_common(n_mau):
        print(f"    {c:4d}×  {v}")

    print(f"\n  CHỈ luật mới đánh dấu — luật cũ tha ({sum(chi_moi.values())} lượt).")
    print("  Đây là phần luật mới siết thêm. ĐỌC TỪNG DÒNG: dòng nào không phải")
    print("  tiền thì đó là một ca chặn oan mới:")
    for v, c in chi_moi.most_common(n_mau):
        print(f"    {c:4d}×  {v}")


def main() -> None:
    do_bang_ca()
    do_van_ban_that()
    print()
    print("=" * 74)
    print("Luật đề xuất CHƯA bật mặc định. Bật = truyền `chi_kiem_so_tien=True`")
    print("vào `narration_numbers_ok`, và sửa `guard_answer` để nó truyền xuống.")
    print("Đó là đổi hành vi hướng ra khách — cần chủ dự án duyệt (brain#42).")
    print("=" * 74)


if __name__ == "__main__":
    main()
