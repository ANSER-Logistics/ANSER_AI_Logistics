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
# Phần GPU tách khỏi RUNTIME ngày 10/11/2026 (issue #17). Nó `-r` lại RUNTIME,
# nên `_doc(GPU)` chỉ chứa phần RIÊNG của nó (dòng bắt đầu bằng "-" bị bỏ qua).
GPU = GOC / "requirements-gpu.txt"
DEV = GOC / "requirements-dev.txt"


def _runtime_va_gpu() -> dict[str, str]:
    """Hai file cùng là phụ thuộc runtime — luật ghim áp cho cả hai như một."""
    return {**_doc(RUNTIME), **_doc(GPU)}

# Gói trong `requirements.txt` + `requirements-gpu.txt` chưa ghim version, đo
# 04/11/2026. Đây là MÓN NỢ
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
    # 25 chứ không 30 nữa: tách GPU (10/11/2026) chuyển 8 gói sang file kia.
    assert len(_doc(RUNTIME)) >= 25
    assert len(_doc(GPU)) >= 5
    assert len(_doc(DEV)) >= 5


def test_khong_them_goi_moi_ma_khong_ghim_version():
    """Bánh xe một chiều: danh sách chưa ghim chỉ được NGẮN đi.

    Gói mới phải ghim. Gói cũ thì ghim dần, mỗi lần một ít, có kiểm.
    """
    chua = _chua_ghim(_runtime_va_gpu())
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
    chua = _chua_ghim(_runtime_va_gpu())
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
    for a, b in ((RUNTIME, DEV), (RUNTIME, GPU), (GPU, DEV)):
        trung = set(_doc(a)) & set(_doc(b))
        assert not trung, (
            f"khai ở cả {a.name} lẫn {b.name}: {sorted(trung)}. Chọn MỘT chỗ — dep "
            f"của test ở requirements-dev.txt, dep cần GPU ở requirements-gpu.txt, "
            f"còn lại ở requirements.txt."
        )


def test_phan_gpu_keo_lai_phan_cpu():
    """`pip install -r requirements-gpu.txt` phải là MỘT lệnh đủ cho máy GPU.

    Thiếu dòng `-r requirements.txt` thì notebook Colab cài phần GPU mà không có
    FastAPI, SQLAlchemy... — và lỗi chỉ lộ ra giữa phiên đo đã trả tiền.
    """
    dong = [d.strip() for d in GPU.read_text(encoding="utf-8").splitlines()]
    assert "-r requirements.txt" in dong


@pytest.mark.parametrize("ten", ["vllm", "bitsandbytes", "accelerate"])
def test_goi_gpu_khong_quay_lai_phan_cpu(ten):
    """`deploy/Dockerfile` cài `requirements.txt`. Một gói GPU lọt lại vào đó là
    image kéo torch CUDA về: vllm ghim cứng `torch==2.9.0`, pip gỡ torch CPU
    Dockerfile vừa cài. Đo 10/11/2026 (issue #17): 5,31 GB wheel thay vì 0,43 GB.
    """
    assert ten not in _doc(RUNTIME), (
        f"'{ten}' nằm trong requirements.txt — deploy/Dockerfile sẽ kéo CUDA về. "
        f"Chuyển nó sang requirements-gpu.txt."
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
    for p in (RUNTIME, GPU, DEV):
        noi_dung = p.read_text(encoding="utf-8")
        assert noi_dung.endswith("\n"), f"{p.name} không kết thúc bằng xuống dòng"
