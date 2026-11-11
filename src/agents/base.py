from abc import ABC

from src.core.engine import ModelEngine
from src.core.serving import KetQuaSinh


class BaseAgent(ABC):
    """
    Mọi hàm sinh trả `KetQuaSinh` (chữ + số token + thời gian gọi model), không
    trả `str` (#16). Chỗ nào cần chữ thì đọc `.text`; `chat.py` cộng số token
    của cả lượt vào `TurnMetric`.
    """

    def __init__(self, engine: ModelEngine, role: str):
        self.engine = engine
        self.role = role

    async def generate(self, prompt: str, **kwargs) -> KetQuaSinh:
        """Raw completion — giữ lại cho tương thích ngược (KHÔNG dùng cho chat ChatML)."""
        max_tokens = kwargs.get('max_new_tokens', 1024)
        temperature = kwargs.get('temperature', 0.1)
        return await self.engine.generate_text(prompt, max_tokens, temperature)

    async def generate_chat(self, system: str, user: str, **kwargs) -> KetQuaSinh:
        """
        Chat đúng chuẩn Qwen — để tokenizer.apply_chat_template lo định dạng ChatML.

        `json_schema` (tuỳ chọn): bật guided decoding, ép output khớp JSON Schema.
        `history` (tuỳ chọn): các lượt trước [{role, content}] — cho hội thoại
        nhiều lượt. Bỏ trống thì mỗi tin nhắn là một phiên độc lập.
        """
        max_tokens = kwargs.get('max_new_tokens', 1024)
        temperature = kwargs.get('temperature', 0.1)
        return await self.engine.generate_chat(
            system,
            user,
            max_tokens,
            temperature,
            json_schema=kwargs.get('json_schema'),
            history=kwargs.get('history'),
        )
