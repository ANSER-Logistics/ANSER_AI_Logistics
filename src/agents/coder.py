"""
src/agents/coder.py — sinh workflow n8n.

BẢN 27/07/2026. Thay đổi so với bản Ngày 7:

  - Định dạng đích là n8n THẬT ("connections" khoá theo tên node), không phải
    "edges" như bản cũ. Workflow bản cũ sinh ra KHÔNG import vào n8n được.
  - Bật guided decoding: output bị ép khớp JSON Schema ở tầng sampling, nên JSON
    sai cấu trúc là bất khả thi. Vòng retry vì thế chỉ còn để bắt lỗi NGHIỆP VỤ
    (thiếu trigger, node mồ côi, SQL ghi dữ liệu), không còn để bắt lỗi cú pháp.
  - Danh mục node + few-shot lấy từ workflow_schema (rút từ template n8n THẬT của
    Body khi có N8N_TEMPLATES_DIR) thay vì hardcode ở đây.
  - max_new_tokens 1200 -> 1600: workflow n8n thật dài hơn dạng "edges" rút gọn vì
    có connections đầy đủ và typeVersion từng node.
"""

from src.agents.base import BaseAgent
from src.core.agent_middleware import AgentMiddleware
from src.core.prompts import Prompts

# Trần token sinh workflow. Hằng số chứ không phải số viết tại chỗ:
# `offline_training/benchmark_v3.py` import chính biến này làm mặc định (P4).
#
# 1600 -> 2048 (15/08/2026): benchmark vốn đã đo ở 2048 và vẫn thấy 3/34 ca cắt
# cụt, nên production ở 1600 đứt sớm hơn cả con số đã báo cáo. Workflow đứt giữa
# chừng không "gần đúng" — nó không import vào n8n được, tức là hỏng hoàn toàn.
MAX_WORKFLOW_TOKENS = 2048


def loi_lan_truoc(err: str) -> str:
    """
    Lời nhắn `/chat` đưa cho model ở lần thử lại, chứa lý do cụ thể từ `validate_workflow()`.

    Một định nghĩa cho cả `chat.py` (production) và `offline_training/benchmark_v3.py` (đo): bộ đo mà tự viết
    lời nhắn thử lại của mình thì đo một thứ khác với thứ khách nhận (#91: v4 trượt n8n ở lần thử đầu, còn
    production thử lại một lần, nên con số "một lần" chỉ là cận dưới).
    """
    return (
        f"Lần trước JSON bị lỗi: {err}. "
        "Sửa lại và chỉ xuất JSON hợp lệ, không thêm chữ nào khác."
    )


def soan_yeu_cau(task: str, plan: str, feedback: str = "") -> str:
    """Câu user gửi cho model sinh workflow; `feedback` (nếu có) là kết quả của `loi_lan_truoc`."""
    user = f"YÊU CẦU: {task}\nKẾ HOẠCH: {plan}"
    if feedback:
        user += (
            f"\n\nLỖI LẦN TRƯỚC: {feedback}\n"
            "Sửa đúng lỗi đó rồi xuất lại workflow."
        )
    return user


class CoderAgent(BaseAgent):
    def __init__(self, engine, memory):
        super().__init__(engine, "coder")
        self.middleware = AgentMiddleware()

    async def write_code(self, task: str, plan: str, feedback: str = ""):
        """
        Sinh workflow n8n từ PLAN.

        `feedback` do chat.py truyền vào ở lần retry, chứa lý do lỗi cụ thể từ
        `validate_workflow()`. Feedback cụ thể sửa đúng hơn nhiều so với việc chỉ
        bảo model "thử lại".
        """
        system = Prompts.CODER_SYSTEM.format(
            tools=self.middleware.get_workflow_tools(),
            example=self.middleware.get_workflow_examples(),
        )

        return await self.generate_chat(
            system=system,
            user=soan_yeu_cau(task, plan, feedback),
            max_new_tokens=MAX_WORKFLOW_TOKENS,
            temperature=0.1,
            json_schema=self.middleware.get_workflow_json_schema(),
            tac_vu="n8n",
        )
