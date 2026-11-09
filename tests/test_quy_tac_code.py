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
# RỖNG từ 07/11/2026: `evaluate_system.py` đã XOÁ hẳn (chủ dự án duyệt), nên
# không còn gì để bỏ qua. Giữ cơ chế lại vì nó vẫn có giá trị cho lần sau —
# nhưng tập rỗng làm hai phép kiểm lặp trên nó không chạy lần nào, nên
# `test_co_file_de_soi` mới là chốt chống xanh suông ở đây.
BO_QUA: set[str] = set()


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


def test_file_bo_qua_dung_la_da_chan_chay():
    """File trong `BO_QUA` phải thật sự đã chặn chạy.

    Bỏ qua một file vì nó đã chết là hợp lý; bỏ qua một file ĐANG CHẠY thì danh
    sách này thành cửa sau.

    KHÔNG dùng `parametrize` ở đây dù nó gọn hơn. `BO_QUA` hiện RỖNG, và
    `parametrize` trên tập rỗng sinh ra một ca SKIP vĩnh viễn:

        SKIPPED [1] tests/test_quy_tac_code.py: got empty parameter set

    Một test không bao giờ chạy được là rác trong danh sách skip — và danh sách
    skip bẩn thì người ta thôi đọc nó. Không phải lo xa: soát 09/11/2026 tìm thấy
    HAI test khác (`test_agentic_plan.py`, thiếu `xgrammar`) đã skip im lặng
    nhiều tháng, và chúng sống sót được chính vì danh sách skip không ai soi nữa.

    Vòng lặp bên trong làm đúng việc đó mà không bao giờ skip: tập rỗng thì thân
    vòng không chạy, test vẫn XANH và vẫn đếm là một ca đã chạy.
    """
    xau = []
    for ten in sorted(BO_QUA):
        p = SRC / ten
        if not p.exists():
            xau.append(f"{ten}: không còn trong src/ — xoá khỏi BO_QUA luôn")
            continue
        noi_dung = p.read_text(encoding="utf-8")
        if not any(x in noi_dung for x in ("sys.exit", "SystemExit", "raise")):
            xau.append(f"{ten}: trong BO_QUA nhưng không thấy chốt chặn chạy nào")
    assert not xau, (
        f"danh sách BO_QUA đã sai lệch: {xau}. File hoạt động lại thì xoá khỏi "
        f"BO_QUA và sửa các vi phạm trong đó."
    )

# ---------------------------------------------------------------------------
# Hằng số `Prompts` — có ai dùng không
# ---------------------------------------------------------------------------
# AGENTS §4.1 quy tắc 7: "Prompt chỉ sống trong prompts.py." Phép kiểm cho CHIỀU
# ĐÓ đã thử và bỏ (xem docstring đầu file). Nhưng chiều NGƯỢC lại thì soát được,
# và nó vừa bắt một thứ đáng giá hơn.
#
# Soát 04/11/2026: `Prompts.INVOICE_SYSTEM` không được tham chiếu Ở ĐÂU CẢ. 11
# trong 12 hằng số có người dùng; đây là cái duy nhất bằng 0.
#
# Điều đáng kể không phải một hằng số chết — mà là HAI tài liệu khẳng định ngược
# lại. Chú thích trong `prompts.py` viết "prompt này ĐANG CHẠY, nên model đang
# thực sự đọc nó", và `AGENTS.md` §R4 viết "Prompt đó đang chạy". Cả hai dùng
# chính khẳng định đó để biện minh cho việc KHÔNG sửa một khối lược đồ đã lệch
# khỏi Body: "đổi một prompt đang chạy thì rủi ro".
#
# Tiền đề sai thì kết luận sai theo: xoá khối đó không có rủi ro chạy nào. Và
# nguy hiểm thật thì NGƯỢC với điều đã ghi — người làm S5 đọc "đang chạy" sẽ coi
# đây là ca di trú cần cẩn trọng, trong khi họ xoá được ngay.
#
# `ARCHITECTURE.md` nói đúng từ đầu ("code chết"). Ba tài liệu, hai nói sai, và
# không ai đối chiếu — đúng loại lỗi một lệnh bắt được trong một giây.


# Hằng số `Prompts` cố ý KHÔNG có người dùng, kèm lý do VÀ kèm điều phải đúng để
# giữ nó. Danh sách này không phải chỗ miễn trừ: nó là nơi khai rằng một prompt
# đang nằm chờ, chứ không phải đang chạy.
PROMPT_CHUA_DUNG: dict[str, str] = {
    "INVOICE_SYSTEM": (
        "Chờ S5 (XAI hoá đơn: reconciliation.py + InvoiceFieldValidator + gộp "
        "prompt hoá đơn, AGENTS §8). Khối [LƯỢC ĐỒ] trong nó ĐÃ LỆCH khỏi Body "
        "(products.stock_quantity, import_transactions, import_details đều sai) "
        "nhưng vì prompt không chạy nên lệch đó không đến được người dùng."
    ),
}


def _hang_so_prompts() -> list[str]:
    nguon = (SRC / "core" / "prompts.py").read_text(encoding="utf-8")
    cay = ast.parse(nguon)
    ra = []
    for nut in ast.walk(cay):
        if isinstance(nut, ast.ClassDef) and nut.name == "Prompts":
            for than in nut.body:
                if isinstance(than, ast.Assign):
                    for dich in than.targets:
                        # Bỏ tên bắt đầu bằng `_`: đó là hằng phụ dùng NỘI BỘ
                        # trong prompts.py, không phải prompt. `_VN_WEEKDAYS`
                        # (bảng tên thứ) lọt qua lần đầu vì
                        # `"_VN_WEEKDAYS".isupper()` là True — dấu gạch dưới
                        # không có hoa/thường.
                        if (isinstance(dich, ast.Name)
                                and dich.id.isupper()
                                and not dich.id.startswith("_")):
                            ra.append(dich.id)
    return ra


def _co_ai_dung(ten: str) -> list[str]:
    import re

    thu_muc = [SRC, GOC / "tests", GOC / "offline_training"]
    ra = []
    for d in thu_muc:
        for p in d.rglob("*.py"):
            if p.name == "prompts.py" or p.name == pathlib.Path(__file__).name:
                continue
            if re.search(rf"\b{ten}\b", p.read_text(encoding="utf-8")):
                ra.append(p.name)
    return ra


def test_tim_duoc_hang_so_prompts():
    """Chốt chống xanh suông: hai phép kiểm dưới lặp trên danh sách hằng số.

    Đổi `Prompts` thành dataclass, hay chỉ đổi tên class, làm `_hang_so_prompts`
    trả về [] và cả hai xanh mà không đọc gì.
    """
    hs = _hang_so_prompts()
    assert len(hs) >= 10, f"chỉ thấy {len(hs)} hằng số trong Prompts — đổi cấu trúc?"
    assert "CODER_SYSTEM" in hs


def test_moi_prompt_hoac_co_nguoi_dung_hoac_duoc_khai_la_chua_dung():
    """Prompt không ai dùng phải được KHAI, không được nằm im như thể đang chạy.

    Một prompt chết nằm im thì vô hại. Một prompt chết mà tài liệu nói là đang
    chạy thì có hại: nó làm mọi phán đoán rủi ro về nó sai theo.
    """
    treo = [h for h in _hang_so_prompts()
            if h not in PROMPT_CHUA_DUNG and not _co_ai_dung(h)]
    assert not treo, (
        f"hằng số Prompts không nơi nào dùng: {treo}. Xoá nó, hoặc thêm vào "
        f"PROMPT_CHUA_DUNG kèm lý do và kèm điều phải đúng để giữ nó."
    )


@pytest.mark.parametrize("ten", sorted(PROMPT_CHUA_DUNG))
def test_prompt_khai_chua_dung_dung_la_chua_dung(ten):
    """Chiều ngược: nối vào luồng chạy rồi mà quên xoá khỏi danh sách.

    Khi đó danh sách nói một prompt đang nằm chờ trong khi nó đã chạy — đúng lớp
    lỗi mà file này vừa được viết ra để chặn, chỉ đổi chiều.
    """
    dung = _co_ai_dung(ten)
    assert not dung, (
        f"'{ten}' nay ĐÃ có người dùng ({dung}) — xoá khỏi PROMPT_CHUA_DUNG, và "
        f"soát lại khối [LƯỢC ĐỒ] trong nó vì giờ nó đến được người dùng."
    )
    assert PROMPT_CHUA_DUNG[ten].strip(), f"'{ten}' phải kèm lý do"
