"""
tests/test_llm_mat_suy_giam.py — GPU/vLLM mất thì `/chat` trả 503 `llm_unavailable`, còn `/tools/*` vẫn 200 (A21, #203).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core import llm_suc_khoe as lk
from src.core.serving import BackendError, BackendTimeout, BackendUnavailable
from tests.test_chat_routing import moi_truong  # noqa: F401  (fixture dựng runtime tối thiểu)

client = TestClient(app)
AI = {"X-User-Id": "1", "X-Store-Id": "1"}


@pytest.fixture(autouse=True)
def sach():
    lk.dat_lai()
    yield
    lk.dat_lai()


def test_mach_mo_sau_3_loi_lien_tiep_va_dong_lai_khi_ok(monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(lk.time, "monotonic", lambda: t[0])
    for _ in range(lk.NGUONG_LOI - 1):
        lk.ghi_loi()
    assert not lk.dang_hong()
    lk.ghi_loi()
    assert lk.dang_hong() and lk.trang_thai() == {"available": False, "consecutive_failures": 3}
    t[0] += lk.THU_LAI_S + 1
    assert not lk.dang_hong(), "hết THU_LAI_S thì cho MỘT lượt đi thử"
    assert lk.dang_hong(), "lượt thứ hai vẫn bị từ chối tới khi lượt thử xong"
    lk.ghi_ok()
    assert not lk.dang_hong() and lk.trang_thai()["available"] is True


def test_thu_lai_that_bai_thi_mo_tiep(monkeypatch):
    t = [0.0]
    monkeypatch.setattr(lk.time, "monotonic", lambda: t[0])
    for _ in range(3):
        lk.ghi_loi()
    t[0] += lk.THU_LAI_S + 1
    assert not lk.dang_hong()
    lk.ghi_loi()
    assert lk.dang_hong()


def test_chat_503_khi_mach_mo_va_tools_van_200(moi_truong):  # noqa: F811
    for _ in range(3):
        lk.ghi_loi()
    r = client.post("/chat", headers=AI, json={"user_id": 1, "store_id": 1, "message": "xin chào"})
    assert r.status_code == 503
    assert r.json()["error"] == "llm_unavailable" and r.headers["Retry-After"] == str(int(lk.THU_LAI_S))
    v = client.post("/tools/vat", json={"items": [{"name": "A", "price": 1_000_000, "qty": 1, "is_reduced_vat": False}],
                                        "prices_include_vat": False, "stated_total": 1_100_000})
    assert v.status_code == 200 and v.json()["calculated_total"] == 1_100_000


def test_health_cho_thay_trang_thai_model():
    for _ in range(3):
        lk.ghi_loi()
    assert client.get("/health").json()["llm"] == {"available": False, "consecutive_failures": 3}


@pytest.mark.parametrize("loi,dem", [(BackendUnavailable("mat"), 1), (BackendTimeout("het gio"), 1), (BackendError("rac"), 0),
                                      (ValueError("x"), 0)])
def test_chi_mat_ket_noi_va_het_gio_moi_tinh_la_gpu_mat(loi, dem):
    """JSON hỏng hay model trả rác không phải GPU mất: không được làm mở mạch."""
    import asyncio

    from src.core.engine import ModelEngine

    async def hong():
        raise loi
    eng = ModelEngine.__new__(ModelEngine)
    asyncio.run(eng.background_worker("t-llm", hong))
    assert lk.trang_thai()["consecutive_failures"] == dem


def test_background_worker_thanh_cong_dong_mach():
    import asyncio

    from src.core.engine import ModelEngine

    async def tot():
        return "ok"
    lk.ghi_loi()
    eng = ModelEngine.__new__(ModelEngine)
    asyncio.run(eng.background_worker("t-llm-ok", tot))
    assert lk.trang_thai()["consecutive_failures"] == 0


# ---------------------------------------------------------------------------
# Thăm dò chủ động (#203)
# ---------------------------------------------------------------------------

class _ServerGia:
    def __init__(self, ket_qua):
        self.ket_qua, self.so_lan = ket_qua, 0

    async def chat(self, req):
        self.so_lan += 1
        assert req.max_tokens == 1, "thăm dò chỉ được sinh MỘT token (chi phí)"
        if isinstance(self.ket_qua, Exception):
            raise self.ket_qua
        return "ok"


def test_tham_do_mat_ket_noi_nap_vao_mach_roi_mo():
    import asyncio
    s = _ServerGia(BackendUnavailable("mat"))
    for _ in range(3):
        assert asyncio.run(lk.mot_lan_tham_do(s)) is False
    assert lk.dang_hong()


def test_tham_do_thanh_cong_dong_mach_va_loi_khac_khong_tinh():
    import asyncio
    for _ in range(3):
        lk.ghi_loi()
    assert asyncio.run(lk.mot_lan_tham_do(_ServerGia(ValueError("rac")))) is None
    assert lk.dang_hong(), "lỗi không phải mất kết nối không đóng mạch"
    lk.dat_lai()
    for _ in range(3):
        lk.ghi_loi()
    assert asyncio.run(lk.mot_lan_tham_do(_ServerGia(None))) is True
    assert not lk.dang_hong()


def test_vong_tham_do_goi_dung_chu_ky_va_bo_qua_khi_chua_co_server():
    import asyncio
    s = _ServerGia(None)
    co = [None, s, s]

    async def chay():
        t = asyncio.create_task(lk.vong_tham_do(lambda: co.pop(0) if co else s, 0.01))
        await asyncio.sleep(0.15)
        t.cancel()
    asyncio.run(chay())
    assert s.so_lan >= 2


@pytest.mark.parametrize("gia_tri,ket", [("", 60.0), ("30", 30.0), ("0", 0.0), ("0.5", 0.5)])
def test_chu_ky_tham_do_doc_tu_env(monkeypatch, gia_tri, ket):
    monkeypatch.setenv("LLM_PROBE_INTERVAL_S", gia_tri)
    assert lk.chu_ky_tham_do_s() == ket


@pytest.mark.parametrize("gia_tri", ["abc", "-1", "nan", "inf"])
def test_chu_ky_hong_thi_tu_choi_khoi_dong(monkeypatch, gia_tri):
    monkeypatch.setenv("LLM_PROBE_INTERVAL_S", gia_tri)
    with pytest.raises(RuntimeError, match="LLM_PROBE_INTERVAL_S"):
        lk.chu_ky_tham_do_s()
