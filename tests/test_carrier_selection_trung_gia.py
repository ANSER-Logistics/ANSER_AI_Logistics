"""
tests/test_carrier_selection_trung_gia.py — một nhà xe, nhiều giá chào (issue #37).

VÌ SAO CÓ FILE NÀY
------------------
`select_carrier` dựng bảng "mỗi nhà xe một giá" bằng

    offers_by_carrier = {o.carrier_id: o for o in offers}

Nhà xe có hai giá chào thì giá ĐỨNG SAU đè giá đứng trước — im lặng, không cảnh
báo, không log. Kết quả xếp hạng phụ thuộc THỨ TỰ các dòng trong dữ liệu nguồn,
một thứ không ai nhìn thấy, và báo giá gửi khách có thể dựa trên giá sai. Cùng
hình dạng với BR-01 (một phụ phí bị bỏ im lặng làm sai báo giá).

Từ PR #41, n8n lọc giá chào theo đúng tuyến trước khi gửi sang Brain, nên mỗi
lời gọi chỉ chứa giá của MỘT tuyến + MỘT loại xe. Hai giá cho cùng nhà xe trong
một lời gọi nghĩa là DỮ LIỆU NGUỒN BỊ TRÙNG (hai dòng cùng carrier_id + route_id
+ loại xe còn hiệu lực trong bảng CarrierQuotes).

HÀNH VI
-------
Nhà xe có hơn một giá chào KHÁC NHAU -> LOẠI khỏi xếp hạng, ghi vào `rejected`
kèm lý do tiếng Việt liệt kê các giá. KHÔNG tự chọn giá thấp nhất / mới nhất:
đó là quy tắc nghiệp vụ, thuộc quyền chủ dự án (issue #37, mục "Ngoài phạm vi").

Hai dòng GIỐNG HỆT (cùng nhà xe, cùng giá, cùng `valid_to`) thì GỘP làm một
(chủ dự án uỷ quyền chốt 15/11/2026). Gộp không phải chọn: không có giá nào bị
bỏ, chỉ một dòng nhập lặp được đếm một lần — kết quả y hệt như dữ liệu chỉ có
một dòng. Cùng giá nhưng khác `valid_to` KHÔNG phải giống hệt (hai hạn hiệu lực
khác nhau, không biết hạn nào đúng) nên vẫn bị loại.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.core.carrier_selection import (
    Carrier,
    QuoteOffer,
    RouteRequest,
    select_carrier,
)


def _req() -> RouteRequest:
    return RouteRequest(origin="Hà Nội", destination="Bắc Ninh", vehicle_type="5T")


def _xe(cid: str, **kw) -> Carrier:
    return Carrier(id=cid, name=f"Nhà xe {cid}", vehicle_types={"5T"},
                   credit_days=30, **kw)


def _id_xep_hang(kq: dict) -> list:
    return [r["carrier_id"] for r in kq["ranked"]]


def _loai(kq: dict, cid) -> list[dict]:
    return [r for r in kq["rejected"] if r["carrier_id"] == cid]


# ---------------------------------------------------------------------------
# Ca chính của issue: tái hiện, phải ĐỎ trên mã cũ
# ---------------------------------------------------------------------------

def test_nha_xe_hai_gia_chao_bi_LOAI_khong_duoc_xep_hang():
    kq = select_carrier(
        [_xe("C001"), _xe("C002")],
        [QuoteOffer("C001", 3_500_000), QuoteOffer("C002", 3_300_000),
         QuoteOffer("C001", 1_800_000)],
        _req(),
    )
    assert _id_xep_hang(kq) == ["C002"], (
        "C001 có hai giá chào mà vẫn được xếp hạng — Brain đã tự chọn một giá"
    )
    loai = _loai(kq, "C001")
    assert len(loai) == 1
    ly_do = loai[0]["reason"]
    assert "2 giá chào" in ly_do
    # Người đọc phải thấy ĐỦ các giá để biết sửa dòng nào trong dữ liệu nguồn.
    assert "3.500.000" in ly_do and "1.800.000" in ly_do
    assert "Hà Nội → Bắc Ninh" in ly_do
    assert "dữ liệu nguồn" in ly_do


def test_ket_qua_khong_phu_thuoc_thu_tu_dong():
    """Mã cũ: đảo thứ tự hai giá của C001 là đổi giá C001 được dùng, và có thể
    đổi luôn nhà xe đứng đầu. Thứ tự dòng trong bảng nguồn không phải dữ liệu."""
    xe = [_xe("C001"), _xe("C002")]
    xuoi = select_carrier(
        xe, [QuoteOffer("C001", 3_500_000), QuoteOffer("C001", 1_800_000),
             QuoteOffer("C002", 3_300_000)], _req())
    nguoc = select_carrier(
        xe, [QuoteOffer("C001", 1_800_000), QuoteOffer("C001", 3_500_000),
             QuoteOffer("C002", 3_300_000)], _req())
    assert xuoi == nguoc


def test_gia_cua_nha_xe_trung_khong_lot_vao_chuan_hoa_gia_cua_nha_xe_khac():
    """Điểm giá = giá thấp nhất trong nhóm / giá hãng này. Nếu giá 500.000 của
    nhà xe bị loại vẫn nằm trong nhóm, C002 sẽ chỉ được 0,5 điểm giá thay vì 1."""
    kq = select_carrier(
        [_xe("C001"), _xe("C002"), _xe("C003")],
        [QuoteOffer("C001", 500_000), QuoteOffer("C001", 2_000_000),
         QuoteOffer("C002", 1_000_000), QuoteOffer("C003", 1_250_000)],
        _req(),
    )
    diem_gia = {
        r["carrier_id"]: next(c["normalized"] for c in r["criteria"]
                              if c["criterion"] == "price")
        for r in kq["ranked"]
    }
    assert diem_gia == {"C002": pytest.approx(1.0), "C003": pytest.approx(0.8)}


# ---------------------------------------------------------------------------
# Biên
# ---------------------------------------------------------------------------

def test_ba_gia_chao_thi_bao_dung_so_luong():
    kq = select_carrier(
        [_xe("C001"), _xe("C002")],
        [QuoteOffer("C001", 1_000_000), QuoteOffer("C001", 1_100_000),
         QuoteOffer("C001", 1_200_000), QuoteOffer("C002", 1_050_000)],
        _req(),
    )
    assert _id_xep_hang(kq) == ["C002"]
    assert "3 giá chào" in _loai(kq, "C001")[0]["reason"]


def test_nha_xe_duy_nhat_bi_trung_thi_khong_ai_duoc_xep_hang():
    kq = select_carrier(
        [_xe("C001")],
        [QuoteOffer("C001", 3_500_000), QuoteOffer("C001", 3_600_000)],
        _req(),
    )
    assert kq["ranked"] == []
    assert len(_loai(kq, "C001")) == 1
    assert kq["explain"]["note"]


def test_hai_dong_trung_y_het_thi_gop_va_xep_hang_binh_thuong():
    """Trước 15/11/2026 test này khoá điều NGƯỢC LẠI ("trùng y hệt vẫn bị loại").
    Chủ dự án chốt: hai dòng giống hệt (cùng nhà xe, cùng giá) là một giá chào
    nhập lặp, không phải hai giá để phải chọn — gộp làm một. Đổi test vì quy tắc
    nghiệp vụ đổi, không phải vì mã sai."""
    kq = select_carrier(
        [_xe("C001"), _xe("C002")],
        [QuoteOffer("C001", 3_500_000), QuoteOffer("C001", 3_500_000),
         QuoteOffer("C002", 3_300_000)],
        _req(),
    )
    assert sorted(_id_xep_hang(kq)) == ["C001", "C002"]
    assert kq["rejected"] == []


def test_gop_dong_trung_cho_ket_qua_y_het_nhu_chi_co_mot_dong():
    """Gộp không được để lại dấu vết trong điểm số: giá của C001 chỉ được đếm
    MỘT lần trong nhóm chuẩn hoá giá, và `offer_price` là giá thật (không nhân đôi)."""
    xe = [_xe("C001"), _xe("C002")]
    lap = select_carrier(
        xe, [QuoteOffer("C001", 3_500_000), QuoteOffer("C001", 3_500_000),
             QuoteOffer("C002", 3_300_000)], _req())
    mot = select_carrier(
        xe, [QuoteOffer("C001", 3_500_000), QuoteOffer("C002", 3_300_000)], _req())
    assert lap == mot
    gia = {r["carrier_id"]: r["offer_price"] for r in lap["ranked"]}
    assert gia == {"C001": 3_500_000, "C002": 3_300_000}


def test_nhieu_dong_trung_y_het_van_gop_thanh_mot():
    kq = select_carrier(
        [_xe("C001"), _xe("C002")],
        [QuoteOffer("C001", 3_500_000)] * 4 + [QuoteOffer("C002", 3_300_000)],
        _req(),
    )
    assert sorted(_id_xep_hang(kq)) == ["C001", "C002"]
    assert kq["rejected"] == []


def test_nha_xe_duy_nhat_nhap_lap_y_het_thi_van_duoc_xep_hang():
    """Biên đối xứng với `test_nha_xe_duy_nhat_bi_trung_thi_khong_ai_duoc_xep_hang`:
    chỉ một nhà xe và hai dòng giống hệt thì không có gì để loại, kết quả không
    được rơi về nhánh "không hãng nào đáp ứng"."""
    kq = select_carrier(
        [_xe("C001")],
        [QuoteOffer("C001", 3_500_000), QuoteOffer("C001", 3_500_000)],
        _req(),
    )
    assert _id_xep_hang(kq) == ["C001"]
    assert kq["rejected"] == []


def test_ba_dong_hai_giong_mot_khac_thi_van_loai_va_khong_liet_ke_trung():
    """Hai dòng 3.500.000 giống hệt + một dòng 1.800.000: vẫn là hai GIÁ khác
    nhau, vẫn loại. Lý do phải nói "2 giá chào" (không phải 3) và mỗi giá xuất
    hiện đúng MỘT lần — liệt kê "3.500.000đ, 3.500.000đ, 1.800.000đ" làm người
    đọc tưởng có ba giá khác nhau."""
    kq = select_carrier(
        [_xe("C001"), _xe("C002")],
        [QuoteOffer("C001", 3_500_000), QuoteOffer("C001", 3_500_000),
         QuoteOffer("C001", 1_800_000), QuoteOffer("C002", 3_300_000)],
        _req(),
    )
    assert _id_xep_hang(kq) == ["C002"]
    loai = _loai(kq, "C001")
    assert len(loai) == 1
    ly_do = loai[0]["reason"]
    assert "2 giá chào" in ly_do
    assert "3 giá chào" not in ly_do
    assert ly_do.count("3.500.000đ") == 1
    assert ly_do.count("1.800.000đ") == 1


def test_ba_dong_hai_giong_mot_khac_khong_phu_thuoc_thu_tu_dong():
    xe = [_xe("C001"), _xe("C002")]
    a = QuoteOffer("C001", 3_500_000)
    b = QuoteOffer("C001", 3_500_000)
    c = QuoteOffer("C001", 1_800_000)
    d = QuoteOffer("C002", 3_300_000)
    ket_qua = [
        select_carrier(xe, thu_tu, _req())
        for thu_tu in ([a, b, c, d], [c, a, b, d], [a, c, d, b], [d, b, c, a])
    ]
    assert all(kq == ket_qua[0] for kq in ket_qua)


def test_cung_gia_cung_valid_to_la_giong_he_thi_gop():
    """`valid_to` là trường duy nhất khác của QuoteOffer ngoài nhà xe và giá.
    Hai dòng trùng cả hạn hiệu lực là giống hệt."""
    kq = select_carrier(
        [_xe("C001"), _xe("C002")],
        [QuoteOffer("C001", 3_500_000, "2026-12-31"),
         QuoteOffer("C001", 3_500_000, "2026-12-31"),
         QuoteOffer("C002", 3_300_000)],
        _req(),
    )
    assert sorted(_id_xep_hang(kq)) == ["C001", "C002"]
    assert kq["rejected"] == []


@pytest.mark.parametrize("han_a, han_b", [
    ("2026-12-31", "2027-03-31"),   # hai hạn khác nhau
    ("2026-12-31", None),           # một dòng có hạn, một dòng không
])
def test_cung_gia_khac_valid_to_khong_phai_giong_he_thi_van_loai(han_a, han_b):
    """Cùng giá nhưng hạn hiệu lực khác nhau: không biết hạn nào đúng, và gộp là
    âm thầm vứt một hạn đi. Giống hệt nghĩa là GIỐNG HỆT — không đoán."""
    kq = select_carrier(
        [_xe("C001"), _xe("C002")],
        [QuoteOffer("C001", 3_500_000, han_a), QuoteOffer("C001", 3_500_000, han_b),
         QuoteOffer("C002", 3_300_000)],
        _req(),
    )
    assert _id_xep_hang(kq) == ["C002"]
    loai = _loai(kq, "C001")
    assert len(loai) == 1
    ly_do = loai[0]["reason"]
    assert "2 giá chào" in ly_do
    # Hai giá chào trông y hệt nhau về tiền: lý do phải chỉ ra chỗ KHÁC (hạn),
    # nếu không người đọc thấy "3.500.000đ, 3.500.000đ" và không hiểu vì sao loại.
    assert "2026-12-31" in ly_do
    if han_b is not None:
        assert han_b in ly_do


def test_giong_he_nhung_khac_kieu_so_nguyen_va_thap_phan_van_gop():
    """JSON gửi 3500000 (int) hay 3500000.0 (float) là cùng một số: `==` của
    Python coi chúng bằng nhau nên vẫn gộp."""
    kq = select_carrier(
        [_xe("C001"), _xe("C002")],
        [QuoteOffer("C001", 3_500_000), QuoteOffer("C001", 3_500_000.0),
         QuoteOffer("C002", 3_300_000)],
        _req(),
    )
    assert sorted(_id_xep_hang(kq)) == ["C001", "C002"]
    assert kq["rejected"] == []


def test_khong_co_xe_phu_hop_thi_bao_ly_do_xe_va_chi_bao_MOT_lan():
    """Ràng buộc loại xe đứng trước: nhà xe không có xe 5T thì giá chào trùng
    hay không cũng không liên quan. Mỗi nhà xe chỉ một dòng trong `rejected`."""
    kq = select_carrier(
        [Carrier(id="C001", name="Nhà xe C001", vehicle_types={"1.5T"}), _xe("C002")],
        [QuoteOffer("C001", 1_000_000), QuoteOffer("C001", 2_000_000),
         QuoteOffer("C002", 3_300_000)],
        _req(),
    )
    loai = _loai(kq, "C001")
    assert len(loai) == 1
    assert "không có xe 5T" in loai[0]["reason"]


def test_nha_xe_mot_gia_khong_bi_anh_huong():
    """Chốt chiều ngược: sửa không được làm loại oan nhà xe bình thường."""
    kq = select_carrier(
        [_xe("C001"), _xe("C002")],
        [QuoteOffer("C001", 3_500_000), QuoteOffer("C002", 3_300_000)],
        _req(),
    )
    assert sorted(_id_xep_hang(kq)) == ["C001", "C002"]
    assert kq["rejected"] == []


# ---------------------------------------------------------------------------
# Qua HTTP — đường Body thật sự đi
# ---------------------------------------------------------------------------

def test_endpoint_carrier_selection_loai_nha_xe_trung_gia():
    client = TestClient(app)
    resp = client.post("/tools/carrier-selection", json={
        "carriers": [
            {"id": "C001", "name": "Nhà xe C001", "vehicle_types": ["5T"]},
            {"id": "C002", "name": "Nhà xe C002", "vehicle_types": ["5T"]},
        ],
        "offers": [
            {"carrier_id": "C001", "price": 3_500_000},
            {"carrier_id": "C001", "price": 1_800_000},
            {"carrier_id": "C002", "price": 3_300_000},
        ],
        "request": {"origin": "Hà Nội", "destination": "Bắc Ninh", "vehicle_type": "5T"},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [r["carrier_id"] for r in body["ranked"]] == ["C002"]
    assert "2 giá chào" in _loai(body, "C001")[0]["reason"]


def test_endpoint_carrier_selection_gop_hai_dong_trung_y_het():
    """Đường Body thật sự đi: hai dòng giống hệt qua JSON (cùng `valid_to`) vẫn
    gộp, nhà xe vẫn được xếp hạng."""
    client = TestClient(app)
    resp = client.post("/tools/carrier-selection", json={
        "carriers": [
            {"id": "C001", "name": "Nhà xe C001", "vehicle_types": ["5T"]},
            {"id": "C002", "name": "Nhà xe C002", "vehicle_types": ["5T"]},
        ],
        "offers": [
            {"carrier_id": "C001", "price": 3_500_000, "valid_to": "2026-12-31"},
            {"carrier_id": "C001", "price": 3_500_000, "valid_to": "2026-12-31"},
            {"carrier_id": "C002", "price": 3_300_000},
        ],
        "request": {"origin": "Hà Nội", "destination": "Bắc Ninh", "vehicle_type": "5T"},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert sorted(r["carrier_id"] for r in body["ranked"]) == ["C001", "C002"]
    assert body["rejected"] == []
