"""
tests/test_a9_loc_ten_sau_cum_mo_ta.py — tên khách đứng sau cụm mô tả công khai ("vận tải", "cổ phần"...) phải bị xoá khỏi truy vấn web (KH90 A9, brain#327; R2).

VÌ SAO CÓ FILE NÀY
------------------
Từ BR-26 (15/11/2026) sau từ đánh dấu đối tác ("công ty", "khách hàng"...) tên viết thường bị xoá. Nhưng các từ mô tả ("vận tải", "xây dựng", "cổ phần", "mới thành lập") nằm trong danh sách từ thông
dụng nên DỪNG vòng quét: "công ty vận tải minh long có phải nộp thuế không" đi nguyên văn tới bộ tìm kiếm, kèm tên khách. Đặc tả đã chốt 12/11 (kanzo #230, mục f) bảo GIỮ cụm mô tả rồi quét TIẾP, không đếm
vào ba từ lạ. Chỗ đó chưa từng được làm.

GIỚI HẠN CỦA BỘ ĐO (đọc trước khi tin con số): các câu dưới đây do chính người viết luật bịa, nên 0 rò lọt trên chúng là cận trên lạc quan; và mọi cụm mô tả/tên đều do ta nghĩ ra, trong khi
khách thật gõ những cụm ta chưa nghĩ tới. Số đáng tin là chế độ bóng trên câu hỏi thật (A6, #208).
"""

from __future__ import annotations

import itertools

import pytest

from src.core import retrieval_policy as rp
from src.core.retrieval_policy import _CUM_MO_TA, loc_truy_van_web

# ---------------------------------------------------------------------------
# Ca cụ thể
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("vao,ra", [
    # Tên viết thường và viết hoa sau cụm mô tả: xoá.
    ("công ty vận tải minh long có phải nộp thuế không", "công ty vận tải có phải nộp thuế không"),
    ("công ty vận tải Minh Long có phải nộp thuế không", "công ty vận tải có phải nộp thuế không"),
    ("công ty TNHH vận tải Minh Long xuất hoá đơn", "công ty TNHH vận tải xuất hoá đơn"),
    ("công ty cổ phần thương mại minh long có bắt buộc không", "công ty cổ phần thương mại có bắt buộc không"),
    ("nhà cung cấp dịch vụ vận tải minh phát có phải", "nhà cung cấp dịch vụ vận tải có phải"),
    ("khách hàng nhỏ và vừa hà nam phải nộp thuế", "khách hàng nhỏ và vừa phải nộp thuế"),
    ("công ty mới minh long thành lập", "công ty mới thành lập"),
    ("công ty vận tải xây dựng minh long nộp thuế", "công ty vận tải xây dựng nộp thuế"),
    ("khách hàng cá nhân minh long mua dầu có xuất hoá đơn không", "khách hàng cá nhân mua dầu có xuất hoá đơn không"),
])
def test_ten_sau_cum_mo_ta_bi_xoa(vao, ra):
    assert loc_truy_van_web(vao) == ra


@pytest.mark.parametrize("cau", [
    # GIỮ NGUYÊN theo đặc tả (kanzo #230).
    "công ty của tôi nộp thuế gì",
    "công ty vận tải phải nộp thuế gì",
    "khách hàng cá nhân mua dầu có xuất hoá đơn không",
    "công ty mới thành lập phải nộp thuế gì",
    "công ty TNHH: thuế nào phát sinh",
    # Cụm mô tả không còn bị coi là tên: trước A9 "xây dựng" mất khỏi truy vấn này.
    "công ty xây dựng cầu đường quốc lộ miền bắc phải nộp thuế gì",
    "công ty cổ phần phải nộp thuế gì",
    "công ty cho thuê phải nộp thuế gì",
    "công ty xăng dầu phải xuất hoá đơn không",
    "doanh nghiệp nhỏ và vừa được giảm thuế gì",
    "công ty vận tải",
    "khách hàng nước ngoài mua hàng có phải nộp thuế không",
])
def test_cau_cong_khai_khong_ten_di_nguyen_van(cau):
    assert loc_truy_van_web(cau) == cau


def test_xay_dung_khong_con_bi_coi_la_hai_tu_ten():
    """Trước A9: "xây" và "dựng" là hai từ lạ, bị xoá và tính vào ba từ cho phép. Nay là cụm mô tả: giữ, và không tính."""
    assert loc_truy_van_web("công ty xây dựng phải nộp thuế gì") == "công ty xây dựng phải nộp thuế gì"
    assert rp._xoa_ten_rieng("công ty xây dựng phải nộp thuế gì", ()) == "công ty phải nộp thuế gì", "bản cũ (không có cụm mô tả) xoá oan"


def test_cum_mo_ta_khong_dem_vao_ba_tu_la():
    """Ba từ tên sau cụm mô tả vẫn được xoá (cụm không ăn vào hạn mức), từ lạ thứ tư thì không gửi."""
    assert loc_truy_van_web("công ty vận tải xây dựng minh long phát nộp thuế") == "công ty vận tải xây dựng nộp thuế"
    assert loc_truy_van_web("công ty vận tải minh long phát đạt nộp thuế") == "", "bốn từ lạ: fail-closed"


def test_tu_lap_di_lap_lai_cum_mo_ta_khong_treo_vong_lap():
    cau = "công ty " + "vận tải " * 200 + "minh long nộp thuế"
    assert loc_truy_van_web(cau).endswith("nộp thuế") and "minh" not in loc_truy_van_web(cau)


def test_dau_cau_sau_ten_la_het_menh_de_khong_quet_sang_menh_de_khac():
    """"công ty minh long, vận tải xyz": dấu phẩy sau tên là hết mệnh đề; cụm "vận tải" ở mệnh đề sau không kéo vòng quét đi tiếp."""
    assert loc_truy_van_web("công ty minh long, vận tải xyz nộp thuế") == "công ty vận tải xyz nộp thuế"


def test_dau_cau_sau_cum_mo_ta_cung_dung_vong_quet():
    assert loc_truy_van_web("công ty vận tải, minh long ở hà nội") == "công ty vận tải, minh long ở hà nội", "chỗ hở đã ghi trong docstring: dấu phẩy có thể là danh sách tên"


def test_ten_cum_mo_ta_sap_xep_dai_truoc():
    do_dai = [len(c) for c in _CUM_MO_TA]
    assert do_dai == sorted(do_dai, reverse=True), "cụm dài phải thử trước: 'mới thành lập' trước 'mới'"
    assert ("mới", "thành", "lập") in _CUM_MO_TA and ("mới",) in _CUM_MO_TA


def test_khong_dua_vao_cum_nhung_tu_hay_lam_ten():
    """Cấm theo đặc tả #230: thêm một từ hay làm tên vào cụm mô tả là mở lỗ R2."""
    cam = {"phát", "tân", "đại", "đạt", "an", "bình", "hưng", "việt", "nam", "long", "minh", "hà", "hải", "thế", "sao", "huy", "bảo", "hoà", "thanh", "vân",
           "gia", "tài", "chính", "lý", "mai", "thương", "tư", "nhân", "trung"}
    # Không có mục ĐƠN nào là từ hay làm tên; từ hay làm tên chỉ được đứng trong một CỤM thông dụng đã duyệt từng cái (A9b).
    assert not any(len(c) == 1 and c[0] in cam for c in _CUM_MO_TA), [c for c in _CUM_MO_TA if len(c) == 1 and c[0] in cam]
    duoc_duyet = {("tài", "chính"), ("bảo", "hiểm"), ("đại", "lý"), ("gia", "công"), ("tư", "nhân"), ("cá", "nhân"), ("thương", "mại"), ("hữu", "hạn"), ("trách", "nhiệm", "hữu", "hạn")}
    chua_ten = {c for c in _CUM_MO_TA if len(c) > 1 and cam & set(c)}
    assert chua_ten <= duoc_duyet, chua_ten - duoc_duyet
    assert ("thành",) not in _CUM_MO_TA, '"thành" chỉ được đứng trong cụm "mới thành lập", không đứng riêng'


# ---------------------------------------------------------------------------
# Đo: bộ sinh ca có tên và không tên
# ---------------------------------------------------------------------------

TU_DANH_DAU = ["công ty", "khách hàng", "nhà cung cấp", "đối tác", "nhà xe"]
MO_TA = [" ".join(c) for c in _CUM_MO_TA]
DUOI = ["phải nộp thuế gì", "có phải xuất hoá đơn không", "kê khai thuế GTGT thế nào", "có bắt buộc không"]
# Tên mà luật hiện có CÓ THỂ xoá: không chứa từ nào của `_TU_THONG_DUNG` (từ đó dừng vòng quét) và không quá ba từ viết thường.
TEN = ["minh long", "minh long phát", "hoàng phát", "minh đạt", "Minh Long", "Hoàng Gia Phát", "hoàng gia", "thanh vân", "mai linh", "tài lộc", "bảo ngọc"]


def _loc(q: str, cum=_CUM_MO_TA) -> str:
    try:
        return rp._xoa_ten_rieng(q, cum)
    except rp._KhongLocSach:
        return ""


_TU_MO_TA = {t for c in _CUM_MO_TA for t in c}


def _co_ten_lot(ra: str, ten: str) -> bool:
    """Tên còn trong kết quả. Âm tiết của tên trùng một từ của cụm mô tả công khai ("gia" của "gia công") không tính là lọt: nó là cụm mô tả đứng đúng chỗ."""
    return any(t.lower() in ra.lower().split() for t in ten.split() if t.lower() not in _TU_MO_TA)


CA_CO_TEN = [(f"{d} {m} {t} {duoi}", t) for d, m, t, duoi in itertools.product(TU_DANH_DAU, MO_TA, TEN, DUOI)]
CA_KHONG_TEN = [f"{d} {m} {duoi}" for d, m, duoi in itertools.product(TU_DANH_DAU, MO_TA, DUOI)]


def test_do_ro_lot_tren_ca_co_ten_moi_it_hon_cu_va_bang_khong():
    cu = sum(1 for q, t in CA_CO_TEN if _co_ten_lot(_loc(q, ()), t))
    moi = sum(1 for q, t in CA_CO_TEN if _co_ten_lot(_loc(q), t))
    assert len(CA_CO_TEN) >= 1000
    assert cu > 0.5 * len(CA_CO_TEN), "luật cũ phải để lọt nhiều tên sau cụm mô tả, nếu không bộ ca này không đo đúng chỗ"
    assert moi == 0, f"{moi}/{len(CA_CO_TEN)} tên còn lọt sau khi giữ cụm mô tả và quét tiếp (cũ: {cu})"


def test_do_chan_oan_tren_ca_khong_ten_bang_khong_va_khong_doi_so_voi_luat_cu():
    doi = [q for q in CA_KHONG_TEN if _loc(q) != _loc(q, ())]
    chan_moi = [q for q in CA_KHONG_TEN if _loc(q) == "" and _loc(q, ()) != ""]
    assert len(CA_KHONG_TEN) >= 300
    assert not chan_moi, f"chặn oan mới: {chan_moi[:3]}"
    # Khác luật cũ chỉ được là CẢI THIỆN: cụm mô tả không còn bị xoá oan. Mỗi câu khác phải GIỮ NGUYÊN câu gốc (không có tên để xoá).
    assert all(_loc(q) == q for q in CA_KHONG_TEN), [q for q in CA_KHONG_TEN if _loc(q) != q][:3]
    assert len(doi) <= len(CA_KHONG_TEN)


def test_tong_so_ca_do_duoc_noi_ro():
    print(f"\nca có tên: {len(CA_CO_TEN)}, ca không tên: {len(CA_KHONG_TEN)}")
    assert len(CA_CO_TEN) == len(TU_DANH_DAU) * len(MO_TA) * len(TEN) * len(DUOI)


# ---------------------------------------------------------------------------
# Công cụ đo trên kho câu hỏi của repo
# ---------------------------------------------------------------------------

def test_cong_cu_do_chay_duoc_va_khong_co_chan_oan_moi():
    from offline_training import do_loc_ten

    r = do_loc_ten.do()
    assert r["tong"] > 1000 and r["cong_khai_co_tu_danh_dau"] >= 20, "kho câu hỏi phải có đủ câu để phép đo có nghĩa"
    assert r["chan_moi"] == []
    assert r["khac_nhau"] == [], f"luật mới đổi câu công khai trong kho: {r['khac_nhau'][:2]}"
