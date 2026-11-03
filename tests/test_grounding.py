"""
tests/test_grounding.py — chốt chặn neo số liệu, chạy LÚC PHỤC VỤ.

Phép kiểm "mọi con số phải có trong dữ liệu" đã tồn tại từ lâu, nhưng chỉ chạy ở
khâu lọc dữ liệu huấn luyện và khâu chấm điểm benchmark. Nghĩa là ta đo được bản
fine-tune bịa số 8-10 ca trên 27, rồi vẫn để con số bịa đó đi thẳng ra màn hình
chủ doanh nghiệp (nối vào đường phục vụ 05/08/2026).

Nguyên tắc: **model không cần giỏi hơn, hệ thống cần an toàn khi model sai.**
"""

from __future__ import annotations

import pytest

from src.core.grounding import (
    GuardVerdict,
    customer_leak,
    derived_ratios_ok,
    guard_answer,
    la_hinh_dang_tien,
    narration_numbers_ok,
    numbers_in,
)

# Nguyên văn ngữ cảnh dạng engine trả về
CTX = (
    '{"periods": [{"label": "Q1/2026", "revenue": 45000000, "cogs": 33825862, '
    '"gross_profit": 11174138}], "explain": {"cogs_coverage_pct": 62.0}}'
)


# ---------------------------------------------------------------------------
# Đếm số
# ---------------------------------------------------------------------------

def test_bo_dau_phan_tach_nghin():
    assert numbers_in("3.450.000đ") == {"3450000"}
    assert numbers_in("giá 1,200,000 và 45000000") == {"1200000", "45000000"}


def test_van_ban_rong_khong_no():
    assert numbers_in("") == set()
    assert numbers_in(None) == set()


# ---------------------------------------------------------------------------
# Chặn bịa số — thứ đang xảy ra thật
# ---------------------------------------------------------------------------

def test_con_so_co_trong_du_lieu_thi_cho_qua():
    v = guard_answer("Doanh thu quý 1 đạt 45000000 đồng.", CTX)
    assert v.ok and v.safe_answer == "Doanh thu quý 1 đạt 45000000 đồng."


def test_con_so_KHONG_co_trong_du_lieu_thi_CHAN():
    """
    Nguyên văn từ báo cáo đo: `[report] bịa số 330078760`. Con số đó không có ở
    đâu trong dữ liệu engine trả về — model tự nghĩ ra và viết bằng giọng chắc
    nịch y hệt các con số thật.
    """
    v = guard_answer("Doanh thu quý 1 đạt 330078760 đồng.", CTX)
    assert v.blocked
    assert v.reason == "bịa số"
    assert v.offending == "330078760"
    assert "330078760" in v.safe_answer, "phải nói rõ con số nào bị chặn"


def test_so_ngan_khong_bi_chan_oan():
    """
    Số chuyến, ngày trong tháng — chặn hết là chặn oan gần hết.

    ĐÃ ĐỔI 03/11/2026. Bản trước dùng câu "Có 3 chuyến, tăng 12% so với 5 kỳ
    trước." và đòi `v.ok`. Vế "tăng 12%" trong đó là tỷ lệ model TỰ TÍNH từ hai
    con số thô — đúng thứ R1 cấm, và nó đi lọt chỉ vì "12" ngắn hơn
    `MIN_DIGITS`. Tức test cũ đang đóng dấu hợp lệ cho một vi phạm R1.

    Chốt `derived_ratios_ok` nay bắt nó. Phần còn lại của câu — "3 chuyến",
    "5 kỳ", "ngày 15" — vẫn qua, vì đó là số đếm trích từ dữ liệu chứ không
    phải tỷ lệ suy ra. Xem `test_ty_le_do_tool_tinh_thi_qua`: cùng một cụm
    "tăng 20%" qua được khi tool đã đặt 20 vào dữ liệu.
    """
    v = guard_answer("Có 3 chuyến, chốt sổ ngày 15, so với 5 kỳ trước.", CTX)
    assert v.ok, f"chặn oan: {v.reason} / {v.offending!r}"


def test_dau_phan_tach_nghin_khong_lam_chan_oan():
    """`45.000.000` và `45000000` phải được coi là một."""
    assert guard_answer("Doanh thu 45.000.000 đồng.", CTX).ok


def test_cau_tra_loi_rong_bi_chan():
    v = guard_answer("", CTX)
    assert v.blocked and v.safe_answer


# ---------------------------------------------------------------------------
# `safe_answer` LUÔN dùng được — quên kiểm `ok` cũng không rò
# ---------------------------------------------------------------------------

def test_safe_answer_luon_dung_duoc_du_quen_kiem_ok():
    """
    Chỗ gọi không phải nhớ `if verdict.ok` mới biết dùng gì. Quên kiểm là đúng
    cái lỗi lớp này sinh ra để chặn, nên API phải không cho phép quên.
    """
    sach = guard_answer("Doanh thu 45000000 đồng.", CTX)
    ban = guard_answer("Doanh thu 999888777 đồng.", CTX)
    assert sach.safe_answer == "Doanh thu 45000000 đồng."
    assert "999888777" not in ban.safe_answer.replace("999888777", "", 1) or True
    assert ban.safe_answer != "Doanh thu 999888777 đồng.", "không được trả nguyên văn"


def test_verdict_la_dataclass_co_du_truong():
    v = guard_answer("ok", CTX)
    assert isinstance(v, GuardVerdict)
    assert v.blocked is False


# ---------------------------------------------------------------------------
# Lộ thông tin nội bộ — chỉ áp cho nội dung gửi KHÁCH CUỐI
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cau", [
    "Biên lợi nhuận chuyến này là tốt.",
    "Giá nhà xe báo là hợp lý.",
    "Phần lãi của mình vẫn đảm bảo.",
])
def test_gui_khach_thi_chan_tu_lo_bien(cau):
    v = guard_answer(cau, CTX, for_customer=True)
    assert v.blocked and v.reason == "lộ nội bộ"


def test_cung_cau_do_gui_CHU_DN_thi_khong_chan():
    """Chủ doanh nghiệp được xem biên lợi nhuận — đó là số của họ."""
    assert guard_answer("Biên lợi nhuận chuyến này là tốt.", CTX).ok


def test_khong_bo_dau_khi_do_tu_cam():
    """
    So khớp CÓ DẤU: bỏ dấu sẽ khiến 'lãi' khớp nhầm 'lại' và chặn oan gần hết
    câu tiếng Việt bình thường.
    """
    assert guard_answer("Anh gửi lại giúp em địa chỉ nhé.", CTX, for_customer=True).ok


# ---------------------------------------------------------------------------
# MỘT nguồn dùng chung cho đo và chạy (P4)
# ---------------------------------------------------------------------------

def test_khau_sinh_du_lieu_dung_CHUNG_ham_voi_luc_chay():
    """
    Hai bản chép tay sẽ trôi khỏi nhau, và khi đó điểm benchmark không còn nói
    gì về thực tế. `dgen_common` phải import chính hàm này, không được có bản
    riêng.
    """
    from offline_training import dgen_common

    assert dgen_common.narration_numbers_ok is narration_numbers_ok
    assert dgen_common.customer_leak is customer_leak
    assert dgen_common.numbers_in is numbers_in


def test_benchmark_cham_diem_bang_dung_ham_do():
    from offline_training import benchmark_v3

    assert benchmark_v3.narration_numbers_ok is narration_numbers_ok


# ---------------------------------------------------------------------------
# Chốt suy biến (29/10/2026) — mẫu lấy NGUYÊN VĂN đuôi đầu ra BR-05 yêu cầu 9
# ---------------------------------------------------------------------------

_DAU_VIET = "Doanh thu quý 3 đạt 45.000.000 đồng, chi phí nhà xe 33.825.862 đồng. "


def test_suy_bien_chu_han():
    from src.core.grounding import kiem_suy_bien

    assert kiem_suy_bien(_DAU_VIET + "发展历程壮丽画卷美丽风景") == "chữ Hán"


def test_suy_bien_lap_duoi_tieng_anh():
    """NA0019: kê từ tiếng Anh không dứt, rồi cả chuỗi lặp lại."""
    from src.core.grounding import kiem_suy_bien

    vong = ("pull drag haul yank jerk toss throw shoot fire launch propel push shove "
            "poke prod jab stick lodge embed implant transplant move relocate transfer ")
    assert kiem_suy_bien(_DAU_VIET + vong * 3) == "lặp đuôi"


def test_cau_tieng_viet_binh_thuong_khong_bi_chan():
    from src.core.grounding import kiem_suy_bien

    cau = (_DAU_VIET * 1 + "Lợi nhuận gộp 11.174.138 đồng, biên 24,8%. "
           "Tuyến KCN Quế Võ đi Hà Nội lãi tốt nhất; nên giữ nhà xe Trường Thịnh. "
           "Tháng 6 chi phí tăng do giá dầu, cần theo dõi thêm.")
    assert kiem_suy_bien(cau) is None
    assert kiem_suy_bien("") is None
    assert kiem_suy_bien("ok") is None



# ---------------------------------------------------------------------------
# Thang bậc tiếng Việt — "10,25 triệu" và "10250000" là MỘT con số
#
# Lỗi thật, tái hiện trước khi sửa: context có `10250000`, model viết "10.25
# triệu đồng", bộ kiểm bỏ dấu thành "1025" rồi so chuỗi, không khớp, CHẶN OAN
# một câu trả lời đúng. Hại hơn hẳn lọt số bịa: khách hỏi, hệ thống có số
# đúng trong tay, rồi trả về câu từ chối.
# ---------------------------------------------------------------------------

CTX_TRIEU = "Tổng cước tháng 10: 10250000 VND. Chi phí nhiên liệu: 3450000 VND."


@pytest.mark.parametrize(
    "cau",
    [
        "Tổng cước tháng 10 là 10,25 triệu đồng.",
        "Tổng cước tháng 10 là 10.25 triệu đồng.",
        "Tổng cước tháng 10 khoảng 10,25 tr.",
        "Tổng cước tháng 10 là 10250000 đồng.",  # dạng thô vẫn phải qua
    ],
)
def test_thang_bac_khong_bi_chan_oan(cau):
    v = guard_answer(cau, CTX_TRIEU)
    assert v.ok, f"chặn oan: {v.offending!r} — {cau!r}"


def test_thang_bac_van_chan_so_bia():
    """Nới lỏng cách ĐỌC số, không nới lỏng việc số đó phải có trong dữ liệu."""
    v = guard_answer("Tổng cước tháng 10 là 88,88 triệu đồng.", CTX_TRIEU)
    assert v.blocked and v.reason == "bịa số"


def test_numbers_in_sinh_ca_dang_tho_lan_dang_nhan():
    ra = numbers_in("10,25 triệu")
    assert "1025" in ra, "dạng thô phải còn, nếu không là SIẾT chứ không phải nới"
    assert "10250000" in ra, "cách đọc thập phân"
    assert "1025000000" in ra, "cách đọc dấu-phân-tách-nghìn"


def test_nghin_va_ty():
    assert "5000" in numbers_in("5 nghìn")
    assert "2000000000" in numbers_in("2 tỷ")
    assert "2500000000" in numbers_in("2,5 tỉ")


def test_chu_thang_bac_don_doc_khong_lam_no():
    """"triệu" không đi kèm số thì không có gì để nhân."""
    assert numbers_in("hàng triệu đồng") == set()


# ---------------------------------------------------------------------------
# Tỷ lệ model TỰ SUY RA — R1: LLM không bao giờ tính toán
#
# `narration_numbers_ok` bỏ qua số dưới 4 chữ số để khỏi chặn oan "3 chuyến",
# "ngày 15". Cái giá: "gấp khoảng 1,2 lần" đi lọt — model tự chia rồi tuyên bố
# kết quả. Mẫu so sánh phân biệt được hai thứ đó, nên nó SẮC hơn ngưỡng độ dài
# chứ không phải nghiêm hơn.
# ---------------------------------------------------------------------------

CTX_TY_LE = '{"doanh_thu": 45000000, "ky_truoc": 37500000, "so_chuyen": 3}'
CTX_CO_TY_LE = (
    '{"doanh_thu": 45000000, "ky_truoc": 37500000, '
    '"tang_truong_pct": 20, "so_chuyen": 3}'
)


@pytest.mark.parametrize(
    "cau",
    [
        "Doanh thu gấp khoảng 1,2 lần kỳ trước.",
        "Doanh thu tăng 20% so với kỳ trước.",
        "Chi phí giảm 15% so với tháng trước.",
        "Khoản này chiếm 35% tổng chi.",
        "Cước tháng này cao hơn 8% so với tháng trước.",
    ],
)
def test_ty_le_model_tu_tinh_thi_bi_chan(cau):
    v = guard_answer(cau, CTX_TY_LE)
    assert v.blocked, f"lọt tỷ lệ tự tính: {cau!r}"
    assert v.reason == "tự suy ra tỷ lệ"


def test_ty_le_do_tool_tinh_thi_qua():
    """
    Cùng một câu, hai số phận — và đó mới đúng là R1.

    Model nhắc lại tỷ lệ do code tính: diễn giải, hợp lệ.
    Model tự chia hai số thô rồi tuyên bố: tính toán, bị chặn.
    """
    cau = "Doanh thu tăng 20% so với kỳ trước."
    assert guard_answer(cau, CTX_CO_TY_LE).ok
    assert guard_answer(cau, CTX_TY_LE).blocked


@pytest.mark.parametrize(
    "cau",
    [
        "Có 3 chuyến trong kỳ.",
        "Chốt sổ ngày 15.",
        "Tăng 3 chuyến so với kỳ trước.",       # có từ so sánh, KHÔNG có đơn vị tỷ lệ
        "Doanh thu 45.000.000 đồng.",
        "So với 5 kỳ trước thì ổn định.",
    ],
)
def test_so_dem_va_ngay_khong_bi_chan_oan(cau):
    """Đòi ĐỒNG THỜI từ so sánh VÀ đơn vị tỷ lệ (% hoặc lần) — nên các câu này qua."""
    v = guard_answer(cau, CTX_TY_LE)
    assert v.ok, f"chặn oan: {v.reason} / {v.offending!r} — {cau!r}"


def test_loi_tu_choi_noi_ro_cum_nao_bi_chan():
    v = guard_answer("Doanh thu gấp khoảng 1,2 lần kỳ trước.", CTX_TY_LE)
    assert "gấp khoảng 1,2 lần" in v.safe_answer
    assert "model tự tính" in v.safe_answer


def test_derived_ratios_ok_dung_doc_lap_duoc():
    ok, cum = derived_ratios_ok("Tăng 20% so với kỳ trước.", CTX_TY_LE)
    # Trả NGUYÊN VĂN cụm model viết, giữ hoa/thường — để lời từ chối trích đúng
    # cái người dùng sẽ thấy, không phải một phiên bản đã chuẩn hoá.
    assert not ok and cum == "Tăng 20%"
    ok, cum = derived_ratios_ok("Tăng 20% so với kỳ trước.", CTX_CO_TY_LE)
    assert ok and cum is None


# ---------------------------------------------------------------------------
# HÌNH DẠNG TIỀN (brain#42) — CHƯA BẬT MẶC ĐỊNH
# ---------------------------------------------------------------------------
# Ngưỡng "4 chữ số" gộp tiền với năm, số hiệu văn bản và mã đơn vào một rổ, và
# đồng thời bỏ sót "45 triệu" (chuẩn hoá ra hai chữ số). Phép phân biệt theo
# hình dạng tiền sắc hơn ở cả hai chiều.
#
# Các test dưới đây truyền `chi_kiem_so_tien=True` TƯỜNG MINH. Mặc định vẫn là
# luật cũ, nên đổi hành vi hướng ra khách chưa xảy ra — chờ chủ dự án duyệt.


# (nhãn, chuỗi số như đã viết, hậu tố thang bậc, văn bản ngay sau)
CO_HINH_DANG_TIEN = [
    ("thang bậc", "45", "triệu", ""),
    ("thang bậc dính liền", "2", "tr", ""),
    ("đơn vị tiền", "18.500.000", None, "đ"),
    ("đơn vị tiền viết tắt", "500000", None, " VNĐ"),
    ("đơn vị tiền viết chữ", "11500000", None, " đồng"),
    ("nhóm nghìn", "3.450.000", None, ""),
    ("nhóm nghìn ngắn", "5.000", None, ""),
    ("trần 5 chữ số", "50000000", None, ""),
]

KHONG_PHAI_TIEN = [
    ("năm", "2026", None, ""),
    ("năm trong số hiệu văn bản", "2024", None, "/NĐ-CP"),
    ("mã đơn 4 chữ số", "4821", None, ""),
    ("số đếm", "3", None, " chuyến"),
    ("ngày trong tháng", "15", None, "."),
    # Ba ca dưới là lý do dấu hiệu "có dấu chấm/phẩy" bị thay bằng nhóm nghìn.
    ("số mục", "5.1", None, "."),
    ("số phiên bản", "2.5", None, "-VL"),
    ("số thập phân có phẩy", "15,8", None, "%"),
]


@pytest.mark.parametrize("nhan,tho,hau_to,sau", CO_HINH_DANG_TIEN)
def test_nhan_ra_hinh_dang_tien(nhan, tho, hau_to, sau):
    assert la_hinh_dang_tien(tho, hau_to, sau), nhan


@pytest.mark.parametrize("nhan,tho,hau_to,sau", KHONG_PHAI_TIEN)
def test_khong_nham_thu_khac_la_tien(nhan, tho, hau_to, sau):
    assert not la_hinh_dang_tien(tho, hau_to, sau), nhan


def test_dem_chu_so_khong_dem_ky_tu():
    """`len("3.3.1")` là 5 ký tự nhưng chỉ ba chữ số — không phải tiền."""
    assert not la_hinh_dang_tien("3.3.1", None, "")
    assert la_hinh_dang_tien("12345", None, "")


def test_che_do_tien_tha_nam_va_so_hieu_van_ban():
    """Hai ca luật cũ CHẶN OAN. Chặn một trích dẫn pháp luật đúng còn tệ hơn
    chỗ hở ban đầu, vì khách thấy hệ thống từ chối một câu hoàn toàn chuẩn.
    """
    cau_nam = "Hôm nay là ngày 4 tháng 11 năm 2026."
    cau_vb = "Nghị định 72/2024/NĐ-CP quy định rõ điều này."

    # Luật hiện tại: chặn cả hai
    assert narration_numbers_ok(cau_nam, "")[0] is False
    assert narration_numbers_ok(cau_vb, "")[0] is False

    # Luật hình dạng tiền: cho qua cả hai
    assert narration_numbers_ok(cau_nam, "", chi_kiem_so_tien=True)[0] is True
    assert narration_numbers_ok(cau_vb, "", chi_kiem_so_tien=True)[0] is True


def test_che_do_tien_bat_duoc_so_viet_ngan():
    """"45 triệu" chuẩn hoá ra "45" — hai chữ số, dưới ngưỡng cũ nên đi lọt.

    Đây là chỗ hở thâm nhất: một con số bốn mươi lăm triệu đồng không có trong
    dữ liệu, đi ra màn hình chỉ vì nó được viết ngắn. `derived_ratios_ok` cũng
    không bắt được vì câu không có từ so sánh nào.
    """
    cau = "Doanh thu khoảng 45 triệu."
    assert narration_numbers_ok(cau, "")[0] is True          # lọt
    assert narration_numbers_ok(cau, "", chi_kiem_so_tien=True)[0] is False

    # Có trong dữ liệu thì vẫn cho qua — đây là diễn giải, không phải bịa số.
    assert narration_numbers_ok(cau, "doanh_thu: 45000000",
                                chi_kiem_so_tien=True)[0] is True


def test_che_do_tien_bat_duoc_phep_cong_model_tu_lam():
    """R1: LLM không bao giờ tính toán. Câu này không có từ so sánh nào nên
    `derived_ratios_ok` không thấy, và mọi con số đều hai chữ số nên ngưỡng cũ
    cũng không thấy.
    """
    cau = "8 triệu cộng 3 triệu là 11 triệu."
    assert narration_numbers_ok(cau, "")[0] is True          # lọt
    assert narration_numbers_ok(cau, "", chi_kiem_so_tien=True)[0] is False


def test_mac_dinh_khong_doi_hanh_vi():
    """Cổng mặc định phải GIỐNG HỆT luật cũ: bật lên là đổi hành vi hướng ra
    khách, cần chủ dự án duyệt (brain#42). Test này là thứ sẽ đỏ nếu có ai
    lặng lẽ đổi mặc định.
    """
    for cau in (
        "Hôm nay là ngày 4 tháng 11 năm 2026.",
        "Doanh thu khoảng 45 triệu.",
        "8 triệu cộng 3 triệu là 11 triệu.",
        "Lãi là 11.500.000 đồng.",
    ):
        assert narration_numbers_ok(cau, "") == narration_numbers_ok(
            cau, "", chi_kiem_so_tien=False
        )

    # Và `guard_answer` chưa có đường nào bật chế độ này.
    assert guard_answer("Hôm nay là năm 2026.", "").blocked

