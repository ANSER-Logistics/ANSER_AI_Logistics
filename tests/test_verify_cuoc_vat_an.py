"""
tests/test_verify_cuoc_vat_an.py — hoá đơn cước mà tờ in CHỈ có dòng TỔNG: đầu ra thật của model phải bị `verify` chặn (#124).

VÌ SAO CÓ FILE NÀY
------------------
Bộ đo VLM (`vlm_hoadon.py`) có biến thể `vat_hidden`: tờ in không có cộng tiền hàng, thuế suất, tiền thuế; đáp án đúng cho ba trường
đó là `None`. Đo 18/11/2026 ở 5 model, ba model tốt nhất (3B, Qwen3-VL-4B, Qwen2.5-VL-7B) đều điền một số khác 0 vào `subtotal` ở cả hai
ca (VH0013, VH0027), dù prompt dặn "không đoán". Số đó KHÔNG phải bịa tuỳ ý: là chính dòng TỔNG (đã gồm thuế), con số duy nhất in trên tờ.

Câu hỏi an toàn là: số sai đó có lọt vào sổ không? Kiểm ngày 19/11/2026 bằng đầu ra thật của 4 model: cả 8 lượt (4 model x 2 tờ) bị
`verify` chặn (`ok=False`), với đủ hai lý do: "Cộng tiền hàng lệch" (tính lại từ các khoản khác số model điền) và "Không đọc được VAT".
Bản đầu của chú thích trên #124 viết "hướng sửa nằm ở mã"; đó là sai: mã đã tính lại `subtotal` từ các khoản và đã bắt. Test này khoá hành vi
ĐANG ĐÚNG, để một lần sửa `verify` sau này không làm mất nó mà không ai thấy.

CÁI CHƯA ĐƯỢC CHẶN HẾT: lệch lũy thừa của 10 ĐỒNG LOẠT ở hoá đơn cước đầy đủ (đơn giá, cộng tiền hàng, thuế, tổng cùng nhỏ đi 1.000 lần)
qua được mọi phép đối chiếu NHẤT QUÁN, vì chúng vẫn nhất quán với nhau (xem `offline_training/phan_loai_loi_vlm.py`, cổng `LECH_LUY_THUA_10`).
Từ A8 (22/11/2026, BR-19 phần 2b) có hai lớp khác: model chép số tiền như in và mã đọc (`so_tien_ocr.py`, chưa đo trên ảnh), và kiểm QUY MÔ
trong `verify` (tổng cước dưới 100.000 đ thì hạ cờ). Kiểm quy mô chỉ bắt phần lệch làm tổng nhỏ dưới ngưỡng, tức hoá đơn in dưới 100 triệu
đồng; hoá đơn lớn hơn bị chia 1.000 vẫn trên ngưỡng và vẫn lọt. Hai test cuối ghi cả hai nửa ra, thay vì giả vờ không có lỗ.
"""

from __future__ import annotations

import pytest

from offline_training.vlm_hoadon import sinh_ca
from src.core.freight_invoice import FreightInvoice, verify

AN_VAT = [c for c in sinh_ca(28) if c["kind"] == "freight" and c["variant"] == "vat_hidden"]
DAY_DU = next(c for c in sinh_ca(28) if c["kind"] == "freight" and c["variant"] == "clean")


def _hoa_don(gt: dict, **ghi_de) -> FreightInvoice:
    d = dict(gt)
    d.update(ghi_de)
    return FreightInvoice.model_validate({k: v for k, v in d.items() if k in FreightInvoice.model_fields})


def test_co_du_ca_vat_hidden_de_kiem():
    """Chốt chống xanh suông: bộ đo phải có ca `vat_hidden`, và đáp án của chúng phải thật sự là None."""
    assert len(AN_VAT) >= 2
    for c in AN_VAT:
        assert c["gt"]["subtotal"] is None and c["gt"]["vat_rate"] is None and c["gt"]["vat_amount"] is None


@pytest.mark.parametrize("ca", AN_VAT, ids=lambda c: c["id"])
def test_model_dien_dong_tong_vao_cong_tien_hang_bi_chan(ca):
    """Đúng lỗi quan sát được: `subtotal` = `total` (đã gồm thuế), thuế suất và tiền thuế để None."""
    gt = ca["gt"]
    kq = verify(_hoa_don(gt, subtotal=gt["total"]))
    assert kq["ok"] is False
    lyDo = " | ".join(kq["issues"])
    assert "Cộng tiền hàng lệch" in lyDo, "số model điền khác tổng các khoản phải bị bắt"
    assert "Không đọc được VAT" in lyDo, "VAT chưa đọc được không được coi là 0"


@pytest.mark.parametrize("ca", AN_VAT, ids=lambda c: c["id"])
def test_model_tra_dung_none_van_khong_ok_vi_khong_kiem_duoc_vat(ca):
    """Làm đúng (để None) cũng KHÔNG `ok`: không đọc được VAT thì không có cơ sở nói tổng đúng. 'Không kiểm được' khác 'đã kiểm và đúng'."""
    kq = verify(_hoa_don(ca["gt"]))
    assert kq["ok"] is False
    assert any("Không đọc được VAT" in x for x in kq["issues"])
    assert kq["computed"]["total"] is None and kq["computed"]["vat_amount"] is None, "chưa biết thì là None, không phải 0"


@pytest.mark.parametrize("ca", AN_VAT, ids=lambda c: c["id"])
def test_model_dien_vat_bang_0_va_cong_tien_hang_bang_tong_van_bi_chan(ca):
    """Biến thể của Qwen3-VL-2B ở VH0027: điền 0 vào tiền thuế. Số 0 là 'một giá trị đã đọc', nên phải bị chặn bằng phép kiểm khác."""
    gt = ca["gt"]
    kq = verify(_hoa_don(gt, subtotal=gt["total"], vat_amount=0))
    assert kq["ok"] is False
    assert any("Cộng tiền hàng lệch" in x for x in kq["issues"])


def test_hoa_don_day_du_doc_dung_thi_qua_de_chung_minh_bo_kiem_khong_chan_het():
    """Đối chứng: cùng đường kiểm, tờ đọc đúng thì `ok`. Không có ca này thì các test trên chỉ chứng minh `verify` luôn từ chối."""
    assert verify(_hoa_don(DAY_DU["gt"]))["ok"] is True


def test_lech_1000_lan_dong_loat_o_hoa_don_nho_bi_kiem_quy_mo_bat():
    """
    Mọi số tiền cùng nhỏ đi 1.000 lần thì mọi phép đối chiếu vẫn nhất quán (không cái nào báo lệch), nhưng tổng rơi xuống dưới 100.000 đ
    nên kiểm quy mô (A8) hạ cờ. Trước A8 test này khẳng định `ok` là True: đó là lỗ hổng đã biết, nay đã đóng cho hoá đơn nhỏ.
    """
    gt = DAY_DU["gt"]
    nho = {
        "charges": [{**c, "unit_price": c["unit_price"] / 1000} for c in gt["charges"]],
        "subtotal": gt["subtotal"] / 1000, "vat_amount": gt["vat_amount"] / 1000, "total": gt["total"] / 1000,
    }
    kq = verify(_hoa_don(gt, **nho))
    assert kq["ok"] is False
    assert any("nghi đọc lệch 1.000 lần" in x for x in kq["issues"])
    assert not any(x.startswith(("Cộng tiền hàng lệch", "Tiền thuế lệch", "Tổng cộng lệch")) for x in kq["issues"]), "các phép nhất quán vẫn im lặng"


def test_LO_HONG_DA_BIET_lech_1000_lan_hoa_don_lon_van_qua_verify():
    """
    Phần lỗ CHƯA đóng: tờ in 150 triệu + VAT 10% = 165 triệu, mọi số bị chia 1.000 thành 150.000 / 15.000 / 165.000. Tổng 165.000 vẫn trên
    ngưỡng quy mô nên `verify` báo `ok`. Chỉ lớp chép chuỗi (`so_tien_ocr`) bắt được, và nó chưa đo trên ảnh. Nếu test này đỏ vì `ok` thành
    False, đó là tin tốt: cập nhật docstring đầu file và gỡ test này.
    """
    h = FreightInvoice(
        carrier_name="Nhà xe A", invoice_date="2026-03-14",
        charges=[{"kind": "cước", "quantity": 1, "unit_price": 150_000}],
        vat_rate=10.0, subtotal=150_000, vat_amount=15_000, total=165_000,
    )
    assert verify(h)["ok"] is True
