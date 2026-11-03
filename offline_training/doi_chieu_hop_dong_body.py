"""
offline_training/doi_chieu_hop_dong_body.py — Body gửi gì, Brain nhận gì.

    python offline_training/doi_chieu_hop_dong_body.py
    python offline_training/doi_chieu_hop_dong_body.py --file duong/dan/brain.ts

Trả mã thoát 1 nếu Body gửi trường mà schema của Brain không có.

VÌ SAO CÓ FILE NÀY
------------------
AGENTS.md §1 gọi các schema trong `tools.py` là **bản sao mô tả** của thứ thuộc
về Body: "Chúng lệch được, và đã từng lệch. Trước khi tin vào chúng, đối chiếu
lại với Body."

Từ 04/11/2026 `_ToolIn` đặt `extra="forbid"` — trường lạ không còn bị bỏ lặng
lẽ nữa mà trả 422. Đó là thứ cần thiết (BR-01: một phụ phí bị bỏ im lặng làm
sai báo giá gửi khách), nhưng nó biến mọi chỗ lệch thành một lời gọi hỏng.

Lệch ĐÃ CÓ THẬT ngay lúc soát: `brain.ts::auditPartners` khai
`customers: Array<Partial<BrainPartner> & { code: string }>`, mà `BrainPartner`
có `role: string` — còn `PartnerIn` bên Brain thì không. Trước khi siết, `role`
bị bỏ im lặng nên không ai thấy. Sau khi siết, nó thành 422.

Nên việc đối chiếu không được là chuyện nhớ thì làm. Nó phải là một lệnh.

CHỈ ĐỌC, KHÔNG SỬA BODY
-----------------------
Script này chỉ TẢI VỀ và ĐỌC. AGENTS.md §1: Body không được sửa, chỉ được đề
xuất thay đổi bằng văn bản.

R2: `brain.ts` là mã nguồn công khai của chính dự án, không phải dữ liệu khách
hàng. Không gửi gì ra ngoài — chỉ `GET` một file từ GitHub.

GIỚI HẠN ĐÃ BIẾT
----------------
Đây là so sánh VĂN BẢN, không phải phân tích cú pháp TypeScript. Nó đọc được
`type X = { ... }` dạng nhiều dòng lẫn một dòng, nhưng không theo được
`interface`, `extends`, hay type hợp nhất phức tạp. Cặp nào không đọc được thì
nó NÓI RA là bỏ qua, chứ không im lặng báo "ok" — báo ok nhầm còn tệ hơn không
kiểm.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import urllib.request

# Nguồn sự thật: `brain.ts` của Body. Đường dẫn đổi hai lần trong một tuần
# (Dgsonn/ANSER-v2 -> Dgsonn/ANSER-logistics -> ANSER-Logistics/ANSER-logistics-body),
# nên để ở một hằng số, và khi 404 thì nói thẳng là có thể repo lại đổi chỗ.
URL_BRAIN_TS = (
    "https://raw.githubusercontent.com/ANSER-Logistics/ANSER-logistics-body/"
    "master/frontend/src/server/brain.ts"
)

DUONG_TOOLS = pathlib.Path(__file__).resolve().parent.parent / "src" / "api" / "routes" / "tools.py"

# (nguồn bên Body, class bên Brain). Chỉ liệt kê thứ Body THỰC SỰ GỬI ĐI —
# kiểu trả về không cần đối chiếu chiều này.
#
# Nguồn bên Body có hai dạng, và dạng thứ hai mới là chỗ rủi ro ẩn:
#
#   "type:BrainSaleLine"        — `type X = { … }`, có tên, dễ soi
#   "ham:auditInventory"        — khai INLINE trong chữ ký hàm, KHÔNG có tên
#   "body:comparePeriods"       — object literal dựng ngay tại lời gọi
#
# Bản đầu của file này chỉ đọc dạng có tên, nên ba payload inline đi lọt — đúng
# những payload không ai review vì chúng không xuất hiện ở đâu dưới dạng một
# khai báo kiểu.
CAP_DOI_CHIEU = [
    ("type:BrainSaleLine", "SaleLineIn"),
    ("type:BrainExpenseLine", "ExpenseLineIn"),
    ("type:BrainReportRequest", "ReportRequestIn"),
    ("type:BrainInventoryLine", "InventoryLineIn"),
    ("type:BrainPartner", "PartnerIn"),
    ("type:BrainPeriodSide", "PeriodSideIn"),
    ("type:BrainProduct", "ProductIn"),
    ("ham:auditInventory", "InventoryAuditRequest"),
    ("ham:auditPartners", "PartnerAuditRequest"),
    ("body:comparePeriods", "PeriodDiffRequest"),
]


def truong_cua_type_ts(nguon: str, ten: str) -> set[str] | None:
    """Tên các trường của `type <ten> = { … }`. None khi không đọc được."""
    # Bắt tới dấu `}` ĐẦU TIÊN ở đầu dòng, hoặc `}` cùng dòng với kiểu một dòng.
    # Bản đầu của hàm này dùng `.*?\n\};` nên với type viết một dòng nó nuốt
    # sang type kế tiếp và báo oan 5 trường. Báo oan làm người ta bỏ qua công
    # cụ, nên thà bỏ sót còn hơn.
    m = re.search(rf"type\s+{re.escape(ten)}\s*=\s*\{{(.*?)\}}\s*;", nguon, re.S)
    if not m:
        return None
    than = m.group(1)
    if "{" in than:          # type lồng nhau — ngoài tầm của so khớp văn bản
        return None
    return set(re.findall(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\??\s*:", than))


def truong_cua_ham_inline(nguon: str, ten_ham: str) -> set[str] | None:
    """Trường của payload khai inline: `export async function X(req: { … })`."""
    m = re.search(
        rf"export\s+async\s+function\s+{re.escape(ten_ham)}\s*\(\s*\w+\s*:\s*\{{(.*?)\}}\s*\)",
        nguon,
        re.S,
    )
    if not m:
        return None
    than = m.group(1)
    # Chỉ lấy trường ở TẦNG NGOÀI. `Array<Partial<X> & { code: string }>` có một
    # `{` lồng bên trong — bỏ nó đi trước khi tách tên, nếu không `code` bị tính
    # là trường của payload và sinh báo oan.
    than = re.sub(r"\{[^{}]*\}", "", than)
    return set(re.findall(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\??\s*:", than, re.M))


def truong_cua_body_literal(nguon: str, ten_ham: str) -> set[str] | None:
    """
    Trường của `body: { … }` dựng ngay tại lời gọi, trong thân `ten_ham`.

    Bắt cả dạng viết tắt `{ truoc, sau }` lẫn dạng đủ `{ a: x, b: y }`.
    """
    m = re.search(
        rf"export\s+async\s+function\s+{re.escape(ten_ham)}\s*\(.*?\{{(.*?)\n\}}",
        nguon,
        re.S,
    )
    if not m:
        return None
    mb = re.search(r"body\s*:\s*\{(.*?)\}", m.group(1), re.S)
    if not mb:
        return None
    ra: set[str] = set()
    for phan in mb.group(1).split(","):
        phan = phan.strip()
        if not phan:
            continue
        ten = phan.split(":")[0].strip()
        if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", ten):
            ra.add(ten)
    return ra or None


def truong_ben_body(nguon: str, dac_ta: str) -> set[str] | None:
    """Phân phối theo tiền tố `type:` / `ham:` / `body:`."""
    loai, _, ten = dac_ta.partition(":")
    if loai == "type":
        return truong_cua_type_ts(nguon, ten)
    if loai == "ham":
        return truong_cua_ham_inline(nguon, ten)
    if loai == "body":
        return truong_cua_body_literal(nguon, ten)
    return None


def truong_cua_class_py(nguon: str, ten: str) -> set[str] | None:
    """Tên các trường của `class <ten>(...)`. None khi không tìm thấy."""
    m = re.search(rf"^class {re.escape(ten)}\([^)]*\):(.*?)(?=^class |\Z)",
                  nguon, re.S | re.M)
    if not m:
        return None
    return set(re.findall(r"^\s{4}([a-z_][a-z0-9_]*)\s*:", m.group(1), re.M))


def tai_brain_ts(duong_dan: str | None) -> str:
    if duong_dan:
        return pathlib.Path(duong_dan).read_text(encoding="utf-8")
    with urllib.request.urlopen(URL_BRAIN_TS, timeout=30) as r:  # noqa: S310
        return r.read().decode("utf-8")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", help="Đọc brain.ts từ đĩa thay vì tải về")
    args = ap.parse_args(argv)

    try:
        body = tai_brain_ts(args.file)
    except Exception as exc:
        print(
            f"Không đọc được brain.ts: {exc}\n"
            f"URL đang dùng: {URL_BRAIN_TS}\n"
            "Repo Body đã đổi chỗ hai lần trong một tuần — kiểm lại đường dẫn "
            "trước khi kết luận là mạng hỏng.",
            file=sys.stderr,
        )
        return 2

    brain = DUONG_TOOLS.read_text(encoding="utf-8")

    so_lech = 0
    so_bo_qua = 0
    for ts, py in CAP_DOI_CHIEU:
        a = truong_ben_body(body, ts)
        b = truong_cua_class_py(brain, py)
        if a is None:
            print(f"  BỎ QUA  {ts:28s} — không đọc được ở brain.ts")
            so_bo_qua += 1
            continue
        if b is None:
            print(f"  BỎ QUA  {py:24s} — không tìm thấy trong tools.py")
            so_bo_qua += 1
            continue
        thua = a - b
        if thua:
            print(f"  LỆCH    {ts} → {py}")
            print(f"          Body gửi, Brain KHÔNG nhận: {sorted(thua)}")
            print("          Với extra=\"forbid\" thì lời gọi này trả 422.")
            so_lech += 1
        else:
            print(f"  ok      {ts:28s} → {py}")

    print()
    if so_bo_qua:
        print(f"{so_bo_qua} cặp không đối chiếu được — kiểm tay, đừng coi là đạt.")
    if so_lech:
        print(f"{so_lech} chỗ lệch. Thêm trường vào schema bên Brain, HOẶC đề xuất "
              "Body bỏ trường (văn bản — không sửa repo Body).")
        return 1
    print("Không chỗ nào lệch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
