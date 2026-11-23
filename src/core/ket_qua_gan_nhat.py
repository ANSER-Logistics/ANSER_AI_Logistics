"""
src/core/ket_qua_gan_nhat.py — kết quả engine gần nhất của mỗi hội thoại, để câu "vì sao ra con số đó" ở lượt sau còn thứ để giải thích (A2, brain#322).

VÌ SAO CẦN
----------
Nhánh EXPLAIN tìm khối JSON của engine (`explain`, `periods`, `internal`...) trong LỊCH SỬ hội thoại. Nhưng thứ Brain trả về, và Body lưu lại để gửi kèm `history`
ở lượt sau, là câu văn xuôi do model diễn giải: khối JSON của engine không nằm trong đó. Nên dù Body gửi `history` đầy đủ, EXPLAIN vẫn không có gì để giải thích,
và câu hỏi "vì sao lãi gộp ra số này" luôn nhận "chưa có kết quả nào gần đây". Giữ khối engine ở phía Brain, theo (kho, người dùng), là cách duy nhất không đòi Body đổi hợp đồng.

QUY TẮC (R1, R2)
----------------
- Chỉ lưu khối do ENGINE TẤT ĐỊNH tính (kết quả tool), không bao giờ văn xuôi của model: giải thích dựa trên văn xuôi là bịa lý do cho một kết luận đã bịa.
- Khoá là (kho, người dùng): khối của khách này không bao giờ đến tay khách khác. Đây là dữ liệu khách (biên lợi nhuận, giá vốn), nên chỉ giữ TRONG BỘ NHỚ, có hạn dùng
  và có trần số mục; không ghi log nội dung; mất khi tiến trình khởi động lại (khi ấy EXPLAIN nói thẳng là chưa có, không bịa).
- Khối quá lớn (vượt `toi_da_ky_tu`) không lưu: đưa vào ngữ cảnh của model sẽ tràn, và cắt giữa chừng thì JSON hỏng, giải thích trên nửa số liệu còn tệ hơn không giải thích.
- Hạn dùng tính bằng đồng hồ đơn điệu (không nhảy khi chỉnh giờ hệ thống).
- Một tiến trình, một luồng (event loop): Dockerfile chạy `--workers 1`. Nâng số worker thì kho này không dùng chung được; khi ấy cần chuyển sang Redis (đã có `REDIS_URL`).
"""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Optional

# Khoá nhận biết một khối engine giải thích được. Engine nào cũng trả `explain`/`warnings`, nên tìm theo cấu trúc thay vì đoán theo câu chữ.
KHOA_GIAI_THICH = ("explain", "ranked", "internal", "periods", "warnings")


def la_khoi_giai_thich(obj: Any) -> bool:
    return isinstance(obj, dict) and any(k in obj for k in KHOA_GIAI_THICH)


def khoi_giai_thich(du_lieu: Any) -> Optional[dict]:
    """
    Khối engine giải thích được GẦN NHẤT trong dữ liệu neo của một lượt; None nếu không có.

    `du_lieu` là thứ `process_chat` gọi `grounding_ctx`: chuỗi JSON của một khối (nhánh REPORT) hoặc của danh sách
    `[{"tool": ..., "result": ...}]` (vòng agentic). Kết quả tool lỗi (`{"error": ...}`) không có khoá nào ở trên nên không lọt qua.
    """
    if isinstance(du_lieu, str):
        if not du_lieu.strip():
            return None
        try:
            du_lieu = json.loads(du_lieu)
        except ValueError:
            return None
    if la_khoi_giai_thich(du_lieu):
        return du_lieu
    if isinstance(du_lieu, list):
        for muc in reversed(du_lieu):
            ket_qua = muc.get("result") if isinstance(muc, dict) else None
            if la_khoi_giai_thich(ket_qua):
                return ket_qua
    return None


class KetQuaGanNhat:
    def __init__(
        self,
        ttl_giay: float,
        toi_da_muc: int,
        toi_da_ky_tu: int,
        dong_ho: Callable[[], float] = time.monotonic,
    ):
        if ttl_giay <= 0 or toi_da_muc < 1 or toi_da_ky_tu < 1:
            raise ValueError("ttl_giay, toi_da_muc, toi_da_ky_tu phải dương")
        self._ttl = ttl_giay
        self._toi_da_muc = toi_da_muc
        self._toi_da_ky_tu = toi_da_ky_tu
        self._dong_ho = dong_ho
        self._kho: OrderedDict[tuple[str, str], tuple[float, str]] = OrderedDict()

    @staticmethod
    def khoa(store_id: Any, user_id: Any) -> tuple[str, str]:
        return (str(store_id), str(user_id))

    def ghi(self, khoa: tuple[str, str], khoi: dict) -> bool:
        """
        Lưu khối cho hội thoại `khoa`, thay khối cũ. Trả False khi khối quá lớn hoặc không tuần tự hoá được.

        Khối cũ bị bỏ ở CẢ HAI trường hợp: lượt này đã cho ra một kết quả mới, nên nếu không lưu được nó mà vẫn giữ khối cũ
        thì "vì sao" sẽ được trả lời bằng số của một kết quả khác với cái người dùng đang nhìn.
        """
        self._kho.pop(khoa, None)
        try:
            chuoi = json.dumps(khoi, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return False
        if len(chuoi) > self._toi_da_ky_tu:
            return False
        self._kho[khoa] = (self._dong_ho() + self._ttl, chuoi)
        while len(self._kho) > self._toi_da_muc:
            self._kho.popitem(last=False)
        return True

    def lay(self, khoa: tuple[str, str]) -> Optional[str]:
        """Chuỗi JSON của khối còn hạn; None nếu không có hoặc đã quá hạn (mục quá hạn bị xoá)."""
        muc = self._kho.get(khoa)
        if muc is None:
            return None
        het_han, chuoi = muc
        if self._dong_ho() >= het_han:
            del self._kho[khoa]
            return None
        return chuoi

    def __len__(self) -> int:
        return len(self._kho)
