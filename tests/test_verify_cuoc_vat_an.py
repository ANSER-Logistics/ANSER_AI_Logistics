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

CÁI KHÔNG ĐƯỢC KHOÁ Ở ĐÂY: lệch lũy thừa của 10 ĐỒNG LOẠT ở hoá đơn cước đầy đủ (đơn giá, cộng tiền hàng, thuế, tổng cùng nhỏ đi 1.000 lần)
vẫn qua `verify` vì mọi phép đối chiếu nhất quán với nhau. Đó là lỗ hổng thật, không có phép kiểm nhất quán nào bắt được (xem
`offline_training/phan_loai_loi_vlm.py`, cổng `LECH_LUY_THUA_10`); test cuối ghi nó ra thay vì giả vờ không có.
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


def test_LO_HONG_DA_BIET_lech_1000_lan_dong_loat_van_qua_verify():
    """
    Ghi lại điều CHƯA được chặn, không phải điều mong muốn: mọi số tiền cùng nhỏ đi 1.000 lần thì mọi phép đối chiếu vẫn nhất quán và
    `verify` báo `ok`. Chỉ đáp án (hoặc bắt VLM chép số đúng như in rồi phân tích bằng mã) bắt được. Nếu một ngày test này đỏ vì `ok` thành
    False, đó là tin tốt: cập nhật docstring đầu file và gỡ test này.
    """
    gt = DAY_DU["gt"]
    nho = {
        "charges": [{**c, "unit_price": c["unit_price"] / 1000} for c in gt["charges"]],
        "subtotal": gt["subtotal"] / 1000, "vat_amount": gt["vat_amount"] / 1000, "total": gt["total"] / 1000,
    }
    assert verify(_hoa_don(gt, **nho))["ok"] is True
