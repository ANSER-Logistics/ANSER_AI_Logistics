"""
tests/test_qt4_nuot_loi.py — AGENTS §4.1 quy tắc 4: không nuốt exception.

`test_quy_tac_code.py` chỉ bắt handler mà thân là đúng một `pass` không chú thích.
Đợt soát 12/11/2026 tìm ra thêm một dạng nó không thấy: handler **`return` /
`continue`** không log, trong đó có những chỗ biến "không biết" thành một con số
trông như kết quả:

  - `metrics.summarize` bỏ qua dòng JSONL hỏng rồi tính p50/p95 như thể dữ liệu đủ;
  - `inventory._period_days` trả 0 ngày khi ngày hỏng, làm im lặng phép kiểm hàng chết;
  - hai route đọc hoá đơn trả `schema_invalid` cho khách mà server không ghi gì.

Và một điều ngược lại cần giữ: log ở chỗ đọc hoá đơn KHÔNG được chép nội dung hoá
đơn (R2 — log cũng là nơi dữ liệu khách nằm lại).
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from src.api.routes import documents as docs_mod
from src.core import metrics
from src.core.inventory import InventoryLine, audit_inventory

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"

# ---------------------------------------------------------------------------
# 1. metrics.summarize
# ---------------------------------------------------------------------------


def _ghi(path: Path, dong: list[str]) -> Path:
    path.write_text("\n".join(dong) + "\n", encoding="utf-8")
    return path


def test_dong_metrics_hong_duoc_dem_va_canh_bao(tmp_path, caplog):
    f = _ghi(tmp_path / "m.jsonl", [
        json.dumps({"latency_ms": 100, "ok": True, "route": "A"}),
        "{day khong phai json",
        json.dumps({"latency_ms": 300, "ok": True, "route": "A"}),
    ])
    with caplog.at_level(logging.WARNING, logger="projecta.metrics"):
        out = metrics.summarize(path=f)
    assert out["count"] == 2
    assert out["dong_hong"] == 1
    assert any("không đọc được" in r.getMessage() for r in caplog.records)


def test_metrics_sach_thi_dong_hong_la_0_va_khong_canh_bao(tmp_path, caplog):
    f = _ghi(tmp_path / "m.jsonl", [json.dumps({"latency_ms": 100, "ok": True, "route": "A"})])
    with caplog.at_level(logging.WARNING, logger="projecta.metrics"):
        out = metrics.summarize(path=f)
    assert out["dong_hong"] == 0 and not caplog.records


def test_toan_dong_hong_van_khong_che_giau(tmp_path):
    f = _ghi(tmp_path / "m.jsonl", ["rac", "rac nua"])
    out = metrics.summarize(path=f)
    assert out["count"] == 0 and out["dong_hong"] == 2


# ---------------------------------------------------------------------------
# 2. inventory: ngày kỳ không đọc được
# ---------------------------------------------------------------------------

_LINE = InventoryLine(code="A", name="Hang A", unit="l", opening_qty=10, opening_value=100,
                      in_qty=5, in_value=60, out_qty=0, out_value=0, closing_qty=15, closing_value=160)


@pytest.mark.parametrize("bat_dau, ket_thuc", [("hôm qua", "2026-10-31"), ("2026-10-01", "31/10/2026"), ("rac", "rac")])
def test_ngay_ky_hong_thi_noi_ro_khong_im_lang(bat_dau, ket_thuc):
    out = audit_inventory([_LINE], period_start=bat_dau, period_end=ket_thuc)
    assert out["period"]["days"] == 0
    assert any("Không đọc được ngày của kỳ" in w for w in out["warnings"]), out["warnings"]


@pytest.mark.parametrize("bat_dau, ket_thuc", [("2026-10-01", "2026-10-31"), (None, None), ("", "")])
def test_ngay_ky_dung_hoac_khong_khai_thi_khong_canh_bao_them(bat_dau, ket_thuc):
    out = audit_inventory([_LINE], period_start=bat_dau, period_end=ket_thuc)
    assert not any("Không đọc được ngày của kỳ" in w for w in out["warnings"])


def test_cung_ngay_bat_dau_ket_thuc_la_0_ngay_hop_le_khong_bi_canh_bao():
    """Kỳ một ngày có 0 ngày chênh — đó là ngày ĐÚNG đọc được, không phải ngày hỏng."""
    out = audit_inventory([_LINE], period_start="2026-10-01", period_end="2026-10-01")
    assert not any("Không đọc được ngày của kỳ" in w for w in out["warnings"])


# ---------------------------------------------------------------------------
# 3. Log lỗi lược đồ hoá đơn: có ghi, nhưng KHÔNG chép nội dung
# ---------------------------------------------------------------------------


class _Mau(BaseModel):
    so_tien: int
    ten: str


def test_log_loi_luoc_do_khong_chep_noi_dung_hoa_don(caplog):
    bi_mat = "CONG-TY-TNHH-BI-MAT-0123456789"
    with pytest.raises(ValidationError) as e:
        _Mau(so_tien=bi_mat, ten=12345)           # type: ignore[arg-type]  # cả hai trường đều sai
    # Thông báo gốc của pydantic CÓ chứa giá trị đầu vào — đó là lý do phải cẩn thận.
    assert bi_mat in str(e.value)

    with caplog.at_level(logging.WARNING, logger="projecta.api.documents"):
        docs_mod._log_loi_luoc_do("Mau", e.value)

    chu = " ".join(r.getMessage() for r in caplog.records)
    assert "ValidationError" in chu and "2 lỗi" in chu
    assert bi_mat not in chu, "log chép nội dung hoá đơn — dữ liệu khách nằm lại trong log"


def test_log_loi_luoc_do_chiu_duoc_loi_khong_phai_pydantic(caplog):
    with caplog.at_level(logging.WARNING, logger="projecta.api.documents"):
        docs_mod._log_loi_luoc_do("Mau", RuntimeError("boom"))
    assert any("RuntimeError" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# 4. Luật mở rộng: except RỘNG không log, không raise phải được khai
# ---------------------------------------------------------------------------

_LOG = {"debug", "info", "warning", "error", "exception", "critical", "log"}

# (đường dẫn, hàm bao ngoài) -> lý do im lặng ở LOG là đúng. Mỗi dòng PHẢI có lý do.
DUOC_PHEP: dict[tuple[str, str], str] = {
    ("src/api/routes/tools.py", "run_tool"):
        "trả khối lỗi có cấu trúc cho VÒNG AGENTIC (model sửa ở bước sau); log mỗi lần "
        "model điền sai tham số sẽ nổ trên luồng bình thường",
    ("src/core/serving.py", "health"):
        "trả `reason` ra /health — chính /health là nơi kết quả được nhìn thấy",
}


def _rong(nut: ast.ExceptHandler) -> bool:
    return nut.type is None or (isinstance(nut.type, ast.Name) and nut.type.id in {"Exception", "BaseException"})


def _co_log_hoac_raise(nut: ast.ExceptHandler) -> bool:
    for n in ast.walk(nut):
        if isinstance(n, ast.Raise):
            return True
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in _LOG:
            return True
        # Hàm trợ giúp ghi log đặt tên `_log_…` (ví dụ `_log_loi_luoc_do`): tách ra để
        # giữ quy tắc "không chép dữ liệu khách vào log" ở MỘT chỗ thay vì hai.
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id.startswith("_log_"):
            return True
    return False


def _ham_bao_ngoai(cay: ast.AST, muc_tieu: ast.AST) -> str:
    ten = ""
    for n in ast.walk(cay):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(c is muc_tieu for c in ast.walk(n)):
                ten = n.name            # lấy hàm LỒNG SÂU nhất chứa nó (duyệt sau ghi đè)
    return ten


def _quet() -> list[tuple[str, str, int]]:
    ra = []
    for p in sorted(SRC.rglob("*.py")):
        cay = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(cay):
            if isinstance(n, ast.ExceptHandler) and _rong(n) and not _co_log_hoac_raise(n):
                ra.append((p.relative_to(REPO).as_posix(), _ham_bao_ngoai(cay, n), n.lineno))
    return ra


def test_except_rong_khong_log_phai_nam_trong_danh_sach_khai_bao():
    la = [(f, h, ln) for f, h, ln in _quet() if (f, h) not in DUOC_PHEP]
    assert not la, (
        "`except Exception`/bare mà không log cũng không raise: "
        + ", ".join(f"{f}:{ln} ({h})" for f, h, ln in la)
        + ". Thêm `logger.warning` kèm ngữ cảnh (đừng chép dữ liệu khách), hoặc khai vào "
        "DUOC_PHEP kèm lý do."
    )


def test_danh_sach_duoc_phep_khong_chua_muc_da_het_hieu_luc():
    """Mục khai rồi mà handler đã bị sửa/xoá thì phải xoá khỏi danh sách, kẻo nó thành lỗ hổng."""
    con = {(f, h) for f, h, _ in _quet()}
    het = [k for k in DUOC_PHEP if k not in con]
    assert not het, f"mục DUOC_PHEP không còn khớp handler nào: {het}"


def test_bo_quet_that_su_nhin_thay_handler(tmp_path):
    """Chốt chống xanh suông: bộ quét phải tìm ra ca xấu trong một file thử."""
    f = tmp_path / "x.py"
    f.write_text("def h():\n    try:\n        1/0\n    except Exception:\n        return 0\n", encoding="utf-8")
    cay = ast.parse(f.read_text(encoding="utf-8"))
    xau = [n for n in ast.walk(cay) if isinstance(n, ast.ExceptHandler) and _rong(n) and not _co_log_hoac_raise(n)]
    assert len(xau) == 1 and _ham_bao_ngoai(cay, xau[0]) == "h"
    assert len(_quet()) >= 2, "không thấy handler nào ở src/ — bộ quét hỏng"
