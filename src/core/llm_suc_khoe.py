"""
src/core/llm_suc_khoe.py — mạch ngắt cho model ngôn ngữ: GPU mất thì nói thẳng, không xếp hàng vô ích (A21, #203).

Vấn đề: khi vLLM mất (GPU lỗi, server sập), `/chat` vẫn nhận (200, `task_id`) rồi tác vụ nền thất bại, nên Body chờ rồi nhận lỗi muộn. Phần tất định
(`/tools/*`) KHÔNG dùng model nên vẫn chạy được: đó là hạ cấp có kiểm soát mà pilot cần.

Cách làm: đếm các lần gọi model THẤT BẠI LIÊN TIẾP vì `BackendUnavailable` hoặc `BackendTimeout`. Từ `NGUONG_LOI` lần trở lên thì `dang_hong()` trả True và
`/chat` trả 503 `llm_unavailable` kèm `Retry-After`. Sau `THU_LAI_S` giây cho MỘT lượt đi qua để thử lại (nửa mở); thành công thì đóng mạch, thất bại
thì mở tiếp. Lỗi không phải mất kết nối (JSON hỏng, model trả rác) KHÔNG tính: đó không phải GPU mất.

shortcut: trạng thái nằm trong tiến trình (đúng khi một tiến trình, như compose hiện nay); nhiều bản sao thì mỗi bản tự đếm. Chuyển sang Redis nếu chạy nhiều worker.
"""

from __future__ import annotations

import threading
import time

NGUONG_LOI = 3
THU_LAI_S = 30.0

_khoa = threading.Lock()
_loi_lien_tiep = 0
_mo_tu: float | None = None          # thời điểm mạch mở
_dang_thu = False                    # một lượt thử lại đang bay


def ghi_loi() -> None:
    """Một lần gọi model thất bại vì mất kết nối hay hết giờ."""
    global _loi_lien_tiep, _mo_tu, _dang_thu
    with _khoa:
        _loi_lien_tiep += 1
        _dang_thu = False
        if _loi_lien_tiep >= NGUONG_LOI:
            _mo_tu = time.monotonic()


def ghi_ok() -> None:
    global _loi_lien_tiep, _mo_tu, _dang_thu
    with _khoa:
        _loi_lien_tiep, _mo_tu, _dang_thu = 0, None, False


def dang_hong() -> bool:
    """True = từ chối lượt mới. Mạch mở quá `THU_LAI_S` thì cho MỘT lượt đi thử (các lượt khác vẫn bị từ chối tới khi nó xong)."""
    global _dang_thu
    with _khoa:
        if _mo_tu is None:
            return False
        if time.monotonic() - _mo_tu >= THU_LAI_S and not _dang_thu:
            _dang_thu = True
            return False
        return True


def trang_thai() -> dict[str, object]:
    with _khoa:
        return {"available": _mo_tu is None, "consecutive_failures": _loi_lien_tiep}


def dat_lai() -> None:
    """Cho test."""
    ghi_ok()


# ---------------------------------------------------------------------------
# Thăm dò chủ động
# ---------------------------------------------------------------------------
# `/health` của vLLM trả 200 cả khi GPU lỗi (nghiên cứu 20/11/2026), nên chỉ đếm lỗi của lượt thật thì 3 người dùng đầu mới thấy lỗi. Thăm dò sinh MỘT token
# tới chính model mỗi `LLM_PROBE_INTERVAL_S` giây (mặc định 60; 0 tắt) và nạp vào cùng mạch ngắt. Chỉ chạy khi backend text là server vLLM.

async def mot_lan_tham_do(server) -> bool | None:
    """Một lượt thăm dò. True = model trả lời; False = mất kết nối hay hết giờ (đã ghi vào mạch); None = lỗi khác (không phải GPU mất, không đổi mạch)."""
    from src.core.serving import BackendTimeout, BackendUnavailable, ChatRequest
    try:
        await server.chat(ChatRequest(messages=[{"role": "user", "content": "."}], max_tokens=1, temperature=0.0))
    except (BackendUnavailable, BackendTimeout):
        ghi_loi()
        return False
    except Exception:
        import logging

        from src.core.utils import loai_loi
        logging.getLogger("anser.llm_suc_khoe").warning("Thăm dò model: lỗi không phải mất kết nối: %s", loai_loi())
        return None
    ghi_ok()
    return True


async def vong_tham_do(lay_server, chu_ky_s: float) -> None:
    """Chạy tới khi bị huỷ. `lay_server()` trả client vLLM hoặc None (chưa khởi tạo hay không dùng server)."""
    import asyncio
    while True:
        await asyncio.sleep(chu_ky_s)
        server = lay_server()
        if server is not None:
            await mot_lan_tham_do(server)


def chu_ky_tham_do_s() -> float:
    """`LLM_PROBE_INTERVAL_S`: giây giữa hai lượt thăm dò; 0 = tắt. Giá trị hỏng thì dịch vụ không khởi động (như `FUEL_PRICE_*`)."""
    import os
    tho = os.getenv("LLM_PROBE_INTERVAL_S", "").strip()
    if not tho:
        return 60.0
    try:
        v = float(tho)
    except ValueError:
        raise RuntimeError(f"LLM_PROBE_INTERVAL_S={tho!r} không phải số") from None
    if v < 0 or v != v or v == float("inf"):
        raise RuntimeError(f"LLM_PROBE_INTERVAL_S={tho!r} phải là số >= 0 hữu hạn (0 = tắt)")
    return v
