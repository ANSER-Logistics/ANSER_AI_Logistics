"""
src/api/routes/chat.py — Chat endpoint và task polling.

Bản Ngày 7. Thay đổi so với bản cũ:

1. Ba nhánh GENERAL / RETRIEVAL / DATA_INTERNAL không còn dùng chung
   `manager.consult()`. Mỗi nhánh gọi method riêng với prompt riêng.
   Đây là fix cho lỗi model lặp vô hạn bảng "4 loại giao thức".

2. Nhánh TECHNICAL validate JSON TRƯỚC KHI trả về. Nếu model sinh JSON hỏng
   (ngoặc lệch, expression sai) thì retry 1 lần với feedback cụ thể; vẫn hỏng
   thì trả thông báo tiếng Việt thay vì đẩy rác xuống Body.

3. Log kèm score/margin của router để đo chất lượng định tuyến.

Ghi chú: nhánh FINANCIAL đã gỡ — validate hoá đơn đi qua /ocr (documents.py).
"""

import asyncio
import json
import logging
import os
import time
import unicodedata
import uuid
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from src.agents.coder import loi_lan_truoc
from src.api.chay_ngoai_loop import chay_ngoai_loop, chay_tren_kho
from src.api.dependencies import (
    ChatRequest,
    clean_output,
    extract_user_content,
    require_api_token,
    resolve_identity,
    runtime,
    web_search_fallback,
)
from src.core import llm_suc_khoe, metrics
from src.core.config import AI_NOTICE, MAX_HISTORY_TURNS, Config
from src.core.doc_dau_vao import noi_tra_loi_hoi_thue
from src.core.engine import TASK_REGISTRY
from src.core.grounding import LOI_SUY_BIEN, guard_answer, kiem_suy_bien
from src.core.retrieval_policy import KHONG_CO_TAI_LIEU, decide_web_fallback
from src.core.schemas import RetailChatResponse
from src.core.serving import DemSinh
from src.core.tool_planner import plan_tools, vao_vong_agentic
from src.core.utils import extract_json_block, loai_loi
from src.core.workflow_schema import sua_lien_ket_noop, validate_workflow

logger = logging.getLogger("projecta.api.chat")

router = APIRouter()

# SaasAPI singleton nhẹ (tạo engine 1 lần) — dùng cho route DATA_INTERNAL
_saas = None

# Thông báo khi không sinh nổi workflow hợp lệ
_WORKFLOW_FAILED_MSG = (
    "Tôi chưa dựng được quy trình hợp lệ cho yêu cầu này. "
    "Bạn mô tả rõ hơn giúp tôi 3 điểm: chạy vào lúc nào, "
    "lấy dữ liệu từ đâu, và gửi kết quả đi đâu."
)


def _get_saas():
    global _saas
    if _saas is None:
        from src.core.saas_api import SaasAPI
        _saas = SaasAPI()
    return _saas


def _kb_workspace() -> str:
    """
    Khoá phạm vi kho tri thức — CỐ TÌNH không phải `store_id`.

    Hợp đồng và bảng giá cước là của cả công ty. Lấy kho đang chọn làm khoá thì
    tài liệu nạp lúc đứng ở kho A trở nên vô hình khi hỏi lúc đứng ở kho B, mà
    biểu hiện duy nhất là "không tìm thấy" — không lỗi, không cảnh báo.
    """
    return Config().kb_workspace_id


def _canh_bao_lech_pham_vi(kb_ws: str, request_id: str) -> None:
    """
    Tra không ra gì mà kho lại CÓ tài liệu dưới phạm vi khác -> nói to lên.

    Đây đúng là kiểu hỏng không để lại dấu vết: khách nạp 30 tài liệu, giao diện
    hiện đủ 30, chat vẫn trả lời "chưa tìm thấy tài liệu nào". Không lỗi, không
    ngoại lệ, chỉ là hai bên dùng hai khoá khác nhau. Một dòng log ở đây biến
    nhiều ngày mò mẫm thành một câu trả lời.
    """
    kb = getattr(runtime, "kb", None)
    liet_ke = getattr(kb, "workspaces", None)
    if not callable(liet_ke):
        return
    try:
        khac = [w for w in liet_ke() if w != kb_ws]
    except Exception:
        # Hàm này tồn tại để biến một lỗi lệch phạm vi không dấu vết thành một dòng
        # log (xem docstring). Chính nó hỏng mà im lặng thì chỉ chuyển chỗ giấu.
        logger.warning(
            "Không liệt kê được phạm vi của kho tri thức để chẩn đoán lệch phạm vi: %s",
            loai_loi(),
        )
        return
    if khac:
        logger.warning(
            "Kho tri thức KHÔNG có tài liệu nào dưới phạm vi %r, nhưng có dưới %s. "
            "Đường nạp và đường tra đang dùng hai khoá khác nhau — kiểm tra "
            "KB_WORKSPACE_ID (Brain) và BRAIN_KB_WORKSPACE (Body).",
            kb_ws, khac,
            extra={"request_id": request_id},
        )


def _load_history(user_id) -> list[dict]:
    """
    Lịch sử hội thoại của user, dạng messages.

    Suy giảm mềm: chưa nối DB hoặc DB lỗi thì trả [] — Brain vẫn trả lời được,
    chỉ mất ngữ cảnh. Không bao giờ để việc đọc lịch sử làm hỏng một câu hỏi.
    """
    memory = getattr(runtime, "memory", None)
    if memory is None or not hasattr(memory, "get_history_messages"):
        return []
    try:
        return memory.get_history_messages(user_id)
    except Exception:
        logger.warning("Không đọc được lịch sử hội thoại: %s", loai_loi())
        return []


def _lich_su_tu_request(req) -> Optional[list[dict]]:
    """
    Lịch sử do Body gửi kèm, dạng messages, chỉ `MAX_HISTORY_TURNS` tin GẦN NHẤT.

    `None` = Body không gửi (Body cũ) -> chỗ gọi lùi về DB. `[]` = Body gửi và đây là lượt đầu -> không
    đọc DB. Lược đồ đã kiểm vai (chỉ user/assistant) và độ dài, nên ở đây chỉ cắt và đổi dạng. Nội dung
    KHÔNG ghi log (dữ liệu khách, R2).
    """
    if req.history is None:
        return None
    tin = [{"role": m.role, "content": m.content} for m in req.history]
    return tin[-MAX_HISTORY_TURNS:]


def _save_turn(user_id, store_id, user_msg: str, answer: str) -> None:
    """Lưu lượt vừa xong để lượt sau có ngữ cảnh. Lỗi lưu không làm hỏng câu trả lời."""
    memory = getattr(runtime, "memory", None)
    if memory is None or not hasattr(memory, "add_message"):
        return
    try:
        memory.add_message(user_id, store_id, "user", user_msg)
        memory.add_message(user_id, store_id, "assistant", answer)
    except Exception:
        logger.warning("Không lưu được lượt hội thoại: %s", loai_loi())


# Hàm THUẦN, đã chuyển sang `src/core/utils.py` (03/08/2026). Giữ alias để 5 chỗ
# gọi trong file này không phải sửa.
#
# Vì sao chuyển: `agents/agentic.py` phải import ngược lên module route này chỉ
# để dùng nó — một hàm đếm ngoặc trên chuỗi, chẳng liên quan gì HTTP. Import đặt
# trong thân hàm nên né được vòng lặp import và KHÔNG AI THẤY GÌ.
_extract_json_block = extract_json_block


# Validate workflow nay nằm ở src/core/workflow_schema.py — NGUỒN SỰ THẬT DUY NHẤT
# dùng chung với prompt CoderAgent và JSON Schema của guided decoding.
#
# Bản cũ định nghĩa lại luật ngay tại đây và kiểm theo "edges" + "id", trong khi
# prompt dạy n8n và dữ liệu train lại là Make.com — ba định dạng mâu thuẫn
# (ARCHITECTURE.md §11.1). Xoá bản sao ở đây là một phần của việc sửa lỗi đó.
_validate_workflow = validate_workflow


def _sua_noop(obj, request_id: str):
    """
    Bỏ liên kết tới node `noOp` không tồn tại (xem `workflow_schema.sua_lien_ket_noop`) TRƯỚC khi kiểm. Ghi nhật ký số liên kết đã bỏ;
    KHÔNG ghi tên node hay nội dung (có thể là chữ của người dùng).
    """
    moi, da_bo = sua_lien_ket_noop(obj)
    if da_bo:
        logger.info("Workflow: bỏ %d liên kết tới node noOp không tồn tại", len(da_bo), extra={"request_id": request_id})
    return moi


async def _fetch_report_lines(store_id, request_id: str):
    """
    Dòng bán hàng + chi phí THÔ từ hệ thống bán hàng.

    Trả (sales, expenses, thông_báo_lỗi). Tách riêng khỏi `_build_report_context`
    vì vòng agentic cần chính những dòng thô này làm `arguments` cho tool
    `report`, còn nhánh REPORT cần bản đã tính. Một nguồn, hai chỗ dùng (P4).
    """
    saas = _get_saas()
    fetch = getattr(saas, "get_report_lines", None)
    if fetch is None:
        return None, None, (
            "Tôi chưa nối được với dữ liệu bán hàng để dựng báo cáo. "
            "Cần bên hệ thống bán hàng mở API xuất dòng bán + chi phí theo kỳ "
            "(hoặc đưa file MISA xuất ra) thì tôi tính được ngay."
        )
    try:
        raw = fetch(workspace_id=store_id) or {}
        sales = list(raw.get("sales") or [])
        expenses = list(raw.get("expenses") or [])
    except Exception:
        logger.warning(
            "REPORT: không lấy được dữ liệu: %s", loai_loi(),
            extra={"request_id": request_id},
        )
        return None, None, (
            "Tôi chưa lấy được số liệu bán hàng để dựng báo cáo. "
            "Thử lại sau ít phút hoặc báo quản trị viên kiểm tra kết nối."
        )

    if not sales:
        return None, None, (
            "Chưa có dòng bán hàng nào trong dữ liệu nên tôi chưa dựng được "
            "báo cáo. Kiểm tra giúp tôi kỳ cần xem đã có dữ liệu chưa."
        )
    return sales, expenses, None


async def _build_report_context(store_id, request_id: str):
    """
    Lấy số liệu bán hàng/chi phí rồi cho engine TẤT ĐỊNH tính (P1).

    Trả (context_json, thông_báo_lỗi). Chưa nối được nguồn dữ liệu thì trả
    thông báo thay vì để model bịa một báo cáo nghe hợp lý — báo cáo tài chính
    sai mà trông bình thường là loại lỗi không ai phát hiện tới lúc quyết toán.
    """
    from src.core import reporting as rp

    sales, expenses, err = await _fetch_report_lines(store_id, request_id)
    if err:
        return None, err

    report = rp.build_report(rp.ReportRequest(
        sales=[rp.SaleLine(**s) for s in sales],
        expenses=[rp.ExpenseLine(**e) for e in expenses],
    ))
    return json.dumps(report, ensure_ascii=False), None


# Tool cần dữ liệu hệ thống mà hiện chưa có nguồn. Câu chữ nói rõ NGƯỜI DÙNG
# phải làm gì, không phải "lỗi hệ thống" — với khách 4-5 người thì việc cần làm
# thường là xuất một file từ phần mềm kế toán rồi tải lên.
_CHUA_CO_NGUON = {
    "inventory_audit": (
        "Tôi chưa có bảng tổng hợp tồn kho để soi. Bạn xuất bảng Tổng hợp "
        "Nhập-Xuất-Tồn từ phần mềm kế toán (MISA/Fast/Bravo) ra file Excel rồi "
        "tải lên mục Tồn kho — tôi soi ngay và chỉ ra từng dòng nghi sai."
    ),
    "forecast_reorder": (
        "Tôi chưa có lịch sử bán theo kỳ của mặt hàng nên chưa dự báo được. "
        "Cần số lượng bán từng tháng của ít nhất 6 tháng gần đây, kèm tồn hiện "
        "tại và thời gian đặt hàng về, thì tôi tính được điểm cần đặt lại."
    ),
    "carrier_selection": (
        "Tôi chưa có danh sách nhà xe kèm giá chào cho chuyến này. Bạn cho tôi "
        "biết các nhà xe đang cân nhắc và giá mỗi bên báo, tôi xếp hạng theo "
        "giá, khoảng cách bãi, công nợ, tỷ lệ đúng hẹn."
    ),
    "partner_audit": (
        "Tôi chưa có danh sách công nợ để soi. Bạn xuất Danh sách khách hàng "
        "(và Danh sách nhà cung cấp) từ phần mềm kế toán ra file Excel rồi tải "
        "lên — tôi chỉ ra ngay khách nào đang giữ nhiều tiền nhất, chỗ nào số dư "
        "ngược dấu, và đối tác nào vừa mua vừa bán để bù trừ được."
    ),
    "vat_catalog_audit": (
        "Tôi chưa có danh mục hàng hoá để đối chiếu thuế suất. Bạn xuất Danh "
        "sách hàng hóa, dịch vụ từ phần mềm kế toán ra file Excel rồi tải lên — "
        "tôi soát từng mã xem đang để 8% hay 10% có khớp Nghị định 174/2025 không."
    ),
}


async def _provide_tool_data(
    name: str, args: dict, store_id, request_id: str, user_msg: str = "", history=None
):
    """
    Bơm dữ liệu hệ thống vào `arguments` TRƯỚC khi tool chạy.

    Trả (arguments, thiếu_gì|None). Đây là hàng rào chống bịa DỮ LIỆU ĐẦU VÀO:
    chốt chặn neo số liệu chỉ soi được câu trả lời so với kết quả tool, nên nếu
    model tự nghĩ ra doanh thu rồi đưa vào tool, mọi con số sau đó đều "có
    nguồn" và đi lọt hết. Ghi đè, không hợp nhất — số của model không được
    quyền sống sót cạnh số thật.

    Với tool lấy số từ CHÍNH CÂU NGƯỜI DÙNG (`vat`, `quote`, `carrier_selection`),
    nguồn thật là câu đó — xem `src/core/doc_dau_vao.py` (chốt 28/10/2026):
      - `vat`: hoá đơn dán có cấu trúc thì mã bóc dòng hàng, ghi đè `items` (B);
        rồi A hai chiều: mọi số tiền trong câu phải có trong tham số, và mọi số
        tiền model điền phải có trong câu; cuối cùng giá đã gồm VAT hay chưa do
        mã đọc từ câu — không nói rõ thì hỏi lại.
      - `quote`: A hai chiều.
      - `carrier_selection`: mã bóc các lời chào giá trong câu thành
        `carriers`/`offers`; không bóc được >= 2 lời chào thì hỏi lại như cũ.
    """
    from src.core import doc_dau_vao as ddv

    if name == "report":
        sales, expenses, err = await _fetch_report_lines(store_id, request_id)
        if err:
            return args, err
        return {**args, "sales": sales, "expenses": expenses}, None

    # vat / quote / carrier_selection: đầu vào lấy từ câu người dùng. Logic nằm
    # ở `doc_dau_vao.chot_dau_vao` — benchmark gọi đúng hàm này.
    args, hoi_lai, ly_do = ddv.chot_dau_vao(name, args, user_msg, history=history)
    if ly_do == "boc_loi_chao":
        logger.info(
            "carrier_selection: bóc %d lời chào từ câu người dùng",
            len(args["offers"]), extra={"request_id": request_id},
        )
        return args, None
    if hoi_lai:
        logger.warning(
            "%s: chốt đầu vào hỏi lại (%s)", name, ly_do,
            extra={"request_id": request_id},
        )
        return args, hoi_lai

    thieu = _CHUA_CO_NGUON.get(name)
    if thieu:
        return args, thieu

    return args, None


async def _run_agentic(user_msg, plan, store_id, history, request_id, metric, dem: DemSinh):
    """
    Vòng agentic với TOOL ĐÃ ĐƯỢC CHỌN SẴN bằng luật.

    Trả (câu_trả_lời, dữ_liệu_neo). Dữ liệu neo là kết quả tool — mọi con số
    trong câu trả lời phải có ở đó, và chốt chặn ở cuối `process_chat` kiểm
    đúng điều đó. Số token của mọi lần gọi model trong vòng cộng vào `dem`.
    """
    from src.agents.agentic import AgenticLoop
    from src.api.routes.tools import get_tool_defs, run_tool

    async def provider(ten: str, args: dict):
        return await _provide_tool_data(ten, args, store_id, request_id, user_msg, history)

    out = await AgenticLoop(
        runtime.manager,
        get_tool_defs(),
        run_tool,
        planner=lambda q, names: list(plan),
        data_provider=provider,
    ).run(user_msg, history=history)

    dem_vong = out.get("dem_sinh")
    if isinstance(dem_vong, DemSinh):
        dem.gop(dem_vong)
    metric.tool_calls = out.get("tool_calls")
    metric.tool_plan = ",".join(plan)
    metric.asked_back = bool(out.get("data_missing"))
    logger.info(
        "Agentic: kế hoạch=%s, đã gọi %s tool, chạm trần=%s",
        plan, out.get("tool_calls"), out.get("hit_limit"),
        extra={"request_id": request_id},
    )

    quan_sat = out.get("observations") or []
    neo = json.dumps(quan_sat, ensure_ascii=False, default=str) if quan_sat else ""
    return out["answer"], neo


# Khoá nhận biết một lượt cũ có khối giải thích được. Engine nào cũng trả
# `explain`/`warnings`, nên tìm theo cấu trúc thay vì đoán theo câu chữ.
_EXPLAINABLE_KEYS = ("explain", "ranked", "internal", "periods", "warnings")


def _find_explainable(history: Optional[list]) -> Optional[str]:
    """
    Tìm khối kết quả engine gần nhất trong lịch sử để giải thích.

    Chỉ nhận JSON có cấu trúc của engine — không nhận văn xuôi, vì giải thích
    dựa trên văn xuôi của chính model là bịa lý do cho một kết luận đã bịa.
    """
    for item in reversed(history or []):
        if item.get("role") != "assistant":
            continue
        obj, _err = _extract_json_block(item.get("content", ""))
        if isinstance(obj, dict) and any(k in obj for k in _EXPLAINABLE_KEYS):
            # P2: khối `internal` chứa biên lợi nhuận — giải thích cho CHỦ DN
            # thì được, nhưng không để nó lọt vào ngữ cảnh nào khác.
            return json.dumps(obj, ensure_ascii=False)
    return None


_N8N_LOI_TOI_DA = 500
_N8N_BUOC_TOI_DA = 40


def _lam_sach_chuoi_ngoai(x: Any, toi_da: int) -> str:
    """
    Chuỗi từ ngoài tiến trình thành một dòng hiển thị được. Không phải `str` thì rỗng. Cắt TRƯỚC khi duyệt (một chuỗi vài chục
    triệu ký tự không được tốn CPU của một lượt chat), rồi bỏ ký tự thuộc nhóm Cc/Cf/Cs/Co (điều khiển, định dạng như đảo chiều
    chữ, thay thế, dùng riêng) và gộp mọi khoảng trắng. Lấy dư gấp bốn lần giới hạn để khoảng trắng bị gộp không làm hụt nội dung.
    """
    if not isinstance(x, str):
        return ""
    dong = "".join(" " if c.isspace() else c
                   for c in x[: toi_da * 4]
                   if c.isspace() or unicodedata.category(c) not in ("Cc", "Cf", "Cs", "Co"))
    return " ".join(dong.split())[:toi_da]


def _loi_tu_n8n(body: Any) -> Optional[tuple[str, str]]:
    """
    `(bước, lý do)` khi n8n trả phản hồi lỗi `{ok: false, stage, error}`; None nếu phản hồi không có dạng đó.

    Nhánh lỗi của luồng báo giá (`workflows/logistics/`) trả HTTP 200 kèm `ok: false` và lời của Brain trong
    `error` (cố ý 200: 4xx/5xx làm Brain nói "lỗi kết nối n8n", sai). Trước #80 chat.py chỉ xét `draft_id`, nên
    luôn khuyên "kiểm tra danh sách nháp" dù n8n đã nói rõ vì sao không có nháp (Sơn chạy thật trên n8n 2.48.5,
    18/11/2026). Chuỗi này đến từ bên ngoài tiến trình: CHỈ nhận kiểu chuỗi (dict hay số bị in dạng Python là vô nghĩa với
    người đọc, nên coi như không có lý do), bỏ ký tự điều khiển và ký tự định dạng (ESC, đảo chiều chữ), gộp khoảng trắng,
    cắt độ dài.
    """
    if not isinstance(body, dict) or body.get("ok") is not False:
        return None
    ly_do = _lam_sach_chuoi_ngoai(body.get("error"), _N8N_LOI_TOI_DA)
    if not ly_do:
        return None
    return _lam_sach_chuoi_ngoai(body.get("stage"), _N8N_BUOC_TOI_DA), ly_do


async def _handle_logistics_quote(
    user_msg: str, request_id: str, history: Optional[list] = None,
    dem: Optional[DemSinh] = None,
) -> str:
    """
    Nhánh LOGISTICS: trích xuất -> kiểm tra đủ trường -> gọi webhook n8n.

    Thiết kế cho tình huống thật của khách: chủ DN nhắn khi ĐANG LÁI XE.
    Vì vậy mọi nhánh lỗi đều trả câu tiếng Việt ngắn, nói rõ cần bổ sung gì —
    không bao giờ trả stack trace hay im lặng.

    `history` cho phép câu nối tiếp: sau "báo giá HN đi Hải Phòng xe 5 tấn",
    câu "thế xe 3 tấn thì sao?" phải giữ lại tuyến từ lượt trước.
    """
    from src.api.dependencies import runtime
    from src.core.prompts import Prompts
    from src.core.schemas import QUOTE_REQUIRED_FIELDS, QuoteExtraction

    if runtime.manager is None:
        # Chỗ gọi duy nhất (`chat_endpoint`) đã chặn rồi, nên nhánh này không
        # chạy hôm nay. Viết ra vì hàm này là `async def` ở mức module — ai
        # cũng gọi được, và không có gì ép họ chặn trước. Trả câu tiếng Việt
        # ngắn, đúng khuôn mọi nhánh lỗi khác ở đây: chủ DN có thể đang lái xe.
        return ("Hệ thống AI chưa sẵn sàng nên tôi chưa báo giá được. "
                "Bạn thử lại sau ít phút giúp tôi.")

    # 1) Trích xuất (LLM, guided_json)
    #    Lịch sử phải được bọc y hệt lúc train (P4) — xem
    #    Prompts.format_extraction_history.
    raw = (dem or DemSinh()).cong(await runtime.manager.extract_quote_request(
        user_msg, history=Prompts.format_extraction_history(history)
    ))
    obj, err = _extract_json_block(raw)
    if obj is None:
        logger.warning(
            "LOGISTICS: không parse được trích xuất (%s)", err,
            extra={"request_id": request_id},
        )
        return (
            "Tôi chưa đọc được yêu cầu báo giá. Bạn nhắn giúp theo dạng: "
            "\"Báo giá xe 5 tấn từ [điểm lấy] đi [điểm giao], hàng [loại], "
            "ngày [ngày], gửi [email khách]\"."
        )

    try:
        extracted = QuoteExtraction(**obj)
    except Exception:
        logger.warning(
            "LOGISTICS: trích xuất sai schema: %s", loai_loi(),
            extra={"request_id": request_id},
        )
        return "Tôi chưa đọc được yêu cầu báo giá. Bạn mô tả lại tuyến, loại xe giúp tôi nhé."

    # 2) Đủ trường bắt buộc chưa? Thiếu thì HỎI, không đoán (P1).
    data = extracted.model_dump()
    missing = [label for f, label in QUOTE_REQUIRED_FIELDS.items() if not data.get(f)]
    if missing:
        return (
            "Để làm báo giá tôi cần thêm: " + ", ".join(missing) + ". "
            "Bạn bổ sung giúp nhé."
        )

    # 3) Kích hoạt workflow n8n
    webhook_url = os.getenv("N8N_QUOTE_WEBHOOK_URL", "").strip()
    if not webhook_url:
        logger.error(
            "LOGISTICS: chưa cấu hình N8N_QUOTE_WEBHOOK_URL",
            extra={"request_id": request_id},
        )
        return (
            "Hệ thống báo giá chưa được nối với n8n (thiếu N8N_QUOTE_WEBHOOK_URL). "
            "Báo quản trị viên cấu hình rồi thử lại."
        )

    try:
        from src.core.utils import HttpClientPool
        client = HttpClientPool.get_client()
        r = await client.post(webhook_url, json=data, timeout=30.0)
        r.raise_for_status()
        body = r.json()
        draft_id = body.get("draft_id") if isinstance(body, dict) else None
    except Exception:
        logger.error(
            "LOGISTICS: gọi webhook n8n thất bại: %s", loai_loi(),
            extra={"request_id": request_id},
        )
        return (
            "Tôi đã hiểu yêu cầu nhưng chưa kích hoạt được quy trình báo giá "
            "(lỗi kết nối n8n). Thử lại sau ít phút hoặc báo quản trị viên."
        )

    if not draft_id:
        loi = _loi_tu_n8n(body)
        if loi:
            # n8n NÓI RÕ vì sao không có nháp: chuyển lý do đó cho người hỏi thay vì bảo họ đi tìm một
            # nháp không tồn tại (#80). Chắc chắn là chưa tạo: n8n trả `ok: false`.
            buoc, ly_do = loi
            logger.warning(
                "LOGISTICS: n8n báo lỗi ở bước %r: %s", buoc, ly_do,
                extra={"request_id": request_id},
            )
            return (
                f"Chưa tạo được báo giá{f' (bước {buoc})' if buoc else ''}: {ly_do} "
                "Báo giá này chưa được tạo và chưa gửi khách. Sửa nguyên nhân rồi nhắn báo giá lại."
            )
        # n8n trả 200 nhưng không kèm mã nháp. Bản trước thay bằng "?" rồi vẫn nói
        # "Đã tạo nháp báo giá ?" — tuyên bố thành công mà không có gì để chỉ vào.
        # Không có mã thì không ai tìm lại được nháp, nên nói thật là chưa xác nhận.
        logger.error(
            "LOGISTICS: n8n trả thành công nhưng không có draft_id",
            extra={"request_id": request_id},
        )
        return (
            "Yêu cầu báo giá đã được gửi đi nhưng tôi chưa nhận được mã bản nháp "
            "từ hệ thống, nên chưa xác nhận được là đã tạo xong. Bạn kiểm tra danh "
            "sách nháp báo giá, hoặc báo quản trị viên kiểm tra quy trình n8n."
        )

    # Câu xác nhận dựng bằng hàm DÙNG CHUNG với dữ liệu train đa lượt (P4):
    # lượt assistant trong data chính là câu này, nên lịch sử lúc serve có đúng
    # hình dạng mà model đã học.
    return Prompts.format_quote_confirmation(data, draft_id)


@router.get("/api/v1/task/{task_id}")
async def get_task_status(task_id: str, x_user_id: Optional[str] = Header(None)):
    """
    Trạng thái + KẾT QUẢ của một lượt hỏi AI. Chỉ chủ của task đọc được.

    Endpoint này trả về CÂU TRẢ LỜI đầy đủ — với sản phẩm kế toán thì đó là tên
    khách, mã số thuế, số công nợ. Trước 15/08/2026 nó không kiểm gì cả: không
    token (nay đã có `auth_guard` ở tầng router), và không hỏi người đọc là ai.
    Body là hệ đa người dùng, nên một token chung không đủ tách hai kế toán.

    404 chứ không 403 khi sai chủ: 403 xác nhận task đó CÓ TỒN TẠI, tức là biến
    endpoint thành máy dò task id hợp lệ. Hai trường hợp phải trông y hệt nhau.

    ĐỔI HÀNH VI: client tạo task bằng định danh trong THÂN request rồi hỏi kết
    quả mà không kèm `X-User-Id` sẽ nhận 404. Body logistics đã gửi sẵn header
    này ở mọi lượt hỏi (`askBrain` truyền `identity` cho cả POST lẫn GET) nên
    không phải sửa gì; client nào còn đi đường cũ thì thêm đúng một header.
    """
    task = TASK_REGISTRY.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    chu = task.pop("_owner", None)
    if chu is not None and str(x_user_id) != chu:
        logger.warning(
            "Từ chối đọc task %s: người hỏi %r không phải chủ", task_id, x_user_id
        )
        raise HTTPException(status_code=404, detail="Task not found")

    task.pop("_created_at", None)
    return {**task, "ai_notice": AI_NOTICE} if task.get("status") == "completed" else task


# ---------------------------------------------------------------------------
# Gửi kết quả về Body (webhook)
# ---------------------------------------------------------------------------
#
# Trước 16/11/2026 đây là MỘT lần `client.post` rồi log "Webhook dispatched", với hai lỗi câm:
#   1. `httpx` không ném khi Body trả 401 hay 500. Mọi phản hồi HTTP đều được log là "đã gửi", kể cả
#      khi Body từ chối: kết quả mất mà log nói thành công.
#   2. Body khởi động lại (có chuyện, và lâu hơn một giây) hay quá tải thoáng qua thì lần gửi duy nhất
#      mất luôn kết quả.
#
# Giờ: lần đầu gửi NGAY trong luồng như cũ (đường thành công không đổi một nhịp nào); thất bại
# TẠM THỜI (lỗi mạng, hết giờ, 408, 429, 5xx) thì thử lại ở NỀN sau 1 giây rồi 4 giây, để tác vụ vẫn
# báo hoàn thành ngay và Body hỏi `GET /api/v1/task/{id}` vẫn lấy được kết quả. Lỗi 4xx khác (401, 403,
# 404, 422) KHÔNG thử lại: gửi lại cùng một thứ không làm nó hết sai, chỉ làm log ồn thêm.
#
# GIAO NHẬN "ÍT NHẤT MỘT LẦN": lần gửi đầu có thể đã tới Body nhưng phản hồi lạc mất (hết giờ), rồi lần
# thử lại gửi lần hai. Mỗi lần gửi mang header `X-Task-ID`; Body nên bỏ qua task_id đã nhận.
#
# Không bao giờ log `payload` (là câu trả lời cho khách), chỉ task_id, mã trạng thái và số lần thử.
_WEBHOOK_THU_LAI_SAU = (1.0, 4.0)
_WEBHOOK_MA_THU_LAI = frozenset({408, 429})


async def _ngu(giay: float) -> None:
    """Một chỗ để test thay: không ai muốn test đợi 5 giây thật."""
    await asyncio.sleep(giay)


async def _gui_mot_lan(client, url: str, payload: dict, headers: dict) -> tuple[bool, bool, str]:
    """Một lần gửi. Trả `(thanh_cong, nen_thu_lai, mo_ta)`."""
    try:
        r = await client.post(url, json=payload, headers=headers)
    except Exception:   # mạng, hết giờ, DNS: đều tạm thời; không ném ra ngoài
        # Chỉ ghi LOẠI lỗi (AGENTS §4.1 quy tắc 4): thông điệp của httpx có thể kèm URL, và không bao giờ
        # ghi `payload`, vì đó là câu trả lời cho khách.
        logger.warning("Webhook về Body: không gửi được (%s)", loai_loi())
        return False, True, f"{loai_loi()}"
    if r.status_code < 400:
        return True, False, f"HTTP {r.status_code}"
    return False, (r.status_code >= 500 or r.status_code in _WEBHOOK_MA_THU_LAI), f"HTTP {r.status_code}"


async def _thu_lai_webhook(client, url: str, payload: dict, headers: dict, task_id: str, mo_ta: str) -> bool:
    for i, cho in enumerate(_WEBHOOK_THU_LAI_SAU, start=2):
        await _ngu(cho)
        ok, thu_lai, mo_ta = await _gui_mot_lan(client, url, payload, headers)
        if ok:
            logger.info("Webhook về Body thành công ở lần thử %d, task %s", i, task_id)
            return True
        if not thu_lai:
            break
    logger.error(
        "Webhook về Body THẤT BẠI, task %s (%s). Kết quả vẫn lấy được qua GET /api/v1/task/%s",
        task_id, mo_ta, task_id,
    )
    return False


_WEBHOOK_NEN: set = set()   # giữ tham chiếu: asyncio chỉ giữ tham chiếu yếu tới tác vụ nền


async def _gui_webhook(client, url: str, payload: dict, headers: dict, task_id: str) -> bool:
    """
    Gửi lần đầu ngay; nếu thất bại tạm thời thì lên lịch thử lại ở nền. Trả kết quả của LẦN ĐẦU
    (True = Body đã nhận). Không bao giờ ném.
    """
    ok, thu_lai, mo_ta = await _gui_mot_lan(client, url, payload, headers)
    if ok:
        logger.info("Webhook dispatched for task %s", task_id)
        return True
    if not thu_lai:
        logger.error(
            "Webhook về Body bị TỪ CHỐI, task %s (%s), không thử lại. Kết quả vẫn lấy được qua GET /api/v1/task/%s",
            task_id, mo_ta, task_id,
        )
        return False
    logger.warning("Webhook về Body lỗi tạm thời, task %s (%s); sẽ thử lại ở nền", task_id, mo_ta)
    nen = asyncio.ensure_future(_thu_lai_webhook(client, url, payload, headers, task_id, mo_ta))
    _WEBHOOK_NEN.add(nen)
    nen.add_done_callback(_WEBHOOK_NEN.discard)
    return False



async def _phan_loai(manager, user_msg: str) -> dict:
    """
    Phân loại câu hỏi mà KHÔNG chặn event loop. Lớp embedding của router gọi `encode` (chặn, 83 đến 277 ms), và
    embedder đó dùng CHUNG với kho tri thức, nên chỗ chạy do `manager.cach_chay` quyết (lý do ở đó): ngay trên loop
    nếu chỉ là từ khoá, trên worker của kho nếu dùng chung embedder, thread pool mặc định nếu embedder riêng.

    Manager không có `phan_loai` (đồ giả trong test) thì giữ đường cũ `analyze_task`.
    """
    if not hasattr(manager, "phan_loai"):
        return await manager.analyze_task(user_msg)
    cach = manager.cach_chay(user_msg)
    if cach == "kho":
        return await chay_tren_kho(manager.phan_loai, user_msg)
    if cach == "ngoai_loop":
        return await chay_ngoai_loop(manager.phan_loai, user_msg)
    return manager.phan_loai(user_msg)


def _cach_phan_loai(manager, user_msg: str) -> Optional[str]:
    """Nơi `_phan_loai` sẽ chạy câu này ("ngay", "kho", "ngoai_loop"), cho số đo. None nếu manager không biết."""
    if not hasattr(manager, "cach_chay"):
        return None
    try:
        return manager.cach_chay(user_msg)
    except Exception:       # đo đạc hỏng không được làm hỏng nghiệp vụ
        logger.warning("Không xác định được nơi phân loại: %s", loai_loi())
        return None


def _webhook_headers(task_id: str, request_id: str = "") -> dict[str, str]:
    """
    Header cho webhook gọi về Body. KHÔNG bịa token khi chưa cấu hình.

    Bản trước truyền một chuỗi mặc định viết thẳng trong mã nguồn làm đối số
    thứ hai của `os.getenv("API_AUTH_TOKEN", ...)`. Ba chỗ sai trong một dòng:

    1. R2b.1 — credential hardcode trong mã nguồn, mà repo này công khai.
       Chuỗi đó ai cũng đọc được.
    2. Trái với quy ước của chính dự án: `require_api_token` coi
       `API_AUTH_TOKEN` rỗng là TẮT xác thực, còn ở đây rỗng lại thành "gửi
       đúng chuỗi này".
    3. Làm một cấu hình THIẾU trông như đã cấu hình xong. Body nhận một header
       đúng hình dạng; nếu Body cũng mặc định cùng chuỗi đó thì xác thực
       "qua" bằng một giá trị nằm trên GitHub. Nếu Body từ chối thì lỗi hiện
       ra là "token sai", không phải "Brain chưa có token".

    Chưa có token thì BỎ HẲN header và nói ra trong log. Mọi triển khai đúng
    đều có token (compose dùng `${API_TOKEN:?}`, tức thiếu là dựng không lên),
    nên ở đó hành vi KHÔNG đổi.

    Cân nhắc đã bỏ: dừng hẳn việc gửi khi không có token. An toàn hơn, nhưng
    làm mất kết quả Body đang chờ — đổi một lỗi cấu hình thành một lượt chat
    không có hồi đáp.

    Là hàm cấp module chứ không nằm trong closure của `chat_endpoint`, vì một
    luật bảo mật nằm trong closure thì không test được tại chỗ — và đường
    webhook này trước 04/11/2026 KHÔNG có test nào.

    Cố ý KHÔNG chép chuỗi mặc định cũ vào đây: để nguyên thì mọi lần quét bí
    mật sau này lại bắt được nó trong một chú thích. Xem `git log -S` nếu cần.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Task-ID": task_id,
    }
    api_token = os.getenv("API_AUTH_TOKEN", "").strip()
    if api_token:
        headers["X-Webhook-Token"] = api_token
    else:
        logger.warning(
            "Webhook gửi KHÔNG kèm token: API_AUTH_TOKEN chưa đặt",
            extra={"request_id": request_id},
        )
    return headers


@router.post("/chat")
async def chat_endpoint(
    req: ChatRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    x_api_token: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_store_id: Optional[str] = Header(None),
):
    require_api_token(x_api_token)
    if llm_suc_khoe.dang_hong():
        # GPU/vLLM mất: nói thẳng ngay thay vì nhận tác vụ rồi thất bại muộn. `/tools/*` không dùng model nên vẫn chạy (A21, #203).
        return JSONResponse(
            status_code=503, content={"error": "llm_unavailable", "detail": "Model ngôn ngữ đang không khả dụng.",
                                      "retry_after_s": int(llm_suc_khoe.THU_LAI_S)},
            headers={"Retry-After": str(int(llm_suc_khoe.THU_LAI_S))})
    user_id, store_id = resolve_identity(req, x_user_id, x_store_id)
    await runtime.ensure_text_runtime()
    # Kiểm cả `engine`, không chỉ `manager`/`coder`.
    #
    # `manager` chỉ được tạo khi `engine` tồn tại (`RuntimeState` dựng theo thứ
    # tự đó), nên chặn `manager` là ĐỦ về logic. Nhưng đó là một bất biến ngầm
    # nằm ở file khác: cuối hàm này dùng `runtime.engine.background_worker`, và
    # nếu ngày nào thứ tự dựng runtime đổi thì chỗ đó hỏng mà cổng chặn ở đây
    # vẫn cho qua.
    #
    # Viết ra thì tốn một phép kiểm luôn đúng, và đổi lại một lỗi lúc chạy
    # thành một lỗi lúc kiểm kiểu.
    if not runtime.engine or not runtime.manager or not runtime.coder:
        raise HTTPException(status_code=503, detail="Text runtime unavailable")

    user_msg = extract_user_content(req.message)
    request_id = request.state.request_id
    logger.info(
        "Chat request received",
        extra={"request_id": request_id, "user_id": user_id, "store_id": store_id},
    )

    task_id = str(uuid.uuid4())
    # Ghi chủ TRƯỚC khi chạy nền: worker ghi đè cả bản ghi ở mỗi chặng, nên chủ
    # phải có mặt từ đầu (TaskRegistry.set mang `_owner` theo qua các lần ghi).
    TASK_REGISTRY.set(task_id, {"status": "processing", "_owner": str(user_id)})

    async def process_chat():
        timer = metrics.Timer().__enter__()
        metric = metrics.TurnMetric(
            request_id=request_id, route="?", ok=False, latency_ms=0,
            user_id=user_id, store_id=store_id, message_chars=len(user_msg),
        )
        # Cộng số token của MỌI lần gọi model trong lượt này (#16). Một bộ đếm
        # riêng cho mỗi lượt — biến cục bộ của `process_chat`, không dùng chung.
        dem = DemSinh()

        # Lịch sử hội thoại — thiếu nó thì mọi tin nhắn là một phiên độc lập,
        # "thế xe 3 tấn thì sao?" không thể hiểu được.
        # Body gửi kèm `history` (BR-38, Body#28) thì dùng đúng nó và KHÔNG đọc DB: với DB thật của
        # Body sáu bảng lịch sử không tồn tại nên đọc ra rỗng. Body cũ không gửi thì lùi về đọc DB như
        # trước. Đọc DB nằm ngoài event loop (§4.1-2): `/health` và việc poll tác vụ không chờ SQL.
        history = _lich_su_tu_request(req)
        if history is None:
            history = await chay_ngoai_loop(_load_history, user_id)
        metric.history_turns = len(history)

        # Đo thời gian phân loại và nơi nó chạy (#85): câu cần embedding xếp hàng sau việc của kho, và chỉ
        # đo ngoài đời mới biết điều đó có làm người dùng chờ không.
        metric.router_cach = _cach_phan_loai(runtime.manager, user_msg)
        t_router = time.perf_counter()
        decision = await _phan_loai(runtime.manager, user_msg)
        metric.router_ms = int((time.perf_counter() - t_router) * 1000)
        cat = decision.get("category", "GENERAL")
        metric.route = cat
        metric.router_score = decision.get("score")
        metric.router_margin = decision.get("margin")
        metric.router_method = decision.get("method")
        logger.info(
            "Route selected: %s (score=%.2f margin=%.3f method=%s, history=%d lượt)",
            cat,
            decision.get("score", 0.0),
            decision.get("margin", 0.0),
            decision.get("method", "?"),
            len(history),
            extra={"request_id": request_id, "route": cat},
        )

        resp = ""
        # Dữ liệu TẤT ĐỊNH mà câu trả lời phải neo vào. Nhánh nào có thì gán;
        # rỗng nghĩa là không có gì để đối chiếu, và khi đó KHÔNG chặn.
        grounding_ctx = ""

        # ------------------------------------------------------------------
        # VÒNG AGENTIC — tool do LUẬT chọn, không phải model
        # ------------------------------------------------------------------
        # Chạy TRƯỚC bảng rẽ nhánh vì nó cắt ngang các nhánh cũ: "tháng này lãi
        # bao nhiêu, mặt hàng nào lãi nhất, có nên nhập thêm không" là ba bước
        # nối tiếp, kiến trúc một-lần-gọi của các nhánh dưới không làm được.
        #
        # LOGISTICS và TECHNICAL đứng ngoài: cả hai đã có luồng struct riêng
        # (trích xuất báo giá -> n8n; sinh workflow -> validate), đều tất định
        # và đều đang chạy được. Không đụng vào thứ đang chạy được.
        from src.api.routes.tools import get_tool_defs

        plan = plan_tools(user_msg, [t["name"] for t in get_tool_defs()])

        # Câu nào được vào vòng agentic và câu nào đi luồng riêng (LOGISTICS, TECHNICAL) do MỘT hàm quyết:
        # `tool_planner.vao_vong_agentic`, để bộ đo (`offline_training/do_nghiep_vu.py`) và chỗ này không
        # bao giờ lệch nhau. Lý do của ba ngoại lệ cho LOGISTICS nằm ở docstring của hàm đó.
        # Lượt trước Brain hỏi "giá đã gồm VAT chưa", lượt này người dùng trả
        # lời: ghép với tin nhắn hoá đơn trước đó và chạy lại `vat` — câu trả
        # lời trơn "chưa gồm VAT" tự nó không có kế hoạch nào.
        cau_noi_thue = noi_tra_loi_hoi_thue(user_msg, history)
        if cau_noi_thue:
            resp, grounding_ctx = await _run_agentic(
                cau_noi_thue, ["vat"], store_id, history, request_id, metric, dem
            )
        elif vao_vong_agentic(cat, plan, user_msg):
            resp, grounding_ctx = await _run_agentic(
                user_msg, plan, store_id, history, request_id, metric, dem
            )

        # ------------------------------------------------------------------
        # LOGISTICS — trích xuất yêu cầu báo giá -> kích hoạt workflow n8n
        # ------------------------------------------------------------------
        # Brain CHỈ làm: (1) tiếng Việt tự do -> struct có schema, (2) trả lời
        # xác nhận. Toàn bộ đọc Sheet + tính giá + nháp + duyệt nằm bên n8n +
        # /tools (luồng logistics_quote_request -> logistics_quote_approve).
        elif cat == "LOGISTICS":
            resp = await _handle_logistics_quote(user_msg, request_id, history=history, dem=dem)
            metric.asked_back = "tôi cần thêm" in resp.lower()

        # ------------------------------------------------------------------
        # TECHNICAL — sinh workflow n8n, validate trước khi trả
        # ------------------------------------------------------------------
        # ------------------------------------------------------------------
        # REPORT — báo cáo/phân tích nhiều kỳ, văn dài
        # ------------------------------------------------------------------
        # Số do engine tất định (reporting.build_report qua /tools/report) tính;
        # LLM chỉ diễn giải (P1). Dữ liệu bán hàng đến từ Body — chưa nối thì
        # nói thẳng là chưa có, KHÔNG bịa một báo cáo nghe hợp lý.
        elif cat == "REPORT":
            report_ctx, report_err = await _build_report_context(store_id, request_id)
            grounding_ctx = report_ctx or ""
            if report_err:
                resp = report_err
                metric.asked_back = True
            else:
                resp = dem.cong(await runtime.manager.answer_report(
                    user_msg, context=report_ctx, history=history
                ))

        # ------------------------------------------------------------------
        # EXPLAIN — xAI: giải thích kết quả vừa đưa ra
        # ------------------------------------------------------------------
        # Khối `explain` của lần tính gần nhất nằm trong lịch sử hội thoại.
        # Không có gì để giải thích thì nói rõ, không bịa lý do.
        elif cat == "EXPLAIN":
            explain_ctx = _find_explainable(history)
            if explain_ctx is None:
                resp = (
                    "Tôi chưa có kết quả nào gần đây để giải thích. "
                    "Bạn hỏi lại ngay sau khi tôi đưa ra báo giá, gợi ý hãng xe "
                    "hoặc báo cáo nhé — khi đó tôi nói rõ được từng yếu tố."
                )
                metric.asked_back = True
            else:
                grounding_ctx = explain_ctx
                resp = dem.cong(await runtime.manager.explain_result(
                    user_msg, context=explain_ctx, history=history
                ))

        elif cat == "TECHNICAL":
            # Tên riêng, KHÔNG dùng lại `plan`: ở trên `plan` là kế hoạch tool
            # (list[str]), còn đây là văn bản kế hoạch workflow model viết ra.
            ke_hoach_wf = dem.cong(await runtime.manager.plan_or_ask(req.message))

            if "[PLAN]" not in ke_hoach_wf:
                # Model hỏi lại cho rõ yêu cầu -> trả nguyên câu hỏi
                resp = clean_output(ke_hoach_wf)
                metric.asked_back = True
            else:
                raw = dem.cong(await runtime.coder.write_code(user_msg, ke_hoach_wf))
                obj, err = _extract_json_block(raw)
                obj = _sua_noop(obj, request_id)

                ok = False
                if obj is not None:
                    ok, err = _validate_workflow(obj)

                metric.workflow_retried = not ok
                if not ok:
                    # Retry đúng 1 lần, đưa lỗi cụ thể làm feedback
                    logger.warning(
                        "Workflow JSON không hợp lệ (%s) — thử lại",
                        err, extra={"request_id": request_id},
                    )
                    raw = dem.cong(await runtime.coder.write_code(
                        user_msg, ke_hoach_wf, feedback=loi_lan_truoc(err)))
                    obj, err = _extract_json_block(raw)
                    obj = _sua_noop(obj, request_id)
                    if obj is not None:
                        ok, err = _validate_workflow(obj)

                metric.workflow_valid = ok
                if ok:
                    # Trả JSON đã chuẩn hoá — Body parse chắc chắn được
                    resp = json.dumps(obj, ensure_ascii=False)
                    logger.info(
                        "Workflow hợp lệ: %d node",
                        len(obj["payload"]["nodes"]),
                        extra={"request_id": request_id},
                    )
                else:
                    logger.error(
                        "Workflow vẫn hỏng sau retry: %s",
                        err, extra={"request_id": request_id},
                    )
                    resp = _WORKFLOW_FAILED_MSG

        # ------------------------------------------------------------------
        # DATA_INTERNAL — dữ liệu thật từ DB cửa hàng
        # ------------------------------------------------------------------
        elif cat == "DATA_INTERNAL":
            saas = _get_saas()
            # Kỳ ĐỌC TỪ CÂU HỎI. Bản cũ đóng cứng "today": hỏi "tháng trước bán
            # được bao nhiêu" thì model chỉ nhận số HÔM NAY, và chốt chặn neo số
            # liệu không bắt được vì con số ấy có thật trong ngữ cảnh. Đúng số,
            # sai câu hỏi — không có triệu chứng nào (sửa 05/08/2026).
            from src.core.saas_api import parse_period

            ky = parse_period(user_msg)
            try:
                products = await chay_ngoai_loop(saas.lookup_product, user_msg, workspace_id=store_id)
                if ky.ho_tro:
                    sales = await chay_ngoai_loop(
                        saas.get_sales_report, workspace_id=store_id, period=ky.period
                    )
                    khoi_ban = (
                        f"[DOANH SỐ {ky.nhan.upper()}]\n"
                        f"{json.dumps(sales, ensure_ascii=False)}"
                    )
                else:
                    # KHÔNG đưa số hôm nay vào đây. Thiếu số thì model nói không
                    # biết; có số sai kỳ thì nó trả lời trôi chảy và sai.
                    khoi_ban = (
                        f"[DOANH SỐ {ky.nhan.upper()}]\n"
                        f"CHƯA LẤY ĐƯỢC — hệ thống mới truy vấn được hôm nay, "
                        f"tuần này và tháng này. Nói rõ điều này với người dùng "
                        f"và mời họ hỏi lại theo một trong ba kỳ đó."
                    )
                    metric.asked_back = True
                db_context = f"[SẢN PHẨM KHỚP TRUY VẤN]\n{products}\n\n{khoi_ban}"
            except Exception:
                logger.warning(
                    "Truy vấn DB thất bại: %s", loai_loi(),
                    extra={"request_id": request_id},
                )
                db_context = "(không lấy được dữ liệu từ cơ sở dữ liệu)"

            grounding_ctx = db_context
            resp = dem.cong(await runtime.manager.answer_data(
                user_msg, context=db_context, history=history
            ))

        # ------------------------------------------------------------------
        # RETRIEVAL — RAG tài liệu nội bộ, fallback web
        # ------------------------------------------------------------------
        elif cat == "RETRIEVAL":
            # Lời gọi cũ là `kb.search(user_msg, top_k=2)`, trong khi chữ ký là
            # `search(workspace_id, query, top_k)`. Nó ném TypeError, rơi đúng
            # vào `except Exception` ngay dưới, ghi một dòng warning rồi im lặng
            # nhảy sang tra web. Nghĩa là kho tài liệu CHƯA TỪNG được dùng ở
            # đường phục vụ, và không có triệu chứng nào ngoài "câu trả lời hơi
            # chung chung" (sửa 05/08/2026).
            context_docs = ""
            found_internal = False
            kb_ws = _kb_workspace()

            if runtime.kb:
                try:
                    passages = await chay_tren_kho(runtime.kb.search, kb_ws, user_msg, top_k=2)
                    if passages:
                        from src.core.knowledge import format_for_prompt
                        context_docs = f"[TÀI LIỆU NỘI BỘ]\n{format_for_prompt(passages)}"
                        found_internal = True
                        logger.info(
                            "Tìm thấy %d đoạn tài liệu nội bộ", len(passages),
                            extra={"request_id": request_id},
                        )
                    else:
                        await chay_tren_kho(_canh_bao_lech_pham_vi, kb_ws, request_id)
                except Exception:
                    logger.warning(
                        "KB search lỗi: %s", loai_loi(),
                        extra={"request_id": request_id},
                    )

            if not found_internal:
                # Không thấy trong tài liệu thì KHÔNG mặc nhiên tra web. Trả một
                # bài viết trên mạng cho câu "chính sách công nợ bên mình thế
                # nào" là loại sai tệ nhất: nghe hợp lý, không dấu hiệu nghi ngờ,
                # người đọc đang cần ra quyết định.
                quyet = decide_web_fallback(user_msg)
                metric.web_fallback = quyet.allow
                logger.info(
                    "RETRIEVAL: web=%s (%s)", quyet.allow, quyet.reason,
                    extra={"request_id": request_id},
                )
                if quyet.allow:
                    web_results = await chay_ngoai_loop(web_search_fallback, user_msg)
                    context_docs = (
                        f"[KẾT QUẢ TÌM KIẾM]\n{web_results}" if web_results else ""
                    )
                else:
                    # Câu tất định — đây là lúc hệ thống thú nhận không biết, và
                    # câu thú nhận đó không được nhờ model diễn đạt lại.
                    resp = KHONG_CO_TAI_LIEU
                    metric.asked_back = True

            if not resp:
                grounding_ctx = context_docs
                resp = dem.cong(await runtime.manager.answer_retrieval(
                    user_msg, context=context_docs, history=history
                ))

        # ------------------------------------------------------------------
        # GENERAL — hội thoại, giải thích (KHÔNG tính toán: câu có phép tính tiền/thuế
        # mà có luật tool thì đã đi vòng agentic ở trên; còn lại model từ chối tự tính)
        # ------------------------------------------------------------------
        else:
            resp = dem.cong(await runtime.manager.answer_general(user_msg, history=history))

        cleaned = clean_output(resp)

        # CHỐT CHẶN NEO SỐ LIỆU — chạy TRƯỚC khi câu trả lời ra ngoài.
        #
        # `narration_numbers_ok` đã tồn tại từ lâu và chạy ở hai chỗ: lọc dữ
        # liệu huấn luyện, và chấm điểm benchmark. Nhưng KHÔNG chạy ở chỗ thứ
        # ba, chỗ quan trọng nhất — lúc phục vụ. Nghĩa là ta đo được model bịa
        # số 8-10 ca trên 27, rồi vẫn để con số bịa đó đi thẳng ra màn hình chủ
        # doanh nghiệp (nối vào 05/08/2026).
        #
        # CHỈ chặn khi CÓ dữ liệu gốc để đối chiếu. Nhánh GENERAL và LOGISTICS
        # không có `grounding_ctx`; chặn ở đó là chặn oan mọi con số >= 4 chữ số,
        # kể cả số người dùng vừa tự nhắc trong câu hỏi.
        #
        # Chốt SUY BIẾN đứng trước (29/10/2026): rác tiếng Trung/lặp đuôi không
        # chứa số nên chốt số liệu cho qua, và nó xảy ra ở cả nhánh không có
        # `grounding_ctx`. TECHNICAL đứng ngoài — đầu ra là JSON workflow, đã có
        # validate riêng.
        ly_do_suy_bien = None if cat == "TECHNICAL" else kiem_suy_bien(cleaned)
        if ly_do_suy_bien:
            logger.warning(
                "Chặn câu trả lời suy biến (%s, %d ký tự)", ly_do_suy_bien, len(cleaned),
                extra={"request_id": request_id},
            )
            metric.blocked_reason = f"suy biến: {ly_do_suy_bien}"
            cleaned = LOI_SUY_BIEN
        elif grounding_ctx:
            verdict = guard_answer(cleaned, grounding_ctx)
            if verdict.blocked:
                logger.warning(
                    "Chặn câu trả lời (%s: %s)", verdict.reason, verdict.offending,
                    extra={"request_id": request_id},
                )
                metric.blocked_reason = verdict.reason
                cleaned = verdict.safe_answer


        # Lưu lượt để câu sau có ngữ cảnh + ghi nhật ký đo lường
        # PHẢI `await`, không ném vào nền: lượt sau đọc lại lịch sử, nên việc ghi phải xong
        # TRƯỚC khi tác vụ báo `completed` (ghi trước đọc). Chạy ngoài loop để SQL chậm không
        # giữ chân cả server.
        await chay_ngoai_loop(_save_turn, user_id, store_id, user_msg, cleaned)

        timer.__exit__(None, None, None)
        metric.latency_ms = timer.ms
        metric.answer_chars = len(cleaned)
        metric.ok = cleaned != _WORKFLOW_FAILED_MSG
        # Số token và thời gian gọi model của CẢ lượt (#16). None = không biết
        # (mock, hoặc có lần gọi server không trả `usage`) — không bao giờ 0.
        metric.completion_tokens = dem.completion_tokens
        metric.model_ms = dem.model_ms
        metric.model_calls = dem.so_lan or None
        metrics.record(metric)

        chat_response = RetailChatResponse(answer=cleaned, sources=None)

        # Proactive Webhook Dispatcher
        callback_url = os.getenv("BODY_CALLBACK_URL")
        if callback_url:
            try:
                from src.core.utils import HttpClientPool

                # Chỉ parse JSON nếu output THỰC SỰ là JSON (nhánh TECHNICAL).
                # Bản cũ repair_json mọi output, kể cả văn xuôi -> tạo rác.
                parsed, _ = _extract_json_block(cleaned)
                payload = {"task_id": task_id, "result": parsed or cleaned, "ai_notice": AI_NOTICE}

                headers = _webhook_headers(task_id, request_id)

                client = HttpClientPool.get_client()
                await _gui_webhook(client, callback_url, payload, headers, task_id)
            except Exception:
                logger.error("Webhook dispatch failed for task %s: %s", task_id, loai_loi())

        return chat_response.model_dump()

    background_tasks.add_task(runtime.engine.background_worker, task_id, process_chat)
    return {"task_id": task_id, "status": "processing"}
