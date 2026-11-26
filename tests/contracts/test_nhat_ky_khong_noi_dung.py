"""
tests/contracts/test_nhat_ky_khong_noi_dung.py — chuỗi canary đi qua MỌI route, kể cả đường lỗi, không được xuất hiện trong nhật ký (R2, A23/#205).

Cách làm: một chuỗi chữ-số ngẫu nhiên (canary) được nhét vào thân JSON (ở giá trị, tên trường và chuỗi truy vấn), vào tên và nội dung tệp tải lên, rồi gửi tới
từng route lấy từ OpenAPI (route mới tự vào diện kiểm). Mọi bản ghi nhật ký của mọi logger ở mức DEBUG, cùng stdout/stderr, phải không chứa canary
(nguyên văn, hoa, hay mã hoá phần trăm).

Chốt chống xanh suông: (1) đối chứng dương, một logger cố ý ghi canary thì bộ dò PHẢI thấy; (2) bộ ghi không rỗng, tức đã thật sự bắt được log;
(3) danh sách route không rỗng.
"""

from __future__ import annotations

import logging
import re
import secrets
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from tests.support.bang_route import bang_route

CANARY = "cnr" + secrets.token_hex(8)       # chỉ chữ và số: không bị bộ lọc ký tự đặc biệt che
client = TestClient(app, raise_server_exceptions=False)
AI = {"X-User-Id": "1", "X-Store-Id": "1"}


def _dang_canary() -> list[str]:
    return [CANARY, CANARY.upper(), urllib.parse.quote(CANARY)]


def _thay(text: str) -> list[str]:
    return [d for d in _dang_canary() if d in text]


def _duong(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


def _gui(method: str, path: str, kieu: str):
    p = _duong(path)
    if kieu == "json":
        than = {"message": CANARY, "text": CANARY, "query": CANARY, "name": CANARY, CANARY: CANARY, "items": [{"name": CANARY, "price": CANARY}],
                "user_id": 1, "store_id": 1, "carrier_cost": CANARY}
        return client.request(method, f"{p}?q={CANARY}", json=than, headers=AI)
    tep = {"file": (f"{CANARY}.xlsx", CANARY.encode() * 50, "application/octet-stream")}
    return client.request(method, f"{p}?q={CANARY}", files=tep, data={"workspace": CANARY, "note": CANARY}, headers=AI)


ROUTE = [r for r in bang_route(app) if r[0] in ("POST", "PUT", "PATCH", "DELETE", "GET")]


def test_chot_chong_xanh_suong(caplog):
    assert len(ROUTE) >= 20
    caplog.set_level(logging.DEBUG)
    logging.getLogger("anser.canary_doi_chung").warning("co y ghi %s", CANARY)
    assert _thay("\n".join(r.getMessage() for r in caplog.records)), "bộ dò không thấy canary cố ý ghi ra: phép kiểm vô nghĩa"
    assert caplog.records


@pytest.mark.parametrize("kieu", ["json", "multipart"])
@pytest.mark.parametrize("method,path", ROUTE, ids=[f"{m} {p}" for m, p in ROUTE])
def test_canary_khong_vao_nhat_ky(method, path, kieu, caplog, capfd):
    caplog.set_level(logging.DEBUG)
    _gui(method, path, kieu)
    # `httpx`/`httpcore` là nhật ký của CHÍNH TestClient (nó ghi URL kèm chuỗi truy vấn), không phải của server.
    log = "\n".join(f"{r.getMessage()}\n{r.exc_text or ''}" for r in caplog.records if not r.name.startswith(("httpx", "httpcore")))
    out, err = capfd.readouterr()
    thay = _thay(log) or _thay(out) or _thay(err)
    assert not thay, f"{method} {path} ({kieu}): canary lọt vào nhật ký/đầu ra chuẩn:\n{log[:1500]}"


# ---------------------------------------------------------------------------
# Đường lỗi SÂU trong handler: thông báo lỗi có canary không được vào log (SQL kèm tham số, `input`, URL...)
# ---------------------------------------------------------------------------

def _log_sach(caplog) -> str:
    return "\n".join(f"{r.getMessage()}\n{r.exc_text or ''}" for r in caplog.records if not r.name.startswith(("httpx", "httpcore")))


def test_tool_nem_loi_chua_canary_khong_vao_log(caplog, monkeypatch):
    import src.api.routes.tools as tools_mod

    async def hong(req, token):
        raise RuntimeError(f"loi co noi dung {CANARY}")
    ten = next(iter(tools_mod._TOOL_IMPL))
    monkeypatch.setitem(tools_mod._TOOL_IMPL, ten, (lambda **kw: object(), hong))   # bỏ qua bước kiểm tham số: cần chạm tới handler
    caplog.set_level(logging.DEBUG)
    import asyncio
    asyncio.run(tools_mod.run_tool(ten, {}))
    assert not _thay(_log_sach(caplog))


def test_memory_loi_db_khong_ghi_cau_lenh_kem_tham_so(caplog):
    from src.core.memory import MemoryManager

    class _Hong:
        def connect(self):
            raise RuntimeError(f"INSERT ... [parameters: ('{CANARY}',)]")

    mm = MemoryManager.__new__(MemoryManager)
    mm.engine = _Hong()
    caplog.set_level(logging.DEBUG)
    try:
        mm.add_message(1, 1, "user", CANARY)
    except Exception:       # noqa: S110 - chỉ cần kiểm nhật ký
        pass
    assert not _thay(_log_sach(caplog))


def test_uvicorn_tat_nhat_ky_truy_cap():
    """Nhật ký truy cập của uvicorn ghi đường dẫn KÈM chuỗi truy vấn (tên tệp, từ khoá tìm kiếm): tắt trong ảnh triển khai."""
    import pathlib
    dockerfile = (pathlib.Path(__file__).resolve().parents[2] / "deploy" / "Dockerfile").read_text(encoding="utf-8")
    assert "--no-access-log" in dockerfile


def test_loai_loi_co_vi_tri_de_tim_cho_hong_ma_khong_co_noi_dung():
    from src.core.utils import loai_loi

    def sau():
        raise ValueError(f"chua noi dung {CANARY}")

    def truoc():
        sau()

    try:
        truoc()
    except ValueError:
        s = loai_loi()
    assert s.startswith("ValueError tại ") and "test_nhat_ky_khong_noi_dung.py:" in s and "sau" in s and "truoc" in s
    assert not _thay(s)


# ---------------------------------------------------------------------------
# Khoá việc ghi log: lỗi cũ không được quay lại
# ---------------------------------------------------------------------------

# Chỗ được phép ghi thân thông báo của ngoại lệ, kèm lý do. Mọi chỗ khác dùng `loai_loi()` (tên loại + vị trí).
LOG_THAN_LOI_DUOC_PHEP = {
    "core/workflow_schema.py": "đường dẫn và lỗi đọc MẪU workflow của repo, không có dữ liệu khách",
}


def _lenh_log_ghi_loi(goc) -> list[str]:
    """Quét bằng `ast` (không theo dòng): bắt cả lời gọi `logger.x(...)` viết nhiều dòng. Vi phạm = đối số vị trí là tên ngoại lệ trần, hoặc `exc_info=True`."""
    import ast
    # `err` KHÔNG nằm trong danh sách: ở chat.py nó là chuỗi lý do do validator của Brain tạo (`_extract_json_block`, `validate_workflow`), không phải ngoại lệ.
    ten_loi = {"exc", "e", "error", "ex"}
    ra = []
    for f in sorted(goc.rglob("*.py")):
        rel = f.relative_to(goc).as_posix()
        if rel in LOG_THAN_LOI_DUOC_PHEP:
            continue
        for nut in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if not (isinstance(nut, ast.Call) and isinstance(nut.func, ast.Attribute) and isinstance(nut.func.value, ast.Name)
                    and nut.func.value.id in {"logger", "log", "LOG", "_logger"}
                    and nut.func.attr in {"debug", "info", "warning", "error", "exception", "critical"}):
                continue
            xau = any(isinstance(a, ast.Name) and a.id in ten_loi for a in nut.args[1:])
            traceback = any(k.arg == "exc_info" and isinstance(k.value, ast.Constant) and k.value.value is True for k in nut.keywords)
            if xau or traceback:
                ra.append(f"src/{rel}:{nut.lineno}")
    return ra


def test_khong_logger_nao_ghi_than_thong_bao_ngoai_le_hay_traceback():
    """`logger.x("...", exc)` ghi cả thân thông báo (SQL kèm tham số, URL, `input` của pydantic), `exc_info=True` ghi cả traceback có thông báo. Cấm trừ chỗ khai báo."""
    import pathlib
    goc = pathlib.Path(__file__).resolve().parents[2] / "src"
    vi_pham = _lenh_log_ghi_loi(goc)
    assert not vi_pham, "ghi thân thông báo ngoại lệ vào nhật ký (dùng `loai_loi()` từ src.core.utils):\n" + "\n".join(vi_pham)


MAU_NHIEU_DONG = """import logging
logger = logging.getLogger('x')
try:
    pass
except Exception as exc:
    logger.warning(
        'lỗi: %s', exc,
        extra={'a': 1},
    )
    logger.error('lỗi', exc_info=True)
    logger.info('ổn %s', type(exc).__name__)
"""


def test_bo_quet_log_bat_duoc_loi_goi_nhieu_dong(tmp_path):
    """Chốt chống xanh suông: bản quét theo dòng từng bỏ sót lời gọi `logger.warning(` viết trải nhiều dòng."""
    (tmp_path / "x.py").write_text(MAU_NHIEU_DONG, encoding="utf-8")
    assert _lenh_log_ghi_loi(tmp_path) == ["src/x.py:6", "src/x.py:10"]


def test_chot_danh_sach_duoc_phep_khong_chet():
    import pathlib
    goc = pathlib.Path(__file__).resolve().parents[2] / "src"
    for rel in LOG_THAN_LOI_DUOC_PHEP:
        assert (goc / rel).exists(), f"{rel} không còn: xoá khỏi LOG_THAN_LOI_DUOC_PHEP"
