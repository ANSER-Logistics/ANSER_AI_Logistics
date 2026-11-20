"""
tests/test_n8n_v6.py — hai họ mẫu n8n cho anser-v6, rút từ ca hỏng thật của anser-v5 (#91, 20/11/2026).

v5 vẫn hỏng 5/34 câu n8n. Hai họ nhắm vào hai hình dạng đề mà họ `bo_loc` của v5 chưa bao giờ có:
  - C `tinh_roi_loc`: lấy -> TÍNH -> IF -> dựng -> gửi (đề `gia_canh_bao_bien_mong`, `no_bao_cao_tap_trung`: nhánh "không" nối tới `noOp` không có);
  - B `gui_tung`: bước có chữ "từng" là MỘT node (đề `no_doi_chieu_ncc`: model sinh hai node trùng tên).
Cái dễ sai ở đây là cái không báo lỗi: mẫu trùng bước của bộ đo (điểm v6 đo nhớ thuộc lòng), một họ chiếm hết (model học một khuôn), hoặc mẫu
tên node trùng nhau (đúng lỗi cần dạy bỏ).
"""

from __future__ import annotations

import json
import random

import pytest

from offline_training.make_n8n_bo_loc import _chuan, buoc_cua_bo_do
from offline_training.make_n8n_pairs import dong_train
from offline_training.make_n8n_v6 import dung_mau_gui_tung, dung_mau_tinh_roi_loc, sinh
from src.agents.coder import soan_yeu_cau
from src.core.workflow_schema import get_node_catalog, validate_workflow

NODE_IF = "n8n-nodes-base.if"


@pytest.fixture(scope="module")
def mau():
    return sinh(get_node_catalog(), 80)


def test_du_so_mau_va_moi_mau_qua_validate_workflow(mau):
    assert len(mau) == 80
    loi = [(m["_id"], validate_workflow(m["answer"])[1]) for m in mau if not validate_workflow(m["answer"])[0]]
    assert not loi, loi[:3]


def test_ca_hai_ho_deu_co_mat(mau):
    """Chốt chống xanh suông: thiếu một họ là họ kia chiếm hết và model học một khuôn."""
    c = sum(1 for m in mau if m["ho"] == "tinh_roi_loc")
    b = sum(1 for m in mau if m["ho"] == "gui_tung")
    assert c >= 0.4 * len(mau) and b >= 0.15 * len(mau), (c, b)


def test_khong_mau_nao_dung_lai_buoc_cua_bo_do(mau):
    cam = buoc_cua_bo_do()
    trung = [(m["_id"], b) for m in mau for b in m["buoc"] if _chuan(b) in cam]
    assert not trung, trung[:3]


def test_ke_hoach_khong_trung_nhau(mau):
    assert len({m["plan"] for m in mau}) == len(mau)


def test_ten_node_khong_trung_nhau_trong_moi_mau(mau):
    """Đúng lỗi của `no_doi_chieu_ncc`: n8n định tuyến theo TÊN nên hai node cùng tên là workflow hỏng."""
    for m in mau:
        ten = [n["name"] for n in m["answer"]["payload"]["nodes"]]
        assert len(ten) == len(set(ten)), (m["_id"], ten)


def test_moi_buoc_cua_ke_hoach_la_dung_mot_node(mau):
    """Kế hoạch có k bước thì workflow có đúng k node: bước "từng" không được tách thành hai node (họ B), bước tính không bị gộp (họ C)."""
    for m in mau:
        nodes = m["answer"]["payload"]["nodes"]
        assert [n["name"] for n in nodes] == m["buoc"] or sorted(n["name"] for n in nodes) == sorted(m["buoc"]), m["_id"]


def test_ho_gui_tung_co_mot_node_ten_co_chu_tung(mau):
    for m in (x for x in mau if x["ho"] == "gui_tung"):
        co_tung = [n["name"] for n in m["answer"]["payload"]["nodes"] if " từng " in n["name"].lower() + " "]
        assert len(co_tung) == 1, (m["_id"], co_tung)


def _if(m):
    for n in m["answer"]["payload"]["nodes"]:
        if n["type"] == NODE_IF:
            return n["name"], m["answer"]["payload"]["connections"][n["name"]]["main"]
    raise AssertionError("mẫu không có IF")


def test_ho_tinh_roi_loc_co_buoc_tinh_dung_truoc_if(mau):
    for m in (x for x in mau if x["ho"] == "tinh_roi_loc"):
        ten_if, _ = _if(m)
        con = m["answer"]["payload"]["connections"]
        truoc = [src for src, o in con.items() if any(lk["node"] == ten_if for br in o["main"] for lk in br)]
        assert len(truoc) == 1 and truoc[0].startswith("Tính"), (m["_id"], truoc)


def test_nhanh_khong_trong_khi_ke_hoach_im_lang_va_noi_khi_co_buoc(mau):
    co_trong = co_noi = 0
    for m in (x for x in mau if x["ho"] == "tinh_roi_loc"):
        _, main = _if(m)
        if m["co_buoc_khong"]:
            assert len(main[1]) == 1 and main[1][0]["node"] == m["buoc"][-1]
            co_noi += 1
        else:
            assert main[1] == [], m["_id"]
            co_trong += 1
    assert co_trong > 0 and co_noi > 0, "cần cả hai biến thể, như họ bo_loc"


def test_dung_hai_ho_deu_tat_dinh_theo_seed():
    cat = get_node_catalog()
    assert dung_mau_gui_tung(cat, random.Random(3)) == dung_mau_gui_tung(cat, random.Random(3))
    assert dung_mau_tinh_roi_loc(cat, random.Random(3), False) == dung_mau_tinh_roi_loc(cat, random.Random(3), False)


def test_dong_train_dung_khuon_user_cua_runtime(mau):
    m = mau[0]
    d = dong_train("HE THONG", m)
    assert d["_source"] == "n8n_v6" and d["_id"] == m["_id"]
    assert d["messages"][1]["content"] == soan_yeu_cau(m["task"], m["plan"])
    assert json.loads(d["messages"][2]["content"]) == m["answer"]
