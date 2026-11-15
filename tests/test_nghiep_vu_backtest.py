"""
tests/test_nghiep_vu_backtest.py — cổng chặn hồi quy cho cửa trước của Brain trên câu hỏi nghiệp vụ.

`offline_training/do_nghiep_vu.py` đo bộ câu hỏi hư cấu (`generated/eval_nghiep_vu.jsonl`) qua ĐÚNG đường mà
`chat.py` dùng (router từ khoá + `plan_tools` + `vao_vong_agentic`). File này biến phép đo thành cổng ở CI:
luật mới mà làm trượt một câu đã đúng thì test đỏ, và danh sách câu sai ĐÃ BIẾT phải khai tường minh.

ĐỌC TRƯỚC KHI TIN: số 97/98 là TRONG MẪU. Luật đã được sửa theo chính các câu này. Con số ngoài mẫu duy nhất đã
đo được là 31/49 trước khi sửa và 33/49 sau lần sửa đầu (tập holdout đầu tiên, nay đã bị dùng, nên chuyển thành dev).
Cổng này chống HỒI QUY; nó KHÔNG chứng minh Brain hiểu câu của khách.
"""

from __future__ import annotations

from offline_training import do_nghiep_vu as nv

# Câu sai đã biết, kèm lý do. Thêm vào đây phải kèm lý do; bớt đi thì tốt.
SAI_DA_BIET = {
    "NV014": "mơ hồ: hỏi luật hay đối chiếu danh mục hàng của khách? Luật vat_catalog_audit cố ý bắt 'mặt hàng nào ... 8%'",
}


def _chay():
    return nv.chay(nv.doc_bo_de())


def test_bo_de_doc_duoc_va_khong_trung_id():
    bo = nv.doc_bo_de()
    ids = [c["id"] for c in bo]
    assert len(ids) == len(set(ids)) >= 90
    for c in bo:
        assert {"id", "nhom", "cau", "tool", "tap"} <= set(c)
        assert c["tap"] in ("dev", "holdout")


def test_chi_con_nhung_cau_sai_da_khai_bao():
    sai = {r["id"] for r in _chay() if not r["dung"]}
    moi = sai - set(SAI_DA_BIET)
    assert not moi, f"câu mới sai (hồi quy?): {sorted(moi)}. Chạy: python offline_training/do_nghiep_vu.py --loi"


def test_khai_bao_sai_da_biet_khong_bi_bo_quen_khi_da_het_sai():
    """Câu đã hết sai thì phải xoá khỏi danh sách: danh sách không được thành nơi che lỗi."""
    sai = {r["id"] for r in _chay() if not r["dung"]}
    het_sai = set(SAI_DA_BIET) - sai
    assert not het_sai, f"đã đúng rồi, xoá khỏi SAI_DA_BIET: {sorted(het_sai)}"


def test_do_chinh_xac_tong_the_khong_tut_duoi_san():
    rows = _chay()
    dung = sum(r["dung"] for r in rows)
    assert dung / len(rows) >= 0.95, f"{dung}/{len(rows)}"


def test_khong_nhom_nao_bi_bo_trong():
    """Mỗi nhóm nghiệp vụ phải còn ít nhất 3 câu, nếu không con số theo nhóm vô nghĩa."""
    from collections import Counter

    dem = Counter(c["nhom"] for c in nv.doc_bo_de())
    nho = {k: v for k, v in dem.items() if v < 3 and k not in ("bao_gia_n8n", "workflow")}
    assert not nho, nho
