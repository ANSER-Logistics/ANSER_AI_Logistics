"""
src/core/so_bang_chu.py — đọc số tiền VIẾT BẰNG CHỮ ("năm triệu rưỡi", "hai trăm nghìn") ra VND.

MỘT định nghĩa cho hai nơi dùng (R4):
  - `doc_dau_vao.doc_so_tien`: đọc số tiền người dùng nói, để so với tham số model điền;
  - `grounding.narration_numbers_ok`: đọc số tiền model VIẾT trong câu trả lời, để so với dữ liệu tool.

Trước 20/11/2026 bộ đọc nằm trong `doc_dau_vao.py`. `grounding.py` không dùng được nó vì nó là mô-đun thuần
thư viện chuẩn mà `offline_training` cũng import, còn `doc_dau_vao` kéo theo `vat_catalog` và các mô-đun xlsx.
Nên tách ra đây, nguyên văn, chỉ đổi tên `_so_bang_chu` thành `so_bang_chu`.

Chỉ thư viện chuẩn, không gọi model, không đụng mạng.

GIỚI HẠN, CÓ CHỦ ĐÍCH: số chữ chỉ được coi là TIỀN khi có đơn vị nghìn/triệu/tỷ ("năm trăm" trơn không phải tiền).
"""

from __future__ import annotations

import re

# Số viết bằng chữ. Không dấu chỉ nhận những chữ ít nhập nhằng; "tư", "lăm",
# "nhăm", "mốt" chỉ là số khi đứng ngay sau "mươi".
_CHU_SO = {
    "không": 0, "khong": 0, "một": 1, "mot": 1, "hai": 2, "ba": 3, "bốn": 4,
    "bon": 4, "năm": 5, "nam": 5, "sáu": 6, "sau": 6, "bảy": 7, "bẩy": 7,
    "bay": 7, "tám": 8, "tam": 8, "chín": 9, "chin": 9,
}
_SAU_MUOI = {"mốt": 1, "tư": 4, "lăm": 5, "nhăm": 5, "lam": 5}
_MUOI = {"mươi", "muoi"}
_TRAM = {"trăm", "tram"}
_LINH = {"linh", "lẻ"}
_RUOI = {"rưỡi", "ruoi"}
_DON_VI_CHU = {
    "nghìn": 1_000, "ngàn": 1_000, "nghin": 1_000, "ngan": 1_000,
    "triệu": 1_000_000, "trieu": 1_000_000, "tỷ": 1_000_000_000, "tỉ": 1_000_000_000,
}
_TY = {"tỷ", "tỉ"}
_NGHIN = {"nghìn", "ngàn", "nghin", "ngan"}
_TU_SO = (set(_CHU_SO) | set(_SAU_MUOI) | _MUOI | {"mười"} | _TRAM | _LINH | _RUOI
          | set(_DON_VI_CHU))


def _gia_tri_chu(tu: list[str]) -> int | None:
    """Một cụm số bằng chữ -> VND. None = không hợp ngữ pháp số, hoặc không có
    đơn vị nghìn/triệu/tỷ (khi đó không coi là tiền)."""
    tong = nhom = 0
    cho = None                   # chữ số đang chờ: chưa biết là hàng trăm, chục hay đơn vị
    don_vi = None                # đơn vị gần nhất đã gặp
    chinh_xac = False            # phần SAU đơn vị cuối có "không trăm" hoặc "linh/lẻ": đọc đủ, không nói tắt
    truoc = None
    for t in tu:
        if t in _SAU_MUOI and truoc in (_MUOI | {"mười"}):
            if cho is not None:
                return None
            cho = _SAU_MUOI[t]
        elif t in _CHU_SO:
            if cho is not None:                       # hai chữ số liền nhau: "hai ba triệu"
                return None
            cho = _CHU_SO[t]
        elif t in _MUOI and cho:                      # "hai mươi"
            nhom, cho = nhom + cho * 10, None
        elif t == "mười" or (t in _MUOI and cho is None):   # "mười", "muoi" không dấu
            nhom += 10
        elif t in _TRAM:
            if cho is None:
                return None
            # `cho == 0` là "không trăm" ("một triệu không trăm năm mươi nghìn" = 1.050.000): hàng trăm trống,
            # cách đọc chuẩn của một nhóm ba chữ số không phải nhóm đầu. Bản trước từ chối cả cụm, rồi các
            # lần thử ngắn hơn cắt nó thành HAI số sai (1.000.000 và 50.000).
            if cho == 0:
                chinh_xac = True
            nhom, cho = nhom + cho * 100, None
        elif t in _LINH:
            if truoc not in _TRAM:
                return None
            chinh_xac = True
        elif t in _DON_VI_CHU:
            v = nhom + (cho or 0)
            if (not v and t in _TY and truoc in _NGHIN and 0 < tong < 1_000_000):
                # "một nghìn tỷ" = 10^12: nghìn x tỷ, không phải hai đơn vị rời nhau. Bản trước thấy "tỷ" không có
                # số đứng trước, từ chối cả cụm, và cắt còn "một nghìn" = 1.000.
                tong, nhom, cho, don_vi, truoc = tong * 1_000_000_000, 0, None, 1_000_000_000, t
                continue
            if not v:
                return None
            don_vi = _DON_VI_CHU[t]
            tong, nhom, cho = tong + v * don_vi, 0, None
            chinh_xac = False
        elif t in _RUOI:
            if truoc in _TRAM:
                nhom += 50                            # "trăm rưỡi" = 150
            elif truoc is not None and truoc in _DON_VI_CHU:
                # `truoc is not None` dư ở lúc chạy (None không nằm trong dict)
                # nhưng cần cho bộ kiểm kiểu: `x in dict` không thu hẹp `x`.
                tong += _DON_VI_CHU[truoc] // 2       # "năm triệu rưỡi"
            else:
                return None
        else:
            return None
        truoc = t
    if not don_vi:
        return None
    du = nhom + (cho or 0)
    if du and chinh_xac:
        # "hai nghìn không trăm linh năm" = 2.005, "hai triệu không trăm năm mươi" = 2.000.050: đã nói rõ hàng trăm
        # trống thì phần còn lại là đơn vị thật, không phải nói tắt. Bản trước đọc 2.005 thành 2.500.
        tong += du
    elif du:
        # Nói tắt sau đơn vị: "năm triệu hai" = 5,2 triệu; "hai triệu năm trăm"
        # = 2 triệu 500 nghìn.
        tong += du * don_vi // 10 if (nhom == 0 and du < 10) else du * don_vi // 1000
    return tong or None


def so_bang_chu(cau: str) -> list[tuple[int, int]]:
    """[(vị trí, giá trị)] cho mọi cụm số viết bằng chữ có đơn vị."""
    ra: list[tuple[int, int]] = []
    cum: list[re.Match] = []

    def chot() -> None:
        tu = [m.group(0).lower() for m in cum]
        i = 0
        while i < len(tu):
            for j in range(len(tu), i, -1):           # cụm dài nhất hợp lệ từ i
                v = _gia_tri_chu(tu[i:j])
                if v:
                    ra.append((cum[i].start(), v))
                    i = j
                    break
            else:
                i += 1

    for m in re.finditer(r"[^\W\d_]+", cau):
        la_tu_so = m.group(0).lower() in _TU_SO
        if la_tu_so and cum and not cau[cum[-1].end():m.start()].strip():
            cum.append(m)
            continue
        chot()
        cum = [m] if la_tu_so else []
    chot()
    return ra
