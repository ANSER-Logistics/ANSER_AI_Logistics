"""
offline_training/soat_hinh_dang_tra_ve.py — hàm nào trả về hai hình dạng khác nhau.

    python offline_training/soat_hinh_dang_tra_ve.py

Tìm hàm có nhiều nhánh `return {…}` mà TẬP KHOÁ không giống nhau. Luôn thoát 0:
đây là công cụ SOÁT, không phải cổng chặn.

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
import pathlib
import sys

GOC = pathlib.Path(r"D:\AI_ANSER")


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


def main():
    tong = 0
    for p in sorted(GOC.rglob("*.py")):
        r = p.relative_to(GOC)
        if any(x in r.parts for x in (".git", "node_modules", "__pycache__", "tests")):
            continue
        for ten, dong, tap, lech in soat_file(p):
            print(f"\n{r}:{dong}  {ten}()")
            for ln, k in tap:
                print(f"    return dòng {ln}: {len(k)} khoá")
            for ln, thieu in lech:
                print(f"    -> dòng {ln} THIẾU: {thieu}")
            tong += 1
    print(f"\ntổng hàm có nhánh lệch hình dạng: {tong}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
