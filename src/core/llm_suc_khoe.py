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
