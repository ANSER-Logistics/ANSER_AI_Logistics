"""
tests/integration/workflows/test_n8n_bo_loc.py — mẫu n8n "bộ lọc nghiệp vụ" cho anser-v5 (#91).

anser-v4 hỏng n8n 14/34, 8 trong 12 lỗi còn lại sau thử lại là nhánh "không" của IF nối tới một node `noOp` không tồn tại. Họ mẫu
này dạy: kế hoạch im lặng về nhánh "không" thì để nhánh đó TRỐNG; kế hoạch có bước cho nhánh "không" thì nối bước đó vào.

Cái dễ sai ở đây là cái không báo lỗi: (1) chỉ có một họ thì model học "IF không bao giờ nối nhánh không", cũng sai;
(2) mẫu trùng bước của bộ đo thì điểm v5 đo nhớ thuộc lòng chứ không đo năng lực; (3) dòng train lệch khuôn user của runtime thì
model học một khuôn không bao giờ gặp lúc chạy thật (P4).
"""

from __future__ import annotations

import json

import pytest

from offline_training.make_n8n_bo_loc import _chuan, buoc_cua_bo_do, dung_mau, sinh
from offline_training.make_n8n_pairs import dong_train
from src.agents.coder import soan_yeu_cau
from src.core.workflow_schema import get_node_catalog, validate_workflow

NODE_IF = "n8n-nodes-base.if"


@pytest.fixture(scope="module")
def mau():
    return sinh(get_node_catalog(), 90)


def _if_main(m):
    for n in m["answer"]["payload"]["nodes"]:
        if n["type"] == NODE_IF:
            return n["name"], m["answer"]["payload"]["connections"][n["name"]]["main"]
    raise AssertionError("mẫu không có IF")


def test_du_so_mau_va_moi_mau_qua_validate_workflow(mau):
    assert len(mau) == 90
    loi = [(m["_id"], validate_workflow(m["answer"])[1]) for m in mau if not validate_workflow(m["answer"])[0]]
    assert not loi, loi[:3]


def test_hai_ho_deu_co_mat_du_so(mau):
    """Chốt chống xanh suông: thiếu một họ là model chỉ học được nửa phép đối chiếu."""
    co = sum(1 for m in mau if m["co_buoc_khong"])
    assert 0.2 * len(mau) <= co <= 0.5 * len(mau), f"{co}/{len(mau)} mẫu có bước cho nhánh không"


def test_nhanh_khong_trong_khi_ke_hoach_im_lang(mau):
    for m in (x for x in mau if not x["co_buoc_khong"]):
        ten_if, main = _if_main(m)
        assert len(main) == 2 and main[0] and main[1] == [], (m["_id"], main)
        # kế hoạch không có bước nào thừa so với node: không có node "tự nghĩ ra"
        assert {n["name"] for n in m["answer"]["payload"]["nodes"]} == set(m["buoc"]), m["_id"]


def test_nhanh_khong_noi_dung_buoc_khi_ke_hoach_co_buoc(mau):
    for m in (x for x in mau if x["co_buoc_khong"]):
        ten_if, main = _if_main(m)
        assert len(main[1]) == 1, (m["_id"], main)
        dich = main[1][0]["node"]
        assert dich == m["buoc"][-1], "bước cho nhánh không là bước CUỐI của kế hoạch"
        assert dich in {n["name"] for n in m["answer"]["payload"]["nodes"]}
        assert main[0] and main[0][0]["node"] != dich


def test_khong_node_noop_va_khong_ket_noi_toi_node_khong_ton_tai(mau):
    """Đúng lỗi của v4: nhánh không nối tới tên `noOp` mà không có node đó."""
    for m in mau:
        ten = {n["name"] for n in m["answer"]["payload"]["nodes"]}
        assert not any(n["type"].endswith(".noOp") for n in m["answer"]["payload"]["nodes"]), m["_id"]
        for out in m["answer"]["payload"]["connections"].values():
            for nhanh in out["main"]:
                for lk in nhanh:
                    assert lk["node"] in ten, (m["_id"], lk["node"])


def test_khong_trung_bat_ky_buoc_nao_cua_bo_do(mau):
    cam = buoc_cua_bo_do()
    assert len(cam) > 100, "chốt chống xanh suông: bộ đo phải có đủ bước"
    trung = sorted({b for m in mau for b in m["buoc"] if _chuan(b) in cam})
    assert not trung, trung


def test_dau_do_bat_duoc_viec_trung_bo_do(monkeypatch):
    """Chứng minh test không câm: thêm một bước của bộ đo vào từ vựng thì `sinh` phải nổ, không lặng lẽ qua."""
    from offline_training import make_n8n_bo_loc as r
    from offline_training.make_n8n_eval import DE_BAI

    buoc_do = DE_BAI[0][2][2]   # "Có hàng nào dưới ngưỡng?"
    dt = dict(r.DOI_TUONG[0], hoi=buoc_do)
    monkeypatch.setattr(r, "DOI_TUONG", [dt])
    with pytest.raises(AssertionError, match="bộ đo"):
        sinh(get_node_catalog(), 5)


def test_ke_hoach_khac_nhau_va_id_khong_trung(mau):
    assert len({m["plan"] for m in mau}) == len(mau)
    assert len({m["_id"] for m in mau}) == len(mau)
    assert {m["_source"] for m in mau} == {"n8n_bo_loc"}


def test_tat_dinh_theo_seed_va_doi_theo_seed():
    cat = get_node_catalog()
    a, b, c = sinh(cat, 20, seed=1), sinh(cat, 20, seed=1), sinh(cat, 20, seed=2)
    assert [m["plan"] for m in a] == [m["plan"] for m in b]
    assert [m["plan"] for m in a] != [m["plan"] for m in c]


def test_het_cach_ghep_thi_dung_som_khong_lap():
    """Đòi nhiều hơn số tổ hợp có thể thì trả ít hơn, không trả bản trùng."""
    ra = sinh(get_node_catalog(), 100_000)
    assert 100 < len(ra) < 100_000
    assert len({m["plan"] for m in ra}) == len(ra)


def test_do_dai_dap_an_nam_trong_ngan_sach_cua_workflow_that(mau):
    """Workflow thật dài 1,6-2,1 nghìn ký tự (Thành, #91); trần sinh là 2.048 token. Mẫu sinh phải nằm dưới MAX_ANSWER_CHARS."""
    from offline_training.make_n8n_pairs import MAX_ANSWER_CHARS

    dai = max(len(json.dumps(m["answer"], ensure_ascii=False)) for m in mau)
    assert dai < MAX_ANSWER_CHARS and dai < 4_000, dai


def test_dong_train_dung_khuon_user_cua_runtime(mau):
    """P4: user = đúng chuỗi `coder.soan_yeu_cau` dựng lúc chạy thật; assistant = JSON của đáp án; `_source` đi theo mẫu."""
    m = mau[0]
    d = dong_train("HE THONG", m)
    assert d["_source"] == "n8n_bo_loc" and d["_id"] == m["_id"]
    assert d["messages"][0] == {"role": "system", "content": "HE THONG"}
    assert d["messages"][1]["content"] == soan_yeu_cau(m["task"], m["plan"])
    assert json.loads(d["messages"][2]["content"]) == m["answer"]


def test_dong_train_mac_dinh_nguon_n8n_cho_mau_template():
    d = dong_train("S", {"_id": "x", "task": "t", "plan": "p", "answer": {"a": 1}})
    assert d["_source"] == "n8n"


def test_dung_mau_hai_ho_cung_mot_trinh_dung(mau):
    """Hai họ chỉ khác đúng một bước và một liên kết: không viết hai bộ dựng khác nhau (R4)."""
    import random

    cat = get_node_catalog()
    a = dung_mau(cat, random.Random(7), co_buoc_khong=False)
    b = dung_mau(cat, random.Random(7), co_buoc_khong=True)
    assert b["buoc"][:-1] == a["buoc"] and len(b["answer"]["payload"]["nodes"]) == len(a["answer"]["payload"]["nodes"]) + 1
