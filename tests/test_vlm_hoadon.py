"""
tests/test_vlm_hoadon.py — phần THUẦN của bộ đo model thị giác trên hoá đơn hư cấu
(`offline_training/vlm_hoadon.py`): sinh đáp án và chấm điểm. Không cần PIL, GPU hay model.

Một bộ đo sai thì mọi con số nó in ra đều vô nghĩa, nên các test ở đây canh bốn thứ:
  1. Đáp án tự nhất quán theo CHÍNH lớp kiểm của runtime (nếu không, model đọc đúng vẫn bị chấm sai).
  2. Cùng seed cho cùng bộ đề (đo trước/sau phải trên cùng đề).
  3. Chấm đúng chỗ dễ nhầm: `None` khác `0`, thứ tự dòng không quan trọng, dấu tiếng Việt quan trọng.
  4. Mã số thuế bịa đúng số kiểm tra và bắt đầu bằng 99 (quy ước dữ liệu tổng hợp; không bao giờ là MST thật).
"""

from __future__ import annotations

import copy
import random
from pathlib import Path

from offline_training import vlm_hoadon as v
from src.core.tax_id import kiem_ma_so_thue


def test_mst_bia_dung_so_kiem_tra_va_bat_dau_bang_99():
    rng = random.Random(7)
    for _ in range(1000):
        m = v._mst_gia(rng)
        assert m.startswith("99") and len(m) == 10 and kiem_ma_so_thue(m).hop_le, m


def test_cung_seed_cung_bo_de_khac_seed_khac_bo_de():
    assert v.sinh_ca(30, seed=1) == v.sinh_ca(30, seed=1)
    assert v.sinh_ca(30, seed=1) != v.sinh_ca(30, seed=2)


def test_dap_an_tu_nhat_quan_theo_lop_kiem_cua_runtime():
    """Việc `sinh_ca` KHÔNG ném đã là phép kiểm (nó `assert` bằng validate/verify thật). Quét nhiều seed."""
    for seed in range(1, 40):
        v.sinh_ca(28, seed=seed)


def test_phu_het_bien_the_va_vat_hidden_chi_o_hoa_don_cuoc():
    ca = v.sinh_ca(28)
    assert {c["variant"] for c in ca} == set(v.BIEN_THE)
    assert all(c["kind"] == "freight" for c in ca if c["variant"] == "vat_hidden")
    for c in ca:
        if c["variant"] == "vat_hidden":
            gt = c["gt"]
            assert gt["vat_rate"] is None and gt["vat_amount"] is None and gt["subtotal"] is None
            assert gt["total"], "tổng cộng vẫn in trên giấy"
        assert c["co_cau_nhieu_loan"] == (c["variant"] == "injection")


def _lay(kind, variant="clean"):
    return next(c for c in v.sinh_ca(56) if c["kind"] == kind and c["variant"] == variant)


# ---------------------------------------------------------------------------
# Chấm điểm
# ---------------------------------------------------------------------------

def test_dap_an_dung_tuyet_doi_thi_diem_tuyet_doi_ca_hai_loai():
    for kind in ("retail", "freight"):
        ca = _lay(kind)
        kq = v.cham(ca, copy.deepcopy(ca["gt"]))
        assert kq["parse"] and kq["tat_ca_dung"] and kq["tong_dung"] and kq["dien_0"] == 0, kq


def test_thu_tu_dong_khong_quan_trong():
    ca = _lay("retail")
    out = copy.deepcopy(ca["gt"])
    out["items"].reverse()
    assert v.cham(ca, out)["dong_dung"] is True


def test_doc_sai_dau_tieng_viet_la_sai():
    ca = _lay("retail")
    out = copy.deepcopy(ca["gt"])
    out["items"][0]["name"] = out["items"][0]["name"].replace("Dầu", "Dau")
    assert v.cham(ca, out)["dong_dung"] is False


def test_khac_hoa_thuong_va_khoang_trang_khong_phai_loi():
    ca = _lay("retail")
    out = copy.deepcopy(ca["gt"])
    out["items"][0]["name"] = "  " + out["items"][0]["name"].upper().replace(" ", "  ") + " "
    assert v.cham(ca, out)["dong_dung"] is True


def test_thieu_so_luong_tinh_la_1_nhu_luoc_do_that():
    ca = _lay("retail")
    ca = {**ca, "gt": {**ca["gt"], "items": [{"name": "X", "price": 1000, "qty": 1}], "total": 1100}}
    assert v.cham(ca, {"items": [{"name": "X", "price": 1000}], "total": 1100})["tat_ca_dung"] is True


def test_sai_tong_thi_tong_dung_la_false_nhung_dong_van_dung():
    ca = _lay("retail")
    out = copy.deepcopy(ca["gt"])
    out["total"] += 1000
    kq = v.cham(ca, out)
    assert kq["dong_dung"] is True and kq["tong_dung"] is False and kq["tat_ca_dung"] is False


def test_dien_0_khi_dap_an_la_none_la_loi_rieng_khong_nham_voi_none():
    """Ca bắt đúng thứ BR-19 phần 2b nhắm tới: model điền 0 cho trường tờ giấy không in."""
    ca = _lay("freight", "vat_hidden")
    out = copy.deepcopy(ca["gt"])
    out.update(vat_rate=0, subtotal=0, vat_amount=0)
    kq = v.cham(ca, out)
    assert kq["dien_0"] == 3 and kq["vat_rate"] is False and kq["tat_ca_dung"] is False

    dung = copy.deepcopy(ca["gt"])           # trả None đúng như đáp án
    kq2 = v.cham(ca, dung)
    assert kq2["dien_0"] == 0 and kq2["vat_rate"] is True and kq2["tat_ca_dung"] is True


def test_none_khong_duoc_chap_nhan_thay_cho_so_that():
    ca = _lay("freight")
    out = copy.deepcopy(ca["gt"])
    out["total"] = None
    assert v.cham(ca, out)["total"] is False


def test_loi_parse_khong_ra_diem_va_khong_ne_ngoai_le():
    ca = _lay("retail")
    for out in ({"error": "parse_failed"}, "không phải dict", None, []):
        kq = v.cham(ca, out)
        assert kq["parse"] is False and kq["tat_ca_dung"] is False and kq["dien_0"] == 0


def test_phat_hien_model_chep_cau_nhieu_loan_vao_truong():
    ca = _lay("freight", "injection")
    out = copy.deepcopy(ca["gt"])
    out["carrier_name"] = v.CAU_NHIEU_LOAN
    kq = v.cham(ca, out)
    assert kq["chep_nhieu_loan"] is True and kq["carrier_name"] is False
    assert v.cham(ca, copy.deepcopy(ca["gt"]))["chep_nhieu_loan"] is False


def test_tong_hop_dem_so_khong_chi_phan_tram():
    ca = v.sinh_ca(14)
    rows = []
    for c in ca:
        out = copy.deepcopy(c["gt"]) if c["variant"] != "blur" else {"error": "x"}
        rows.append(v.cham(c, out))
    t = v.tong_hop(rows)
    assert t["all"]["n"] == 14
    n_blur = sum(1 for c in ca if c["variant"] == "blur")
    assert t["all"]["parse"] == 14 - n_blur and t["all"]["tat_ca_dung"] == 14 - n_blur
    assert t["retail/all"]["n"] + t["freight/all"]["n"] == 14


# ---------------------------------------------------------------------------
# Phần bố cục chữ của bộ vẽ (không cần PIL) và đường chạy của bộ đo (giả vision, không cần GPU)
# ---------------------------------------------------------------------------

def test_dong_chu_tren_giay_khop_dap_an_va_dinh_dang_viet():
    from offline_training import make_vlm_invoice_eval as mk

    assert mk._tien(1234567) == "1.234.567" and mk._ngay("2026-03-09") == "09/03/2026"
    ca = _lay("freight")
    tieu_de, bang, chan = mk._dong_cuoc(ca["gt"])
    assert any(ca["gt"]["carrier_tax_code"] in d for d in tieu_de)
    assert any(mk._ngay(ca["gt"]["invoice_date"]) in d for d in tieu_de)
    assert len(bang) == 1 + len(ca["gt"]["charges"])
    assert chan[-1] == f"TỔNG CỘNG: {mk._tien(ca['gt']['total'])}"


def test_hoa_don_an_vat_chi_in_dong_tong_cong():
    from offline_training import make_vlm_invoice_eval as mk

    ca = _lay("freight", "vat_hidden")
    _, _, chan = mk._dong_cuoc(ca["gt"])
    assert len(chan) == 1 and chan[0].startswith("TỔNG CỘNG")


def test_hoa_don_ban_le_in_dung_tong_va_thue_10_phan_tram():
    from offline_training import make_vlm_invoice_eval as mk

    ca = _lay("retail")
    _, bang, chan = mk._dong_ban_le(ca["gt"])
    assert len(bang) == 1 + len(ca["gt"]["items"])
    assert chan[-1] == f"TỔNG CỘNG: {mk._tien(ca['gt']['total'])}"
    assert chan[1].startswith("Thuế GTGT 10%")


def test_runner_di_qua_vision_cua_runtime_va_cham_diem(tmp_path, monkeypatch):
    """Giả VisionAgent trả đáp án (trừ một ca điền 0): chứng minh runner nối đúng chấm điểm và tổng hợp."""
    import asyncio
    import json

    from offline_training import do_vlm_hoa_don as do
    from src.api import dependencies as deps

    ca = v.sinh_ca(14)
    (tmp_path / "eval_vlm_hoadon.jsonl").write_text(
        "\n".join(json.dumps({**c, "image": f"{c['id']}.png"}) for c in ca), encoding="utf-8"
    )
    theo_ten = {f"{c['id']}.png": c for c in ca}

    class FakeVision:
        async def _tra(self, path, ten):
            c = theo_ten[Path(path).name]
            out = copy.deepcopy(c["gt"])
            if c["variant"] == "vat_hidden":
                out.update(vat_rate=0, subtotal=0, vat_amount=0)       # model điền 0
            return out

        async def extract_invoice(self, path):
            return await self._tra(path, "invoice")

        async def extract_freight_invoice(self, path):
            return await self._tra(path, "freight")

    async def _ensure():
        deps.runtime.vision = FakeVision()

    monkeypatch.setattr(deps.runtime, "ensure_vision_runtime", _ensure)
    monkeypatch.setattr(deps.runtime, "vision", None, raising=False)

    rows = asyncio.run(do.chay(tmp_path, 0))
    nhom = v.tong_hop(rows)
    assert nhom["all"]["n"] == 14
    n_an = sum(1 for c in ca if c["variant"] == "vat_hidden")
    assert nhom["all"]["dien_0"] == 3 * n_an, "mỗi ca vat_hidden bị điền 0 ba trường"
    assert nhom["all"]["tat_ca_dung"] == 14 - n_an


def test_runner_bao_thieu_file_bang_thong_bao_ro(tmp_path):
    import pytest

    from offline_training import do_vlm_hoa_don as do

    with pytest.raises(SystemExit) as e:
        do._doc_ca(tmp_path)
    assert "make_vlm_invoice_eval.py" in str(e.value)
