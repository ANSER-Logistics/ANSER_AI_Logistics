"""
tests/integration/api/test_hmac_auth.py — xác thực HMAC từng yêu cầu (A6, issue #193).

Ba lớp:
1. VECTOR VÀNG: bốn bộ (chuỗi cần ký, chữ ký) do bên TypeScript (Node, `node:crypto`) tính, kiểm bên Python tính ra đúng từng byte. Có tiếng Việt,
   emoji kèm CRLF, chuỗi truy vấn khó, thân rỗng. Phía Body phải chạy đúng các vector này trước khi bật `enforce`.
2. Hàm thuần `kiem`: mỗi lý do thất bại một ca, kể cả các chỗ Python dễ dãi (xuống dòng cuối, chữ số Ả Rập, `_` trong số).
3. Qua HTTP thật của app: ba chế độ, 401 đến trước 422, thân đọc được hai lần, nonce phát lại, mọi endpoint chặn khi không có chữ ký.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import src.api.dependencies as deps
import src.api.main as main_mod
from src.api import hmac_auth as h
from src.api.main import app
from tests.support.bang_route import bang_route

KHOA = ("0123456789abcdef" * 4).encode("utf-8")

# (tên, key_id, ts, nonce, method, path, query, body_hex, chuỗi cần ký, chữ ký) — sinh bởi Node v24 (`node:crypto`), 20/11/2026
VECTOR = [
    ("post_json_unicode", "body-1", "1790000000", "00112233445566778899aabbccddeeff", "POST", "/tools/quote", "",
     "7b226f726967696e223a2248434d222c2264657374223a2248c3a0204ee1bb9969222c226b67223a313530302c226e6f7465223a22c491227d",
     "ANSER-HMAC-V1\nbody-1\n1790000000\n00112233445566778899aabbccddeeff\nPOST\n/tools/quote\n\neff00f0fef92eb791d3bb0aeb9310fcec06f5a63097107618def49e095efc588",
     "9647a630a2d1fbfae1616c924743bec743ba0e0c0d240bc3d18917866706c0db"),
    ("get_query", "body-1", "1790000001", "ffeeddccbbaa99887766554433221100", "GET", "/health",
     "a=A&a=x%20y&b=2&c=%C3%A9%21%27%28%29%2A~%2B%26%3D%25", "",
     "ANSER-HMAC-V1\nbody-1\n1790000001\nffeeddccbbaa99887766554433221100\nGET\n/health\na=A&a=x%20y&b=2&c=%C3%A9%21%27%28%29%2A~%2B%26%3D%25\ne3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
     "d397e0b5a5db864666d3109a87797bceb3e97722269c3e400e334df84d01b8ea"),
    ("post_empty", "n8n-1", "1790000002", "a" * 32, "POST", "/tools/ping", "", "",
     "ANSER-HMAC-V1\nn8n-1\n1790000002\naaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\nPOST\n/tools/ping\n\ne3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
     "3659b13a3638b5b758bf04e90b755bbfefac0b64ed829ca98ca5377173b90b3b"),
    ("post_emoji_crlf", "body-2", "1790000003", "b" * 32, "POST", "/chat", "",
     "7b0d0a2020226d7367223a202278696e206368c3a06f20f09f9880222c0d0a20202262223a20312c202261223a20320d0a7d",
     "ANSER-HMAC-V1\nbody-2\n1790000003\nbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\nPOST\n/chat\n\ndca7b0d54dc85b8ca323120b057f1407a83cf387a3b48f6b6ca1d8a13172fffa",
     "6c80623fb90cacbed885a8e27892942196ecae7e1b746e097cce4c4dc7925434"),
]


@pytest.mark.parametrize("v", VECTOR, ids=[v[0] for v in VECTOR])
def test_vector_vang_python_ra_dung_nhu_typescript(v):
    _, key_id, ts, nonce, method, path, query, body_hex, canon, sig = v
    body = bytes.fromhex(body_hex)
    assert h.chuoi_can_ky(key_id, ts, nonce, method, path, query, body) == canon
    assert h.ky(KHOA, key_id, ts, nonce, method, path, query, body) == sig


# ---------------------------------------------------------------------------
# Hàm thuần
# ---------------------------------------------------------------------------

def _hdr(v, **ghi_de):
    _, key_id, ts, nonce, method, path, query, body_hex, canon, sig = v
    d = {"x-key-id": key_id, "x-timestamp": ts, "x-nonce": nonce, "x-signature": "v1=" + sig}
    d.update(ghi_de)
    return d


def _kiem(v, headers=None, bay_gio=None, kho=None, khoa=None, **ghi_de):
    _, key_id, ts, nonce, method, path, query, body_hex, canon, sig = v
    kw = dict(method=method, path=path, raw_query=query, headers=headers if headers is not None else _hdr(v),
              body=bytes.fromhex(body_hex), bay_gio=float(ts) if bay_gio is None else bay_gio,
              kho=kho or h.KhoNonce(), khoa=khoa or {"body-1": KHOA, "body-2": KHOA, "n8n-1": KHOA})
    kw.update(ghi_de)
    return h.kiem(**kw)


@pytest.mark.parametrize("v", VECTOR, ids=[v[0] for v in VECTOR])
def test_kiem_chap_nhan_vector_vang(v):
    assert _kiem(v) == h.KetQua(True, "ok", v[1])


def test_kiem_ly_do_that_bai():
    v = VECTOR[0]
    assert _kiem(v, headers={}).ly_do == h.THIEU_HEADER
    bo = _hdr(v)
    del bo["x-nonce"]
    assert _kiem(v, headers=bo).ly_do == h.THIEU_HEADER
    assert _kiem(v, headers=_hdr(v, **{"x-signature": "v1=" + "0" * 63})).ly_do == h.SAI_DINH_DANG
    assert _kiem(v, headers=_hdr(v, **{"x-signature": "0" * 64})).ly_do == h.SAI_DINH_DANG        # thiếu tiền tố v1=
    assert _kiem(v, headers=_hdr(v, **{"x-signature": "v1=" + "0" * 64})).ly_do == h.SAI_CHU_KY
    assert _kiem(v, khoa={"khac": KHOA}).ly_do == h.KHOA_LA
    assert _kiem(v, bay_gio=1790000000 + 301).ly_do == h.HET_HAN
    assert _kiem(v, bay_gio=1790000000 - 301).ly_do == h.HET_HAN
    assert _kiem(v, bay_gio=1790000000 + 300).ok                                                   # biên: đúng 300 giây vẫn nhận
    assert _kiem(v, headers={**_hdr(v), "content-encoding": "gzip"}).ly_do == h.CO_NEN
    assert _kiem(v, path="/tools/qu ote").ly_do == h.SAI_DUONG_DAN
    assert _kiem(v, path="/tools/quo%74e").ly_do == h.SAI_DUONG_DAN
    assert _kiem(v, path="/tools/quote/..;x").ly_do == h.SAI_DUONG_DAN


def test_kiem_sua_mot_byte_la_sai_chu_ky():
    v = VECTOR[0]
    assert _kiem(v, body=bytes.fromhex(v[7]) + b" ").ly_do == h.SAI_CHU_KY
    assert _kiem(v, raw_query="a=1").ly_do == h.SAI_CHU_KY
    assert _kiem(v, method="GET").ly_do == h.SAI_CHU_KY
    assert _kiem(v, path="/tools/quote2").ly_do == h.SAI_CHU_KY
    assert _kiem(v, headers=_hdr(v, **{"x-key-id": "body-2"})).ly_do == h.SAI_CHU_KY              # đổi key id: chuỗi ký khác


@pytest.mark.parametrize("ts", ["1_790_000", "+179000000", " 179000000", "1790000000\n", "١٧٩٠٠٠٠٠٠٠", "179000000", "17900000000"])
def test_timestamp_dai_dot_python_deu_bi_tu_choi(ts):
    """`int()` của Python chấp nhận cả những chuỗi này; `re.fullmatch` thì không."""
    assert _kiem(VECTOR[0], headers=_hdr(VECTOR[0], **{"x-timestamp": ts})).ly_do == h.SAI_DINH_DANG


@pytest.mark.parametrize("nonce", ["00112233445566778899aabbccddeeff\n", "00112233445566778899AABBCCDDEEFF", "0011", " " * 32])
def test_nonce_sai_dang_bi_tu_choi(nonce):
    assert _kiem(VECTOR[0], headers=_hdr(VECTOR[0], **{"x-nonce": nonce})).ly_do == h.SAI_DINH_DANG


def test_chu_ky_khong_ascii_khong_lam_hong_so_sanh():
    """`hmac.compare_digest` ném TypeError trên str không ASCII; phải bị chặn ở bước kiểm dạng, trả lý do chứ không ném."""
    r = _kiem(VECTOR[0], headers=_hdr(VECTOR[0], **{"x-signature": "v1=" + "é" * 64}))
    assert r.ly_do == h.SAI_DINH_DANG


def test_nonce_chi_ghi_sau_khi_chu_ky_dung():
    v, kho = VECTOR[0], h.KhoNonce()
    assert _kiem(v, headers=_hdr(v, **{"x-signature": "v1=" + "0" * 64}), kho=kho).ly_do == h.SAI_CHU_KY
    assert len(kho) == 0, "chữ ký sai không được làm đầy bộ nhớ nonce của người thật"
    assert _kiem(v, kho=kho).ok
    assert _kiem(v, kho=kho).ly_do == h.PHAT_LAI


def test_nonce_het_han_sau_660_giay_va_theo_tung_key_id():
    kho = h.KhoNonce()
    assert not kho.da_gap_roi_ghi("a", "n" * 32, 1000.0)
    assert not kho.da_gap_roi_ghi("b", "n" * 32, 1000.0), "cùng nonce khác key id là hai khoá khác nhau"
    assert kho.da_gap_roi_ghi("a", "n" * 32, 1000.0 + 659)
    assert not kho.da_gap_roi_ghi("a", "n" * 32, 1000.0 + 661 + 600), "sau cửa sổ nhớ thì được dùng lại (đã quá hạn giờ nên bị chặn ở bước giờ)"


def test_kho_nonce_day_bo_muc_cu_nhat_chu_khong_tu_choi_nguoi_that():
    kho = h.KhoNonce(toi_da=3)
    for i in range(3):
        assert not kho.da_gap_roi_ghi("k", f"{i}" * 32, 1000.0 + i)
    assert not kho.da_gap_roi_ghi("k", "9" * 32, 1010.0)
    assert len(kho) == 3


# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------

def test_cau_hinh_sai_thi_tu_choi_khoi_dong(monkeypatch):
    for ten in [k for k in __import__("os").environ if k.startswith(h.TIEN_TO_KHOA)]:
        monkeypatch.delenv(ten)
    monkeypatch.setenv("API_HMAC_MODE", "bat")
    with pytest.raises(RuntimeError, match="không hợp lệ"):
        h.kiem_cau_hinh()
    monkeypatch.setenv("API_HMAC_MODE", "log")
    with pytest.raises(RuntimeError, match="không có biến"):
        h.kiem_cau_hinh()
    monkeypatch.setenv("API_HMAC_KEY_BODY", "ngan")
    with pytest.raises(RuntimeError, match="ngắn hơn") as e:
        h.kiem_cau_hinh()
    assert "ngan" not in str(e.value).replace("ngắn", ""), "thông báo lỗi không được in giá trị khoá"
    monkeypatch.setenv("API_HMAC_KEY_BODY", "k" * 40)
    h.kiem_cau_hinh()
    monkeypatch.setenv("API_HMAC_MODE", "off")
    h.kiem_cau_hinh()


def test_ten_bien_thanh_key_id(monkeypatch):
    monkeypatch.setenv("API_HMAC_KEY_BODY", "x" * 40)
    monkeypatch.setenv("API_HMAC_KEY_BODY_2", "y" * 40)
    monkeypatch.setenv("API_HMAC_KEY_N8N", "")
    assert set(h.nap_khoa()) >= {"body", "body-2"} and "n8n" not in h.nap_khoa()


# ---------------------------------------------------------------------------
# Qua HTTP thật của app
# ---------------------------------------------------------------------------

TOKEN = "token-cu-cho-test"
KHOA_BODY = "b" * 40
client = TestClient(app)
THAN_VAT = {"items": [{"name": "Hàng A", "price": 1_000_000, "qty": 2, "is_reduced_vat": False}],
            "prices_include_vat": False, "stated_total": 2_200_000}


@pytest.fixture(autouse=True)
def moi_truong(monkeypatch):
    for ten in [k for k in __import__("os").environ if k.startswith(h.TIEN_TO_KHOA)]:
        monkeypatch.delenv(ten)
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", TOKEN)
    monkeypatch.setattr(main_mod, "API_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("API_HMAC_KEY_BODY", KHOA_BODY)
    h.dat_lai_thong_ke()
    yield
    h.dat_lai_thong_ke()


def _ky(method, path, body: bytes = b"", query="", key_id="body", khoa=KHOA_BODY, ts=None, nonce=None):
    import secrets
    import time
    ts = ts or str(int(time.time()))
    nonce = nonce or secrets.token_hex(16)
    sig = h.ky(khoa.encode(), key_id, ts, nonce, method, path, query, body)
    return {"X-Key-Id": key_id, "X-Timestamp": ts, "X-Nonce": nonce, "X-Signature": "v1=" + sig,
            "Content-Type": "application/json"}


def _goi(method, path, than: bytes = b"", query="", **kw_ky):
    dau = _ky(method, path, than, query, **kw_ky.pop("ky", {}))
    dau.update(kw_ky.pop("them", {}))
    return client.request(method, path + (f"?{query}" if query else ""), content=than, headers=dau)


def _vat():
    return json.dumps(THAN_VAT, ensure_ascii=False).encode("utf-8")


def test_off_khong_doi_gi_ca(monkeypatch):
    monkeypatch.setenv("API_HMAC_MODE", "off")
    assert client.post("/tools/vat", content=_vat(), headers={"Content-Type": "application/json"}).status_code == 401
    r = client.post("/tools/vat", content=_vat(), headers={"Content-Type": "application/json", "X-Api-Token": TOKEN})
    assert r.status_code == 200 and r.json()["calculated_total"] == 2_200_000
    assert h.thong_ke()["counts"] == {}, "chế độ off không kiểm HMAC, không đếm"


def test_log_van_bat_token_cu_va_chi_ghi_nhan_hmac(monkeypatch, caplog):
    monkeypatch.setenv("API_HMAC_MODE", "log")
    assert _goi("POST", "/tools/vat", _vat()).status_code == 401, "log: chữ ký đúng mà thiếu token cũ vẫn bị từ chối"
    r = _goi("POST", "/tools/vat", _vat(), them={"X-Api-Token": TOKEN})
    assert r.status_code == 200
    r = client.post("/tools/vat", content=_vat(), headers={"Content-Type": "application/json", "X-Api-Token": TOKEN})
    assert r.status_code == 200, "log: người gọi cũ chưa ký vẫn qua (chỉ thiếu header, không phải lỗi)"
    dem = h.thong_ke()["counts"]
    assert dem["ok"] == 2 and dem["thieu_header"] == 1 and dem.get("sai_chu_ky", 0) == 0   # hai lượt có ký (cả hai đúng), một lượt cũ


def test_log_ghi_ly_do_sai_chu_ky_nhung_khong_chan(monkeypatch, caplog):
    monkeypatch.setenv("API_HMAC_MODE", "log")
    caplog.set_level("INFO", logger="projecta.api")
    r = _goi("POST", "/tools/vat", _vat(), ky={"khoa": "z" * 40}, them={"X-Api-Token": TOKEN})
    assert r.status_code == 200
    assert h.thong_ke()["counts"] == {"sai_chu_ky": 1}
    nhat_ky = " ".join(rec.getMessage() for rec in caplog.records)
    assert "sai_chu_ky" in nhat_ky and "key_id=body" in nhat_ky
    assert "z" * 40 not in nhat_ky and "Hàng A" not in nhat_ky


def test_enforce_chap_nhan_chu_ky_dung_khong_can_token_cu(monkeypatch):
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    r = _goi("POST", "/tools/vat", _vat())
    assert r.status_code == 200 and r.json()["calculated_total"] == 2_200_000, r.text


def test_enforce_token_cu_khong_con_la_duong_vao(monkeypatch):
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    r = client.post("/tools/vat", content=_vat(), headers={"Content-Type": "application/json", "X-Api-Token": TOKEN})
    assert r.status_code == 401


def test_enforce_phat_lai_bi_chan(monkeypatch):
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    dau = _ky("POST", "/tools/vat", _vat())
    assert client.post("/tools/vat", content=_vat(), headers=dau).status_code == 200
    assert client.post("/tools/vat", content=_vat(), headers=dau).status_code == 401
    assert h.thong_ke()["counts"]["phat_lai"] == 1


def test_enforce_sua_than_la_401_va_401_den_truoc_422(monkeypatch):
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    dau = _ky("POST", "/tools/vat", _vat())
    r = client.post("/tools/vat", content=_vat() + b" ", headers=dau)
    assert r.status_code == 401 and r.json() == {"detail": "Unauthorized"}
    # Thân SAI KHUÔN (422 nếu qua cổng) mà chữ ký không có: vẫn 401, không lộ tên trường.
    r = client.post("/tools/vat", content=b"{}", headers={"Content-Type": "application/json"})
    assert r.status_code == 401 and "items" not in r.text


def test_enforce_moi_ly_do_that_bai_tra_cung_mot_than_401(monkeypatch):
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    cac = [
        client.post("/tools/vat", content=_vat()),                                                       # thiếu header
        _goi("POST", "/tools/vat", _vat(), ky={"khoa": "q" * 40}),                                       # sai chữ ký
        _goi("POST", "/tools/vat", _vat(), ky={"key_id": "la"}),                                         # khoá lạ
        _goi("POST", "/tools/vat", _vat(), ky={"ts": "1000000000"}),                                     # hết hạn
    ]
    assert {(r.status_code, r.text) for r in cac} == {(401, '{"detail":"Unauthorized"}')}


def test_enforce_than_duoc_doc_hai_lan_json_va_multipart(monkeypatch):
    """Cổng đọc thân rồi, handler vẫn phải phân tích được: JSON (đã thử ở trên) và multipart (tệp tải lên)."""
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    bien = "----anserbien"
    than = (f"--{bien}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.txt\"\r\n"
            f"Content-Type: text/plain\r\n\r\nxin chao\r\n--{bien}--\r\n").encode("utf-8")
    dau = _ky("POST", "/tools/vat", than)
    dau["Content-Type"] = f"multipart/form-data; boundary={bien}"
    r = client.post("/tools/vat", content=than, headers=dau)
    assert r.status_code != 401, "chữ ký đúng thì phải qua cổng (route có thể trả 422 vì thân không phải JSON, nhưng không 401)"


def test_enforce_than_qua_lon_bi_chan_truoc_khi_doc(monkeypatch):
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    monkeypatch.setenv("API_HMAC_MAX_BODY_BYTES", "100")
    # JSON hợp lệ: FastAPI phân tích JSON TRƯỚC khi chạy dependency, nên thân không phải JSON ra 422 từ trước cổng (có sẵn từ trước).
    r = _goi("POST", "/tools/vat", b'{"a": "' + b"x" * 101 + b'"}')
    assert r.status_code == 413 and h.thong_ke()["counts"]["than_qua_lon"] == 1


def test_enforce_chuoi_truy_van_tho_duoc_ky(monkeypatch):
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    r = _goi("GET", "/tools", query="a=x%20y&b=%C3%A9")
    assert r.status_code == 200
    dau = _ky("GET", "/tools", b"", "a=1")
    assert client.get("/tools?a=2", headers=dau).status_code == 401


def test_enforce_xoay_khoa_hai_key_id_cung_song(monkeypatch):
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    monkeypatch.setenv("API_HMAC_KEY_BODY_2", "c" * 40)
    assert _goi("POST", "/tools/vat", _vat()).status_code == 200
    assert _goi("POST", "/tools/vat", _vat(), ky={"key_id": "body-2", "khoa": "c" * 40}).status_code == 200
    monkeypatch.delenv("API_HMAC_KEY_BODY")
    assert _goi("POST", "/tools/vat", _vat()).status_code == 401, "thu hồi: xoá biến thì key id đó hết hiệu lực ngay"
    assert _goi("POST", "/tools/vat", _vat(), ky={"key_id": "body-2", "khoa": "c" * 40}).status_code == 200


def test_health_mo_va_cho_thay_che_do_nhung_khong_lo_khoa(monkeypatch):
    monkeypatch.setenv("API_HMAC_MODE", "log")
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()["hmac"]
    assert j["mode"] == "log" and j["key_ids"] == ["body"]
    assert KHOA_BODY not in r.text


def _duong_di_thuc(path: str) -> str:
    import re
    return re.sub(r"\{[^}]+\}", "x", path)


@pytest.mark.parametrize("method,path", [r for r in bang_route(app) if r[1] != "/health"])
def test_enforce_moi_endpoint_chan_khi_khong_co_chu_ky(monkeypatch, method, path):
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    r = client.request(method, _duong_di_thuc(path), json={}, headers={"X-Api-Token": TOKEN})
    assert r.status_code == 401, f"{method} {path} trả {r.status_code}: ở enforce không có chữ ký thì phải 401 (kể cả khi có token cũ)"


def test_khoi_dong_enforce_khong_can_token_cu_nhung_can_khoa(monkeypatch):
    monkeypatch.setenv("ENV", "SERVER")
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", "")
    monkeypatch.setenv("API_HMAC_MODE", "off")
    assert deps.thieu_token_o_trien_khai() is True
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    assert deps.thieu_token_o_trien_khai() is False
    monkeypatch.delenv("API_HMAC_KEY_BODY")
    assert deps.thieu_token_o_trien_khai() is True


def test_enforce_upload_multipart_that_di_qua_cong_va_toi_duoc_handler(monkeypatch):
    """Multipart là đường FastAPI đọc thân bằng `request.form()`: cổng đã đọc thân rồi thì handler vẫn phải đọc được (không 500)."""
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    bien = "----anserbien"
    than = (f"--{bien}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.xlsx\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\nkhong-phai-xlsx\r\n--{bien}--\r\n").encode("utf-8")
    ds = [(m, p) for m, p in bang_route(app) if m == "POST" and "import" in p]
    assert ds, "không tìm thấy route import nhận tệp"
    for m, p in ds:
        dau = _ky(m, p, than)
        dau["Content-Type"] = f"multipart/form-data; boundary={bien}"
        r = client.post(p, content=than, headers=dau)
        assert r.status_code in (400, 415, 422), f"{p}: {r.status_code} {r.text[:200]} (500 = cổng làm hỏng việc đọc thân multipart)"


def test_enforce_than_json_sai_cu_phap_khong_ky_la_401_khong_phai_422(monkeypatch):
    """Dependency chạy SAU khi FastAPI phân tích JSON, nên thân sai cú pháp ra 422 trước cổng; middleware thì chặn trước."""
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    r = client.post("/tools/vat", content=b"{khong phai json", headers={"Content-Type": "application/json"})
    assert r.status_code == 401 and r.json() == {"detail": "Unauthorized"}


def test_log_van_chuyen_tiep_multipart_nguyen_ven(monkeypatch):
    monkeypatch.setenv("API_HMAC_MODE", "log")
    bien = "----anserbien"
    than = (f"--{bien}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.xlsx\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\nkhong-phai-xlsx\r\n--{bien}--\r\n").encode("utf-8")
    p = "/tools/inventory-import"
    dau = _ky("POST", p, than)
    dau["Content-Type"] = f"multipart/form-data; boundary={bien}"
    dau["X-Api-Token"] = TOKEN
    r = client.post(p, content=than, headers=dau)
    assert r.status_code in (400, 415, 422), r.text[:200]
    assert h.thong_ke()["counts"] == {"ok": 1}


def test_enforce_than_gui_theo_tung_manh_van_kiem_dung(monkeypatch):
    """Thân chunked (generator): cổng phải ghép đủ các mảnh rồi mới băm."""
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    than = _vat()
    dau = _ky("POST", "/tools/vat", than)

    def manh():
        for i in range(0, len(than), 17):
            yield than[i:i + 17]
    r = client.post("/tools/vat", content=manh(), headers=dau)
    assert r.status_code == 200, r.text


def test_health_khong_can_chu_ky_o_enforce(monkeypatch):
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    assert client.get("/health").status_code == 200


def test_enforce_ma_middleware_bi_go_van_dong_cua(monkeypatch):
    """Phòng thủ nhiều lớp: không có cờ do middleware đặt thì dependency tự từ chối."""
    import asyncio

    import pytest as _p
    from fastapi import HTTPException
    monkeypatch.setenv("API_HMAC_MODE", "enforce")
    with _p.raises(HTTPException) as e:
        asyncio.run(deps.auth_guard_hmac(x_api_token=TOKEN))
    assert e.value.status_code == 401
