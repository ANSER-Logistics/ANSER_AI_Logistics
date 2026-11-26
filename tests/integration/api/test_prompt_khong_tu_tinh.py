"""
tests/integration/api/test_prompt_khong_tu_tinh.py — GENERAL và RETRIEVAL không được dạy model tính.

VÌ SAO CÓ FILE NÀY
------------------
AGENTS.md R1: "LLM không bao giờ tính toán". Nhưng hai prompt trả lời tự do lại
viết ngược lại, nguyên văn:

    GENERAL_SYSTEM    "Có phép tính thì tính ra kết quả cụ thể và ghi rõ cách tính."
    RETRIEVAL_SYSTEM  "Có phép tính thì tính ra con số cụ thể, ghi rõ công thức."

Mọi nơi khác trong repo đều đúng R1 — AGENT_SYSTEM ("TUYỆT ĐỐI không tự tính
số"), REPORT_SYSTEM ("Không tự cộng trừ ra số mới"), EXPLAIN_SYSTEM ("Không tự
tính lại"). Hai prompt này là chỗ duy nhất bảo model làm điều R1 cấm, và chúng là
đường mà câu hỏi tiền/thuế rơi vào khi không luật nào của `tool_planner` khớp.

Con số tiền sai mà nghe có vẻ đúng là loại lỗi tệ nhất: không ai phát hiện tới
lúc quyết toán. Nên nội dung hai prompt được khoá bằng test — sửa lại thành lời
dạy tính là đỏ.

CHÚ Ý "ĐỪNG HỨA THỨ HỆ THỐNG KHÔNG LÀM". Prompt bảo model "nói cần dùng công cụ
tính" — nhưng ở nhánh GENERAL/RETRIEVAL KHÔNG có công cụ nào chạy: `chat.py` tính
`plan_tools(...)` TRƯỚC bảng rẽ nhánh, và câu nào có kế hoạch tool thì đi vòng
agentic, không bao giờ tới `answer_general`/`answer_retrieval`. Hai test cuối khoá
đúng mối nối đó để lời trong prompt ("lượt này bạn không có công cụ") còn là sự
thật.
"""

from __future__ import annotations

import re

import pytest

from src.agents.manager import ManagerAgent
from src.core import prompts as prompts_mod
from src.core.prompts import Prompts
from src.core.tool_planner import plan_tools

# Hai nhánh trả lời tự do mà model nhìn thấy câu hỏi tiền/thuế thô.
NHANH_TU_DO = ["GENERAL_SYSTEM", "RETRIEVAL_SYSTEM"]

# Những lời dạy TÍNH. Viết theo ý (cụm động từ + đối tượng), không theo từng chữ
# của bản cũ, để diễn đạt lại bằng câu khác mà vẫn bảo model tính thì vẫn đỏ.
LOI_DAY_TINH = [
    r"có phép tính thì",
    r"tính ra",
    r"ghi rõ (cách tính|công thức)",
    r"(hãy|cần|phải)\s+tính\b(?!\s+toán lại)",
]

# Lời HỨA chạy công cụ — thứ hai nhánh này không làm được.
LOI_HUA_CONG_CU = r"(sẽ|đang|đã|để (tôi|mình))\s+(gọi|chạy|dùng|bật|dùng đến)\s+công cụ"


def _prompt_da_render(ten: str) -> str:
    """Prompt đúng như model nhận: RETRIEVAL có {context} phải được format."""
    return getattr(Prompts, ten).replace("{context}", "(ngữ cảnh thử)")


@pytest.mark.parametrize("ten", NHANH_TU_DO)
def test_prompt_khong_bao_model_tinh(ten):
    """R1: không câu nào trong prompt được bảo model tính ra kết quả."""
    van_ban = _prompt_da_render(ten).lower()
    for mau in LOI_DAY_TINH:
        khop = re.search(mau, van_ban)
        assert not khop, (
            f"{ten} còn lời dạy model tính ({khop.group(0)!r}) — vi phạm R1 "
            f"(LLM không bao giờ tính toán)"
        )


@pytest.mark.parametrize("ten", NHANH_TU_DO)
def test_prompt_co_chi_dan_tu_choi_tu_tinh(ten):
    """Phải có chiều ngược lại: nói rõ không tự tính, cần công cụ, hỏi lại dữ kiện."""
    van_ban = _prompt_da_render(ten)
    thap = van_ban.lower()
    assert "không tự tính" in thap, f"{ten} không dặn model KHÔNG tự tính"
    assert "công cụ" in thap, f"{ten} không nói phép tính phải do công cụ làm"
    assert "hỏi lại" in thap, f"{ten} không dặn hỏi lại dữ kiện còn thiếu"
    # Hỏi lại cái gì: ba dữ kiện mà `vat` đòi — không có chúng thì không tính được.
    assert "số tiền" in thap
    assert "thuế suất" in thap


@pytest.mark.parametrize("ten", NHANH_TU_DO)
def test_prompt_khong_hua_chay_cong_cu(ten):
    """Hai nhánh này không có công cụ nào chạy — prompt không được hứa có."""
    van_ban = _prompt_da_render(ten).lower()
    khop = re.search(LOI_HUA_CONG_CU, van_ban)
    assert not khop, f"{ten} hứa chạy công cụ ({khop.group(0)!r}) — nhánh này không chạy"
    assert "không có công cụ" in van_ban, (
        f"{ten} không nói thật rằng lượt này không có công cụ"
    )


def test_mot_dinh_nghia_dung_chung_cho_hai_nhanh():
    """R4: luật 'không tự tính' có MỘT nguồn; hai prompt chỉ nhúng nó vào."""
    luat = prompts_mod._KHONG_TU_TINH
    assert luat.strip()
    assert luat in Prompts.GENERAL_SYSTEM
    assert luat in Prompts.RETRIEVAL_SYSTEM
    # RETRIEVAL_SYSTEM đi qua str.format(context=...): dấu ngoặc nhọn lạc trong
    # luật dùng chung sẽ làm KeyError ngay lúc phục vụ, không phải lúc import.
    assert "{" not in luat and "}" not in luat


def test_retrieval_van_format_duoc_va_giu_nguyen_ngu_canh():
    """Nhúng luật chung không được làm vỡ chỗ giữ chỗ {context} của RAG."""
    ra = Prompts.RETRIEVAL_SYSTEM.format(context="ĐOẠN TÀI LIỆU THỬ 123")
    assert ra.count("ĐOẠN TÀI LIỆU THỬ 123") == 1
    assert ra.rstrip().endswith("ĐOẠN TÀI LIỆU THỬ 123")
    # Câu mở đầu giữ nguyên: preflight_check nhận nhánh của một mẫu train bằng
    # 60 ký tự đầu của prompt — đổi chúng là mọi mẫu cũ thành "không nhận ra".
    assert Prompts.GENERAL_SYSTEM.startswith(
        "Bạn là ANSER Brain — trợ lý cho chủ cửa hàng bán lẻ Việt Nam."
    )
    assert Prompts.RETRIEVAL_SYSTEM.startswith(
        "Bạn là ANSER Brain — chuyên gia thuế GTGT, kho vận và vận hành bán lẻ"
    )


# ---------------------------------------------------------------------------
# Mối nối: prompt đi đúng từ ManagerAgent xuống model
# ---------------------------------------------------------------------------

class _EngineGia:
    def __init__(self):
        self.systems: list[str] = []

    async def generate_chat(self, system, user, max_tokens, temperature, **kw):
        self.systems.append(system)
        return "ok"


def _manager_gia() -> tuple[ManagerAgent, _EngineGia]:
    engine = _EngineGia()
    m = ManagerAgent.__new__(ManagerAgent)   # bỏ SemanticRouter: không cần ở đây
    m.engine = engine
    m.name = "manager"
    m.kb = None
    return m, engine


@pytest.mark.asyncio
async def test_manager_dua_luat_khong_tu_tinh_xuong_model():
    """Đường thật `answer_general` / `answer_retrieval` mang luật tới model."""
    m, engine = _manager_gia()
    await m.answer_general("Tính giúp tôi tổng tiền thuế")
    await m.answer_retrieval("Tính giúp tôi tổng tiền thuế", context="TÀI LIỆU A")
    assert len(engine.systems) == 2
    for system in engine.systems:
        assert "KHÔNG TỰ TÍNH" in system
        assert "Có phép tính thì" not in system
    assert "TÀI LIỆU A" in engine.systems[1]


# ---------------------------------------------------------------------------
# Lời "lượt này không có công cụ" phải là sự thật
# ---------------------------------------------------------------------------

TOOL_MANIFEST = ["vat", "report", "quote", "carrier_selection", "inventory_audit",
                 "forecast_reorder", "partner_audit", "vat_catalog_audit"]


def test_cau_co_luat_tool_thi_khong_toi_nhanh_tu_do():
    """Câu thuế CÓ số tiền có kế hoạch tool -> vòng agentic, không phải GENERAL."""
    assert plan_tools("Hàng 3 triệu chưa gồm VAT, tính thuế GTGT 10% giúp tôi",
                      TOOL_MANIFEST) == ["vat"]


@pytest.mark.parametrize("cau", [
    "Mua 3 cái giá 120.000 đồng chiết khấu 5% thì tổng bao nhiêu?",   # số học thuần
    "Giá bán 2 triệu cộng 10% thì thành bao nhiêu?",                  # không từ khoá thuế
    "Tính giúp tôi tổng tiền thuế",                                   # thiếu số tiền
])
def test_cau_tinh_tien_khong_co_luat_tool_roi_vao_nhanh_tu_do(cau):
    """
    Đây chính là những câu mà luật 'không tự tính' sinh ra để xử: không có tool
    nào chạy, nên nếu prompt bảo model tính thì model tính thật.
    """
    assert plan_tools(cau, TOOL_MANIFEST) == []


class _ManagerGhiNhanh:
    """Manager giả ghi lại nhánh nào được gọi — để chứng minh thứ tự trong chat.py."""

    def __init__(self, category: str):
        self.category = category
        self.da_goi: list[str] = []
        self.decisions: list[dict] = []

    async def analyze_task(self, text):
        return {"category": self.category, "score": 1.0, "margin": 1.0, "method": "test"}

    async def answer_general(self, task, history=None):
        self.da_goi.append("answer_general")
        return "Trả lời tự do."

    async def answer_retrieval(self, task, context="", history=None):
        self.da_goi.append("answer_retrieval")
        return "Trả lời từ tài liệu."

    async def answer_data(self, task, context="", history=None):
        self.da_goi.append("answer_data")
        return "Trả lời từ dữ liệu."

    async def generate_chat(self, system, user, **kwargs):
        import json
        self.da_goi.append("generate_chat")
        return json.dumps(self.decisions.pop(0), ensure_ascii=False)


@pytest.fixture
def chay_chat(monkeypatch):
    """Dựng runtime tối thiểu (không GPU) rồi trả hàm gửi một câu vào /chat."""
    from fastapi.testclient import TestClient

    from src.api import dependencies as deps
    from src.api.main import app
    from src.core.engine import ModelEngine

    client = TestClient(app)

    async def khong_lam_gi():
        return None

    def dung(manager: _ManagerGhiNhanh):
        monkeypatch.setattr(deps.runtime, "ensure_text_runtime", khong_lam_gi)
        monkeypatch.setattr(deps.runtime, "manager", manager, raising=False)
        monkeypatch.setattr(deps.runtime, "coder", object(), raising=False)
        monkeypatch.setattr(deps.runtime, "memory", None, raising=False)
        monkeypatch.setattr(deps.runtime, "kb", None, raising=False)
        monkeypatch.setattr(deps.runtime, "engine",
                            ModelEngine.__new__(ModelEngine), raising=False)

        def hoi(cau: str) -> str:
            ai = {"X-User-Id": "1", "X-Store-Id": "1"}
            r = client.post("/chat", headers=ai,
                            json={"user_id": 1, "store_id": 1, "message": cau})
            assert r.status_code == 200
            kq = client.get(f"/api/v1/task/{r.json()['task_id']}", headers=ai).json()
            assert kq["status"] == "completed", kq
            return kq["result"]["answer"]

        return hoi

    return dung


def test_chat_cau_thue_co_so_tien_chay_tool_chu_khong_roi_vao_general(chay_chat):
    """Router xếp GENERAL, nhưng kế hoạch tool có `vat` -> tool chạy, GENERAL không."""
    manager = _ManagerGhiNhanh("GENERAL")
    manager.decisions = [
        {"thought": "tính thuế", "tool": "vat",
         "arguments": {"items": [{"name": "Hàng", "price": 3000000, "qty": 1}],
                       "prices_include_vat": False}},
        {"thought": "đã có số", "answer": "Đã tính bằng công cụ."},
    ]
    hoi = chay_chat(manager)

    hoi("Hàng 3 triệu chưa gồm VAT, tính thuế GTGT 10% giúp tôi")

    assert "answer_general" not in manager.da_goi
    assert manager.decisions == [], "vòng agentic phải thực sự chạy"


def test_chat_cau_so_hoc_khong_luat_tool_roi_vao_general_khong_chay_tool(chay_chat):
    """
    Câu số học thuần: không tool nào chạy, nhánh GENERAL trả lời một mình. Đó là
    lý do prompt GENERAL phải nói thật "lượt này bạn không có công cụ".
    """
    manager = _ManagerGhiNhanh("GENERAL")
    hoi = chay_chat(manager)

    hoi("Mua 3 cái giá 120.000 đồng chiết khấu 5% thì tổng bao nhiêu?")

    assert manager.da_goi == ["answer_general"]
