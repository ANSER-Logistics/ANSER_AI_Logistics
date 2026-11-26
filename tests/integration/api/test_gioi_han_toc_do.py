"""
tests/integration/api/test_gioi_han_toc_do.py — giới hạn tốc độ theo khách (#218): vượt hạn mức thì 429 kèm Retry-After, khách khác cùng lúc vẫn 200, và lớp này không bao giờ làm sập Body.

Ba điều phải giữ: (1) khách A vượt hạn mức không làm khách B chậm đi; (2) `X-Store-Id` do client khai CHỈ được tin khi yêu cầu đã qua HMAC (chưa qua thì cả nhóm một xô chung); (3) lỗi bất kỳ trong
lớp này thì cho qua (fail-open) chứ không chặn người thật. Phần tích hợp dùng HMAC thật ở chế độ enforce.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import gioi_han_toc_do as g
from src.api import hmac_auth as h
from src.api.main import app

# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------


def test_mac_dinh_hai_nhom():
    c = g.doc_cau_hinh({})
    assert c == {"gpu": g.HanMuc(30.0, 10), "tools": g.HanMuc(300.0, 60)}


def test_doc_tu_moi_truong():
    c = g.doc_cau_hinh({"RATE_LIMIT_GPU_PER_MIN": "12.5", "RATE_LIMIT_GPU_BURST": "3", "RATE_LIMIT_TOOLS_PER_MIN": "100", "RATE_LIMIT_TOOLS_BURST": "7"})
    assert c["gpu"] == g.HanMuc(12.5, 3) and c["tools"] == g.HanMuc(100.0, 7)


def test_khong_mot_la_tat_nhom_va_dinh_khong_con_bi_kiem():
    c = g.doc_cau_hinh({"RATE_LIMIT_GPU_PER_MIN": "0", "RATE_LIMIT_GPU_BURST": "0"})
    assert c["gpu"].moi_phut == 0


@pytest.mark.parametrize("env,ten", [
    ({"RATE_LIMIT_GPU_PER_MIN": "nhieu"}, "RATE_LIMIT_GPU_PER_MIN"),
    ({"RATE_LIMIT_GPU_PER_MIN": "-1"}, "RATE_LIMIT_GPU_PER_MIN"),
    ({"RATE_LIMIT_GPU_PER_MIN": "nan"}, "RATE_LIMIT_GPU_PER_MIN"),
    ({"RATE_LIMIT_GPU_PER_MIN": "inf"}, "RATE_LIMIT_GPU_PER_MIN"),
    ({"RATE_LIMIT_GPU_PER_MIN": "100001"}, "RATE_LIMIT_GPU_PER_MIN"),
    ({"RATE_LIMIT_GPU_BURST": "3.5"}, "RATE_LIMIT_GPU_BURST"),
    ({"RATE_LIMIT_GPU_BURST": "0"}, "RATE_LIMIT_GPU_BURST"),
    ({"RATE_LIMIT_TOOLS_BURST": "-2"}, "RATE_LIMIT_TOOLS_BURST"),
    ({"RATE_LIMIT_TOOLS_PER_MIN": "abc"}, "RATE_LIMIT_TOOLS_PER_MIN"),
])
def test_gia_tri_hong_bi_tu_choi_va_neu_ten_bien(env, ten):
    with pytest.raises(RuntimeError, match=ten):
        g.doc_cau_hinh(env)


def test_loi_cau_hinh_khong_in_gia_tri():
    with pytest.raises(RuntimeError) as e:
        g.doc_cau_hinh({"RATE_LIMIT_GPU_PER_MIN": "bi-mat-123"})
    assert "bi-mat-123" not in str(e.value)


def test_cau_hinh_hong_thi_khong_khoi_dong(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_GPU_PER_MIN", "nhieu")
    with pytest.raises(RuntimeError, match="RATE_LIMIT_GPU_PER_MIN"):
        with TestClient(app):
            pass


@pytest.mark.parametrize("method,path,nhom", [
    ("POST", "/chat", "gpu"), ("POST", "/ocr", "gpu"), ("POST", "/ocr/freight", "gpu"), ("POST", "/upload", "gpu"),
    ("POST", "/knowledge/search", "gpu"), ("POST", "/knowledge/documents", "gpu"),
    ("POST", "/tools/vat", "tools"), ("POST", "/tools/quote", "tools"), ("POST", "/mcp/tools/call", "tools"), ("GET", "/mcp/tools/list", "tools"),
    ("GET", "/health", None), ("GET", "/api/v1/task/abc", None), ("GET", "/tools", None), ("GET", "/knowledge/documents", None),
    ("DELETE", "/knowledge/documents", None), ("OPTIONS", "/chat", None), ("OPTIONS", "/tools/vat", None), ("GET", "/chat", None),
])
def test_nhom_cua_tung_route(method, path, nhom):
    assert g.nhom_cua(method, path) == nhom


def test_moi_route_post_cua_app_co_nhom_neu_la_gpu_hoac_tools():
    """Chốt chống quên route mới: route POST nào của app mà không thuộc hai nhóm thì phải có mặt trong danh sách miễn đã biết (để thêm route mới là phải quyết)."""
    from tests.support.bang_route import bang_route
    mien_da_biet = {"/knowledge/documents"}     # DELETE/GET; POST của nó đã ở nhóm gpu
    khong_nhom = sorted({p for m, p in bang_route(app) if m == "POST" and g.nhom_cua(m, p) is None and p not in mien_da_biet})
    assert khong_nhom == [], f"route POST chưa thuộc nhóm hạn mức nào: {khong_nhom}. Thêm vào `_ROUTE_GPU` hoặc quyết định miễn có chủ đích."


# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------

K = ("gpu", "body", "cua-hang-a")


def test_dinh_roi_toi_het_thi_cho_dung_thoi_gian():
    kho = g.KhoXo()
    han = g.HanMuc(60.0, 2)           # 1 token mỗi giây
    assert kho.thu(K, han, 100.0) == 0.0 and kho.thu(K, han, 100.0) == 0.0
    cho = kho.thu(K, han, 100.0)
    assert cho == pytest.approx(1.0)
    assert kho.thu(K, han, 100.5) == pytest.approx(0.5), "chưa đủ một token: chờ nốt phần còn thiếu"
    assert kho.thu(K, han, 101.0) == 0.0, "đủ một giây thì có token mới"


def test_khong_tich_qua_dinh_khi_ranh():
    kho = g.KhoXo()
    han = g.HanMuc(60.0, 2)
    assert kho.thu(K, han, 0.0) == 0.0
    for _ in range(2):
        kho.thu(K, han, 1000.0)       # rảnh 1000 giây rồi gửi: chỉ được đúng 2 (đỉnh), không phải 1000
    assert kho.thu(K, han, 1000.0) > 0


def test_khach_khac_khoa_khac_khong_anh_huong():
    kho = g.KhoXo()
    han = g.HanMuc(6.0, 1)
    assert kho.thu(("gpu", "body", "a"), han, 0.0) == 0.0
    assert kho.thu(("gpu", "body", "a"), han, 0.0) > 0
    assert kho.thu(("gpu", "body", "b"), han, 0.0) == 0.0
    assert kho.thu(("gpu", "n8n", "a"), han, 0.0) == 0.0
    assert kho.thu(("tools", "body", "a"), han, 0.0) == 0.0, "hai nhóm không chia sẻ xô"


def test_dong_ho_chay_lui_khong_cap_them_token():
    kho = g.KhoXo()
    han = g.HanMuc(60.0, 1)
    assert kho.thu(K, han, 100.0) == 0.0
    assert kho.thu(K, han, 50.0) > 0


def test_day_khoa_thi_bo_khoa_cu_nhat_va_khong_tu_choi_nguoi_moi():
    kho = g.KhoXo(toi_da_khoa=3)
    han = g.HanMuc(6.0, 1)
    for i in range(5):
        assert kho.thu(("gpu", "body", f"c{i}"), han, float(i)) == 0.0
    assert len(kho) == 3


def test_toi_da_khoa_vo_ly():
    with pytest.raises(ValueError):
        g.KhoXo(0)


def test_nhieu_luong_cung_luc_dem_dung():
    kho = g.KhoXo()
    han = g.HanMuc(60.0, 50)
    cho_qua = []

    def chay():
        for _ in range(40):
            if kho.thu(K, han, 0.0) == 0.0:
                cho_qua.append(1)

    ts = [threading.Thread(target=chay) for _ in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(cho_qua) == 50, "200 lượt cùng một thời điểm, đỉnh 50: đúng 50 qua, không hơn không kém"


# ---------------------------------------------------------------------------
# Khoá đếm
# ---------------------------------------------------------------------------

def _scope(store=None):
    dau = [(b"x-store-id", store.encode())] if store is not None else []
    return {"type": "http", "headers": dau}


def test_chua_qua_hmac_thi_xo_chung_va_bo_qua_store_id_tu_khai():
    assert g.khoa_dem(_scope("cua-hang-a"), "gpu") == ("gpu", "-", "")
    assert g.khoa_dem(_scope("cua-hang-b"), "gpu") == ("gpu", "-", "")


def test_da_qua_hmac_thi_dem_theo_key_id_va_store_id():
    t1, t2 = h.da_xac_thuc.set(True), h.key_id_xac_thuc.set("body")
    try:
        assert g.khoa_dem(_scope("cua-hang-a"), "gpu") == ("gpu", "body", "cua-hang-a")
        assert g.khoa_dem(_scope(None), "tools") == ("tools", "body", "")
        assert g.khoa_dem(_scope("x" * 500), "gpu")[2] == "x" * g.TOI_DA_DO_DAI_STORE_ID, "store id dài bị cắt để bộ nhớ có trần"
    finally:
        h.key_id_xac_thuc.reset(t2)
        h.da_xac_thuc.reset(t1)


# ---------------------------------------------------------------------------
# Middleware trên app nhỏ, đồng hồ giả
# ---------------------------------------------------------------------------

class _GiaHmac:
    """Đóng vai `HmacMiddleware` (đứng NGOÀI lớp giới hạn): có `X-Test-Key` thì đặt hai ContextVar như HMAC enforce đã kiểm đúng."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        key = next((v.decode() for k, v in scope.get("headers", ()) if k == b"x-test-key"), None)
        if scope["type"] == "http" and key:
            t1, t2 = h.da_xac_thuc.set(True), h.key_id_xac_thuc.set(key)
            try:
                await self.app(scope, receive, send)
            finally:
                h.key_id_xac_thuc.reset(t2)
                h.da_xac_thuc.reset(t1)
        else:
            await self.app(scope, receive, send)


class Dong:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _app_nho(han=None, dh=None, kho=None, cau_hinh=None):
    han = han or {"gpu": g.HanMuc(60.0, 3), "tools": g.HanMuc(60.0, 5)}
    nho = FastAPI()
    goi = []

    @nho.post("/chat")
    async def chat():
        goi.append("chat")
        return {"ok": True}

    @nho.post("/tools/vat")
    async def vat():
        return {"ok": True}

    @nho.get("/health")
    async def health():
        return {"ok": True}

    @nho.get("/api/v1/task/{x}")
    async def task(x: str):
        return {"ok": True}

    nho.add_middleware(g.GioiHanTocDoMiddleware, cau_hinh=cau_hinh or (lambda: han), kho_xo=kho if kho is not None else g.KhoXo(), dong_ho=dh or Dong())
    nho.add_middleware(_GiaHmac)
    nho.goi = goi            # type: ignore[attr-defined]
    return nho


def _post(c, path="/chat", store="a", key="body"):
    dau = {"X-Store-Id": store}
    if key:
        dau["X-Test-Key"] = key
    return c.post(path, json={}, headers=dau)


def test_vuot_hang_muc_thi_429_kem_retry_after_va_than_dung():
    c = TestClient(_app_nho())
    ma = [_post(c).status_code for _ in range(5)]
    assert ma == [200, 200, 200, 429, 429]
    r = _post(c)
    assert r.status_code == 429 and r.headers["content-type"] == "application/json"
    assert r.json() == {"detail": "Too Many Requests"}
    assert r.headers["retry-after"] == "1"


def test_retry_after_lam_tron_len_va_tre_nhat_la_mot_giay():
    nho = _app_nho(han={"gpu": g.HanMuc(6.0, 1), "tools": g.HanMuc(6.0, 1)})        # 1 token mỗi 10 giây
    c = TestClient(nho)
    assert _post(c).status_code == 200
    r = _post(c)
    assert r.status_code == 429 and r.headers["retry-after"] == "10"


def test_sau_khi_cho_dung_thoi_gian_thi_qua_lai():
    dh = Dong()
    c = TestClient(_app_nho(han={"gpu": g.HanMuc(60.0, 1), "tools": g.HanMuc(60.0, 1)}, dh=dh))
    assert _post(c).status_code == 200
    assert _post(c).status_code == 429
    dh.t += 1.0
    assert _post(c).status_code == 200


def test_khach_a_vuot_khong_lam_khach_b_cham_di():
    c = TestClient(_app_nho())
    for _ in range(10):
        _post(c, store="a")
    assert _post(c, store="a").status_code == 429
    assert [_post(c, store="b").status_code for _ in range(3)] == [200, 200, 200], "khách B (cùng khoá HMAC, store khác) không bị ảnh hưởng"
    assert _post(c, store="a", key="n8n").status_code == 200, "cùng store nhưng khoá HMAC khác là xô khác"


def test_chua_qua_hmac_thi_store_id_tu_khai_khong_tach_xo():
    c = TestClient(_app_nho())
    ma = [_post(c, store=f"gia-{i}", key=None).status_code for i in range(5)]
    assert ma == [200, 200, 200, 429, 429], "đổi X-Store-Id mỗi lượt không thoát được hạn mức khi chưa có HMAC"


def test_nhom_gpu_va_tools_khong_chia_se_xo():
    c = TestClient(_app_nho())
    for _ in range(4):
        _post(c, "/chat")
    assert _post(c, "/chat").status_code == 429
    assert _post(c, "/tools/vat").status_code == 200


def test_route_mien_khong_bi_gioi_han():
    c = TestClient(_app_nho(han={"gpu": g.HanMuc(6.0, 1), "tools": g.HanMuc(6.0, 1)}))
    assert [c.get("/health").status_code for _ in range(20)] == [200] * 20
    assert [c.get("/api/v1/task/abc").status_code for _ in range(20)] == [200] * 20
    assert [c.options("/chat").status_code in (200, 405) for _ in range(20)] == [True] * 20


def test_tat_nhom_bang_khong_thi_khong_chan():
    c = TestClient(_app_nho(han={"gpu": g.HanMuc(0.0, 0), "tools": g.HanMuc(0.0, 0)}))
    assert [_post(c).status_code for _ in range(50)] == [200] * 50


def test_429_khong_chay_handler():
    nho = _app_nho(han={"gpu": g.HanMuc(6.0, 1), "tools": g.HanMuc(6.0, 1)})
    c = TestClient(nho)
    _post(c)
    _post(c)
    _post(c)
    assert nho.goi == ["chat"], "yêu cầu bị từ chối không được vào tới handler"


def test_dem_tu_choi_theo_nhom_vao_thong_ke():
    g.dat_lai()
    c = TestClient(_app_nho(kho=g.kho))
    for _ in range(6):
        _post(c)
    assert g.thong_ke()["rejected"] == {"gpu": 3}
    assert g.thong_ke()["tracked_keys"] == 1


# ---------------------------------------------------------------------------
# Fail-open
# ---------------------------------------------------------------------------

def test_loi_doc_cau_hinh_thi_cho_qua_va_ghi_log_khong_noi_dung(caplog):
    def hong():
        raise RuntimeError("noi dung-nhay-cam")

    c = TestClient(_app_nho(cau_hinh=hong))
    caplog.set_level(logging.DEBUG)
    assert [_post(c, store="CANARY-STORE").status_code for _ in range(10)] == [200] * 10
    log = "\n".join(r.getMessage() + (r.exc_text or "") for r in caplog.records)
    assert "Giới hạn tốc độ lỗi, cho qua" in log
    assert "CANARY-STORE" not in log and "noi dung-nhay-cam" not in log, "không ghi thân lỗi và không ghi X-Store-Id"


def test_loi_trong_bo_dem_thi_cho_qua():
    class KhoHong(g.KhoXo):
        def thu(self, *a, **k):
            raise ValueError("hỏng")

    c = TestClient(_app_nho(kho=KhoHong()))
    assert [_post(c).status_code for _ in range(10)] == [200] * 10


# ---------------------------------------------------------------------------
# Tích hợp: app thật, HMAC enforce thật
# ---------------------------------------------------------------------------

KHOA = "k" * 40
TOKEN = "token-thu-nghiem-" + "t" * 20
THAN_VAT = {"items": [{"name": "Hàng A", "price": 1_000_000, "qty": 2, "is_reduced_vat": False}], "prices_include_vat": False, "stated_total": 2_200_000}


@pytest.fixture
def app_that(monkeypatch):
    from src.api import dependencies as deps
    from src.api import main as main_mod

    for ten in [k for k in __import__("os").environ if k.startswith(h.TIEN_TO_KHOA)]:
        monkeypatch.delenv(ten)
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(main_mod, "API_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("API_HMAC_KEY_BODY", KHOA)
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    monkeypatch.setenv("RATE_LIMIT_TOOLS_PER_MIN", "60")
    monkeypatch.setenv("RATE_LIMIT_TOOLS_BURST", "2")
    h.dat_lai_thong_ke()
    g.dat_lai()
    yield TestClient(app)
    h.dat_lai_thong_ke()


def _vat_ky(c, store):
    than = json.dumps(THAN_VAT, ensure_ascii=False).encode("utf-8")
    ts, nonce = str(int(time.time())), secrets.token_hex(16)
    sig = h.ky(KHOA.encode(), "body", ts, nonce, "POST", "/tools/vat", "", than)
    return c.post("/tools/vat", content=than, headers={
        "X-Key-Id": "body", "X-Timestamp": ts, "X-Nonce": nonce, "X-Signature": "v1=" + sig,
        "Content-Type": "application/json", "X-Store-Id": store,
    })


def test_that_khach_a_vuot_429_khach_b_van_200(app_that):
    assert [_vat_ky(app_that, "cua-hang-a").status_code for _ in range(2)] == [200, 200]
    r = _vat_ky(app_that, "cua-hang-a")
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert _vat_ky(app_that, "cua-hang-b").status_code == 200, "khách B cùng lúc vẫn 200"


def test_that_chu_ky_sai_thi_401_khong_ton_token_cua_ai(app_that):
    r = app_that.post("/tools/vat", json=THAN_VAT, headers={"X-Store-Id": "cua-hang-a"})
    assert r.status_code == 401
    assert [_vat_ky(app_that, "cua-hang-a").status_code for _ in range(2)] == [200, 200], "yêu cầu 401 không được trừ hạn mức của khách"


def test_that_health_ke_so_lan_tu_choi_va_hang_muc(app_that):
    for _ in range(4):
        _vat_ky(app_that, "cua-hang-a")
    b = app_that.get("/health").json()["rate_limit"]
    assert b["rejected"] == {"tools": 2}
    assert b["limits"]["tools"] == {"per_min": 60.0, "burst": 2} and b["limits"]["gpu"] == {"per_min": 0.0, "burst": 10}
    assert b["tracked_keys"] == 1
    assert "cua-hang-a" not in json.dumps(b), "/health không lộ khoá của khách"


def test_that_log_429_khong_chua_store_id(app_that, caplog):
    caplog.set_level(logging.DEBUG)
    for _ in range(4):
        _vat_ky(app_that, "CANARY-CUA-HANG-" + "z" * 8)
    log = "\n".join(r.getMessage() + (r.exc_text or "") for r in caplog.records if not r.name.startswith(("httpx", "httpcore")))
    assert "429 nhóm=tools key_id=body" in log
    assert "CANARY-CUA-HANG" not in log


def test_that_hmac_tat_thi_mot_xo_chung_bat_chap_store_id(monkeypatch):
    from src.api import dependencies as deps
    from src.api import main as main_mod

    monkeypatch.setattr(deps, "API_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(main_mod, "API_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("API_HMAC_MODE", "off")
    monkeypatch.setenv("RATE_LIMIT_TOOLS_PER_MIN", "60")
    monkeypatch.setenv("RATE_LIMIT_TOOLS_BURST", "2")
    g.dat_lai()
    c = TestClient(app)
    ma = [c.post("/tools/vat", json=THAN_VAT, headers={"X-Api-Token": TOKEN, "X-Store-Id": f"c{i}"}).status_code for i in range(3)]
    assert ma == [200, 200, 429]


def test_that_mac_dinh_khong_cham_vao_route_ngoai_hai_nhom(app_that, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_TOOLS_PER_MIN", "1")
    monkeypatch.setenv("RATE_LIMIT_TOOLS_BURST", "1")
    assert [app_that.get("/health").status_code for _ in range(10)] == [200] * 10
