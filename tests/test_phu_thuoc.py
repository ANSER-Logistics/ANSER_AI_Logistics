"""
tests/test_phu_thuoc.py — hai file requirements có nói thật không.

VÌ SAO CÓ FILE NÀY
------------------
AGENTS §3.2.4: "**Ghim version** khi thêm thư viện vào `requirements.txt`." Soát
04/11/2026 thấy **29 trên 37** gói không ghim, nên quy tắc đó thực tế chưa được
thi hành ở đâu.

Nhưng ghim cả 29 trong một lượt là việc KHÔNG nên tự làm: `torch`, `vllm`,
`transformers`, `bitsandbytes`, `accelerate` ràng buộc lẫn nhau rất chặt, và máy
soát này không có GPU để thử. Một bộ ghim sai không lộ ra ở `pytest` — nó lộ ra
giữa một phiên Colab đã trả tiền. Nên file này **chốt bánh xe một chiều**: danh
sách chưa ghim được khai ra, và thêm gói mới không ghim thì test đỏ.

Tuỳ chọn đã bỏ: đòi ghim hết ngay. Nó biến một món nợ ĐANG NẰM YÊN thành một
test đỏ, và test đỏ thì người ta tắt.

CA ĐÃ BẮT ĐƯỢC
--------------
`pytest` từng được khai Ở CẢ HAI FILE với hai ràng buộc khác nhau:
`requirements.txt` ghim `==8.2.0`, `requirements-dev.txt` để trống. CI cài file
dev nên giải ra bản mới nhất — đo được **9.0.3**, cách một major.

Nghĩa là suốt thời gian đó mọi dòng "pytest xanh" đều đến từ 9.x, trong khi cái
ghim 8.2.0 mô tả một version không ai chạy. Và `deploy/Dockerfile` cài
`requirements.txt`, nên image sản xuất mang theo pytest mà `src/` không hề import.
"""

from __future__ import annotations

import pathlib
import re

import pytest

GOC = pathlib.Path(__file__).resolve().parent.parent
RUNTIME = GOC / "requirements.txt"
DEV = GOC / "requirements-dev.txt"

# Gói trong `requirements.txt` chưa ghim version, đo 04/11/2026. Đây là MÓN NỢ
# ĐƯỢC KHAI, không phải danh sách miễn trừ: mỗi lần ghim được một gói thì xoá
# khỏi đây, và test ở dưới đỏ nếu còn sót tên đã ghim.
CHUA_GHIM: frozenset[str] = frozenset({
    # Nhóm AI — cần một phiên có GPU thật để xác nhận (issue #6, phần cuối).
    "chromadb", "decord", "einops", "lm-format-enforcer", "numpy", "openai",
    "qwen_vl_utils", "scikit-learn", "sentence-transformers", "sentencepiece",
    "timm",
    # Chưa cài trên máy soát nên không có bản nào làm căn cứ.
    "nest_asyncio", "pyngrok",
    # Cố ý không ghim — lý do ngay trên dòng của nó trong requirements.txt.
    "pytz",
})

CHUA_GHIM_DEV: frozenset[str] = frozenset({
    "pytest-cov", "ruff", "mypy", "pre-commit", "jsonschema",
})


def _doc(p: pathlib.Path) -> dict[str, str]:
    """{tên gói chuẩn hoá: ràng buộc nguyên văn}."""
    ra: dict[str, str] = {}
    for dong in p.read_text(encoding="utf-8").splitlines():
        dong = dong.split("#")[0].strip()
        if not dong or dong.startswith("-"):
            continue
        ten = re.split(r"[=<>~!\[]", dong, maxsplit=1)[0].strip()
        ra[ten.lower().replace("_", "-")] = dong
    return ra


def _chua_ghim(goi: dict[str, str]) -> set[str]:
    return {t for t, rb in goi.items() if not re.search(r"[=<>~!]", rb)}


def test_hai_file_requirements_ton_tai():
    """Chốt chống xanh suông: mọi phép kiểm dưới đây lặp trên nội dung hai file.

    Sai đường dẫn làm chúng đọc dict rỗng và xanh hết. Lớp lỗi này đã xảy ra bốn
    lần trong ngày 04/11/2026 — xem 0c11d8f, 9efad94, 43bde4b, f036880.
    """
    assert len(_doc(RUNTIME)) >= 30
    assert len(_doc(DEV)) >= 5


def test_khong_them_goi_moi_ma_khong_ghim_version():
    """Bánh xe một chiều: danh sách chưa ghim chỉ được NGẮN đi.

    Gói mới phải ghim. Gói cũ thì ghim dần, mỗi lần một ít, có kiểm.
    """
    chua = _chua_ghim(_doc(RUNTIME))
    moi = chua - {t.lower().replace("_", "-") for t in CHUA_GHIM}
    assert not moi, (
        f"gói mới thêm mà không ghim version: {sorted(moi)}. "
        f"AGENTS §3.2.4 đòi ghim. Nếu cố ý để trống thì thêm vào CHUA_GHIM kèm "
        f"lý do trong commit."
    )


def test_khong_them_goi_dev_moi_ma_khong_ghim():
    """Cùng luật cho file dev."""
    chua = _chua_ghim(_doc(DEV))
    moi = chua - {t.lower().replace("_", "-") for t in CHUA_GHIM_DEV}
    assert not moi, f"gói dev mới thêm mà không ghim version: {sorted(moi)}"


def test_danh_sach_chua_ghim_khong_chua_goi_da_ghim():
    """Chiều ngược: ghim xong rồi mà quên xoá khỏi danh sách.

    Để lại thì danh sách món nợ dài hơn thực tế, và lần sau không ai tin nó nữa
    — đúng cái làm một danh sách khai báo trở thành vô dụng.
    """
    chua = _chua_ghim(_doc(RUNTIME))
    da_ghim_nhung_con_khai = {
        t for t in (x.lower().replace("_", "-") for x in CHUA_GHIM)
        if t not in chua
    }
    assert not da_ghim_nhung_con_khai, (
        f"đã ghim rồi nhưng còn trong CHUA_GHIM: {sorted(da_ghim_nhung_con_khai)}"
    )


def test_khong_goi_nao_khai_o_ca_hai_file():
    """Một gói, một chỗ khai ràng buộc.

    `pytest` từng ở cả hai file với hai ràng buộc khác nhau (`==8.2.0` ở runtime,
    để trống ở dev). Gói nào thắng thì phụ thuộc THỨ TỰ CÀI — tức phụ thuộc một
    chuyện không ai ghi ở đâu. Đo 04/11: cái thắng là 9.0.3, còn con số 8.2.0 ở
    `requirements.txt` mô tả một version không ai chạy.
    """
    trung = set(_doc(RUNTIME)) & set(_doc(DEV))
    assert not trung, (
        f"khai ở cả hai file: {sorted(trung)}. Chọn MỘT chỗ — dep của test thì "
        f"ở requirements-dev.txt, dep của runtime thì ở requirements.txt."
    )


@pytest.mark.parametrize("ten", ["pytest", "pytest-cov", "pytest-asyncio", "ruff", "mypy"])
def test_dep_cua_test_khong_nam_trong_requirements_runtime(ten):
    """Dep của test không được ở `requirements.txt`.

    `deploy/Dockerfile` cài chính file đó, nên mỗi dòng ở đây là một gói ĐI VÀO
    IMAGE SẢN XUẤT. `src/` không import pytest, ruff hay mypy ở đâu cả.
    """
    assert ten not in _doc(RUNTIME), (
        f"'{ten}' là dep của test nhưng nằm trong requirements.txt, và "
        f"deploy/Dockerfile cài file đó vào image sản xuất."
    )


def test_file_requirements_ket_thuc_bang_xuong_dong():
    """Thiếu ký tự xuống dòng cuối file thì `cat >>` dán gói mới vào gói cuối.

    `requirements.txt` thiếu nó cho tới 04/11/2026: một lệnh thêm gói bằng `>>`
    sẽ sinh ra `rank_bm25==0.2.2numpy` — pip báo lỗi, nhưng chỉ sau khi người ta
    đã mất thời gian đoán.
    """
    for p in (RUNTIME, DEV):
        noi_dung = p.read_text(encoding="utf-8")
        assert noi_dung.endswith("\n"), f"{p.name} không kết thúc bằng xuống dòng"
