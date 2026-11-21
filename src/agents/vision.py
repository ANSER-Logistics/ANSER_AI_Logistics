# src/agents/vision.py
"""
VisionAgent — lớp mỏng bọc quanh ModelEngine.generate_vision (model thị giác theo VISION_MODEL_ID, mặc định Qwen3-VL-2B).

MỘT model VLM duy nhất cho cả 3 vai trò (đã LOẠI BỎ Florence-2):
  1. caption  — mô tả ảnh bằng tiếng Việt
  2. ocr      — trích xuất văn bản thô
  3. invoice  — trích xuất hóa đơn ra JSON có cấu trúc (cho luồng nhập kho)

VisionAgent KHÔNG tự load model; nó dùng chung model thị giác do ModelEngine sở hữu,
nên không còn cảnh nạp 2 model vision song song.
"""
import logging

from json_repair import repair_json

from src.core.prompts import Prompts

logger = logging.getLogger("projecta.agents.vision")


class VisionAgent:
    # Nguyên văn nằm ở `Prompts` (AGENTS §4.1 quy tắc 7); đây chỉ là bảng tra theo tên tác vụ.
    PROMPTS = {
        "caption": Prompts.VLM_CAPTION,
        "ocr": Prompts.VLM_OCR,
        "invoice": Prompts.VLM_INVOICE,
        "freight": Prompts.VLM_FREIGHT,
    }

    def __init__(self, engine):
        if engine is None:
            raise ValueError("VisionAgent cần một ModelEngine instance")
        self.engine = engine
        logger.info("VisionAgent ready (dùng chung model thị giác của ModelEngine)")

    def _prompt_for(self, task_hint: str) -> str:
        task_hint = (task_hint or "").lower()
        # "freight" phải xét TRƯỚC "invoice": chuỗi "freight_invoice" chứa cả hai,
        # xét sau là mọi hoá đơn vận tải rơi vào nhánh bán lẻ.
        if "freight" in task_hint or "van_tai" in task_hint or "vận tải" in task_hint:
            return self.PROMPTS["freight"]
        if "invoice" in task_hint or "hoa_don" in task_hint or "hóa đơn" in task_hint:
            return self.PROMPTS["invoice"]
        if "ocr" in task_hint:
            return self.PROMPTS["ocr"]
        return self.PROMPTS["caption"]

    async def analyze_image(self, image_path: str, task_hint: str = "caption",
                            json_schema: dict | None = None,
                            phai_tron_ven: bool = False) -> str:
        """
        Trả về text. task_hint ∈ {'caption', 'ocr', 'invoice', 'freight'}.

        `phai_tron_ven`: người gọi sẽ lấy SỐ từ đầu ra (mọi đường trích hoá đơn). Đầu ra cụt
        ở `max_tokens` thì trả "Error analyzing image: ..." thay vì nửa chuỗi, vì nửa chuỗi
        đi qua `repair_json` thành một object hợp lệ mang con số cụt (xem `BackendTruncated`).
        """
        prompt = self._prompt_for(task_hint)
        th = (task_hint or "").lower()
        max_tokens = 1024 if any(k in th for k in ("ocr", "invoice", "freight")) else 512
        try:
            return await self.engine.generate_vision(
                image_path, prompt, max_new_tokens=max_tokens, json_schema=json_schema,
                phai_tron_ven=phai_tron_ven,
            )
        except Exception as exc:
            logger.error("Vision inference failed: %s", type(exc).__name__)
            return f"Error analyzing image: {exc}"

    async def extract_invoice(self, image_path: str) -> dict:
        """
        Vai trò 2 (OCR hóa đơn): trả dict {items, total} đã parse từ JSON của VLM.
        Trả {'error': ...} nếu không đọc/parse được — KHÔNG bịa số.
        """
        return await self._extract_json(image_path, task_hint="invoice")

    async def extract_freight_invoice(self, image_path: str) -> dict:
        """
        Hoá đơn CƯỚC VẬN TẢI của nhà xe -> dict theo lược đồ `FreightInvoice`.

        Có ràng buộc giải mã theo lược đồ: model chỉ sinh được token nào giữ cho
        chuỗi hợp lệ. Khác hẳn `extract_invoice` — đường bán lẻ sinh tự do rồi
        vá cú pháp bằng `json_repair`, mà vá cú pháp không dựng lại được trường
        bị thiếu.

        Con số ở đây CHƯA đáng tin: `freight_invoice.verify()` mới là chỗ tính
        lại toàn bộ bằng code và đối chiếu với số in trên tờ giấy.
        """
        from src.core.freight_invoice import json_schema

        return await self._extract_json(
            image_path, task_hint="freight", json_schema=json_schema()
        )

    async def _extract_json(self, image_path: str, task_hint: str,
                            json_schema: dict | None = None) -> dict:
        """Đọc ảnh -> dict. Trả {'error': ...} nếu hỏng — KHÔNG bịa số."""
        raw = await self.analyze_image(image_path, task_hint=task_hint,
                                       json_schema=json_schema, phai_tron_ven=True)
        if isinstance(raw, str) and raw.startswith("Error"):
            return {"error": raw}
        try:
            parsed = repair_json(raw, return_objects=True)
            if isinstance(parsed, dict):
                return parsed
            return {"error": "VLM không trả JSON object", "raw": raw}
        except Exception as exc:
            # Chỉ ghi loại lỗi: `raw` là văn bản đọc từ ảnh hoá đơn (dữ liệu khách).
            logger.warning("Không sửa được đầu ra VLM thành JSON (%s)", type(exc).__name__)
            return {"error": f"parse_failed: {exc}", "raw": raw}
