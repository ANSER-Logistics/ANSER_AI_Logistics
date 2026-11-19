"""
tests/test_auth_bao_phu.py — KHÔNG endpoint nào được thoát khỏi cổng xác thực.

Ngày 15/08/2026, quét từng endpoint qua HTTP thật lộ ra hai chỗ mở công khai:

  GET /tools                  -> 16.623 byte lược đồ nội bộ của 8 tool
  GET /api/v1/task/{task_id}  -> CÂU TRẢ LỜI của AI: tên khách, MST, số công nợ

Hai mươi endpoint kia đều gọi `require_api_token` đúng, nên không có gì cho thấy
hai cái này sai. Đó là hình dạng của mọi lỗi bỏ sót: cái sai trông hệt cái đúng,
chỉ khác ở chỗ THIẾU một dòng — mà thiếu thì không ai in ra được.

826 test lúc đó chạy bằng TestClient trong tiến trình và không test nào đặt câu
hỏi "endpoint này có kiểm token không". Nên bộ này hỏi thẳng, và hỏi về TOÀN BỘ
bảng route chứ không về một danh sách viết tay — danh sách viết tay thì endpoint
thứ 24 lại rơi ra ngoài đúng như cũ.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from fastapi.testclient import TestClient  # noqa: E402

import src.api.dependencies as deps  # noqa: E402
import src.api.main as main_mod  # noqa: E402
from src.api.main import app  # noqa: E402
from tests.bang_route import bang_route

client = TestClient(app)

TOKEN_THU = "token-thu-cho-test"


@pytest.fixture(autouse=True)
def bat_xac_thuc(monkeypatch):
    """
    Bật xác thực CHỈ trong bộ này, bằng cách vá biến module chứ không đặt env.

    Bản đầu đặt `os.environ["API_AUTH_TOKEN"]` ở đầu file. Hỏng theo hai chiều
    ngược nhau, tuỳ thứ tự pytest nạp file:

      - File khác nạp `src.api.dependencies` TRƯỚC -> biến module đã tính xong
        từ env rỗng, gán env lúc này không tới được nó. Cổng không bật, cả bộ
        này đỏ.
      - Bộ này nạp trước -> env dính cho TOÀN BỘ phiên test, và 60 test khác
        (vốn không gửi token) nhận 401.

    Cả hai đều là một chuyện: `API_AUTH_TOKEN` đọc env MỘT LẦN lúc import. Nên
    thứ phải vá là biến module, và vá có phạm vi.

    `main` giữ bản sao riêng cho `/health`, phải vá cả hai.
    """
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", TOKEN_THU)
    monkeypatch.setattr(main_mod, "API_AUTH_TOKEN", TOKEN_THU)

# `/health` cố ý mở: nó là chỗ để biết Brain sống hay chết, và để nhìn
# `auth_enabled`. Người hỏi chưa có token vẫn phải nhận được câu trả lời đó.
MO_CO_Y = {"/health", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}


def _duong_di_thuc(path: str) -> str:
    """`/api/v1/task/{task_id}` -> `/api/v1/task/x`. Tham số nào cũng được."""
    import re
    return re.sub(r"\{[^}]+\}", "x", path)


def moi_endpoint():
    """Lấy từ `tests/bang_route.py`, không duyệt `app.routes` (#30: FastAPI ≥0.162 ra 0)."""
    for method, path in bang_route(app):
        if path not in MO_CO_Y:
            yield pytest.param(method, path, id=f"{method} {path}")


def test_bang_route_khong_rong():
    """Chốt chống xanh suông cho HAI test parametrize ngay dưới.

    `parametrize` trên danh sách rỗng không đỏ — nó sinh một ca SKIP
    ("got empty parameter set"), và `pytest -q` không in lý do skip. Đo
    10/11/2026: FastAPI 0.162.2 gói route của `include_router` vào
    `_IncludedRouter` thay vì trải ra `app.routes`, nên `moi_endpoint()` ra rỗng
    và cả 46 ca kiểm token biến mất trong im lặng. Cổng token vẫn chặn đúng —
    chỉ là không còn gì chứng minh điều đó.

    Ngưỡng 20, không phải con số chính xác: thêm hay bớt một endpoint không được
    làm test này đỏ; chỉ mất GẦN HẾT bảng route mới đỏ. Từ #30 bảng lấy từ
    `app.openapi()` (xem `tests/bang_route.py`), nên đỏ ở đây thì xem cách FastAPI
    dựng OpenAPI trước khi nghi code.
    """
    so = len(list(moi_endpoint()))
    assert so >= 20, (
        f"chỉ thấy {so} endpoint trong bảng route — bảng route bị đổi hình dạng "
        f"(thường do nâng FastAPI), hai test kiểm token dưới đây đang không kiểm gì."
    )


def test_khong_route_nao_an_khoi_openapi():
    """Cái giá của việc lấy bảng route từ `openapi()` (#30), và chốt chặn nó.

    Route khai `include_in_schema=False` không có trong OpenAPI, nên sẽ không nằm
    trong hai test kiểm token dưới đây: đúng loại endpoint "ẩn" mà bộ này dựng ra
    để bắt. Hôm nay `src/` không có chỗ nào khai thế (đo 20/11/2026). Ai cần ẩn một
    route khỏi tài liệu thì phải thêm nó vào bộ kiểm token bằng cách khác trước.
    """
    goc = pathlib.Path(__file__).resolve().parent.parent / "src"
    co = [
        f"{f.relative_to(goc.parent)}:{i}"
        for f in sorted(goc.rglob("*.py"))
        for i, dong in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"include_in_schema\s*=\s*False", dong)
    ]
    assert not co, f"route ẩn khỏi OpenAPI sẽ lọt khỏi bộ kiểm token: {co}"


@pytest.mark.parametrize("method,path", list(moi_endpoint()))
def test_moi_endpoint_deu_chan_khi_khong_co_token(method, path):
    """
    KHÔNG token -> 401. Không phải 422, không phải 200.

    422 cũng là trượt: nó nghĩa là FastAPI đã validate thân request TRƯỚC khi
    kiểm token, nên người chưa xác thực đọc được tên từng trường bắt buộc trong
    thông báo lỗi. Dò được lược đồ mà không cần token.
    """
    resp = client.request(method, _duong_di_thuc(path), json={}, headers={})
    assert resp.status_code == 401, (
        f"{method} {path} trả {resp.status_code} thay vì 401.\n"
        f"  200 = endpoint mở công khai.\n"
        f"  422 = validate thân request chạy trước kiểm token (lộ lược đồ).\n"
        f"  Cổng nằm ở `auth_guard` gắn lúc include_router trong src/api/main.py."
    )


@pytest.mark.parametrize("method,path", list(moi_endpoint()))
def test_token_sai_cung_bi_chan(method, path):
    resp = client.request(method, _duong_di_thuc(path), json={},
                          headers={"X-API-Token": "khong-phai-token-that"})
    assert resp.status_code == 401, f"{method} {path} nhận token SAI mà vẫn cho qua"


def test_health_van_mo_de_biet_brain_song_hay_chet():
    """Đóng /health lại là tự bịt mắt: không token thì không biết Brain ra sao."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["auth_enabled"] is True, (
        "API_AUTH_TOKEN có đặt mà /health báo auth_enabled=False — "
        "đúng tín hiệu dựng ra để phát hiện Brain mở toang lúc triển khai."
    )


def test_health_noi_that_khi_KHONG_co_token(monkeypatch):
    """`auth_enabled=False` phải nói ra được, nếu không tín hiệu này vô dụng."""
    monkeypatch.setattr(deps, "API_AUTH_TOKEN", "")
    monkeypatch.setattr(main_mod, "API_AUTH_TOKEN", "")
    assert client.get("/health").json()["auth_enabled"] is False
