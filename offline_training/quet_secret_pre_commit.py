"""
offline_training/quet_secret_pre_commit.py — chặn secret ngay lúc commit.

    python offline_training/quet_secret_pre_commit.py <file> [file ...]
    python offline_training/quet_secret_pre_commit.py --self-check

Gọi từ `.pre-commit-config.yaml`. Trả mã thoát 1 nếu thấy secret, kèm tên file
và chuỗi đã che.

VÌ SAO
------
AGENTS.md R2b: credential đã lộ là credential ĐÃ CHẾT — bot quét GitHub trong
vài giây, nên xoá khỏi git không thu hồi được nó. Chặn trước khi commit rẻ hơn
mọi thứ làm sau: xoay khoá, dọn lịch sử, báo nhà cung cấp.

Sự cố thật 27/07/2026: 3 script archive chứa nguyên chuỗi Neon Postgres, nhân
bản thành 12 file qua các bản backup, bị đẩy lên GitHub public.

DÙNG LẠI `scan_secrets`, KHÔNG VIẾT MẪU LẦN HAI
-----------------------------------------------
Mẫu nhận diện nằm ở `build_dataset_v3.SECRET_PATTERNS` và đã có test phủ
(`tests/test_training_pipeline_v3.py`). Chép mẫu sang đây là tạo nguồn thứ hai
cho cùng một khái niệm, đúng thứ R4 cấm — và nguồn thứ hai sẽ là nguồn không ai
nhớ cập nhật.
"""

from __future__ import annotations

import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from offline_training.build_dataset_v3 import scan_secrets  # noqa: E402

# Hai file test CỐ Ý chứa credential giả để kiểm chính `scan_secrets`. Quét
# chúng là báo oan mỗi lần ai đó sửa test.
#
# shortcut: danh sách viết tay. Thêm file fixture mới mà quên thêm vào đây thì
#           hook báo oan; nâng cấp thành dấu hiệu trong file (ví dụ một dòng
#           `# quet-secret: bo-qua`) khi có file thứ tư.
BO_QUA = {
    "tests/test_training_pipeline_v3.py",
    "tests/test_assistant_upgrades.py",
    # AGENTS.md VIẾT RA chính các mẫu regex trong quy tắc R2b, nên nó luôn khớp
    # với chính bộ quét. Đây là tài liệu quy tắc, không phải chỗ credential sống.
    "AGENTS.md",
}

# Không đọc nhị phân. Quét ảnh/PDF/model chỉ tốn thời gian và sinh rác.
DUOI_BO_QUA = {".png", ".jpg", ".jpeg", ".pdf", ".docx", ".xlsx", ".safetensors",
               ".bin", ".pt", ".zip", ".ico", ".woff", ".woff2"}


def quet(duong_dan: list[str]) -> list[tuple[str, list[str]]]:
    """Trả [(file, [chuỗi đã che])] cho mỗi file có secret."""
    dinh = []
    for ten in duong_dan:
        p = Path(ten)
        if p.suffix.lower() in DUOI_BO_QUA:
            continue
        if p.as_posix() in BO_QUA:
            continue
        try:
            noi_dung = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Không đọc được thì bỏ qua, KHÔNG chặn commit: hook này là lưới an
            # toàn, không phải cổng duy nhất. Chặn vì một file lạ là cách nhanh
            # nhất để người ta gỡ hook ra.
            continue
        hits = scan_secrets(noi_dung)
        if hits:
            dinh.append((ten, hits))
    return dinh


def tu_kiem() -> int:
    """Chứng minh hook THI HÀNH, không chỉ tồn tại."""
    # Ghép lúc chạy, KHÔNG để nguyên một chuỗi trong mã nguồn: để nguyên thì
    # chính file này khớp bộ quét và hook tự chặn mình. Giá trị lúc chạy vẫn
    # đầy đủ nên phép thử không yếu đi.
    gia = "postgres" + "ql://admin:Xk9mQ2pLw@ep-x.neon.tech/db"
    assert scan_secrets(gia), "scan_secrets phải bắt được chuỗi Neon dạng thật"
    assert not scan_secrets("khong co gi o day, chi la mot dong chu thuong"), \
        "scan_secrets không được báo oan trên văn bản thường"
    print("tự kiểm: đạt")
    return 0


def main(argv: list[str]) -> int:
    if "--self-check" in argv:
        return tu_kiem()
    dinh = quet([a for a in argv if not a.startswith("-")])
    if not dinh:
        return 0
    print("CHẶN COMMIT — thấy chuỗi giống secret:\n", file=sys.stderr)
    for ten, hits in dinh:
        for h in hits:
            print(f"  {ten}: {h}", file=sys.stderr)
    print(
        "\nNếu là giá trị THẬT: xoay/vô hiệu nó TRƯỚC, rồi mới dọn file.\n"
        "Nếu là fixture của test: thêm đường dẫn vào BO_QUA trong "
        "offline_training/quet_secret_pre_commit.py.\n"
        "Bỏ qua một lần (chịu trách nhiệm): git commit --no-verify",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
