"""
tests/test_khong_chan_event_loop.py — handler `async def` không được gọi hàm chặn trên event loop
(AGENTS §4.1 quy tắc 2, brain#223, PR-A).

VÌ SAO CÓ FILE NÀY
------------------
Năm chỗ trong route gọi thẳng một hàm đồng bộ tốn thời gian ngay trong `async def`:

    chat.py       web_search_fallback          (DuckDuckGo, chờ mạng)
    knowledge.py  doc_extract.extract          (bóc chữ PDF/DOCX)
    tools.py      load_xlsx_bytes / load_partners_xlsx_bytes / load_products_xlsx_bytes

Một lời gọi như vậy giữ chân CẢ event loop cho tới khi nó xong: `/health`, việc poll
`/api/v1/task/{id}` của Body và mọi request khác đứng chờ. Không lỗi, không cảnh báo, không
test đơn vị nào thấy — vì bản thân hàm vẫn trả kết quả đúng. Cái hỏng là chỗ nó được GỌI.

CÁCH ĐO
-------
Không đo "có gọi `asyncio.to_thread` không" (đó là đo cách làm, không đo điều khách thấy).
Đo thẳng: một coroutine "nhịp tim" tick mỗi 10ms chạy song song với request; hàm chặn được
thay bằng bản `time.sleep(0.3)`. Khoảng trễ lớn nhất giữa hai tick:

    mã cũ  0,306-0,319s  (loop đứng đúng bằng thời gian hàm ngủ)
    mã mới 0,024-0,038s

(Đo 15/11/2026 trên máy dev Windows, Python 3.14. Nhịp tim 10ms nên sàn của số đo là ~0,01s.)

Ngưỡng 0,15s nằm giữa hai số đó, cách mỗi bên một khoảng rộng để máy CI chậm không làm test chập chờn.
Thêm một phép kiểm trực tiếp: hàm chặn phải chạy trên thread KHÁC thread của loop.

`test_nhip_tim_bat_duoc_viec_chan_loop` chạy đầu dò lên một việc chặn loop cố ý, để chứng minh đầu dò
KHÔNG câm: nếu nó không bắt được cái xấu thì mọi ca xanh bên dưới đều vô nghĩa.

KHÔNG THUỘC PR NÀY (xem brain#223): các lời gọi SQL (`_load_history`, `_save_turn`, ...) và mọi
thao tác `KnowledgeBase` (search/add_document/...). Nhóm sau dùng chung embedder, chromadb và cache
BM25, nên chỉ ném ra thread pool mặc định là mở ra race thật — nó cần một worker duy nhất, làm ở PR sau.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

# `openpyxl` import TRƯỚC các module test mượn đồ bên dưới: chúng gọi `pytest.importorskip("openpyxl")`
# lúc import, tức thiếu thư viện là CẢ FILE NÀY bị bỏ qua lặng lẽ. Import thẳng ở đây thì thiếu là lỗi
# thu thập test, to và rõ.
import httpx
import openpyxl  # noqa: F401
import pytest

from src.api import dependencies as deps
from src.api.chay_ngoai_loop import chay_ngoai_loop
from src.api.main import app
from src.api.routes import chat as chat_mod
from src.api.routes import tools as tools_mod
from src.core import doc_extract
from src.core.knowledge import KnowledgeBase
from tests.test_chat_routing import _KhoGia, moi_truong  # noqa: F401  (moi_truong là fixture)
from tests.test_import_endpoints import MIME_XLSX, _bang_doi_tac, _bang_hang_hoa
from tests.test_inventory_import_api import _misa_rows, _xlsx
from tests.test_knowledge import FakeCollection, FakeEmbedder, FakeReranker

TRE_CHAN = 0.3      # thời gian hàm chặn "ngủ"
NHIP = 0.01         # chu kỳ nhịp tim
NGUONG = 0.15       # khoảng trễ tối đa chấp nhận được giữa hai nhịp

CAU_HOI_LUAT = "nghị định 72 quy định thuế suất bao nhiêu"   # RETRIEVAL + được phép tra web


# ---------------------------------------------------------------------------
# Đầu dò
# ---------------------------------------------------------------------------

async def _do_khoang_tre_lon_nhat(viec: Callable[[], Awaitable[Any]]) -> tuple[Any, float]:
    """
    Chạy `viec()` trong lúc một coroutine tick mỗi `NHIP` giây.

    Trả về (kết quả của viec, khoảng trễ lớn nhất giữa hai tick liên tiếp).
    Tick cuối được ghi SAU khi `dung` đã bật: nếu không, việc chặn loop xong ngay
    trước khi nhịp tim kịp thức sẽ làm khoảng trễ đó BIẾN MẤT khỏi số đo.
    """
    mau: list[float] = []
    dung = asyncio.Event()

    async def nhip_tim() -> None:
        while True:
            mau.append(time.perf_counter())
            if dung.is_set():
                return
            await asyncio.sleep(NHIP)

    tac_vu = asyncio.create_task(nhip_tim())
    await asyncio.sleep(NHIP * 5)   # cho nhịp tim vào guồng trước khi đo
    try:
        ket_qua = await viec()
    finally:
        dung.set()
        await tac_vu
    return ket_qua, max(b - a for a, b in zip(mau, mau[1:]))


class _HamCham:
    """
    Bọc một hàm: ghi lại thread nó chạy, ngủ `tre` giây rồi giao cho hàm gốc.

    Giao lại cho hàm gốc (thay vì trả hàng giả) để đường thành công đi hết route như thật —
    nếu không, test xanh chỉ vì route nổ sớm trước khi tới chỗ cần đo.
    """

    def __init__(self, goc: Callable[..., Any]):
        self.goc = goc
        self.tre = 0.0
        self.thread_ids: list[int] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.thread_ids.append(threading.get_ident())
        if self.tre:
            time.sleep(self.tre)
        return self.goc(*args, **kwargs)


def _may_khach() -> httpx.AsyncClient:
    """Khách chạy CHUNG event loop với test — khác `TestClient`, vốn chạy app ở loop/thread riêng."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=30.0,
    )


# ---------------------------------------------------------------------------
# Bốn đường tải file: ba loader xlsx + nạp tài liệu RAG
# ---------------------------------------------------------------------------

def _file_ton_kho() -> dict[str, Any]:
    rows = _misa_rows([["VT001", "Dầu mẫu A", "Lít", 100, 5_000_000, 400, 20_000_000,
                        450, 22_500_000, 50, 2_500_000]])
    return {"files": {"file": ("ton_kho.xlsx", _xlsx(rows), MIME_XLSX)}}


def _file_doi_tac() -> dict[str, Any]:
    data = _bang_doi_tac([1, "KH01", "Công ty mẫu A", "Hà Nội", 5_000_000, "0101234567", "0901"])
    return {"files": {"file": ("khach_hang.xlsx", data, MIME_XLSX)}}


def _file_hang_hoa() -> dict[str, Any]:
    data = _bang_hang_hoa([1, "VT01", "Dầu mẫu B", "Chưa xác định", "HH", "Lít", 4, 7_360_000])
    return {"files": {"file": ("hang_hoa.xlsx", data, MIME_XLSX)}}


def _file_tai_lieu() -> dict[str, Any]:
    noi_dung = "QUY ĐỊNH MẪU\nKhách hàng thanh toán trong 30 ngày kể từ ngày nhận hàng.\n"
    return {
        "files": {"file": ("quy_dinh.txt", noi_dung.encode("utf-8"), "text/plain")},
        "data": {"workspace_id": "khach-mau"},
    }


@dataclass(frozen=True)
class _Diem:
    """Một chỗ gọi hàm chặn: URL, module chứa hàm, tên hàm, và cách dựng request."""

    ten: str
    url: str
    module: Any
    ham: str
    yeu_cau: Callable[[], dict[str, Any]]


DIEM = [
    _Diem("inventory-import", "/tools/inventory-import",
          tools_mod.inv_import, "load_xlsx_bytes", _file_ton_kho),
    _Diem("partner-import", "/tools/partner-import",
          tools_mod.pi, "load_partners_xlsx_bytes", _file_doi_tac),
    _Diem("product-import", "/tools/product-import",
          tools_mod.vc, "load_products_xlsx_bytes", _file_hang_hoa),
    _Diem("knowledge-upload", "/knowledge/documents",
          doc_extract, "extract", _file_tai_lieu),
]
DS_DIEM = [pytest.param(d, id=d.ten) for d in DIEM]


@pytest.fixture
def kho_tri_thuc(monkeypatch):
    """KB thật với đồ giả bên trong — chỉ để đường nạp tài liệu đi hết, không cần model."""
    kb = KnowledgeBase(
        embedder=FakeEmbedder(), reranker=FakeReranker(), collection=FakeCollection(),
    )
    monkeypatch.setattr(deps.runtime, "kb", kb, raising=False)
    return kb


# ---------------------------------------------------------------------------
# Đầu dò phải bắt được cái xấu
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_nhip_tim_bat_duoc_viec_chan_loop():
    """Gọi hàm ngủ THẲNG trên loop (đúng như mã cũ) thì đầu dò phải thấy loop đứng ~0,3s."""

    async def chan_tren_loop():
        time.sleep(TRE_CHAN)

    _, khoang = await _do_khoang_tre_lon_nhat(chan_tren_loop)
    assert khoang >= TRE_CHAN * 0.9, f"đầu dò không thấy loop bị chặn (đo được {khoang:.3f}s)"


@pytest.mark.asyncio
async def test_nhip_tim_khong_bao_dong_gia_khi_viec_qua_thread():
    """Đối chứng của ca trên: cùng việc ngủ 0,3s nhưng qua thread thì loop phải chạy đều."""
    _, khoang = await _do_khoang_tre_lon_nhat(lambda: chay_ngoai_loop(time.sleep, TRE_CHAN))
    assert khoang < NGUONG, f"loop vẫn bị giữ {khoang:.3f}s dù việc đã ở thread"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chay_ngoai_loop_chay_tren_thread_khac_va_giu_nguyen_tham_so():
    def ghi(a, b, *, c):
        return threading.get_ident(), (a, b, c)

    tid, ket_qua = await chay_ngoai_loop(ghi, 1, 2, c=3)

    assert tid != threading.get_ident(), "hàm chặn vẫn chạy trên thread của event loop"
    assert ket_qua == (1, 2, 3)


@pytest.mark.asyncio
@pytest.mark.parametrize("loi", [ValueError("sai"), RuntimeError("thiếu thư viện"), KeyError("k")])
async def test_chay_ngoai_loop_de_ngoai_le_lan_ra_nguyen_loai(loi):
    """`try/except ValueError/RuntimeError` quanh lời gọi ở route phải giữ nguyên nghĩa."""

    def no():
        raise loi

    with pytest.raises(type(loi)) as exc:
        await chay_ngoai_loop(no)
    assert exc.value is loi


# ---------------------------------------------------------------------------
# /chat — tra web
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_web_search_khong_dong_bang_loop(moi_truong, monkeypatch):  # noqa: F811
    monkeypatch.setattr(deps.runtime, "kb", _KhoGia(passages=[]), raising=False)
    cham = _HamCham(lambda q: "Nghị định 72/2024 quy định thuế suất...")
    monkeypatch.setattr(chat_mod, "web_search_fallback", cham)

    ai = {"X-User-Id": "1", "X-Store-Id": "1"}
    body = {"user_id": 1, "store_id": 1, "message": CAU_HOI_LUAT}

    async with _may_khach() as ac:
        # Lượt đầu không ngủ: nạp trước các import lười để không tính vào số đo.
        ban_dau = await ac.post("/chat", headers=ai, json=body)
        assert ban_dau.status_code == 200

        cham.tre = TRE_CHAN
        resp, khoang = await _do_khoang_tre_lon_nhat(
            lambda: ac.post("/chat", headers=ai, json=body)
        )
        assert resp.status_code == 200
        ket_qua = (await ac.get(f"/api/v1/task/{resp.json()['task_id']}", headers=ai)).json()

    # Đường tra web phải đi hết thật, không phải test xanh vì nhánh bị bỏ qua.
    assert ket_qua["status"] == "completed", ket_qua
    assert len(cham.thread_ids) == 2
    assert "KẾT QUẢ TÌM KIẾM" in moi_truong.contexts[-1]
    # Số đo trước (điều Body thấy), phép kiểm cơ chế sau.
    assert khoang < NGUONG, f"event loop bị giữ {khoang:.3f}s trong lúc tra web"
    assert all(t != threading.get_ident() for t in cham.thread_ids), \
        "web_search_fallback vẫn chạy trên thread của event loop"


# ---------------------------------------------------------------------------
# Bốn đường tải file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("diem", DS_DIEM)
async def test_tai_file_khong_dong_bang_loop(diem: _Diem, monkeypatch, kho_tri_thuc):
    cham = _HamCham(getattr(diem.module, diem.ham))
    monkeypatch.setattr(diem.module, diem.ham, cham)

    async with _may_khach() as ac:
        ban_dau = await ac.post(diem.url, **diem.yeu_cau())
        assert ban_dau.status_code == 200, ban_dau.text

        cham.tre = TRE_CHAN
        resp, khoang = await _do_khoang_tre_lon_nhat(
            lambda: ac.post(diem.url, **diem.yeu_cau())
        )

    assert resp.status_code == 200, resp.text
    assert len(cham.thread_ids) == 2
    # Số đo trước (điều Body thấy), phép kiểm cơ chế sau.
    assert khoang < NGUONG, f"event loop bị giữ {khoang:.3f}s trong lúc {diem.ten} đọc file"
    assert all(t != threading.get_ident() for t in cham.thread_ids), \
        f"{diem.ham} vẫn chạy trên thread của event loop"


@pytest.mark.asyncio
@pytest.mark.parametrize("diem", DS_DIEM)
@pytest.mark.parametrize(
    ("loi", "ma"),
    [
        pytest.param(ValueError("File hỏng — lý do cụ thể"), 422, id="ValueError-422"),
        pytest.param(RuntimeError("Thiếu thư viện — pip install ..."), 503, id="RuntimeError-503"),
    ],
)
async def test_loi_trong_thread_van_ra_dung_ma_http(
    diem: _Diem, loi: Exception, ma: int, monkeypatch, kho_tri_thuc
):
    """
    Ngoại lệ ném ở thread phải ra đúng mã HTTP như khi nó ném ngay trên loop: ValueError là lỗi
    của FILE (422, kèm lý do cho người dùng sửa), RuntimeError là lỗi CÀI ĐẶT (503). Nhầm hai
    loại này làm người dùng đi sửa một file không có lỗi.
    """

    def no(*args: Any, **kwargs: Any):
        raise loi

    monkeypatch.setattr(diem.module, diem.ham, no)

    async with _may_khach() as ac:
        resp = await ac.post(diem.url, **diem.yeu_cau())

    assert resp.status_code == ma, resp.text
    assert resp.json()["detail"] == str(loi)
