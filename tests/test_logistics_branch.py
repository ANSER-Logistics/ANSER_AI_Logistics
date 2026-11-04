"""
tests/test_logistics_branch.py — nhánh LOGISTICS: router, trích xuất, webhook.

Chạy ở ENV=LOCAL (không cần GPU): router lớp từ khoá + mock engine.
"""

import json

import pytest

from src.agents.manager import SemanticRouter
from src.core.schemas import QUOTE_REQUIRED_FIELDS, QuoteExtraction

# ===========================================================================
# Router — câu logistics phải vào đúng nhánh ngay từ lớp từ khoá
# ===========================================================================

# Chế độ từ khoá, ÉP TƯỜNG MINH. Chú thích cũ ghi "ENV dev không có torch nên
# chạy chế độ từ khoá" — đúng trên máy CI, sai trên máy có torch: ở đó test này
# âm thầm kiểm đường ngữ nghĩa thay vì đường từ khoá mà tiêu đề mục nói tới.
ROUTER = SemanticRouter(tu_nap_embedder=False)


@pytest.mark.parametrize("query", [
    "báo giá xe 5 tấn từ Hữu Nghị đi Hải Phòng",
    "cho anh giá cước chuyến hàng lạnh đi Bắc Giang",
    "cần một đầu kéo đi Hải Phòng thứ 3 tuần sau",
    "khách hỏi thuê xe 3 tấn đi Bắc Ninh ngày mai",
    "giá cước tuyến Hà Nội - Hải Phòng giờ bao nhiêu",
])
def test_router_keyword_hits_logistics(query):
    out = ROUTER.route_with_score(query)
    assert out["route"] == "LOGISTICS", f"{query!r} -> {out}"
    assert out["method"] == "keyword"


@pytest.mark.parametrize("query,expected", [
    # "tạo quy trình" vẫn phải vào TECHNICAL dù nói về báo cáo
    ("tạo quy trình tự động gửi báo cáo doanh số mỗi tối", "TECHNICAL"),
    # thuế vẫn vào RETRIEVAL
    ("thuế GTGT 8% tính thế nào", "RETRIEVAL"),
])
def test_logistics_rule_does_not_steal_other_routes(query, expected):
    assert ROUTER.route_with_score(query)["route"] == expected


# ===========================================================================
# Schema trích xuất
# ===========================================================================

def test_quote_extraction_schema_all_optional():
    """Guided_json cần mọi field nullable — model không bị ép đoán trường thiếu."""
    q = QuoteExtraction()   # không trường nào -> vẫn hợp lệ
    assert q.origin is None

    schema = QuoteExtraction.model_json_schema()
    assert set(QUOTE_REQUIRED_FIELDS) <= set(schema["properties"])


def test_quote_required_fields_have_vietnamese_labels():
    """Nhãn tiếng Việt dùng để HỎI LẠI người dùng — phải có đủ."""
    for field, label in QUOTE_REQUIRED_FIELDS.items():
        assert label and not label.isascii(), f"{field} thiếu nhãn tiếng Việt"


# ===========================================================================
# _handle_logistics_quote — các nhánh phản hồi
# ===========================================================================

@pytest.mark.asyncio
async def test_missing_fields_asks_back(monkeypatch):
    """Trích xuất thiếu trường bắt buộc -> hỏi lại, nêu ĐÚNG tên trường thiếu."""
    from src.api.routes import chat as chat_mod

    async def fake_extract(msg, history=None):
        return json.dumps({"origin": "Hữu Nghị", "destination": None,
                           "vehicle_type": "5T"})

    class FakeManager:
        extract_quote_request = staticmethod(fake_extract)

    monkeypatch.setattr(chat_mod, "runtime", None, raising=False)  # không dùng module-level
    from src.api import dependencies
    monkeypatch.setattr(dependencies.runtime, "manager", FakeManager())

    out = await chat_mod._handle_logistics_quote("...", "req-test")
    assert "điểm giao hàng" in out
    assert "điểm lấy hàng" not in out          # trường đã có thì không đòi


@pytest.mark.asyncio
async def test_webhook_not_configured_message(monkeypatch):
    """Đủ trường nhưng chưa cấu hình webhook -> báo rõ, không nuốt lỗi."""
    from src.api import dependencies
    from src.api.routes import chat as chat_mod

    async def fake_extract(msg, history=None):
        return json.dumps({"origin": "Hữu Nghị", "destination": "Hải Phòng",
                           "vehicle_type": "5T"})

    class FakeManager:
        extract_quote_request = staticmethod(fake_extract)

    monkeypatch.setattr(dependencies.runtime, "manager", FakeManager())
    monkeypatch.delenv("N8N_QUOTE_WEBHOOK_URL", raising=False)

    out = await chat_mod._handle_logistics_quote("...", "req-test")
    assert "N8N_QUOTE_WEBHOOK_URL" in out


@pytest.mark.asyncio
async def test_unparseable_extraction_gives_guidance(monkeypatch):
    """Model trả rác (LOCAL mock) -> hướng dẫn định dạng, không stack trace."""
    from src.api import dependencies
    from src.api.routes import chat as chat_mod

    async def fake_extract(msg, history=None):
        return "xin lỗi tôi không hiểu"

    class FakeManager:
        extract_quote_request = staticmethod(fake_extract)

    monkeypatch.setattr(dependencies.runtime, "manager", FakeManager())
    out = await chat_mod._handle_logistics_quote("...", "req-test")
    assert "Báo giá xe 5 tấn" in out           # câu mẫu hướng dẫn


@pytest.mark.asyncio
async def test_happy_path_calls_webhook(monkeypatch):
    """Đủ trường + webhook cấu hình -> POST đúng payload, trả draft_id."""
    from src.api import dependencies
    from src.api.routes import chat as chat_mod
    from src.core import utils as utils_mod

    async def fake_extract(msg, history=None):
        return json.dumps({
            "origin": "Hữu Nghị", "destination": "Hải Phòng",
            "vehicle_type": "5T", "cargo_type": "Hàng lạnh",
            "pickup_date": "2026-07-29",
            "customer_name": "Anh Tuấn", "customer_email": "tuan@minhlong.vn",
        })

    class FakeManager:
        extract_quote_request = staticmethod(fake_extract)

    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass
        def json(self):
            return {"ok": True, "draft_id": "QD-TEST-01"}

    class FakeClient:
        async def post(self, url, json=None, timeout=None):
            captured["url"] = url
            captured["payload"] = json
            return FakeResp()

    monkeypatch.setattr(dependencies.runtime, "manager", FakeManager())
    monkeypatch.setenv("N8N_QUOTE_WEBHOOK_URL", "http://n8n.local/webhook/logistics-quote")
    monkeypatch.setattr(utils_mod.HttpClientPool, "get_client", staticmethod(lambda: FakeClient()))

    out = await chat_mod._handle_logistics_quote("báo giá...", "req-test")

    assert captured["url"].endswith("/logistics-quote")
    assert captured["payload"]["vehicle_type"] == "5T"
    assert captured["payload"]["customer_email"] == "tuan@minhlong.vn"
    assert "QD-TEST-01" in out
    assert "duyệt" in out                       # nhắc rõ luồng nháp -> duyệt


# ===========================================================================
# Workflow JSON hợp lệ về cấu trúc n8n
# ===========================================================================

def test_logistics_workflows_are_valid_n8n_structure():
    """4 file JSON phải parse được và connections chỉ trỏ tới node có thật."""
    from pathlib import Path
    wdir = Path("workflows/logistics")
    files = sorted(wdir.glob("*.json"))
    assert len(files) == 4

    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        names = {n["name"] for n in data["nodes"]}
        assert len(names) == len(data["nodes"]), f"{f.name}: trùng tên node"
        for n in data["nodes"]:
            assert isinstance(n.get("typeVersion"), (int, float)), f"{f.name}/{n['name']}"
            assert isinstance(n.get("position"), list) and len(n["position"]) == 2
        for src, outs in data["connections"].items():
            assert src in names, f"{f.name}: connections từ node lạ {src!r}"
            for branch in outs["main"]:
                for link in branch:
                    assert link["node"] in names, (
                        f"{f.name}: {src} trỏ tới node lạ {link['node']!r}"
                    )


# ---------------------------------------------------------------------------
# Webhook gọi về Body — header xác thực (R2b)
# ---------------------------------------------------------------------------
# Đường `BODY_CALLBACK_URL` trong `chat_endpoint` trước 04/11/2026 KHÔNG có test
# nào, và nó bịa một token: `os.getenv("API_AUTH_TOKEN", <chuỗi viết sẵn>)`.
#
# Logic đó nằm trong closure của `chat_endpoint` nên không test được tại chỗ —
# đã tách thành `_webhook_headers()` ở cấp module. Một luật bảo mật nằm trong
# closure là một luật không ai kiểm được.


def test_webhook_khong_bia_token_khi_chua_cau_hinh(monkeypatch):
    """Chưa đặt `API_AUTH_TOKEN` -> KHÔNG có header token, không phải token bịa.

    Quy ước của chính dự án: `require_api_token` coi rỗng là TẮT xác thực. Gửi
    một chuỗi mặc định viết sẵn trong mã nguồn làm một cấu hình THIẾU trông như
    đã cấu hình xong — và chuỗi đó nằm trong một repo công khai.
    """
    from src.api.routes import chat as chat_mod

    monkeypatch.delenv("API_AUTH_TOKEN", raising=False)
    h = chat_mod._webhook_headers("task-1", "req-1")

    assert "X-Webhook-Token" not in h
    assert h["X-Task-ID"] == "task-1"
    assert h["Content-Type"] == "application/json"


def test_webhook_khong_bia_token_khi_dat_chuoi_rong(monkeypatch):
    """Đặt rỗng (hoặc toàn khoảng trắng) cũng là CHƯA cấu hình.

    `API_AUTH_TOKEN=` trong .env là cách người ta tắt xác thực, và
    `.env.example` ghi đúng như vậy. Không `.strip()` thì một dòng
    `API_AUTH_TOKEN= ` (lỡ thừa dấu cách) biến thành một token bằng ký tự trắng.
    """
    from src.api.routes import chat as chat_mod

    for gia_tri in ("", "   ", "\t"):
        monkeypatch.setenv("API_AUTH_TOKEN", gia_tri)
        assert "X-Webhook-Token" not in chat_mod._webhook_headers("t", "r")


def test_webhook_gui_dung_token_khi_da_cau_hinh(monkeypatch):
    """Đã đặt token -> gửi NGUYÊN VĂN. Đây là trạng thái của mọi triển khai đúng.

    Compose dùng `${API_TOKEN:?}`, tức thiếu là `docker compose up` chết ngay —
    nên ở môi trường thật nhánh này luôn chạy, và hành vi không đổi so với bản
    trước.
    """
    from src.api.routes import chat as chat_mod

    monkeypatch.setenv("API_AUTH_TOKEN", "  abc123  ")
    h = chat_mod._webhook_headers("task-9")

    assert h["X-Webhook-Token"] == "abc123"       # cắt khoảng trắng hai đầu
    assert h["X-Task-ID"] == "task-9"


def test_webhook_khong_con_chuoi_mac_dinh_nao_trong_ma_nguon():
    """Chốt chặn thẳng vào mã nguồn: `getenv` của token xác thực không được có
    đối số thứ hai khác rỗng.

    Phép kiểm hành vi ở trên đỏ nếu ai sửa `_webhook_headers`; test này đỏ nếu
    có ai thêm lại một mặc định ở MỘT CHỖ KHÁC trong repo — `chat.py` không phải
    nơi duy nhất đọc biến này.
    """
    import ast
    import pathlib
    import re

    goc = pathlib.Path(__file__).resolve().parent.parent / "src"
    xau = []
    for p in goc.rglob("*.py"):
        nguon = p.read_text(encoding="utf-8")

        # BỎ MỌI DOCSTRING rồi mới soi. Lần đầu viết test này nó ĐỎ, và thứ nó
        # bắt được là docstring của `_webhook_headers` — chỗ cố ý nhắc lại lời
        # gọi `getenv` cũ để giải thích vì sao không được làm thế. Chốt chặn bắt
        # nhầm chính lời cảnh báo của nó.
        #
        # Đúng cái bẫy đã ghi sẵn ở test_agent_middleware.py::
        # test_khong_dinh_nghia_lai_gi_trong_file_nay. Chú thích `#` không nằm
        # trong AST nên tự khắc được loại.
        try:
            cay = ast.parse(nguon)
        except SyntaxError:          # không chặn cả bộ vì một file lỗi cú pháp
            continue
        for nut in ast.walk(cay):
            if isinstance(nut, (ast.Module, ast.ClassDef,
                                ast.FunctionDef, ast.AsyncFunctionDef)):
                tai_lieu = ast.get_docstring(nut, clean=False)
                if tai_lieu:
                    nguon = nguon.replace(tai_lieu, "")

        mau = re.compile(r"""getenv\(\s*["']API_AUTH_TOKEN["']\s*,\s*([^)]*)\)""")
        for m in mau.finditer(nguon):
            mac_dinh = m.group(1).strip()
            if mac_dinh not in ('""', "''"):
                xau.append(f"{p.name}: mặc định {mac_dinh}")

    assert not xau, (
        f"token xác thực có mặc định viết sẵn trong mã nguồn: {xau}. "
        f"Rỗng nghĩa là CHƯA cấu hình, không phải 'dùng chuỗi này'."
    )
