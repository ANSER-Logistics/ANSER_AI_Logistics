import json
import logging
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger("projecta.utils")

_GIO_VN = timezone(timedelta(hours=7))   # UTC+7, Việt Nam không có giờ mùa hè


def _bay_gio_utc() -> datetime:
    """Đồng hồ của `hom_nay_vn`. Tách riêng để test đặt giờ giả MỘT chỗ cho mọi nơi gọi."""
    return datetime.now(timezone.utc)


def hom_nay_vn(bay_gio: Optional[datetime] = None) -> date:
    """Ngày hôm nay theo GIỜ VIỆT NAM, không theo múi giờ máy chủ.

    `date.today()` lấy múi giờ của máy: container thường chạy UTC, nên từ 00:00 đến 07:00
    sáng ở Việt Nam nó còn là hôm qua. Luồng n8n đã chốt UTC+7 (brain#217); mọi chỗ trong
    Brain cần "hôm nay" PHẢI gọi hàm này, không `date.today()`, không `CURRENT_DATE` của
    DB (R4, một định nghĩa; `tests/test_gio_viet_nam.py` canh).

    Nằm ở `utils.py` (tầng thấp) vì `prompts.py` cũng cần nó, mà `pricing.py` (tầng trên)
    thì không import ngược xuống được (`tests/test_layering.py`). Dấu thời gian là một
    THỜI ĐIỂM (`computed_at`, `ts` của metrics) không dùng hàm này: chúng ở UTC và không
    có nghĩa "hôm nay".
    """
    return (bay_gio or _bay_gio_utc()).astimezone(_GIO_VN).date()


def bo_dau(value: Any) -> str:
    """
    Bỏ dấu tiếng Việt, gộp khoảng trắng, hạ chữ thường.

    Dùng để SO KHỚP (tên cột Excel, từ khoá trong tên hàng), không dùng để hiển
    thị. 'Đơn giá BQ' và 'don gia bq' phải khớp nhau vì mỗi phần mềm kế toán đặt
    tên cột một kiểu.

    Nằm ở đây vì ba module nhập liệu đều cần: inventory_import, partner_import,
    vat_catalog. Trước đó mỗi module giữ một bản y hệt.
    """
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return re.sub(r"\s+", " ", text).strip().lower()


class HttpClientPool:
    # Optional: `None` là trạng thái hợp lệ (chưa mở, hoặc đã đóng) — khai
    # `httpx.AsyncClient = None` là nói dối kiểu, mypy bắt đúng.
    _client: Optional[httpx.AsyncClient] = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None or cls._client.is_closed:
            cls._client = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return cls._client

    @classmethod
    async def close(cls):
        if cls._client and not cls._client.is_closed:
            await cls._client.aclose()
            cls._client = None


def extract_json_block(text: str) -> tuple[Optional[dict], Optional[str]]:
    """
    Tách object JSON đầu tiên trong text bằng cách đếm ngoặc.

    Trả `(dict, None)` nếu hợp lệ, hoặc `(None, lý_do_lỗi)`. Đếm ngoặc chứ không
    dùng regex vì workflow JSON lồng nhiều tầng, và regex không đếm được độ sâu.

    CHUYỂN TỪ `src/api/routes/chat.py` SANG ĐÂY (03/08/2026)
    -------------------------------------------------------
    Hàm này là hàm THUẦN — đếm ngoặc trên một chuỗi, không biết gì về HTTP. Nhưng
    nó nằm trong module route, nên `agents/agentic.py` phải import ngược lên
    `src.api.routes.chat` — và phải đặt import đó trong thân hàm.

    Một module tầng điều phối kéo ngược tầng HTTP vào, chỉ để dùng một hàm cắt
    chuỗi. Import đặt trong thân hàm nên né được vòng lặp import lúc nạp module
    và KHÔNG AI THẤY GÌ — phát hiện khi đối chiếu sơ đồ vẽ tay với bản đồ Grapuco
    sinh tự động.

    `chat.py` giữ một alias để 5 chỗ gọi cũ trong đó không phải sửa.
    """
    if not text:
        return None, "empty output"

    start = text.find("{")
    if start == -1:
        return None, "no JSON object found"

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate), None
                except json.JSONDecodeError as exc:
                    # Thử json_repair cho lỗi nhẹ (dấu phẩy thừa...)
                    try:
                        from json_repair import repair_json
                        repaired: Any = repair_json(candidate, return_objects=True)
                        if isinstance(repaired, dict) and repaired:
                            return repaired, None
                    except ImportError:
                        # Thiếu gói `json_repair` -> lớp sửa lỗi nhẹ KHÔNG chạy.
                        #
                        # Bản trước là `except Exception: pass`, đúng y nguyên văn
                        # điều AGENTS §4.1 quy tắc 4 cấm. Hậu quả không phải sai kết
                        # quả — hàm vẫn trả lỗi ngay dưới đây — mà là MỘT TRIỂN KHAI
                        # THIẾU GÓI trông giống hệt một đầu ra model hỏng: cả hai đều
                        # báo `JSONDecodeError`. Tỷ lệ phải đi đường dự phòng tăng lên
                        # và không có gì cho thấy vì sao.
                        logger.warning(
                            "json_repair không nạp được — lớp sửa JSON nhẹ KHÔNG "
                            "chạy. Cài gói này (có trong requirements.txt) nếu đang "
                            "thấy nhiều lỗi JSONDecodeError."
                        )
                    except Exception as loi_sua:
                        # Gói có nhưng sửa không nổi. Ghi ở mức debug: với đầu ra
                        # model hỏng thật thì đây là đường chạy BÌNH THƯỜNG, nên
                        # warning ở đây sẽ thành nhiễu che mất ca ImportError trên.
                        logger.debug("json_repair không sửa được: %s", loi_sua)
                    return None, f"JSONDecodeError: {exc.msg} tại vị trí {exc.pos}"

    return None, "unbalanced braces (thiếu dấu })"


def loai_loi() -> str:
    """Loại ngoại lệ đang xử lý KÈM VỊ TRÍ (tệp:dòng hàm, bốn khung trong cùng), trong khối `except`. Để ghi log: THÂN thông báo lỗi có thể
    chứa nội dung của khách (câu lệnh SQL kèm tham số, URL kèm chuỗi truy vấn, `input` của pydantic) nên không bao giờ được ghi; còn tên loại và
    vị trí thì đủ để tìm ra chỗ hỏng (R2, #205)."""
    import sys
    import traceback
    from pathlib import PurePath
    loai, _, tb = sys.exc_info()
    if loai is None:
        return "?"
    khung = traceback.extract_tb(tb)[-4:]
    return f"{loai.__name__} tại " + " > ".join(f"{PurePath(k.filename).name}:{k.lineno} {k.name}" for k in khung)
