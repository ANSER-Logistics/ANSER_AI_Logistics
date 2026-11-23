"""
tests/integration/api/test_gioi_han_than_210.py — trần kích thước request trên MỌI route (#210).

Tiêu chí của issue: request quá trần bị từ chối bằng 413/422, KHÔNG BAO GIỜ 500. Thêm một tiêu chí đo được mà
kiểm trong handler không đáp ứng nổi: thân quá trần phải bị từ chối TRƯỚC khi server đọc hết nó.

Danh sách route lấy từ `bang_route(app)` (OpenAPI), không viết tay: thêm route mới là tự vào diện kiểm.
Gọi ASGI trực tiếp (không qua TestClient) để đếm đúng số byte ứng dụng đã kéo từ `receive`.

Bảng route x trần: `ARCHITECTURE.md` mục "Trần kích thước request (#210)".
"""

from __future__ import annotations

import asyncio
import json
import os

os.environ.setdefault("ENV", "LOCAL")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.api.gioi_han_than import TRAN_THAN_MAC_DINH, GioiHanThanMiddleware, phan_loai_do_dai  # noqa: E402
from src.api.main import app  # noqa: E402
from src.core.config import LICH_SU_TOI_DA_KY_TU, MAX_UPLOAD_BYTES  # noqa: E402
from tests.support.bang_route import bang_route  # noqa: E402

KHUC = 64 * 1024
CO_THAN = {"POST", "PUT", "PATCH", "DELETE"}

ROUTE_CO_THAN = [(m, p) for m, p in bang_route(app) if m in CO_THAN]


def _route_nhan_tep() -> list[str]:
    """Route khai thân multipart trong OpenAPI — tức route nhận tệp."""
    ra = []
    for path, ops in app.openapi()["paths"].items():
        for op in ops.values():
            noi_dung = (op.get("requestBody") or {}).get("content", {}) if isinstance(op, dict) else {}
            if "multipart/form-data" in noi_dung:
                ra.append(path)
    return sorted(set(ra))


ROUTE_NHAN_TEP = _route_nhan_tep()


def _dien_tham_so(path: str) -> str:
    return path.replace("{", "x").replace("}", "")


def _goi_asgi(ung_dung, method: str, path: str, than: bytes, headers: dict[str, str | bytes]):
    """Gọi ASGI trực tiếp. Trả (mã, thân phản hồi, số byte ứng dụng đã đọc).

    Giá trị header là `bytes` thì đi nguyên byte: cần để gửi byte latin-1 như 0xB2 (`²`), thứ `str.encode()` (UTF-8)
    không tạo ra được. Ứng dụng ném lỗi ra ngoài thì `asyncio.run` ném lại — trên server thật đó là 500.
    """
    khuc = [than[i:i + KHUC] for i in range(0, len(than), KHUC)] or [b""]
    da_doc = 0
    gui: list[dict] = []

    async def receive():
        nonlocal da_doc
        if not khuc:
            return {"type": "http.disconnect"}
        k = khuc.pop(0)
        da_doc += len(k)
        return {"type": "http.request", "body": k, "more_body": bool(khuc)}

    async def send(tin):
        gui.append(tin)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
        "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
        "headers": [(k.lower().encode(), v if isinstance(v, bytes) else v.encode()) for k, v in headers.items()],
        "client": ("127.0.0.1", 1), "server": ("t", 80),
    }
    asyncio.run(ung_dung(scope, receive, send))
    bat_dau = [t for t in gui if t["type"] == "http.response.start"]
    assert len(bat_dau) == 1, f"phải có đúng MỘT phản hồi, có {len(bat_dau)}"
    than_ra = b"".join(t.get("body", b"") for t in gui if t["type"] == "http.response.body")
    return bat_dau[0]["status"], than_ra, da_doc


def test_bang_route_khong_rong():
    """Chống xanh suông: parametrize trên danh sách rỗng là 0 ca chạy mà vẫn xanh (#29)."""
    assert len(ROUTE_CO_THAN) >= 15, ROUTE_CO_THAN
    assert {"/ocr", "/tools/inventory-import", "/knowledge/documents"} <= set(ROUTE_NHAN_TEP), ROUTE_NHAN_TEP


# ---------------------------------------------------------------------------
# Thân quá trần: 413, và không đọc hết
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", ROUTE_CO_THAN)
def test_content_length_qua_tran_413_khong_doc_byte_nao(method, path):
    than = b"a" * (TRAN_THAN_MAC_DINH + 1)
    ma, ra, da_doc = _goi_asgi(app, method, _dien_tham_so(path), than,
                               {"content-type": "application/json", "content-length": str(len(than))})
    assert ma == 413, (ma, ra[:120])
    assert da_doc == 0, f"đã đọc {da_doc} byte trước khi từ chối — phải từ chối chỉ bằng Content-Length"


@pytest.mark.parametrize("method,path", ROUTE_CO_THAN)
def test_chunked_qua_tran_413_dung_doc_som(method, path):
    """Không có Content-Length (chunked): phải ngừng đọc ngay khi vượt trần, không đọc tới hết.

    Thân multipart ĐÚNG KHUÔN (rác thì parser đã từ chối 400 ở byte đầu, không chạm tới trần) với một tệp gấp 3 trần.
    """
    dau = (b"--X\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.xlsx\"\r\n"
           b"Content-Type: application/octet-stream\r\n\r\n")
    than = dau + b"a" * (TRAN_THAN_MAC_DINH * 3) + b"\r\n--X--\r\n"
    ma, ra, da_doc = _goi_asgi(app, method, _dien_tham_so(path), than,
                               {"content-type": "multipart/form-data; boundary=X"})
    # Route không đọc thân (DELETE /knowledge/documents chỉ nhận query) trả 422 vì thiếu tham số, không kéo byte nào:
    # đúng tiêu chí "413/422, không 500" và không tốn gì. Mọi route ĐỌC thân thì phải là 413.
    assert ma == 413 or (ma == 422 and da_doc == 0), (ma, da_doc, ra[:120])
    assert da_doc <= TRAN_THAN_MAC_DINH + KHUC, f"đọc {da_doc} byte, trần {TRAN_THAN_MAC_DINH}"


@pytest.mark.parametrize("path", ROUTE_NHAN_TEP)
def test_tep_vuot_tran_tep_nhung_duoi_tran_than_van_413(path):
    """Lớp thứ hai: tệp lớn hơn MAX_UPLOAD_BYTES nhưng cả thân vẫn dưới trần request -> handler trả 413, không 500."""
    client = TestClient(app)
    r = client.post(path, files={"file": ("a.xlsx", b"A" * (MAX_UPLOAD_BYTES + 1))},
                    data={"workspace_id": "khach-hu-cau"})
    assert r.status_code == 413, (r.status_code, r.text[:200])


# Header SAI -> 400. Ba ca đầu theo byte latin-1: `isdigit()` trả True cho `²`, `³`, `¹` mà `int()` ném ValueError
# — bản đầu của #217 trả 500 ở đây (wikiepeidia chỉ ra khi duyệt, tái hiện 23/11/2026).
DO_DAI_SAI_CA = [
    b"\xb2", b"\xb9\xb2", b"1\xb3",
    b"abc", b"", b"-1", b"+5", b"1.5", b"1e3", b"0x10", b"1 2", "٣".encode(),
]


@pytest.mark.parametrize("cl", DO_DAI_SAI_CA, ids=repr)
def test_content_length_sai_400_khong_500(cl):
    ma, ra, da_doc = _goi_asgi(app, "POST", "/tools/vat", b"{}", {"content-length": cl})
    assert ma == 400, (ma, ra[:120])
    assert da_doc == 0


# Header ĐÚNG nhưng vượt trần -> 413, kể cả khi dài hơn 4300 chữ số (giới hạn `int()` của Python 3.11+) hay có số 0
# ở đầu. Phân biệt với 400 ở trên: độ dài hợp lệ thì người gửi cần biết là QUÁ LỚN, không phải SAI ĐỊNH DẠNG.
DO_DAI_QUA_TRAN_CA = [
    str(TRAN_THAN_MAC_DINH + 1),
    "0" * 30 + str(TRAN_THAN_MAC_DINH + 1),
    "9" * 5000,
    "1" + "0" * len(str(TRAN_THAN_MAC_DINH)),
]


@pytest.mark.parametrize("cl", DO_DAI_QUA_TRAN_CA, ids=lambda s: f"{len(s)}-chu-so")
def test_content_length_hop_le_qua_tran_413(cl):
    ma, ra, da_doc = _goi_asgi(app, "POST", "/tools/vat", b"{}", {"content-length": cl})
    assert ma == 413, (ma, ra[:120])
    assert da_doc == 0


def test_content_length_so_0_dau_trong_tran_di_qua():
    than = json.dumps(THAN_VAT, ensure_ascii=False).encode()
    ma, ra, _ = _goi_asgi(app, "POST", "/tools/vat", than,
                          {"content-type": "application/json", "content-length": "000" + str(len(than))})
    assert ma == 200 and json.loads(ra)["calculated_total"] == 2_200_000


@pytest.mark.parametrize("dai,mong", [
    ("10", "trong_tran"), ("11", "qua_tran"), ("0", "trong_tran"), ("000", "trong_tran"), ("0010", "trong_tran"),
    ("0011", "qua_tran"), ("100", "qua_tran"), ("9" * 5000, "qua_tran"), ("²", "sai"), ("", "sai"), ("1_0", "sai"),
])
def test_phan_loai_do_dai_bien(dai, mong):
    """Biên của hàm phân loại với trần 10: ngay trần, trên trần một đơn vị, số 0 ở đầu, chuỗi rất dài."""
    assert phan_loai_do_dai(dai, 10) == mong


# ---------------------------------------------------------------------------
# Dưới trần: không đổi gì
# ---------------------------------------------------------------------------

THAN_VAT = {"items": [{"name": "Hàng A", "price": 1_000_000, "qty": 2, "is_reduced_vat": False}],
            "prices_include_vat": False, "stated_total": 2_200_000}


def test_duoi_tran_di_qua_nguyen_ven():
    than = json.dumps(THAN_VAT, ensure_ascii=False).encode()
    ma, ra, da_doc = _goi_asgi(app, "POST", "/tools/vat", than,
                               {"content-type": "application/json", "content-length": str(len(than))})
    assert ma == 200 and json.loads(ra)["calculated_total"] == 2_200_000
    assert da_doc == len(than)


def test_duoi_tran_chunked_di_qua_nguyen_ven():
    than = json.dumps(THAN_VAT, ensure_ascii=False).encode()
    ma, ra, _ = _goi_asgi(app, "POST", "/tools/vat", than, {"content-type": "application/json"})
    assert ma == 200 and json.loads(ra)["calculated_total"] == 2_200_000


def test_health_khong_bi_anh_huong():
    assert TestClient(app).get("/health").status_code == 200


# ---------------------------------------------------------------------------
# /chat: message cùng trần với mỗi tin của history
# ---------------------------------------------------------------------------

def test_chat_message_qua_tran_422():
    r = TestClient(app).post("/chat", json={"user_id": 1, "store_id": 1, "message": "x" * (LICH_SU_TOI_DA_KY_TU + 1)})
    assert r.status_code == 422, r.text[:200]
    assert r.json()["detail"][0]["loc"] == ["body", "message"]


def test_chat_message_dung_tran_van_nhan():
    r = TestClient(app).post("/chat", json={"user_id": 1, "store_id": 1, "message": "x" * LICH_SU_TOI_DA_KY_TU})
    assert r.status_code == 200, r.text[:200]


def test_message_nhan_hom_nay_gui_lai_trong_history_khong_422():
    """Lý do của trần: tin vừa được nhận sẽ quay lại trong `history` ở lượt sau, và history có trần riêng."""
    tin = "x" * LICH_SU_TOI_DA_KY_TU
    r = TestClient(app).post("/chat", json={"user_id": 1, "store_id": 1, "message": "tiếp",
                                            "history": [{"role": "user", "content": tin}]})
    assert r.status_code == 200, r.text[:200]


# ---------------------------------------------------------------------------
# Middleware đơn lẻ: các nhánh khó tạo bằng app thật
# ---------------------------------------------------------------------------

def test_tran_khong_hop_le():
    with pytest.raises(ValueError):
        GioiHanThanMiddleware(app=None, tran=0)


def test_ung_dung_nem_loi_sau_khi_bi_cat_van_413():
    """Ứng dụng không bọc lỗi đọc thân mà để nó bay ra: vẫn 413, không 500."""
    async def ung_dung(scope, receive, send):
        while (await receive()).get("more_body"):
            pass
        raise AssertionError("không được tới đây")

    ma, _, _ = _goi_asgi(GioiHanThanMiddleware(ung_dung, tran=10), "POST", "/x", b"a" * 1000, {})
    assert ma == 413


def test_ung_dung_bat_loi_roi_tra_400_bi_thay_bang_413():
    """Đúng hành vi FastAPI: lỗi đọc thân bị bọc thành 400. Phản hồi đó phải thành 413."""
    async def ung_dung(scope, receive, send):
        try:
            while (await receive()).get("more_body"):
                pass
        except Exception:
            await send({"type": "http.response.start", "status": 400, "headers": []})
            await send({"type": "http.response.body", "body": b"loi doc than"})
            return

    ma, ra, _ = _goi_asgi(GioiHanThanMiddleware(ung_dung, tran=10), "POST", "/x", b"a" * 1000, {})
    assert ma == 413 and b"Payload Too Large" in ra


def test_loi_khong_lien_quan_toi_tran_van_bay_ra():
    """Không nuốt lỗi thật của ứng dụng (AGENTS.md §4.1 quy tắc 4)."""
    async def ung_dung(scope, receive, send):
        raise KeyError("loi that")

    with pytest.raises(KeyError):
        _goi_asgi(GioiHanThanMiddleware(ung_dung, tran=10), "POST", "/x", b"a", {})


def test_khong_phai_http_di_thang():
    goi = []

    async def ung_dung(scope, receive, send):
        goi.append(scope["type"])

    asyncio.run(GioiHanThanMiddleware(ung_dung)({"type": "lifespan"}, None, None))
    assert goi == ["lifespan"]
