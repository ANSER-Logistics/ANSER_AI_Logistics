from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from offline_training.dgen_common import GENERATED_DIR  # noqa: E402
from src.core import doc_extract  # noqa: E402
from src.core.grounding import guard_answer  # noqa: E402
from src.core.knowledge import (  # noqa: E402
    RELEVANCE_THRESHOLD,
    KnowledgeBase,
    Passage,
    format_for_prompt,
    is_effective,
    merge_candidates,
    sigmoid,
    to_date_int,
    to_float_lists,
)
from src.core.retrieval_policy import KHONG_CO_TAI_LIEU, decide_web_fallback  # noqa: E402
from src.core.utils import hom_nay_vn  # noqa: E402

DOCS_DIR = ROOT / "src" / "data" / "docs"
INTERNAL_DOC_NAME = "chinh_sach_cua_hang.txt"
DEFAULT_DATASET_PATH = GENERATED_DIR / "do_rag_eval.jsonl"
NGUONG_RECALL20_MUC_TIEU = 0.80

def _chuan_chuoi(text: str) -> str:
    return " ".join((text or "").split()).casefold()


def doan_khop_nhan(passage_text: str, doan_chuan: str) -> bool:
    """Đoạn truy hồi có chứa chuỗi nguyên văn đáp án không."""
    chuan_gt = _chuan_chuoi(doan_chuan)
    if not chuan_gt:
        return False
    return chuan_gt in _chuan_chuoi(passage_text)


class _MockEmbedder:
    """Embedder bag-of-words tất định, không cần mạng hay GPU."""

    def __init__(self, dim: int = 128) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for tok in re.findall(r"\w+", text.casefold()):
            v[hash(tok) % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def encode(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class _MockReranker:

    def predict(self, pairs: list[list[str]], **kwargs: Any) -> list[float]:
        scores: list[float] = []
        for query, doc in pairs:
            q_toks = set(re.findall(r"\w+", query.casefold()))
            d_toks = set(re.findall(r"\w+", doc.casefold()))
            if not q_toks:
                scores.append(-5.0)
                continue
            overlap = len(q_toks & d_toks) / len(q_toks)
            scores.append((overlap - 0.35) * 10.0)
        return scores


def _khop_where(meta: dict[str, Any], where: dict[str, Any] | None) -> bool:
    if not where:
        return True
    if "$and" in where:
        return all(_khop_where(meta, cond) for cond in where["$and"])
    for k, v in where.items():
        val = meta.get(k)
        if isinstance(v, dict):
            if "$lte" in v and not (val is not None and val <= v["$lte"]):
                return False
            if "$gte" in v and not (val is not None and val >= v["$gte"]):
                return False
        elif val != v:
            return False
    return True


class _MockCollection:

    def __init__(self) -> None:
        self._items: dict[str, tuple[str, list[float], dict[str, Any]]] = {}

    def add(
        self,
        *,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        for i, doc, emb, meta in zip(ids, documents, embeddings, metadatas):
            self._items[i] = (doc, emb, dict(meta))

    def get(self, where: dict[str, Any] | None = None) -> dict[str, list[Any]]:
        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, Any]] = []
        for i, (doc, _, meta) in self._items.items():
            if _khop_where(meta, where):
                ids.append(i)
                docs.append(doc)
                metas.append(meta)
        return {"ids": ids, "documents": docs, "metadatas": metas}

    def delete(self, ids: list[str]) -> None:
        for i in ids:
            self._items.pop(i, None)

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, Any] | None = None,
    ) -> dict[str, list[list[Any]]]:
        q_emb = query_embeddings[0]
        scored: list[tuple[float, str, dict[str, Any]]] = []
        for doc, emb, meta in self._items.values():
            if not _khop_where(meta, where):
                continue
            sim = sum(a * b for a, b in zip(q_emb, emb))
            scored.append((sim, doc, meta))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:n_results]
        return {
            "documents": [[d for _, d, _ in top]],
            "metadatas": [[m for _, _, m in top]],
        }


def truy_hoi_ung_vien(
    kb: KnowledgeBase,
    workspace_id: str,
    query: str,
    *,
    n_dense: int = 10,
    n_bm25: int = 5,
    dung_bm25: bool = True,
    dung_reranker: bool = True,
    tong_doan_kha_dung: int = 0,
    on_date: date | None = None,
) -> list[Passage]:
    if not query.strip():
        return []

    ngay = int((on_date or hom_nay_vn()).strftime("%Y%m%d"))
    dieu_kien: dict[str, Any] = {
        "$and": [
            {"workspace_id": workspace_id},
            {"eff_from_int": {"$lte": ngay}},
            {"eff_to_int": {"$gte": ngay}},
        ]
    }

    dense: list[tuple[str, dict[str, Any]]] = []
    n_query = min(n_dense, tong_doan_kha_dung) if tong_doan_kha_dung > 0 else n_dense
    if n_query > 0:
        kq = kb.collection.query(
            query_embeddings=to_float_lists(kb.embedder.encode([query])),
            n_results=n_query,
            where=dieu_kien,
        )
        docs = (kq.get("documents") or [[]])[0]
        metas = (kq.get("metadatas") or [[]])[0]
        dense = list(zip(docs, metas))

    lexical: list[tuple[str, dict[str, Any]]] = []
    if dung_bm25 and n_bm25 > 0:
        try:
            bm25, pairs = kb._bm25_for(workspace_id)
            if bm25 and pairs:
                from underthesea import word_tokenize

                diem = bm25.get_scores(word_tokenize(query.lower()))
                xep = sorted(zip(diem, pairs), key=lambda x: x[0], reverse=True)
                lexical = [p for _, p in xep if is_effective(p[1], ngay)][:n_bm25]
        except Exception:
            lexical = []

    candidates = merge_candidates(dense, lexical)
    if not candidates:
        return []

    if dung_reranker:
        raw = kb.reranker.predict([[query, text] for text, _ in candidates])
        scored = [
            (sigmoid(float(s)), text, meta)
            for s, (text, meta) in zip(list(raw), candidates)
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
    else:
        n_cand = max(len(candidates), 1)
        scored = [
            (round(1.0 - (idx / (n_cand + 1)), 4), text, meta)
            for idx, (text, meta) in enumerate(candidates)
        ]

    return [
        Passage(
            text=text,
            source=str(meta.get("source", "?")),
            score=round(float(score), 4),
            chunk_index=int(meta.get("chunk_index", 0)),
            heading=str(meta.get("heading", "")),
            effective_from=meta.get("effective_from") or None,
            effective_to=meta.get("effective_to") or None,
        )
        for score, text, meta in scored
    ]


def xac_suat_may_rui(n_tong: int, n_dung: int, k: int) -> float:
    """Xác suất chọn ngẫu nhiên k đoạn không hoàn lại từ n_tong đoạn trúng >= 1 đoạn đúng."""
    if n_tong <= 0 or n_dung <= 0 or k <= 0:
        return 0.0
    if k >= n_tong or n_dung >= n_tong:
        return 1.0
    ty_le_truot = 1.0
    for i in range(k):
        ty_le_truot *= (n_tong - n_dung - i) / (n_tong - i)
    return 1.0 - ty_le_truot


def cluster_bootstrap_ci(
    ket_qua_theo_cum: dict[str, list[dict[str, float]]],
    khoa: str,
    *,
    so_vong: int = 1000,
    seed: int = 20261123,
) -> tuple[float, float]:
    """Khoảng tin cậy 95% theo cụm tài liệu (`doc_id`) bằng bootstrap."""
    cum_ids = sorted(ket_qua_theo_cum.keys())
    if not cum_ids:
        return 0.0, 0.0
    if len(cum_ids) == 1:
        vals = [x[khoa] for x in ket_qua_theo_cum[cum_ids[0]]]
        tb = sum(vals) / len(vals) if vals else 0.0
        return tb, tb

    rng = random.Random(seed)
    mau: list[float] = []
    n_cum = len(cum_ids)
    for _ in range(so_vong):
        chon = [cum_ids[rng.randrange(n_cum)] for _ in range(n_cum)]
        vals = [x[khoa] for cid in chon for x in ket_qua_theo_cum[cid]]
        if vals:
            mau.append(sum(vals) / len(vals))
    mau.sort()
    lo = mau[int(0.025 * len(mau))]
    hi = mau[min(len(mau) - 1, int(0.975 * len(mau)))]
    return lo, hi


@dataclass
class KetQuaDo:
    ten: str
    n_cau_co_tai_lieu: int
    n_cau_tu_choi: int
    n_tai_lieu_doc_lap: int
    tong_doan_trong_kho: int
    recall_15: float
    recall_15_ci: tuple[float, float]
    may_rui_15: float
    recall_20: float
    recall_20_ci: tuple[float, float]
    may_rui_20: float
    mrr: float
    mrr_ci: tuple[float, float]
    refusal_precision: float
    refusal_recall: float
    false_refusal_rate: float
    grounding_ok_rate: float
    grounding_checked: int
    duong_cong_nguong: list[dict[str, float]]


def danh_gia_cau_hinh(
    kb: KnowledgeBase,
    workspace_id: str,
    bo_cau_hoi: list[dict[str, Any]],
    *,
    ten: str = "mac_dinh",
    dung_bm25: bool = True,
    dung_reranker: bool = True,
    nguong: float = RELEVANCE_THRESHOLD,
    on_date: date | None = None,
) -> KetQuaDo:
    """Chạy đánh giá đầy đủ tầng truy hồi, tầng sinh và đường cong ngưỡng."""
    ngay = int((on_date or hom_nay_vn()).strftime("%Y%m%d"))
    got = kb.collection.get(where={"workspace_id": workspace_id})
    all_docs = got.get("documents") or []
    all_metas = got.get("metadatas") or []
    effective_docs = [d for d, m in zip(all_docs, all_metas) if is_effective(m, ngay)]
    n_tong_doan = len(effective_docs)

    cum_metrics: dict[str, list[dict[str, float]]] = {}
    r15_list: list[float] = []
    r20_list: list[float] = []
    mrr_list: list[float] = []
    mr15_list: list[float] = []
    mr20_list: list[float] = []

    tp_refusal = 0
    fp_refusal = 0
    fn_refusal = 0
    tn_answer = 0

    grounding_ok = 0
    grounding_checked = 0
    cache_ung_vien: list[tuple[dict[str, Any], list[Passage]]] = []

    for item in bo_cau_hoi:
        q = item["cau_hoi"]
        co_tl = bool(item.get("co_tai_lieu", True))
        doan_chuan = item.get("doan_chuan", "")
        doc_id = str(item.get("doc_id", "unknown"))

        cand_15 = truy_hoi_ung_vien(
            kb,
            workspace_id,
            q,
            n_dense=10,
            n_bm25=5,
            dung_bm25=dung_bm25,
            dung_reranker=dung_reranker,
            tong_doan_kha_dung=n_tong_doan,
            on_date=on_date,
        )
        cand_20 = truy_hoi_ung_vien(
            kb,
            workspace_id,
            q,
            n_dense=15,
            n_bm25=5,
            dung_bm25=dung_bm25,
            dung_reranker=dung_reranker,
            tong_doan_kha_dung=n_tong_doan,
            on_date=on_date,
        )
        cache_ung_vien.append((item, cand_15))

        if co_tl:
            hit_15 = 1.0 if any(doan_khop_nhan(p.text, doan_chuan) for p in cand_15[:15]) else 0.0
            hit_20 = 1.0 if any(doan_khop_nhan(p.text, doan_chuan) for p in cand_20[:20]) else 0.0
            rr = 0.0
            for rank, p in enumerate(cand_15[:15], start=1):
                if doan_khop_nhan(p.text, doan_chuan):
                    rr = 1.0 / rank
                    break

            n_doan_chua_dap_an = sum(1 for d in effective_docs if doan_khop_nhan(d, doan_chuan))
            mr15 = xac_suat_may_rui(n_tong_doan, n_doan_chua_dap_an, 15)
            mr20 = xac_suat_may_rui(n_tong_doan, n_doan_chua_dap_an, 20)

            r15_list.append(hit_15)
            r20_list.append(hit_20)
            mrr_list.append(rr)
            mr15_list.append(mr15)
            mr20_list.append(mr20)
            cum_metrics.setdefault(doc_id, []).append({"r15": hit_15, "r20": hit_20, "mrr": rr})

        passages_top3 = [p for p in cand_15 if p.score >= nguong][:3]
        he_thong_tu_choi = len(passages_top3) == 0 and not decide_web_fallback(q).allow

        if not co_tl:
            if he_thong_tu_choi:
                tp_refusal += 1
            else:
                fn_refusal += 1
        else:
            if he_thong_tu_choi:
                fp_refusal += 1
            else:
                tn_answer += 1
                cau_mau = item.get("cau_tra_loi_mau", "")
                if cau_mau:
                    grounding_checked += 1
                    ctx = format_for_prompt(passages_top3)
                    if guard_answer(cau_mau, ctx).ok:
                        grounding_ok += 1

    duong_cong: list[dict[str, float]] = []
    for th in [round(0.1 * i, 1) for i in range(1, 10)]:
        tp = fp = fn = tn = hit_after_th = 0
        for item, cand_15 in cache_ung_vien:
            q = item["cau_hoi"]
            co_tl = bool(item.get("co_tai_lieu", True))
            doan_chuan = item.get("doan_chuan", "")
            p_th = [p for p in cand_15 if p.score >= th][:3]
            refused = len(p_th) == 0 and not decide_web_fallback(q).allow
            if not co_tl:
                if refused:
                    tp += 1
                else:
                    fn += 1
            else:
                if refused:
                    fp += 1
                else:
                    tn += 1
                    if any(doan_khop_nhan(p.text, doan_chuan) for p in p_th):
                        hit_after_th += 1
        n_co = fp + tn
        n_khong = tp + fn
        duong_cong.append({
            "nguong": th,
            "recall_top3": (hit_after_th / n_co) if n_co else 0.0,
            "refusal_recall": (tp / n_khong) if n_khong else 1.0,
            "refusal_precision": (tp / (tp + fp)) if (tp + fp) else 1.0,
            "false_refusal_rate": (fp / n_co) if n_co else 0.0,
        })

    n_co_tl = len(r15_list)
    n_tu_choi = tp_refusal + fn_refusal
    r15 = sum(r15_list) / n_co_tl if n_co_tl else 0.0
    r20 = sum(r20_list) / n_co_tl if n_co_tl else 0.0
    mrr = sum(mrr_list) / n_co_tl if n_co_tl else 0.0
    mr15 = sum(mr15_list) / n_co_tl if n_co_tl else 0.0
    mr20 = sum(mr20_list) / n_co_tl if n_co_tl else 0.0

    ref_prec = tp_refusal / (tp_refusal + fp_refusal) if (tp_refusal + fp_refusal) else 1.0
    ref_rec = tp_refusal / (tp_refusal + fn_refusal) if (tp_refusal + fn_refusal) else 1.0
    false_ref = fp_refusal / (fp_refusal + tn_answer) if (fp_refusal + tn_answer) else 0.0
    g_rate = grounding_ok / grounding_checked if grounding_checked else 1.0

    return KetQuaDo(
        ten=ten,
        n_cau_co_tai_lieu=n_co_tl,
        n_cau_tu_choi=n_tu_choi,
        n_tai_lieu_doc_lap=len(cum_metrics),
        tong_doan_trong_kho=n_tong_doan,
        recall_15=r15,
        recall_15_ci=cluster_bootstrap_ci(cum_metrics, "r15"),
        may_rui_15=mr15,
        recall_20=r20,
        recall_20_ci=cluster_bootstrap_ci(cum_metrics, "r20"),
        may_rui_20=mr20,
        mrr=mrr,
        mrr_ci=cluster_bootstrap_ci(cum_metrics, "mrr"),
        refusal_precision=ref_prec,
        refusal_recall=ref_rec,
        false_refusal_rate=false_ref,
        grounding_ok_rate=g_rate,
        grounding_checked=grounding_checked,
        duong_cong_nguong=duong_cong,
    )


# ---------------------------------------------------------------------------
# Đọc corpus `src/data/docs/` và sinh bộ đề tuân thủ R2
# ---------------------------------------------------------------------------

def doc_corpus_tu_thu_muc(thu_muc: Path = DOCS_DIR) -> list[dict[str, Any]]:
    """Bóc chữ toàn bộ tài liệu trong `src/data/docs/` bằng đúng `doc_extract.extract`."""
    if not thu_muc.is_dir():
        return []
    tai_lieu: list[dict[str, Any]] = []
    for p in sorted(thu_muc.iterdir()):
        if not p.is_file():
            continue
        try:
            boc = doc_extract.extract(p.read_bytes(), p.name)
        except Exception:
            continue
        if not boc.text.strip():
            continue
        loai = "noi_bo_go_tay" if p.name == INTERNAL_DOC_NAME else "cong_khai"
        tai_lieu.append({
            "doc_id": p.name,
            "source": p.name,
            "loai_du_lieu": loai,
            "noi_dung": boc.text,
        })
    return tai_lieu


def _cau_hoi_noi_bo_go_tay() -> list[dict[str, Any]]:
 
    noi_bo: list[tuple[str, str, str]] = [
        (
            "Khách hàng mua online bên mình được đổi hàng trong thời gian bao lâu?",
            "Khách hàng được đổi hàng trong vòng **07 ngày** kể từ ngày mua (đối với mua tại cửa hàng) hoặc ngày nhận hàng (đối với mua online).",
            "Khách hàng mua online được đổi hàng trong vòng 07 ngày kể từ ngày nhận hàng.",
        ),
        (
            "Sản phẩm bị lỗi do nhà sản xuất bên mình được đổi mới trong bao nhiêu ngày?",
            "Riêng đối với lỗi do nhà sản xuất: Đổi mới 1-1 trong vòng **30 ngày**.",
            "Sản phẩm lỗi do nhà sản xuất được đổi mới 1-1 trong vòng 30 ngày.",
        ),
        (
            "Những mặt hàng nào bên mình không áp dụng chính sách đổi trả?",
            "**Không áp dụng đổi trả** với: Đồ lót, đồ bơi, tất (vớ), và các sản phẩm trong chương trình \"Xả kho\" (Clearance Sale).",
            "Cửa hàng không áp dụng đổi trả với đồ lót, đồ bơi, tất (vớ) và hàng Xả kho.",
        ),
        (
            "Đơn hàng online trả hàng thì cửa hàng hoàn tiền bằng cách nào và trong bao lâu?",
            "Nếu cửa hàng không còn sản phẩm thay thế, khách hàng sẽ được hoàn tiền 100% qua chuyển khoản ngân hàng trong vòng 3 ngày làm việc.",
            "Cửa hàng hoàn tiền 100% qua chuyển khoản ngân hàng trong vòng 3 ngày làm việc.",
        ),
        (
            "Phí vận chuyển nội thành Hà Nội và TP.HCM của bên mình là bao nhiêu?",
            "**Nội thành Hà Nội & TP.HCM:** Đồng giá 20.000 VNĐ. Giao trong ngày hoặc ngày hôm sau.",
            "Phí vận chuyển nội thành Hà Nội và TP.HCM đồng giá 20.000 VNĐ.",
        ),
        (
            "Đơn hàng giao đi ngoại thành và các tỉnh khác tính phí ship thế nào?",
            "**Ngoại thành & Các tỉnh khác:** Đồng giá 35.000 VNĐ. Thời gian giao hàng 2-4 ngày.",
            "Phí ship ngoại thành và các tỉnh khác đồng giá 35.000 VNĐ, thời gian giao 2-4 ngày.",
        ),
        (
            "Đơn hàng giá trị từ bao nhiêu thì được miễn phí vận chuyển bên mình?",
            "**Miễn phí vận chuyển** cho tất cả đơn hàng có giá trị từ **500.000 VNĐ** trở lên.",
            "Đơn hàng có giá trị từ 500.000 VNĐ trở lên được miễn phí vận chuyển.",
        ),
        (
            "Đơn hàng cồng kềnh như xe đẩy hoặc nôi cũi bên mình phụ thu phí ship bao nhiêu?",
            "Với đơn hàng cồng kềnh (như xe đẩy, nôi cũi), phụ thu phí vận chuyển 50.000 VNĐ.",
            "Đơn hàng cồng kềnh phụ thu phí vận chuyển 50.000 VNĐ.",
        ),
        (
            "Quy đổi điểm tích lũy khách hàng thân thiết bên mình ra tiền thế nào?",
            "1 điểm = 1.000 VNĐ (trừ trực tiếp vào đơn hàng sau).",
            "Mỗi 100.000 VNĐ tích được 1 điểm, và 1 điểm bằng 1.000 VNĐ.",
        ),
        (
            "Khách hàng hạng Vàng (Gold) bên mình cần mức tích lũy bao nhiêu và hưởng quyền lợi gì?",
            "**Hạng Vàng (Gold):** Tích lũy từ 5 triệu - 15 triệu/năm. Quyền lợi: Giảm trực tiếp **5%** trên mọi đơn hàng + Quà sinh nhật trị giá 200k.",
            "Hạng Vàng tích lũy từ 5 triệu đến 15 triệu/năm, giảm trực tiếp 5% mọi đơn hàng và quà sinh nhật 200k.",
        ),
        (
            "Khách hàng hạng Kim Cương (Diamond) bên mình được giảm giá bao nhiêu phần trăm?",
            "**Hạng Kim Cương (Diamond):** Tích lũy trên 15 triệu/năm. Quyền lợi: Giảm trực tiếp **10%** trên mọi đơn hàng + Freeship trọn đời + Quà Tết đặc biệt.",
            "Hạng Kim Cương tích lũy trên 15 triệu/năm, giảm trực tiếp 10% mọi đơn hàng.",
        ),
        (
            "Quẹt thẻ tại cửa hàng bên mình có thu phí cà thẻ không?",
            "Quẹt thẻ (Visa/Mastercard/Napas) - Không thu phí cà thẻ.",
            "Quẹt thẻ tại cửa hàng không thu phí cà thẻ.",
        ),
        (
            "Mua hàng online chuyển khoản trước bên mình được giảm thêm bao nhiêu?",
            "**Chuyển khoản trước:** Giảm thêm 5% tối đa 50k cho đơn hàng chuyển khoản trước.",
            "Khách mua online chuyển khoản trước được giảm thêm 5%, tối đa 50k.",
        ),
        (
            "Thời gian bảo hành chính hãng cho sản phẩm điện tử và máy hút sữa bên mình là bao lâu?",
            "Thời gian bảo hành: **12 tháng** chính hãng.",
            "Thời gian bảo hành chính hãng là 12 tháng.",
        ),
        (
            "Khách hàng gửi sản phẩm bảo hành của bên mình về đâu?",
            "Địa điểm tiếp nhận: Khách hàng gửi về kho trung tâm tại Hà Nội hoặc mang ra cửa hàng gần nhất.",
            "Khách hàng gửi sản phẩm bảo hành về kho trung tâm tại Hà Nội hoặc cửa hàng gần nhất.",
        ),
    ]

    ngoai_kho = [
        "Chính sách thưởng doanh số quý 4 cho nhân viên kinh doanh bên mình quy định thế nào?",
        "Hợp đồng thuê kho bãi tại cảng Hải Phòng của công ty mình có mức phạt chậm trả bao nhiêu?",
        "Quy trình duyệt chi tạm ứng công tác phí nội bộ của công ty mình gồm mấy bước?",
        "Mức phụ cấp ăn trưa và xăng xe hằng tháng cho tài xế bên mình là bao nhiêu?",
        "Danh sách nhà cung cấp bao bì nhựa của bên mình năm 2026 gồm những đơn vị nào?",
        "Quy định phạt đi muộn và nghỉ không phép của nhân sự văn phòng bên mình ra sao?",
        "Hạn mức duyệt chi tối đa của trưởng phòng kinh doanh bên mình là bao nhiêu tiền?",
        "Chính sách chiết khấu thanh toán sớm trong 5 ngày cho khách sỉ bên mình là mấy phần trăm?",
        "Quy trình xử lý sự cố tràn dầu tại kho trung tâm bên mình quy định những gì?",
        "Lịch kiểm kê định kỳ hàng tồn kho cuối tháng của bên mình rơi vào ngày nào?",
        "Điều khoản bảo mật thông tin khách hàng trong hợp đồng lao động bên mình nêu gì?",
        "Chính sách hỗ trợ chi phí đào tạo chứng chỉ lái xe nâng cho nhân viên kho bên mình thế nào?",
        "Quy định thanh lý hàng tồn kho quá hạn sử dụng của công ty mình thực hiện ra sao?",
        "Mức hoa hồng giới thiệu đại lý mới của nhân viên thị trường bên mình tính thế nào?",
        "Hợp đồng nguyên tắc vận chuyển tuyến Bắc Nam bên mình ký với nhà xe nào?",
        "Quy định cấp phát đồng phục bảo hộ lao động hằng năm cho bộ phận kho bên mình ra sao?",
        "Chính sách công nợ đặc biệt dành cho khách hàng dự án nhà nước bên mình quy định thế nào?",
        "Thời gian chốt bảng chấm công và chi trả lương hằng tháng của công ty mình là ngày mấy?",
        "Quy trình tiếp nhận khiếu nại chất lượng dầu nhờn của đại lý bên mình gồm các bước nào?",
        "Mức đặt cọc vỏ phuy sắt 200 lít đối với khách hàng mua lần đầu bên mình là bao nhiêu?",
    ]

    ds: list[dict[str, Any]] = []
    for idx, (q, doan, ans) in enumerate(noi_bo, start=1):
        ds.append({
            "id": f"RAG_NB_{idx:03d}",
            "doc_id": INTERNAL_DOC_NAME,
            "loai_du_lieu": "noi_bo_go_tay",
            "da_ra_soat_nguoi": True,
            "co_tai_lieu": True,
            "cau_hoi": q,
            "doan_chuan": doan,
            "cau_tra_loi_mau": ans,
        })
    for idx, q in enumerate(ngoai_kho, start=1):
        ds.append({
            "id": f"RAG_TC_{idx:03d}",
            "doc_id": f"ngoai_kho_{idx:02d}",
            "loai_du_lieu": "noi_bo_go_tay",
            "da_ra_soat_nguoi": True,
            "co_tai_lieu": False,
            "cau_hoi": q,
            "doan_chuan": "",
            "cau_tra_loi_mau": KHONG_CO_TAI_LIEU,
        })
    return ds


def _trich_cau_hoi_cong_khai(
    tai_lieu_ds: list[dict[str, Any]],
    *,
    max_cau_moi_tai_lieu: int = 4,
    tong_muc_tieu: int = 85,
) -> list[dict[str, Any]]:
    """
    Trích các câu văn chứa quy định/số liệu thực tế từ 21 tài liệu công khai trong
    `src/data/docs/` để tạo câu hỏi kiểm thử truy hồi có nhãn nguyên văn (`doan_chuan`).
    """
    cong_khai = [t for t in tai_lieu_ds if t["loai_du_lieu"] == "cong_khai"]
    ds: list[dict[str, Any]] = []
    idx_global = 1

    for tl in cong_khai:
        if len(ds) >= tong_muc_tieu:
            break
        ten_file = str(tl["source"])
        ten_gon = Path(ten_file).stem.replace("_", " ").replace("+", " ")
        ung_vien: list[str] = []
        for raw_line in str(tl["noi_dung"]).splitlines():
            dong = " ".join(raw_line.split())
            if not (90 <= len(dong) <= 220):
                continue
            if re.search(r"\b(điều|khoản|thuế|tỷ lệ|mức|ngày|năm|đồng|%|tăng trưởng|doanh thu)\b", dong, re.I):
                ung_vien.append(dong)
        if not ung_vien:
            continue
        buoc = max(1, len(ung_vien) // max_cau_moi_tai_lieu)
        chon = ung_vien[::buoc][:max_cau_moi_tai_lieu]
        for doan in chon:
            if len(ds) >= tong_muc_tieu:
                break
            cum_goi = " ".join(doan.split()[:10])
            ds.append({
                "id": f"RAG_CK_{idx_global:03d}",
                "doc_id": tl["doc_id"],
                "loai_du_lieu": "cong_khai",
                "da_ra_soat_nguoi": False,
                "co_tai_lieu": True,
                "cau_hoi": f"Trong tài liệu {ten_gon}, nội dung quy định hoặc số liệu liên quan đến '{cum_goi}...' là gì?",
                "doan_chuan": doan,
                "cau_tra_loi_mau": doan,
            })
            idx_global += 1
    return ds


def tao_bo_de_tu_corpus(
    duong_dan: Path,
    thu_muc_docs: Path = DOCS_DIR,
) -> list[dict[str, Any]]:
    """Sinh và lưu bộ câu hỏi JSONL từ corpus `src/data/docs/`."""
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    tai_lieu_ds = doc_corpus_tu_thu_muc(thu_muc_docs)
    cau_hoi = _cau_hoi_noi_bo_go_tay() + _trich_cau_hoi_cong_khai(tai_lieu_ds)
    duong_dan.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in cau_hoi) + "\n",
        encoding="utf-8",
    )
    return cau_hoi


def doc_bo_cau_hoi(
    duong_dan: Path,
    thu_muc_docs: Path = DOCS_DIR,
) -> list[dict[str, Any]]:
    if not duong_dan.is_file():
        return tao_bo_de_tu_corpus(duong_dan, thu_muc_docs)
    return [
        json.loads(line)
        for line in duong_dan.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

def nap_kho_mac_dinh(
    kb: KnowledgeBase,
    workspace_id: str,
    tai_lieu: list[dict[str, Any]],
) -> None:
    for tl in tai_lieu:
        kb.add_document(
            workspace_id=workspace_id,
            text=tl["noi_dung"],
            source=tl["source"],
            doc_type=tl.get("loai_du_lieu", ""),
        )


def nap_kho_chia_doan_nho(
    kb: KnowledgeBase,
    workspace_id: str,
    tai_lieu: list[dict[str, Any]],
    *,
    kich_thuoc_ky_tu: int = 450,
) -> None:
    """Mô phỏng chia đoạn 128 token (~450 ký tự) của model cũ để so với `chunk_document`."""
    for tl in tai_lieu:
        text = str(tl["noi_dung"])
        src = str(tl["source"])
        doan_nho = [
            text[i : i + kich_thuoc_ky_tu].strip()
            for i in range(0, len(text), kich_thuoc_ky_tu)
            if text[i : i + kich_thuoc_ky_tu].strip()
        ]
        if not doan_nho:
            continue
        meta_chung: dict[str, Any] = {
            "workspace_id": workspace_id,
            "source": src,
            "doc_type": tl.get("loai_du_lieu", ""),
            "effective_from": "",
            "effective_to": "",
            "eff_from_int": to_date_int(None, 10000101),
            "eff_to_int": to_date_int(None, 99991231),
        }
        kb.collection.add(
            ids=[f"{workspace_id}:{src}:small:{idx}" for idx in range(len(doan_nho))],
            documents=doan_nho,
            embeddings=to_float_lists(kb.embedder.encode(doan_nho)),
            metadatas=[{**meta_chung, "chunk_index": idx, "heading": ""} for idx in range(len(doan_nho))],
        )


def in_bao_cao(ket_qua_ds: list[KetQuaDo], cau_hoi: list[dict[str, Any]], nguon_file: Path) -> None:
    n_ra_soat = sum(1 for c in cau_hoi if c.get("da_ra_soat_nguoi"))
    ty_le_ra_soat = (n_ra_soat / len(cau_hoi) * 100) if cau_hoi else 0.0
    n_cong_khai = sum(1 for c in cau_hoi if c.get("loai_du_lieu") == "cong_khai")
    n_noi_bo = len(cau_hoi) - n_cong_khai

    print(f"\n=== BÁO CÁO ĐO RAG (BR-06) | Bộ đề: {nguon_file} ===")
    print(
        f"Tổng câu hỏi: {len(cau_hoi)} (công khai: {n_cong_khai}, nội bộ gõ tay: {n_noi_bo}) | "
        f"Người rà soát: {n_ra_soat}/{len(cau_hoi)} ({ty_le_ra_soat:.1f}%)"
    )

    header = (
        f"\n{'Cấu hình':<26}{'Đoạn':>6}{'Recall@15 (95% CI)':>24}{'May rủi@15':>12}"
        f"{'Recall@20 (95% CI)':>24}{'May rủi@20':>12}{'MRR':>8}"
    )
    print(header)
    print("-" * len(header))
    for kq in ket_qua_ds:
        r15_str = f"{kq.recall_15:.3f} [{kq.recall_15_ci[0]:.2f},{kq.recall_15_ci[1]:.2f}]"
        r20_str = f"{kq.recall_20:.3f} [{kq.recall_20_ci[0]:.2f},{kq.recall_20_ci[1]:.2f}]"
        print(
            f"{kq.ten:<26}{kq.tong_doan_trong_kho:>6}{r15_str:>24}{kq.may_rui_15:>12.3f}"
            f"{r20_str:>24}{kq.may_rui_20:>12.3f}{kq.mrr:>8.3f}"
        )

    chinh = ket_qua_ds[0]
    dat_nguong = "ĐẠT" if chinh.recall_20 >= NGUONG_RECALL20_MUC_TIEU else "CHƯA ĐẠT"
    print(
        f"\nMốc khởi điểm Recall@20 >= {NGUONG_RECALL20_MUC_TIEU:.2f}: "
        f"{chinh.recall_20:.3f} ({dat_nguong}) | Số tài liệu độc lập: {chinh.n_tai_lieu_doc_lap}"
    )

    print("\n--- Chỉ số tầng sinh & từ chối (ngưỡng mặc định RELEVANCE_THRESHOLD) ---")
    print(
        f"Precision từ chối: {chinh.refusal_precision:.3f} | "
        f"Recall từ chối: {chinh.refusal_recall:.3f} | "
        f"Tỷ lệ từ chối nhầm: {chinh.false_refusal_rate:.3f} | "
        f"Trung thực số liệu (grounding.py): {chinh.grounding_ok_rate:.3f} "
        f"({chinh.grounding_checked} ca kiểm)"
    )

    print("\n--- Đường cong ngưỡng ViRanker (sau sigmoid) ---")
    print(f"{'Ngưỡng':>8}{'Recall@3':>12}{'Recall từ chối':>18}{'Prec từ chối':>16}{'Từ chối nhầm':>16}")
    for d in chinh.duong_cong_nguong:
        dau = " <-- mặc định" if abs(d["nguong"] - RELEVANCE_THRESHOLD) < 1e-6 else ""
        print(
            f"{d['nguong']:>8.1f}{d['recall_top3']:>12.3f}{d['refusal_recall']:>18.3f}"
            f"{d['refusal_precision']:>16.3f}{d['false_refusal_rate']:>16.3f}{dau}"
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--de", type=Path, default=DEFAULT_DATASET_PATH, help="File JSONL câu hỏi đánh giá")
    ap.add_argument("--docs-dir", type=Path, default=DOCS_DIR, help="Thư mục corpus tài liệu")
    ap.add_argument("--tao-de", action="store_true", help="Tạo lại file câu hỏi từ corpus")
    ap.add_argument("--mock", action="store_true", help="Dùng model giả lập nhẹ (không cần GPU/mạng)")
    ap.add_argument("--ablation", action="store_true", help="Chạy thêm 3 bước so sánh cải tiến")
    ap.add_argument("--json", dest="json_out", default="", help="Ghi kết quả ra file JSON")
    args = ap.parse_args(argv)

    if args.tao_de or not args.de.is_file():
        cau_hoi = tao_bo_de_tu_corpus(args.de, args.docs_dir)
    else:
        cau_hoi = doc_bo_cau_hoi(args.de, args.docs_dir)

    tai_lieu = doc_corpus_tu_thu_muc(args.docs_dir)
    embedder = _MockEmbedder() if args.mock else None
    reranker = _MockReranker() if args.mock else None
    collection = _MockCollection() if args.mock else None

    ket_qua_ds: list[KetQuaDo] = []
    with tempfile.TemporaryDirectory(prefix="do_rag_") as tmp_dir:
        kb = KnowledgeBase(
            persist_dir=tmp_dir,
            embedder=embedder,
            reranker=reranker,
            collection=collection,
        )
        nap_kho_mac_dinh(kb, "ws_default", tai_lieu)
        ket_qua_ds.append(
            danh_gia_cau_hinh(kb, "ws_default", cau_hoi, ten="1_mac_dinh_hybrid+rerank")
        )

        if args.ablation:
            nap_kho_chia_doan_nho(kb, "ws_128tok", tai_lieu, kich_thuoc_ky_tu=450)
            ket_qua_ds.append(
                danh_gia_cau_hinh(kb, "ws_128tok", cau_hoi, ten="2_chia_doan_128tok")
            )
            ket_qua_ds.append(
                danh_gia_cau_hinh(
                    kb, "ws_default", cau_hoi, ten="3_tat_viranker", dung_reranker=False
                )
            )
            ket_qua_ds.append(
                danh_gia_cau_hinh(
                    kb, "ws_default", cau_hoi, ten="4_chi_vector_khong_bm25", dung_bm25=False
                )
            )

    in_bao_cao(ket_qua_ds, cau_hoi, args.de)

    if args.json_out:
        out_data = [
            {
                "ten": k.ten,
                "n_cau_co_tai_lieu": k.n_cau_co_tai_lieu,
                "n_cau_tu_choi": k.n_cau_tu_choi,
                "n_tai_lieu_doc_lap": k.n_tai_lieu_doc_lap,
                "tong_doan_trong_kho": k.tong_doan_trong_kho,
                "recall_15": round(k.recall_15, 4),
                "recall_15_ci": [round(x, 4) for x in k.recall_15_ci],
                "may_rui_15": round(k.may_rui_15, 4),
                "recall_20": round(k.recall_20, 4),
                "recall_20_ci": [round(x, 4) for x in k.recall_20_ci],
                "may_rui_20": round(k.may_rui_20, 4),
                "mrr": round(k.mrr, 4),
                "mrr_ci": [round(x, 4) for x in k.mrr_ci],
                "refusal_precision": round(k.refusal_precision, 4),
                "refusal_recall": round(k.refusal_recall, 4),
                "false_refusal_rate": round(k.false_refusal_rate, 4),
                "grounding_ok_rate": round(k.grounding_ok_rate, 4),
                "duong_cong_nguong": k.duong_cong_nguong,
            }
            for k in ket_qua_ds
        ]
        Path(args.json_out).write_text(
            json.dumps(out_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
