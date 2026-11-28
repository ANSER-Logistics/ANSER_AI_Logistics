from __future__ import annotations

import json

from offline_training import do_rag as dr
from src.core.knowledge import KnowledgeBase


def test_khop_nhan_bang_chuoi_nguyen_van_khong_phu_thuoc_khoang_trang():
    doan = "Nghị định 174/2025/NĐ-CP\n  áp dụng   thuế suất   8% cho dầu mỡ bôi trơn."
    assert dr.doan_khop_nhan(doan, "áp dụng thuế suất 8% cho dầu mỡ bôi trơn") is True
    assert dr.doan_khop_nhan(doan, "áp dụng thuế suất 10%") is False
    assert dr.doan_khop_nhan(doan, "") is False


def test_xac_suat_may_rui_ngau_nhien():
    assert abs(dr.xac_suat_may_rui(100, 1, 20) - 0.20) < 1e-9
    assert dr.xac_suat_may_rui(10, 1, 15) == 1.0
    assert dr.xac_suat_may_rui(0, 1, 15) == 0.0


def test_cluster_bootstrap_ci_bao_quanh_gia_tri_trung_binh():
    cum = {
        "doc_1": [{"r20": 1.0}, {"r20": 1.0}],
        "doc_2": [{"r20": 0.5}],
        "doc_3": [{"r20": 0.0}],
    }
    lo, hi = dr.cluster_bootstrap_ci(cum, "r20", so_vong=300, seed=42)
    assert 0.0 <= lo <= hi <= 1.0


def test_danh_gia_tren_thu_muc_mau_nho_va_grounding(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "chinh_sach_cua_hang.txt").write_text(
        (dr.DOCS_DIR / "chinh_sach_cua_hang.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (docs_dir / "nghi_dinh_mau.md").write_text(
        "# Nghị định 174/2025/NĐ-CP\n\n"
        "Điều 1. Sản phẩm dầu mỏ tinh chế bao gồm dầu mỡ bôi trơn được áp dụng mức thuế suất GTGT 8% "
        "từ ngày 01/07/2025 đến hết ngày 31/12/2026 theo quy định hiện hành.\n",
        encoding="utf-8",
    )

    de_path = tmp_path / "eval.jsonl"
    cau_hoi = dr.tao_bo_de_tu_corpus(de_path, docs_dir)
    assert any(c["loai_du_lieu"] == "noi_bo_go_tay" and c["co_tai_lieu"] for c in cau_hoi)
    assert any(not c["co_tai_lieu"] for c in cau_hoi)

    tai_lieu = dr.doc_corpus_tu_thu_muc(docs_dir)
    kb = KnowledgeBase(
        persist_dir=str(tmp_path / "vec"),
        embedder=dr._MockEmbedder(),
        reranker=dr._MockReranker(),
        collection=dr._MockCollection(),
    )
    dr.nap_kho_mac_dinh(kb, "ws_test", tai_lieu)
    kq = dr.danh_gia_cau_hinh(kb, "ws_test", cau_hoi, ten="test_mock")

    assert kq.n_cau_co_tai_lieu >= 15
    assert kq.n_cau_tu_choi == 20
    assert 0.0 <= kq.recall_15 <= kq.recall_20 <= 1.0
    assert 0.0 <= kq.mrr <= 1.0
    assert len(kq.duong_cong_nguong) == 9


def test_cli_do_rag_mock_va_ablation_xuat_json(tmp_path, capsys):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "chinh_sach_cua_hang.txt").write_text(
        (dr.DOCS_DIR / "chinh_sach_cua_hang.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    de_path = tmp_path / "eval.jsonl"
    json_out = tmp_path / "ket_qua.json"
    rc = dr.main([
        "--de", str(de_path),
        "--docs-dir", str(docs_dir),
        "--mock",
        "--ablation",
        "--json", str(json_out),
    ])
    assert rc == 0

    out_txt = capsys.readouterr().out
    assert "Recall@15" in out_txt
    assert "Recall@20" in out_txt
    assert "MRR" in out_txt
    assert "Đường cong ngưỡng ViRanker" in out_txt

    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert len(data) == 4
    assert [d["ten"] for d in data] == [
        "1_mac_dinh_hybrid+rerank",
        "2_chia_doan_128tok",
        "3_tat_viranker",
        "4_chi_vector_khong_bm25",
    ]
