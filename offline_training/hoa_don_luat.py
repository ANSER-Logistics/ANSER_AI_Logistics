"""
offline_training/hoa_don_luat.py — phần THUẦN của hoá đơn hư cấu đúng kiểu Việt Nam: số tiền bằng chữ, ký hiệu
và số hoá đơn, khối người bán và người mua giả. Không PIL, không GPU, không mạng: test được ở CI.

VÌ SAO CÓ FILE NÀY
------------------
Không có ảnh hoá đơn thật nào (dữ liệu khách, R2), nên bộ đo model thị giác phải dựng hoá đơn hư cấu. Bộ sinh
cũ (`vlm_hoadon.py`) chỉ có bảng hàng và tổng tiền; hoá đơn thật còn một lớp chữ quanh đó mà model phải đọc
xuyên qua: mã số thuế, số điện thoại, tài khoản ngân hàng, ký hiệu và số hoá đơn, và dòng "Số tiền viết bằng
chữ". Lớp chữ này là chỗ model chép nhầm một con số vào trường khác (lỗi "điền số khác vào trường trống",
#112), nên đo trên giấy trơn thì đo thiếu.

Các quy định mà nghiên cứu ngày 17/11/2026 đọc được (`docs/ky-thuat/NGHIEN_CUU_DU_LIEU_VLM.md` ở repo tài
liệu, mục "Hoá đơn Việt Nam") và file này dùng:
  - Tổng tiền phải ghi bằng số và bằng chữ tiếng Việt.
  - "Ký hiệu mẫu số" là MỘT chữ số; "ký hiệu hoá đơn" gồm SÁU ký tự: C hoặc K, hai chữ số năm, một chữ cái
    loại hoá đơn, hai chữ cái do người bán chọn (ví dụ `C26TAA`); trên giấy hai trường hay in gộp thành
    `1C26TAA`. Số hoá đơn tối đa tám chữ số.
  - Hoá đơn không có thông tin người mua ghi "Bán cho người tiêu dùng".
Nguồn đọc từ Công báo bởi MỘT người nghiên cứu, lớp chữ của PDF mất một số dấu; kế toán phải xác nhận trước
khi dùng bất kỳ điều nào ở đây ngoài việc dựng ảnh thử. Bộ sinh chỉ dùng tập con đúng ở cả chế độ cũ lẫn mới
(loại hoá đơn T, D, L, M), nên không phụ thuộc chữ cái mới thêm từ 01/07/2026.

TOÀN BỘ HƯ CẤU (R2): tên có chữ "Thử Nghiệm"; mã số thuế bắt đầu bằng 99 và đúng số kiểm tra (không ai được
cấp); điện thoại dạng `028 0000 xxxx` và tài khoản dạng `0000xxxxxxxx` (dải không được cấp); không dùng tên,
địa chỉ, số của một doanh nghiệp có thật. `kiem_gia_lap` bắt lỗi đó.
"""

from __future__ import annotations

import random
import re
from typing import Any

_CHU_SO = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_BAC = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ"]       # nhóm ba chữ số thứ i; dưới 10^15 nên tối đa i = 4
_TRONG_SO_MST = (31, 29, 23, 19, 17, 13, 7, 5, 3)


# ---------------------------------------------------------------------------
# Số tiền bằng chữ
# ---------------------------------------------------------------------------

def _doc_nhom_ba(n: int, *, dau_nhom: bool) -> str:
    """Đọc một nhóm 0..999. `dau_nhom`: nhóm đứng đầu số thì không đọc "không trăm" ở trước."""
    tram, chuc, don = n // 100, (n // 10) % 10, n % 10
    phan: list[str] = []
    if tram > 0:
        phan.append(f"{_CHU_SO[tram]} trăm")
    elif not dau_nhom and (chuc > 0 or don > 0):
        phan.append("không trăm")
    if chuc == 1:
        phan.append("mười")
    elif chuc >= 2:
        phan.append(f"{_CHU_SO[chuc]} mươi")
    elif don > 0 and (tram > 0 or not dau_nhom):
        phan.append("linh")
    if don > 0:
        if chuc >= 2 and don == 1:
            phan.append("mốt")
        elif chuc >= 2 and don == 4:
            phan.append("tư")
        elif chuc >= 1 and don == 5:
            phan.append("lăm")
        else:
            phan.append(_CHU_SO[don])
    return " ".join(phan)


def doc_so(n: int) -> str:
    """Số nguyên không âm -> chữ tiếng Việt, chữ thường. Tới dưới 10^15."""
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"cần số nguyên, nhận {type(n).__name__}")
    if n < 0:
        raise ValueError("số tiền âm không đọc được thành chữ trên hoá đơn")
    if n >= 10 ** 15:
        raise ValueError("số quá lớn (từ 10^15 trở lên)")
    if n == 0:
        return "không"
    nhom: list[int] = []
    while n:
        nhom.append(n % 1000)
        n //= 1000
    phan: list[str] = []
    for i in range(len(nhom) - 1, -1, -1):
        g = nhom[i]
        if g == 0:
            continue
        chu = _doc_nhom_ba(g, dau_nhom=(i == len(nhom) - 1))
        phan.append(f"{chu} {_BAC[i]}".strip())
    return " ".join(phan)


def bang_chu_tien(n: int) -> str:
    """
    Dòng "Số tiền viết bằng chữ" của hoá đơn: chữ hoa đầu câu, kết bằng "đồng chẵn".
    Đồng Việt Nam không có số lẻ nên chỉ nhận số nguyên; số thực có phần lẻ là lỗi gọi.
    """
    if isinstance(n, float):
        if n != int(n):
            raise ValueError(f"số tiền có phần lẻ ({n}): hoá đơn đồng Việt Nam không có số lẻ")
        n = int(n)
    chu = doc_so(n)
    return f"{chu[0].upper()}{chu[1:]} đồng chẵn"


# ---------------------------------------------------------------------------
# Ký hiệu, số, ngày
# ---------------------------------------------------------------------------

# Loại hoá đơn đúng ở cả chế độ cũ lẫn mới (TT 78/2021 và TT 91/2026): T đăng ký với cơ quan thuế,
# D đặc thù, L cơ quan thuế cấp theo từng lần, M khởi tạo từ máy tính tiền.
LOAI_HOA_DON = ("T", "D", "L", "M")


def ky_hieu_hoa_don(rng: random.Random, nam: int, *, co_ma_cqt: bool = True, loai: str = "T") -> str:
    """
    "Ký hiệu hoá đơn": SÁU ký tự, ví dụ `C26TAA` = (C có mã cơ quan thuế | K không mã) + 2 số năm +
    loại + 2 chữ cái người bán chọn. Khác "ký hiệu mẫu số" (MỘT chữ số, trường riêng); trên giấy hai
    trường thường in gộp thành `1C26TAA`, xem `ky_hieu_day_du`.
    """
    if loai not in LOAI_HOA_DON:
        raise ValueError(f"loại {loai!r} ngoài tập con dùng được: {LOAI_HOA_DON}")
    if not 2000 <= nam <= 2099:
        raise ValueError(f"năm {nam} ngoài 2000..2099")
    hai_chu = "".join(rng.choice("ABCDEFGHKLMNPQRSTUVXY") for _ in range(2))
    return f"{'C' if co_ma_cqt else 'K'}{nam % 100:02d}{loai}{hai_chu}"


def ky_hieu_day_du(mau_so: int, ky_hieu: str) -> str:
    """Cách in gộp mẫu số (1 chữ số) và ký hiệu hoá đơn (6 ký tự): `1` + `C26TAA` -> `1C26TAA`."""
    if mau_so not in range(1, 10):
        raise ValueError(f"mẫu số là MỘT chữ số 1..9, nhận {mau_so}")
    if not ky_hieu_hop_le(ky_hieu):
        raise ValueError(f"ký hiệu hoá đơn sai dạng: {ky_hieu!r}")
    return f"{mau_so}{ky_hieu}"


_KY_HIEU = re.compile(r"^[CK]\d{2}[TDLM][A-Z]{2}$")


def ky_hieu_hop_le(s: str) -> bool:
    """Ký hiệu hoá đơn (6 ký tự, không kèm mẫu số)."""
    return bool(_KY_HIEU.match(s))


def so_hoa_don(rng: random.Random, *, toi_da: int = 9999) -> str:
    """Số hoá đơn tối đa tám chữ số, in thường đệm số không bên trái: `00001234`."""
    if not 1 <= toi_da <= 99_999_999:
        raise ValueError(f"số hoá đơn tối đa tám chữ số: toi_da phải trong 1..99999999, nhận {toi_da}")
    return f"{rng.randint(1, toi_da):08d}"


def ngay_viet(iso: str) -> str:
    """`2026-11-05` -> `Ngày 05 tháng 11 năm 2026`, dạng in trên hoá đơn."""
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso)
    if not m:
        raise ValueError(f"ngày phải dạng YYYY-MM-DD, nhận {iso!r}")
    return f"Ngày {m.group(3)} tháng {m.group(2)} năm {m.group(1)}"


# ---------------------------------------------------------------------------
# Người bán, người mua giả
# ---------------------------------------------------------------------------

_LOAI_HINH = ["Công ty TNHH", "Công ty Cổ phần", "Doanh nghiệp tư nhân"]
_NGANH = ["Thương mại Dầu nhớt", "Vận tải", "Thương mại và Dịch vụ", "Phân phối Phụ tùng", "Vận tải và Logistics"]
_TINH = ["Hà Nội", "Hải Phòng", "Đà Nẵng", "Nghệ An", "Thừa Thiên Huế", "Khánh Hoà", "Cần Thơ", "Đồng Nai", "Bình Định"]
_TEN_NH = ["Ngân hàng TMCP Thử Nghiệm", "Ngân hàng Thử Nghiệm Việt"]


def mst_gia(rng: random.Random) -> str:
    """MST 10 số bịa: bắt đầu bằng 99, chữ số cuối là số kiểm tra thật (cùng thuật toán `src/core/tax_id.py`)."""
    while True:
        so = [9, 9] + [rng.randint(0, 9) for _ in range(7)]
        du = sum(n * w for n, w in zip(so, _TRONG_SO_MST)) % 11
        if du != 0:
            return "".join(map(str, so)) + str(10 - du)


def dien_thoai_gia(rng: random.Random) -> str:
    return f"028 0000 {rng.randint(0, 9999):04d}"


def tai_khoan_gia(rng: random.Random) -> str:
    return f"0000{rng.randint(0, 99_999_999):08d}"


def doanh_nghiep_gia(rng: random.Random, *, nganh: str | None = None) -> dict[str, str]:
    tinh = rng.choice(_TINH)
    ten = f"{rng.choice(_LOAI_HINH)} {nganh or rng.choice(_NGANH)} Thử Nghiệm {rng.randint(1, 99):02d}"
    return {
        "ten": ten,
        "mst": mst_gia(rng),
        "dia_chi": f"Số {rng.randint(1, 250)} Đường Số {rng.randint(1, 30)}, Khu công nghiệp Thử Nghiệm, {tinh}",
        "dien_thoai": dien_thoai_gia(rng),
        "tai_khoan": tai_khoan_gia(rng),
        "ngan_hang": rng.choice(_TEN_NH),
    }


def nguoi_mua_gia(rng: random.Random, *, ban_cho_nguoi_tieu_dung: bool = False) -> dict[str, str]:
    if ban_cho_nguoi_tieu_dung:
        return {"ten": "Bán cho người tiêu dùng", "mst": "", "dia_chi": ""}
    dn = doanh_nghiep_gia(rng)
    return {"ten": dn["ten"], "mst": dn["mst"], "dia_chi": dn["dia_chi"]}


# ---------------------------------------------------------------------------
# Gói hoàn chỉnh: phần chữ quanh bảng hàng
# ---------------------------------------------------------------------------

def phan_chu_hoa_don(rng: random.Random, *, tong: int, iso_ngay: str, mau_so: int = 1,
                     loai: str = "T", ban_cho_nguoi_tieu_dung: bool = False,
                     nganh_ban: str | None = None) -> dict[str, Any]:
    """
    Mọi chữ quanh bảng hàng của một hoá đơn: người bán, người mua, ký hiệu, số, ngày, hình thức thanh toán,
    dòng bằng chữ. `tong` là TỔNG CỘNG đã biết (đáp án), dòng bằng chữ đọc đúng từ nó.
    """
    nam = int(iso_ngay[:4])
    ky_hieu = ky_hieu_hoa_don(rng, nam, loai=loai)
    return {
        "nguoi_ban": doanh_nghiep_gia(rng, nganh=nganh_ban),
        "nguoi_mua": nguoi_mua_gia(rng, ban_cho_nguoi_tieu_dung=ban_cho_nguoi_tieu_dung),
        "mau_so": str(mau_so),
        "ky_hieu": ky_hieu,
        "ky_hieu_day_du": ky_hieu_day_du(mau_so, ky_hieu),
        "so": so_hoa_don(rng),
        "ngay": ngay_viet(iso_ngay),
        "hinh_thuc_thanh_toan": rng.choice(["TM/CK", "TM", "CK"]),
        "bang_chu": bang_chu_tien(tong),
    }


# ---------------------------------------------------------------------------
# Kiểm: không có chữ nào trông như một doanh nghiệp thật
# ---------------------------------------------------------------------------

def kiem_gia_lap(phan_chu: dict[str, Any]) -> list[str]:
    """Danh sách điều vi phạm quy ước hư cấu; rỗng là đạt. Gọi cho mọi hoá đơn sinh ra."""
    loi: list[str] = []
    ban = phan_chu["nguoi_ban"]
    if "Thử Nghiệm" not in ban["ten"]:
        loi.append(f"tên người bán thiếu 'Thử Nghiệm': {ban['ten']!r}")
    if not ban["mst"].startswith("99"):
        loi.append(f"MST người bán không bắt đầu bằng 99: {ban['mst']!r}")
    if not ban["dien_thoai"].startswith("028 0000"):
        loi.append(f"điện thoại ngoài dải hư cấu: {ban['dien_thoai']!r}")
    if not ban["tai_khoan"].startswith("0000"):
        loi.append(f"tài khoản ngoài dải hư cấu: {ban['tai_khoan']!r}")
    mua = phan_chu["nguoi_mua"]
    if mua["mst"] and not mua["mst"].startswith("99"):
        loi.append(f"MST người mua không bắt đầu bằng 99: {mua['mst']!r}")
    if mua["ten"] != "Bán cho người tiêu dùng" and "Thử Nghiệm" not in mua["ten"]:
        loi.append(f"tên người mua thiếu 'Thử Nghiệm': {mua['ten']!r}")
    if not ky_hieu_hop_le(phan_chu["ky_hieu"]):
        loi.append(f"ký hiệu sai dạng: {phan_chu['ky_hieu']!r}")
    if phan_chu["ky_hieu_day_du"] != phan_chu["mau_so"] + phan_chu["ky_hieu"]:
        loi.append(f"ký hiệu đầy đủ lệch mẫu số và ký hiệu: {phan_chu['ky_hieu_day_du']!r}")
    if not (phan_chu["so"].isdigit() and len(phan_chu["so"]) <= 8):
        loi.append(f"số hoá đơn không phải tối đa tám chữ số: {phan_chu['so']!r}")
    return loi
