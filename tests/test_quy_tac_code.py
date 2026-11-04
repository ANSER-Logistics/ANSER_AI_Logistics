r"""
tests/test_quy_tac_code.py — các quy tắc AGENTS.md §4.1 soát được BẰNG LỆNH.

VÌ SAO CÓ FILE NÀY
------------------
§4.1 có tám quy tắc bắt buộc. Tám quy tắc đó tới nay chỉ được bảo vệ bằng việc
người soát nhớ ra chúng, và soát ngày 04/11/2026 tìm thấy đúng một chỗ vi phạm
nguyên văn quy tắc 4:

    src/core/utils.py      except Exception:
                               pass

Nằm ở lớp sửa JSON nhẹ của `_extract_json_block`. Hậu quả không phải sai kết quả
— hàm vẫn trả lỗi ngay dưới đó — mà là MỘT TRIỂN KHAI THIẾU GÓI `json_repair`
trông giống hệt một đầu ra model hỏng: cả hai đều báo `JSONDecodeError`. Tỷ lệ
phải đi đường dự phòng tăng lên và không có gì cho thấy vì sao.

AGENTS §1 nói về việc đối chiếu: "Đối chiếu bằng lệnh, đừng nhớ." File này áp
chính câu đó cho §4.1.

SOÁT ĐƯỢC GÌ, VÀ KHÔNG SOÁT ĐƯỢC GÌ
-----------------------------------
Chỉ nhận những quy tắc có định nghĩa SẮC. Một phép kiểm ồn hơn tác dụng thì tệ
hơn không có: người ta sẽ thêm `noqa` cho qua, rồi lần sau không ai tin nó nữa.

  ✓ quy tắc 3  không `print`, dùng `logger`
  ✓ quy tắc 4  không nuốt exception

  ✗ quy tắc 7  "prompt chỉ sống trong prompts.py" — đã thử và BỎ. Mẫu khả dĩ là
               tìm `{"role": "system"}` ngoài prompts.py, nhưng nó bắt
               `engine.py:394` — chỗ đó nhận `system` làm THAM SỐ, là lớp bọc
               chat chung, không phải định nghĩa prompt. Không có cách sắc nào
               phân biệt "chuỗi chỉ thị" với "chuỗi dài" nên bỏ hẳn.

  ✗ §3.2 đường dẫn — đã thử và BỎ. Mẫu `\\` bắt `\n`, `\d`, `\W` trong mọi biểu
               thức chính quy của repo: 10 kết quả, 10 dương tính giả. Mà dấu
               gạch chéo `/` trong chuỗi đường dẫn thì Python xử lý đúng trên cả
               hai hệ, nên nó KHÔNG phải lỗi cần bắt.

  ✗ quy tắc 1, 2, 5, 6, 8 — là tính chất của hành vi, không phải hình dạng mã
               nguồn. Chúng thuộc test nghiệp vụ, không thuộc đây.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

GOC = pathlib.Path(__file__).resolve().parent.parent
SRC = GOC / "src"

# `evaluate_system.py` ĐÃ CHẶN CHẠY (04/11/2026, vi phạm R2 — gửi dữ liệu thật
# tới DeepSeek để chấm điểm). Nó vẫn còn trong repo chờ chủ dự án quyết xoá hay
# giữ, nên không soi nó: sửa một file đã chết là việc vô ích, mà để nó làm test
# đỏ thì người ta sẽ tắt test.
BO_QUA = {"evaluate_system.py"}


def _file_nguon() -> list[pathlib.Path]:
    return [p for p in sorted(SRC.rglob("*.py")) if p.name not in BO_QUA]


def test_co_file_de_soi():
    """Chốt chống xanh suông cho hai phép kiểm dưới đây.

    Cả hai lặp trên danh sách file. Danh sách rỗng — đổi tên thư mục, sai đường
    dẫn gốc — làm chúng xanh mà không đọc một dòng nào. Lớp lỗi này đã xảy ra ba
    lần trong ngày 04/11/2026: xem 0c11d8f, 9efad94, 43bde4b.
    """
    ds = _file_nguon()
    assert len(ds) >= 40, f"chỉ thấy {len(ds)} file .py trong src/ — sai đường dẫn?"


def test_quy_tac_3_khong_print_trong_src():
    """`print` trong code phục vụ là một dòng không ai đọc.

    Nhật ký có cấu trúc đi kèm `request_id` nên lần ra được một lượt gọi cụ thể;
    `print` thì không, và trong container nó lẫn vào stdout chung.
    """
    xau = []
    for p in _file_nguon():
        cay = ast.parse(p.read_text(encoding="utf-8"))
        for nut in ast.walk(cay):
            if (isinstance(nut, ast.Call)
                    and isinstance(nut.func, ast.Name)
                    and nut.func.id == "print"):
                xau.append(f"{p.relative_to(GOC).as_posix()}:{nut.lineno}")
    assert not xau, f"dùng print thay vì logger: {xau}"


def test_quy_tac_4_khong_nuot_exception():
    """`except ...: pass` — thân chỉ có `pass` — bị cấm.

    Soi CẢ except hẹp, không riêng `except Exception`. Điều luật nêu
    `except Exception: pass` vì đó là dạng tệ nhất, nhưng `except OSError: pass`
    cũng giấu đi một sự thật: soát 04/11 thấy `_safe_unlink` nuốt im lặng mọi
    lỗi xoá file tạm, và ở bậc T0/T1 (GPU thuê, đĩa nhỏ) đĩa đầy làm cả service
    chết mà không dòng log nào dẫn về đó.

    Có ngoại lệ ĐÚNG — `grounding._hai_cach_doc` thử `float()` rồi bỏ qua khi
    không phải số, và log ở đó sẽ nổ liên tục trên đầu vào bình thường. Nên luật
    không phải "không bao giờ `pass`" mà là: `pass` phải có một dòng chú thích
    ngay trên nó nói vì sao im lặng là đúng. Chú thích bắt người viết dừng lại
    nghĩ, mà vẫn không chặn ca hợp lệ.
    """
    xau = []
    for p in _file_nguon():
        dong = p.read_text(encoding="utf-8").splitlines()
        cay = ast.parse("\n".join(dong))
        for nut in ast.walk(cay):
            if not isinstance(nut, ast.ExceptHandler):
                continue
            if not (len(nut.body) == 1 and isinstance(nut.body[0], ast.Pass)):
                continue
            # Có chú thích ngay trên `pass` (hoặc trên chính dòng `except`)?
            vi_tri_pass = nut.body[0].lineno - 1          # 0-based
            truoc = dong[vi_tri_pass - 1].strip() if vi_tri_pass > 0 else ""
            tren_except = dong[nut.lineno - 2].strip() if nut.lineno >= 2 else ""
            if truoc.startswith("#") or tren_except.startswith("#"):
                continue
            xau.append(f"{p.relative_to(GOC).as_posix()}:{nut.lineno}")
    assert not xau, (
        f"nuốt exception không một chữ giải thích: {xau}. "
        f"Thêm `logger.warning` kèm ngữ cảnh, hoặc một dòng `#` nói vì sao im "
        f"lặng là đúng ở chỗ đó."
    )


@pytest.mark.parametrize("ten", sorted(BO_QUA))
def test_file_bo_qua_dung_la_da_chan_chay(ten):
    """File trong `BO_QUA` phải thật sự đã chặn chạy.

    Bỏ qua một file vì nó đã chết là hợp lý; bỏ qua một file ĐANG CHẠY thì danh
    sách này thành cửa sau. Mở lại `evaluate_system.py` mà quên xoá khỏi đây là
    mở lại một file không ai soát.
    """
    p = SRC / ten
    if not p.exists():
        pytest.skip(f"{ten} đã bị xoá — xoá khỏi BO_QUA luôn")
    noi_dung = p.read_text(encoding="utf-8")
    assert "sys.exit" in noi_dung or "SystemExit" in noi_dung or "raise" in noi_dung, (
        f"{ten} nằm trong BO_QUA nhưng không thấy chốt chặn chạy nào. Nếu nó đã "
        f"hoạt động lại thì xoá khỏi BO_QUA và sửa các vi phạm trong đó."
    )
