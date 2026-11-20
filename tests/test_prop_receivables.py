"""
tests/test_prop_receivables.py — TÍNH CHẤT (property-based) của `src/core/receivables.py`.

VÌ SAO CÓ FILE NÀY
------------------
`tests/test_receivables.py` khoá bằng ví dụ viết tay: mỗi ca là một bộ số người viết nghĩ ra. Cảnh báo "một khách
chiếm quá 20%, ba khách chiếm quá 50%" là phép chia và phép so sánh, nên lỗi của nó nằm ở chỗ người viết không nghĩ
tới: đúng bằng ngưỡng, số dư âm lẫn vào mẫu số, khách chưa có số dư bị coi là 0, thứ tự dòng làm đổi kết quả. Ở đây
`hypothesis` sinh hàng trăm danh sách cho mỗi tính chất và co phản ví dụ về dạng nhỏ nhất.

CÁCH ĐỐI CHỨNG (R1)
-------------------
Phép tính chuẩn dùng `fractions.Fraction` trên số nguyên đồng, nên không có sai số dấu phẩy động nào để che một lỗi
ở biên. Các test đối chứng chỉ dùng số dư NGUYÊN đồng, không có số dư trong khoảng (0, 1] hay [-1, 0): mã coi số dư
không quá 1 đồng là sai số làm tròn (`_TIEN_TOL`), đó là chi tiết cài đặt chứ không phải hợp đồng nên file này
không khoá nó. (Hai test hình dạng và tất định dùng cả số lẻ, vì ở đó không có phép so con số nào.) Mọi con số là
hư cấu (R2): khách "Khách mẫu 007", mã số thuế bịa bắt đầu bằng 99.

HAI NGƯỠNG DO TEAM ĐẶT, CHƯA CÓ KẾ TOÁN XÁC NHẬN
-----------------------------------------------
20% cho một khách và 50% cho ba khách. File này KHÔNG bảo hai con số đó đúng nghiệp vụ, chỉ khoá hành vi QUANH
chúng: đúng bằng ngưỡng thì báo, hơn một đồng thì báo, kém một đồng thì không. Hai hằng `NGUONG_MOT`, `NGUONG_BA`
ở dưới là bản chép của ngưỡng trong mã; `test_nguong_trong_ma_khop_hang_so_cua_file_test` đỏ trước tiên khi ai đó
đổi ngưỡng, kèm lời nhắc phải sửa file này có chủ ý thay vì đọc cả loạt phản ví dụ vô nghĩa.

NHỮNG TÍNH CHẤT BỊ BỎ VÌ KHÔNG PHẢI HỢP ĐỒNG
--------------------------------------------
* Nhân số dư với hằng số dương BẤT KỲ: chỉ đúng với hằng số nguyên >= 1. `_TIEN_TOL` là ngưỡng TUYỆT ĐỐI 1 đồng,
  nên nhân với 0,01 sẽ đẩy mọi số dư xuống dưới ngưỡng và khách biến mất. Đổi đơn vị (nghìn đồng ra đồng) là
  trường hợp thật, và nó nằm trong miền k >= 1.
* Không phụ thuộc thứ tự cho số dư LẺ (có phần thập phân): tổng dấu phẩy động đổi theo thứ tự cộng. Tính chất này
  chỉ kiểm trên số nguyên đồng, nơi phép cộng chính xác.
* Khi nhiều khách đồng hạng đầu, khách nào được NÊU TÊN trong cảnh báo phụ thuộc thứ tự dòng. Con số thì không.
"""

from __future__ import annotations

import copy
from fractions import Fraction

from hypothesis import given, settings
from hypothesis import strategies as st

from src.core import receivables
from src.core.findings import MUC_DO
from src.core.partner_import import KHACH_HANG, NHA_CUNG_CAP, Partner
from src.core.receivables import audit_partners, suc_khoe_von_luu_dong

CAU_HINH = settings(derandomize=True, max_examples=200, deadline=None, database=None)

# Bản chép của ngưỡng trong mã (receivables._MOT_KHACH_PCT / _BA_KHACH_PCT), tính bằng phân số để so chính xác.
NGUONG_MOT = Fraction(20, 100)
NGUONG_BA = Fraction(50, 100)
NGAY_PHAI_THU_CAO = 90

TOI_DA = 10 ** 13      # "số lớn" của đề: một khoản công nợ tới mười nghìn tỷ đồng
SO_KHACH_TOI_DA = 12


# ---------------------------------------------------------------------------
# Sinh dữ liệu
# ---------------------------------------------------------------------------

def so_du_cho(toi_da: int, *, co_none: bool = True):
    """
    Một số dư NGUYÊN đồng. Nhánh số nhỏ 2..12 xuất hiện ba lần để nhiều dòng TRÙNG nhau: biên chính xác
    (5 khách bằng nhau, mỗi khách đúng 20%) chỉ hiện ra khi có nhiều dòng trùng.
    """
    nhanh = [
        st.just(0),
        st.integers(-12, -2),
        st.integers(2, 12), st.integers(2, 12), st.integers(2, 12),
        st.integers(2, toi_da),
        st.integers(-toi_da, -2),
    ]
    if co_none:
        nhanh.append(st.none())     # CHƯA BIẾT, không phải 0
    return st.one_of(*nhanh)


def danh_sach_so_du(toi_da: int = TOI_DA, *, co_none: bool = True, toi_thieu: int = 0):
    return st.lists(so_du_cho(toi_da, co_none=co_none), min_size=toi_thieu, max_size=SO_KHACH_TOI_DA)


# Rất ít giá trị khác nhau: tổng là bội của đỉnh xảy ra thường xuyên, tức là chạm đúng biên 20% và 50%.
GIA_TRI_IT_KHAC_NHAU = st.lists(
    st.sampled_from([None, 0, -3, 2, 3, 4]), max_size=SO_KHACH_TOI_DA
)


def dung_khach(gia_tri, *, tien_to: str = "KH", vai_tro: str = KHACH_HANG) -> list[Partner]:
    """Mỗi giá trị thành một đối tác hư cấu, mã duy nhất theo vị trí, không mã số thuế."""
    return [
        Partner(
            code=f"{tien_to}{i:03d}", name=f"Khách mẫu {i:03d}",
            balance=None if v is None else float(v), tax_id="", role=vai_tro,
        )
        for i, v in enumerate(gia_tri)
    ]


def dung_ncc(gia_tri) -> list[Partner]:
    return dung_khach(gia_tri, tien_to="NCC", vai_tro=NHA_CUNG_CAP)


# ---------------------------------------------------------------------------
# Đọc kết quả, và phép tính đối chứng
# ---------------------------------------------------------------------------

def tap_trung(kq) -> tuple[dict | None, dict | None]:
    """(cảnh báo 'một khách', cảnh báo 'ba khách'). Mỗi loại tối đa MỘT, nếu hơn là lỗi."""
    mot = ba = None
    for f in kq["findings"]:
        if f["kind"] != "customer_concentration":
            continue
        if isinstance(f["evidence"]["khách"], list):
            assert ba is None, "hai cảnh báo 'ba khách' cùng lúc"
            ba = f
        else:
            assert mot is None, "hai cảnh báo 'một khách' cùng lúc"
            mot = f
    return mot, ba


def chuan(gia_tri):
    """
    Phép tính đối chứng bằng Fraction: (các số dư dương giảm dần, tổng, tỷ trọng khách đầu, tỷ trọng ba khách đầu).
    Tỷ trọng là None khi không có nghĩa: không có số dư dương nào, hoặc chưa đủ ba khách.
    """
    duong = sorted((int(v) for v in gia_tri if v is not None and v > 0), reverse=True)
    tong = sum(duong)
    s1 = Fraction(duong[0], tong) if duong else None
    s3 = Fraction(sum(duong[:3]), tong) if len(duong) >= 3 else None
    return duong, tong, s1, s3


def _doi_chieu_phep_tinh(gia_tri) -> None:
    kq = audit_partners(dung_khach(gia_tri))
    mot, ba = tap_trung(kq)
    duong, tong, s1, s3 = chuan(gia_tri)
    chua_biet = sum(1 for v in gia_tri if v is None)

    # Bản tóm tắt cộng chính xác từng đồng (kể cả khi tổng tới 10^14), và chỉ đếm khách có số dư khác 0.
    assert kq["summary"]["tổng_phải_thu"] == tong
    assert kq["summary"]["khách_có_số_dư"] == sum(1 for v in gia_tri if v)

    # Báo ĐÚNG khi và chỉ khi tỷ trọng đạt ngưỡng (đúng bằng cũng báo), và đúng mức: 20% là 'một khách',
    # 50% là 'ba khách', không đổi chỗ cho nhau.
    assert (mot is not None) == (s1 is not None and s1 >= NGUONG_MOT)
    assert (ba is not None) == (s3 is not None and s3 >= NGUONG_BA)

    for f, top, ty in ((mot, duong[:1], s1), (ba, duong[:3], s3)):
        if f is None:
            continue
        ev = f["evidence"]
        # Tỷ trọng nằm trong (0, 100] và khớp phép tính chính xác tới độ làm tròn một chữ số thập phân.
        assert 0 < ev["tỷ_lệ_%"] <= 100
        assert abs(ev["tỷ_lệ_%"] - float(ty * 100)) <= 0.05 + 1e-9
        # Mẫu số là tổng số dư DƯƠNG: số âm và số chưa biết không góp vào.
        assert ev["tổng_phải_thu"] == tong
        assert f["money_impact"] == sum(top)
        assert f["severity"] in MUC_DO
        # Có dòng chưa biết số dư thì bằng chứng phải nói ra, không có thì không bịa khoá.
        assert ev.get("khách_chưa_có_số_dư", 0) == chua_biet
    if mot is not None:
        assert mot["evidence"]["số_dư"] == duong[0]
    if ba is not None:
        assert ba["evidence"]["số_dư"] == duong[:3]


# ---------------------------------------------------------------------------
# Cảnh báo tập trung: khớp phép tính chính xác
# ---------------------------------------------------------------------------

@CAU_HINH
@given(danh_sach_so_du(toi_da=1_000))
def test_canh_bao_khop_phep_tinh_chinh_xac_so_vua(gia_tri):
    """Số vừa, có số âm, số 0 và chưa biết trộn lẫn: báo đúng khi và chỉ khi đạt ngưỡng."""
    _doi_chieu_phep_tinh(gia_tri)


@CAU_HINH
@given(danh_sach_so_du(toi_da=TOI_DA))
def test_canh_bao_khop_phep_tinh_chinh_xac_so_lon_toi_1e13(gia_tri):
    """Một khoản tới 10^13, tổng tới 1,2.10^14: không tràn, không mất chữ số nào ở tổng hay ở tỷ trọng."""
    _doi_chieu_phep_tinh(gia_tri)


@CAU_HINH
@given(GIA_TRI_IT_KHAC_NHAU)
def test_canh_bao_khop_phep_tinh_chinh_xac_khi_hay_cham_dung_bien(gia_tri):
    """Chỉ sáu giá trị khác nhau nên tổng bằng đúng 5 lần (hoặc 2 lần) số lớn nhất xảy ra liên tục."""
    _doi_chieu_phep_tinh(gia_tri)


@CAU_HINH
@given(m=st.integers(2, 10 ** 12))
def test_bien_20_phan_tram_mot_khach_dung_bang_tren_mot_don_vi_duoi_mot_don_vi(m):
    """
    Năm khách bằng nhau là đúng 20%: PHẢI báo (`>=`). Thêm một đồng cho khách đầu thì báo. Sáu khách, năm khách bằng
    nhau và một khách hai đồng (nhỏ nhất còn được tính) thì tỷ trọng kém 20% một chút: KHÔNG báo.
    """
    dung_bang, _ = tap_trung(audit_partners(dung_khach([m] * 5)))
    tren, _ = tap_trung(audit_partners(dung_khach([m + 1] + [m] * 4)))
    duoi, _ = tap_trung(audit_partners(dung_khach([m] * 5 + [2])))
    assert dung_bang is not None and dung_bang["evidence"]["tỷ_lệ_%"] == 20.0
    assert tren is not None
    assert duoi is None


@CAU_HINH
@given(m=st.integers(2, 10 ** 12))
def test_bien_50_phan_tram_ba_khach_dung_bang_tren_mot_don_vi_duoi_mot_don_vi(m):
    """
    Sáu khách bằng nhau: ba khách đầu đúng 50%, PHẢI báo, còn một khách chỉ 16,7% nên không có cảnh báo 'một khách'.
    Thêm một đồng thì báo. Thêm khách thứ bảy hai đồng thì ba khách đầu kém 50% một chút: KHÔNG báo.
    """
    mot, dung_bang = tap_trung(audit_partners(dung_khach([m] * 6)))
    _, tren = tap_trung(audit_partners(dung_khach([m + 1] + [m] * 5)))
    mot_duoi, duoi = tap_trung(audit_partners(dung_khach([m] * 6 + [2])))
    assert mot is None
    assert dung_bang is not None and dung_bang["evidence"]["tỷ_lệ_%"] == 50.0
    assert tren is not None
    assert duoi is None and mot_duoi is None


def test_nguong_trong_ma_khop_hang_so_cua_file_test():
    """
    Ngưỡng 20% và 50% do team đặt, chưa có kế toán xác nhận. Test này đỏ để người đổi ngưỡng biết phải sửa
    `NGUONG_MOT`, `NGUONG_BA` và hai test biên ở file này (số khách dựng ra phụ thuộc ngưỡng) có chủ ý.
    """
    assert receivables._MOT_KHACH_PCT == NGUONG_MOT * 100
    assert receivables._BA_KHACH_PCT == NGUONG_BA * 100
    assert receivables._NGAY_PHAI_THU_CAO == NGAY_PHAI_THU_CAO


@CAU_HINH
@given(danh_sach_so_du(toi_da=1_000, toi_thieu=1), st.integers(0, 10 ** 6))
def test_tang_so_du_khach_lon_nhat_thi_canh_bao_khong_mat_va_ty_trong_khong_giam(gia_tri, them):
    """
    Cộng thêm tiền cho khách lớn nhất thì tỷ trọng của khách đó và của nhóm ba khách đầu chỉ tăng. Nên một
    cảnh báo đang có không được biến mất, và con số tỷ trọng không được giảm.
    """
    gia_tri = list(gia_tri) + [2]                        # bảo đảm có ít nhất một số dư dương
    duong = [(v, i) for i, v in enumerate(gia_tri) if v is not None and v > 0]
    _, i_lon = max(duong)
    tang = list(gia_tri)
    tang[i_lon] += them

    truoc = tap_trung(audit_partners(dung_khach(gia_tri)))
    sau = tap_trung(audit_partners(dung_khach(tang)))
    for f_truoc, f_sau in zip(truoc, sau):
        if f_truoc is not None:
            assert f_sau is not None, "tỷ trọng tăng mà cảnh báo biến mất"
            assert f_sau["evidence"]["tỷ_lệ_%"] >= f_truoc["evidence"]["tỷ_lệ_%"]


@CAU_HINH
@given(st.integers(2, TOI_DA))
def test_mot_khach_duong_duy_nhat_chiem_tron_100_phan_tram(so_du):
    """Một khách thì tỷ trọng là 1, không chia cho 0, không có cảnh báo 'ba khách' vì không có ba khách."""
    mot, ba = tap_trung(audit_partners(dung_khach([so_du])))
    assert mot is not None and mot["evidence"]["tỷ_lệ_%"] == 100.0
    assert mot["money_impact"] == so_du
    assert ba is None


@CAU_HINH
@given(
    st.lists(st.integers(2, TOI_DA), min_size=3, max_size=3),
    st.lists(st.sampled_from([None, 0, -5, -TOI_DA]), max_size=6),
)
def test_ba_khach_duong_thi_ty_trong_cong_lai_bang_mot(ba_so_du, khac):
    """Đúng ba khách còn nợ thì ba tỷ trọng cộng lại là 1: nhóm 'ba khách đầu' là toàn bộ phải thu, mọi số dư khác không đổi điều đó."""
    kq = audit_partners(dung_khach(ba_so_du + khac))
    _, ba = tap_trung(kq)
    assert ba is not None
    assert ba["evidence"]["tỷ_lệ_%"] == 100.0
    assert ba["money_impact"] == sum(ba_so_du) == ba["evidence"]["tổng_phải_thu"]


# ---------------------------------------------------------------------------
# Bất biến
# ---------------------------------------------------------------------------

def _chieu(f) -> str:
    """
    Hình chiếu của một phát hiện, bỏ phần phụ thuộc thứ tự dòng: khi nhiều khách đồng hạng đầu thì khách nào được
    nêu tên là chuyện thứ tự, con số thì không. Cảnh báo tập trung không so mã và tên khách; các loại khác so hết.
    """
    ev = dict(f["evidence"])
    ma = f["code"]
    if f["kind"] == "customer_concentration":
        ev.pop("khách", None)
        ma = None
    return repr((f["kind"], f["severity"], f["title"], f["money_impact"], ma, sorted(ev.items())))


@CAU_HINH
@given(st.data())
def test_ket_qua_khong_phu_thuoc_thu_tu_khach(data):
    """Cùng một tập khách, đảo thứ tự dòng thì cùng các phát hiện và cùng bản tóm tắt (số dư nguyên đồng)."""
    khach = dung_khach(data.draw(danh_sach_so_du()))
    dao = data.draw(st.permutations(khach))
    a = audit_partners(khach)
    b = audit_partners(dao)
    assert sorted(map(_chieu, a["findings"])) == sorted(map(_chieu, b["findings"]))
    assert a["summary"] == b["summary"]


@CAU_HINH
@given(st.data())
def test_them_mot_khach_no_0_khong_doi_ket_qua_cac_khach_khac(data):
    """Một khách số dư 0 không phải là khách nợ: không vào mẫu số, không sinh phát hiện, không đổi thứ tự ai."""
    khach = dung_khach(data.draw(danh_sach_so_du()))
    vi_tri = data.draw(st.integers(0, len(khach)))
    them = copy.deepcopy(khach)
    them.insert(vi_tri, Partner(code="KH-KHONG", name="Khách mẫu không nợ", balance=0.0,
                                role=KHACH_HANG))
    a = audit_partners(khach)
    b = audit_partners(them)
    assert a["findings"] == b["findings"]
    tom_a = {k: v for k, v in a["summary"].items() if k != "số_khách_hàng"}
    tom_b = {k: v for k, v in b["summary"].items() if k != "số_khách_hàng"}
    assert tom_a == tom_b
    assert b["summary"]["số_khách_hàng"] == a["summary"]["số_khách_hàng"] + 1


@CAU_HINH
@given(
    st.lists(so_du_cho(1_000, co_none=False), max_size=SO_KHACH_TOI_DA),
    st.integers(1, 10 ** 6),
)
def test_nhan_moi_so_du_voi_hang_so_nguyen_thi_ty_trong_va_canh_bao_khong_doi(gia_tri, k):
    """
    Đổi đơn vị tiền (nghìn đồng ra đồng, k = 1.000) không đổi tỷ trọng nào, không đổi cảnh báo nào; chỉ các
    khoản tiền nhân lên k lần. Miền k >= 1 và số nguyên: xem đầu file, lý do `_TIEN_TOL` tuyệt đối.
    """
    a = audit_partners(dung_khach(gia_tri))
    b = audit_partners(dung_khach([v * k for v in gia_tri]))
    mot_a, ba_a = tap_trung(a)
    mot_b, ba_b = tap_trung(b)
    assert (mot_a is None) == (mot_b is None)
    assert (ba_a is None) == (ba_b is None)
    for fa, fb in ((mot_a, mot_b), (ba_a, ba_b)):
        if fa is not None:
            assert fa["evidence"]["tỷ_lệ_%"] == fb["evidence"]["tỷ_lệ_%"]
            assert fa["title"] == fb["title"]
            assert fb["money_impact"] == fa["money_impact"] * k
            assert fb["evidence"]["tổng_phải_thu"] == fa["evidence"]["tổng_phải_thu"] * k
    assert a["summary"]["số_phát_hiện"] == b["summary"]["số_phát_hiện"]
    assert b["summary"]["tổng_phải_thu"] == a["summary"]["tổng_phải_thu"] * k


@CAU_HINH
@given(danh_sach_so_du(), danh_sach_so_du())
def test_nha_cung_cap_khong_vao_mau_so_tap_trung_phai_thu(gia_tri_khach, gia_tri_ncc):
    """Phải trả là chuyện khác: thêm nhà cung cấp không đổi cảnh báo tập trung hay tổng phải thu của khách."""
    khach = dung_khach(gia_tri_khach)
    co = audit_partners(khach, dung_ncc(gia_tri_ncc))
    khong = audit_partners(khach, [])
    assert tap_trung(co) == tap_trung(khong)
    assert co["summary"]["tổng_phải_thu"] == khong["summary"]["tổng_phải_thu"]
    # Phải trả cộng chính xác các số dư dương của nhà cung cấp, và số âm không bị gộp vào.
    assert co["summary"]["tổng_phải_trả"] == sum(v for v in gia_tri_ncc if v is not None and v > 0)


# ---------------------------------------------------------------------------
# Số dư âm: tiền thật nằm sai chỗ, không được làm méo tỷ trọng và không được bị bỏ im lặng
# ---------------------------------------------------------------------------

@CAU_HINH
@given(danh_sach_so_du(toi_da=1_000))
def test_so_du_am_khong_lam_meo_ty_trong_va_moi_so_am_deu_duoc_bao(gia_tri):
    khach = dung_khach(gia_tri)
    co_am = audit_partners(khach)
    khong_am = audit_partners([p for p in khach if p.balance is None or p.balance >= 0])

    # 1. Bỏ hết khách số dư âm đi thì cảnh báo tập trung và tổng phải thu vẫn y nguyên: số âm không vào mẫu số
    #    (cộng cả số âm làm mẫu số teo lại và tỷ trọng vượt 100%).
    assert tap_trung(co_am) == tap_trung(khong_am)
    assert co_am["summary"]["tổng_phải_thu"] == khong_am["summary"]["tổng_phải_thu"]

    # 2. Không im lặng: mỗi khách âm có đúng MỘT phát hiện riêng, quy ra đúng số tiền ngược dấu.
    am = {p.code: p.balance for p in khach if p.balance is not None and p.balance < 0}
    bao = {f["code"]: f for f in co_am["findings"] if f["kind"] == "negative_receivable"}
    assert set(bao) == set(am)
    for ma, so_du in am.items():
        assert bao[ma]["evidence"]["số_dư"] == so_du
        assert bao[ma]["money_impact"] == -so_du


# ---------------------------------------------------------------------------
# Chưa biết khác với 0 (R1)
# ---------------------------------------------------------------------------

@CAU_HINH
@given(danh_sach_so_du(toi_da=1_000, co_none=False), st.integers(1, 3), st.data())
def test_khach_chua_co_so_du_khong_bi_coi_la_0_va_duoc_noi_ra(gia_tri, so_none, data):
    """
    Thêm khách `balance=None`: tổng và tỷ trọng không đổi (không phải số 0 đã đo), nhưng bản tóm tắt phải đếm
    họ, bản ghi chú phải nói thẳng 'chưa biết, không phải bằng 0', và mọi cảnh báo tập trung phải ghi số khách thiếu.
    """
    khach = dung_khach(gia_tri)
    them = copy.deepcopy(khach)
    for j in range(so_none):
        vi_tri = data.draw(st.integers(0, len(them)))
        them.insert(vi_tri, Partner(code=f"KH-CHUA-BIET-{j}", name="Khách mẫu chưa biết",
                                    balance=None, role=KHACH_HANG))
    a = audit_partners(khach)
    b = audit_partners(them)

    assert a["summary"]["khách_chưa_có_số_dư"] == 0          # khoá luôn có mặt, kể cả khi bằng 0
    assert b["summary"]["khách_chưa_có_số_dư"] == so_none
    for khoa in ("tổng_phải_thu", "khách_có_số_dư", "tổng_phải_trả"):
        assert b["summary"][khoa] == a["summary"][khoa]

    assert len(a["summary"]["không_phân_tích_được"]) == 1
    ghi_chu = b["summary"]["không_phân_tích_được"]
    assert len(ghi_chu) == 2
    assert f"{so_none} khách hàng" in ghi_chu[1] and "không phải bằng 0" in ghi_chu[1]

    mong_doi = copy.deepcopy(a["findings"])
    for f in mong_doi:
        if f["kind"] == "customer_concentration":
            f["evidence"]["khách_chưa_có_số_dư"] = so_none
    assert b["findings"] == mong_doi


@CAU_HINH
@given(st.lists(st.sampled_from([None, 0, -2, -7, -TOI_DA]), max_size=SO_KHACH_TOI_DA))
def test_khong_co_so_du_duong_nao_thi_khong_chia_cho_0_va_khong_bia_tap_trung(gia_tri):
    """Rỗng, toàn 0, toàn âm, toàn chưa biết: trả kết quả bình thường, không cảnh báo tập trung, không ngoại lệ."""
    kq = audit_partners(dung_khach(gia_tri))
    assert tap_trung(kq) == (None, None)
    assert kq["summary"]["tổng_phải_thu"] == 0
    assert kq["summary"]["số_khách_hàng"] == len(gia_tri)
    chua_biet = sum(1 for v in gia_tri if v is None)
    assert kq["summary"]["khách_chưa_có_số_dư"] == chua_biet
    if chua_biet:
        # Toàn bộ khách chưa biết thì tổng 0 KHÔNG phải kết quả đo: bản ghi chú phải nói ra.
        assert any("CHƯA CÓ số dư" in dong for dong in kq["summary"]["không_phân_tích_được"])


def test_danh_sach_rong_tra_ket_qua_noi_ro_khong_ngoai_le():
    kq = audit_partners([])
    assert kq["findings"] == []
    assert kq["summary"]["số_khách_hàng"] == 0
    assert kq["summary"]["khách_chưa_có_số_dư"] == 0 == kq["summary"]["nhà_cung_cấp_chưa_có_số_dư"]
    assert kq["summary"]["số_phát_hiện"] == 0
    assert kq["summary"]["không_phân_tích_được"], "giới hạn 'không có tuổi nợ' phải luôn được nói ra"


# ---------------------------------------------------------------------------
# Hình dạng, tất định, không sửa đầu vào
# ---------------------------------------------------------------------------

_TEN = ["Khách mẫu", "CÔNG TY TNHH MẪU", "Hộ kinh doanh mẫu"]
# Mã số thuế bịa: hợp lệ, sai số kiểm tra, sai khuôn, số định danh 12 số, và hai mã trùng nhau giữa hai danh sách.
_MST = ["", "0991234566", "9902000029", "0991234562", "12345", "990000000001"]
_SO_DU_DAY_DU = st.one_of(
    st.none(),
    st.integers(-TOI_DA, TOI_DA),
    st.floats(-1e13, 1e13, allow_nan=False, allow_infinity=False),
)


@st.composite
def doi_tac_day_du(draw, tien_to, vai_tro):
    ra = []
    for i in range(draw(st.integers(0, 8))):
        ra.append(Partner(
            code=f"{tien_to}{i:03d}", name=draw(st.sampled_from(_TEN)), balance=draw(_SO_DU_DAY_DU),
            tax_id=draw(st.sampled_from(_MST)), role=vai_tro,
        ))
    return ra


_GIA_VON = st.one_of(st.none(), st.just(0), st.integers(-10, -1), st.integers(1, 10 ** 10))
_DAU_VAO = (doi_tac_day_du("KH", KHACH_HANG), doi_tac_day_du("NCC", NHA_CUNG_CAP), _GIA_VON)


@CAU_HINH
@given(*_DAU_VAO)
def test_tat_dinh_va_khong_sua_dau_vao(khach, ncc, gia_von):
    """Gọi hai lần ra cùng kết quả, và danh sách đưa vào không bị sắp xếp lại hay sửa tại chỗ."""
    truoc = copy.deepcopy((khach, ncc))
    a = audit_partners(khach, ncc, gia_von_moi_ngay=gia_von)
    b = audit_partners(khach, ncc, gia_von_moi_ngay=gia_von)
    assert a == b
    assert (khach, ncc) == truoc


@CAU_HINH
@given(*_DAU_VAO)
def test_hinh_dang_ket_qua_va_thu_tu_nang_truoc_nhieu_tien_truoc(khach, ncc, gia_von):
    """Mọi đầu vào đều ra đúng hình dạng chung của phát hiện, bản tóm tắt nhất quán, và thứ tự nặng trước, nhiều tiền trước."""
    kq = audit_partners(khach, ncc, gia_von_moi_ngay=gia_von)
    fs, tom = kq["findings"], kq["summary"]
    for f in fs:
        assert set(f) == {"kind", "severity", "code", "product", "unit",
                          "title", "evidence", "money_impact", "suggestion"}
        assert f["severity"] in MUC_DO
        assert f["money_impact"] is None or (isinstance(f["money_impact"], int) and f["money_impact"] >= 0)
    hang = {m: i for i, m in enumerate(MUC_DO)}
    khoa = [(hang[f["severity"]], -(f["money_impact"] or 0)) for f in fs]
    assert khoa == sorted(khoa)

    assert tom["số_phát_hiện"] == len(fs)
    assert tom["số_khách_hàng"] == len(khach) and tom["số_nhà_cung_cấp"] == len(ncc)
    assert tom["khách_chưa_có_số_dư"] == sum(1 for p in khach if p.balance is None)
    assert tom["nhà_cung_cấp_chưa_có_số_dư"] == sum(1 for p in ncc if p.balance is None)
    assert tom["tổng_phải_thu"] >= 0 and tom["tổng_phải_trả"] >= 0
    # Giá vốn mỗi ngày chỉ có nghĩa khi dương: không dương thì KHÔNG có khoá, không phải khoá bằng 0.
    assert ("phải_thu_quy_ra_ngày" in tom) == bool(gia_von and gia_von > 0)


@CAU_HINH
@given(g=st.integers(1, 10 ** 9), lech=st.integers(-3, 3))
def test_bien_90_ngay_gia_von_dung_bang_thi_bao_kem_mot_don_vi_thi_khong(g, lech):
    """Phải thu đúng bằng 90 ngày giá vốn thì báo (`>=`); thiếu một đồng thì không."""
    tong = 90 * g + lech
    kq = audit_partners(dung_khach([tong]), gia_von_moi_ngay=g)
    co_bao = any(f["kind"] == "receivable_days_high" for f in kq["findings"])
    assert co_bao == (tong >= NGAY_PHAI_THU_CAO * g)
    assert abs(kq["summary"]["phải_thu_quy_ra_ngày"] - float(Fraction(tong, g))) <= 0.05 + 1e-9


# ---------------------------------------------------------------------------
# Vốn lưu động
# ---------------------------------------------------------------------------

@CAU_HINH
@given(
    phai_thu=st.integers(0, TOI_DA), phai_tra=st.integers(0, TOI_DA), ton_kho=st.integers(0, TOI_DA),
    gia_von=st.one_of(st.none(), st.just(0), st.integers(-10, -1), st.integers(1, 10 ** 10)),
)
def test_von_luu_dong_ket_dung_so_hoc_va_chi_quy_ngay_khi_co_gia_von_duong(
    phai_thu, phai_tra, ton_kho, gia_von
):
    kq = suc_khoe_von_luu_dong(phai_thu=phai_thu, phai_tra=phai_tra, ton_kho=ton_kho,
                               gia_von_moi_ngay=gia_von)
    ket = phai_thu + ton_kho - phai_tra
    assert kq["vốn_lưu_động_kẹt"] == ket
    assert (kq["phải_thu"], kq["tồn_kho"], kq["phải_trả"]) == (phai_thu, ton_kho, phai_tra)
    if not gia_von or gia_von <= 0:
        # Không có giá vốn thì chỉ có ba con số tuyệt đối. Không chia cho 0, không điền 0 ngày.
        assert set(kq) == {"phải_thu", "tồn_kho", "phải_trả", "vốn_lưu_động_kẹt"}
        return
    for khoa, tu in (("phải_thu_ngày", phai_thu), ("tồn_kho_ngày", ton_kho),
                     ("phải_trả_ngày", phai_tra), ("chu_kỳ_tiền_mặt_ngày", ket)):
        assert abs(kq[khoa] - float(Fraction(tu, gia_von))) <= 0.05 + 1e-9
