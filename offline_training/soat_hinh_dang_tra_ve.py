"""
offline_training/soat_hinh_dang_tra_ve.py — hàm nào trả về hai hình dạng khác nhau.

    python offline_training/soat_hinh_dang_tra_ve.py

Tìm hàm có nhiều nhánh `return {…}` mà TẬP KHOÁ không giống nhau. Thoát 0 dù có
kết quả: đây là công cụ SOÁT, không phải cổng chặn. Chỉ thoát 2 khi quét được 0
file (chưa soát gì).

VÌ SAO
------
Người đọc phía bên kia — Body, hay một hàm khác trong Brain — thường khai một
hình dạng duy nhất. Nhánh nào trả thiếu khoá thì bên đó nhận `undefined` lúc
chạy, không lỗi ở đâu cả.

Lỗi thật đã sửa 04/11/2026: `/tools/report` nhánh không-có-dữ-liệu chỉ trả
`{"note": …}`, thiếu bốn trường mà `BrainReport` bên Body khai là bắt buộc.
`BrainProfitPanel.tsx` làm `explain?.cogs_coverage_pct ?? 0` nên màn hình hiện
**0% phủ giá vốn** cho tình huống "không đo được".

NÓ TÌM HÌNH DẠNG, KHÔNG TÌM LỖI
--------------------------------
Lệch hình dạng nhiều khi là ĐÚNG. `mcp_server.validate_invoice_total` cố ý bỏ
hẳn `calculated_total` ở nhánh không tính được — "không tính được thì không có
con số nào để ai đó lỡ tay đem đi dùng". Trả `None` ở đó là mời một `?? 0` rồi
đẻ ra "hoá đơn lệch X đồng", đúng thảm hoạ BR-01.

Mỗi kết quả phải tự trả lời: **người đọc có ĐÒI khoá này không?**

  - Có (hợp đồng khai bắt buộc) -> trả khoá, giá trị tự nói mình là "chưa biết"
  - Không, khoá chỉ chứa một phép tính ĐÃ KHÔNG CHẠY -> đừng tạo ra nó

Bảng đầy đủ ở AGENTS.md §R1.
"""
import ast
import os
import pathlib
import sys

# Gốc repo suy từ vị trí file này, KHÔNG viết cứng. Bản trước ghi cứng một ổ đĩa
# của một máy dev: chạy ở máy nào khác thì quét ra 0 file, in "tổng hàm có nhánh
# lệch hình dạng: 0", và AGENTS §R1 chỉ người đọc chạy đúng lệnh này để soát —
# tức là kết quả sạch nhất là kết quả của một phép soát chưa hề chạy.
GOC = pathlib.Path(__file__).resolve().parent.parent


def khoa_cua_dict(node):
    """Tập khoá chuỗi của một ast.Dict, hoặc None nếu không đọc được."""
    if not isinstance(node, ast.Dict):
        return None
    ra = set()
    for k in node.keys:
        if k is None:          # {**other} — không biết có gì
            return None
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            ra.add(k.value)
        else:
            return None
    return ra


def soat_file(p):
    try:
        cay = ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    ra = []
    for ham in ast.walk(cay):
        if not isinstance(ham, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        tap = []
        for n in ast.walk(ham):
            if isinstance(n, ast.Return) and n.value is not None:
                k = khoa_cua_dict(n.value)
                if k:
                    tap.append((n.lineno, k))
        if len(tap) < 2:
            continue
        hop = set().union(*(k for _, k in tap))
        lech = [(ln, sorted(hop - k)) for ln, k in tap if hop - k]
        if lech:
            ra.append((ham.name, ham.lineno, tap, lech))
    return ra


# Thư mục không phải mã của dự án. `tests` bỏ vì test cố ý viết hàm trả nhiều hình dạng để thử công cụ này.
BO_QUA = (".git", "node_modules", "__pycache__", "tests", ".venv", "venv")


def la_moi_truong_ao(thu_muc: pathlib.Path) -> bool:
    """
    Môi trường ảo Python, BẤT KỂ tên. `pyvenv.cfg` do `python -m venv` và `virtualenv` ghi ở gốc; `conda-meta` là
    của conda. Bản trước chỉ biết tên `.git`, `node_modules`...: máy dev đặt `.venv` trong repo thì công cụ đọc
    hàng nghìn file thư viện và chết với `UnicodeDecodeError` ở file đầu tiên không phải UTF-8 (#143). Kể cả khi
    không chết thì kết quả lẫn hàm của thư viện, và con số "đã quét" thành vô nghĩa.
    """
    return (thu_muc / "pyvenv.cfg").is_file() or (thu_muc / "conda-meta").is_dir()


def cac_file_py() -> list[pathlib.Path]:
    """Mọi `*.py` của dự án dưới `GOC`, đã bỏ `BO_QUA` và môi trường ảo. Cắt nhánh ngay lúc duyệt, không đi vào."""
    ra: list[pathlib.Path] = []
    for thu_muc, con, tep in os.walk(GOC):
        goc_hien_tai = pathlib.Path(thu_muc)
        con[:] = [c for c in con if c not in BO_QUA and not la_moi_truong_ao(goc_hien_tai / c)]
        ra.extend(goc_hien_tai / t for t in tep if t.endswith(".py"))
    return sorted(ra)


def main():
    tong = 0
    da_quet = 0
    for p in cac_file_py():
        r = p.relative_to(GOC)
        da_quet += 1
        for ten, dong, tap, lech in soat_file(p):
            print(f"\n{r}:{dong}  {ten}()")
            for ln, k in tap:
                print(f"    return dòng {ln}: {len(k)} khoá")
            for ln, thieu in lech:
                print(f"    -> dòng {ln} THIẾU: {thieu}")
            tong += 1
    if da_quet == 0:
        # Quét 0 file không phải "không có gì lệch" mà là "chưa soát gì". Mã thoát
        # khác 0 để ai chạy trong script/CI cũng không đọc nhầm thành kết quả sạch.
        print(f"KHÔNG quét được file .py nào dưới {GOC} — chưa soát gì cả.", file=sys.stderr)
        return 2
    print(f"\ntổng hàm có nhánh lệch hình dạng: {tong}  (đã quét {da_quet} file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
