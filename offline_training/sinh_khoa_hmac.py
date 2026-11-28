"""
offline_training/sinh_khoa_hmac.py — sinh khoá HMAC cho Body và n8n (R2b). CHỈ CHỦ DỰ ÁN CHẠY; agent không chạy và không bao giờ thấy đầu ra.

    python offline_training/sinh_khoa_hmac.py                 # in ra màn hình hai dòng KEY=giá trị cho .env của Brain
    python offline_training/sinh_khoa_hmac.py --tep khoa.txt  # ghi vào tệp MỚI (từ chối ghi đè), rồi tự xoá sau khi chép

Mỗi khoá là 64 ký tự hex ngẫu nhiên từ `secrets` (256 bit), vượt mức tối thiểu 32 ký tự của `hmac_auth`. Hai khoá KHÁC nhau: thu hồi Body không làm hỏng n8n.

QUY TRÌNH (R2b: khoá không vào mã, issue, PR, nhật ký trò chuyện, `.env.example`):
  1. Chạy ở máy của bạn, chép dòng `API_HMAC_KEY_BODY=...` và `API_HMAC_KEY_N8N=...` vào `.env` của máy chạy Brain (tệp này đã nằm ngoài git).
  2. Gửi khoá Body cho người triển khai Body và khoá n8n cho người cấu hình n8n qua kênh riêng (không Discord công khai, không email có lưu trữ chung).
  3. Đặt `API_HMAC_MODE=log` trước; xem `/health` khối `hmac.counts`; sạch thì mới `enforce`.
  4. Xoay khoá: sinh bản mới, đặt thêm `API_HMAC_KEY_BODY_2`, đổi Body sang `body-2`, rồi xoá khoá cũ (xem docstring `hmac_auth`).
In ra màn hình là khoá hiện trong lịch sử terminal: xoá lịch sử hay đóng cửa sổ sau khi chép.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from src.api.hmac_auth import KHOA_TOI_THIEU, TIEN_TO_KHOA  # noqa: E402

BEN_GOI = ("body", "n8n")
SO_BYTE = 32


def sinh_khoa() -> dict[str, str]:
    """`{tên biến: khoá hex}` cho từng bên gọi. Không bao giờ ghi log."""
    ra = {f"{TIEN_TO_KHOA}{ben.upper()}": secrets.token_hex(SO_BYTE) for ben in BEN_GOI}
    assert len(set(ra.values())) == len(ra) and all(len(v) >= KHOA_TOI_THIEU for v in ra.values())
    return ra


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sinh khoá HMAC (chỉ chủ dự án chạy).")
    ap.add_argument("--tep", help="ghi vào tệp mới này thay vì in ra màn hình (từ chối ghi đè)")
    a = ap.parse_args(argv)
    dong = "\n".join(f"{k}={v}" for k, v in sinh_khoa().items()) + "\n"
    if a.tep:
        try:
            with open(a.tep, "x", encoding="utf-8") as f:     # "x": tệp đã có thì lỗi, không ghi đè khoá cũ
                f.write(dong)
        except FileExistsError:
            print(f"TỪ CHỐI: {a.tep} đã tồn tại (sẽ không ghi đè).", file=sys.stderr)
            return 2
        print(f"Đã ghi hai khoá vào {a.tep}. Chép vào .env rồi XOÁ tệp này.", file=sys.stderr)
        return 0
    sys.stdout.write(dong)
    print("Hai dòng trên vào .env của máy chạy Brain; gửi từng khoá cho đúng bên qua kênh riêng.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
