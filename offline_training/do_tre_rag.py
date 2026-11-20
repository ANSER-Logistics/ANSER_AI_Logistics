"""
offline_training/do_tre_rag.py — đo độ trễ từng bước của một lần tìm trong kho tri thức, và độ dài cặp đưa vào
bộ xếp hạng lại (#119).

VÌ SAO CÓ FILE NÀY
------------------
Kho tri thức chạy hai model trên CPU theo mặc định (`KB_DEVICE=cpu`): embedder `BAAI/bge-m3` và bộ xếp hạng lại
`namdp-ptit/ViRanker`. Chưa ai đo độ trễ của đường này. Nhóm nghiên cứu RAG (17/11/2026) ước từ FLOP rằng xếp
hạng lại 15 đoạn trên CPU mất 5 đến 20 giây mỗi câu hỏi: nếu đúng thì đó mới là nút cổ chai của nhánh tài liệu.
Nghi vấn thứ hai: `CrossEncoder` không đặt `max_length`, nên đoạn 1.200 ký tự cộng câu hỏi có thể bị cắt.

ĐO ĐÚNG ĐƯỜNG PRODUCTION, KHÔNG CHÉP LẠI NÓ
------------------------------------------
Script KHÔNG viết lại `KnowledgeBase.search()`. Nó bọc đồng hồ quanh bốn thứ mà `search()` gọi (embedder
`encode`, Chroma `query`, BM25 `get_scores`, reranker `predict`) rồi gọi chính `search()`. Chép lại thân hàm để
bấm giờ từng dòng thì phép đo lệch ngay khi ai đó sửa `search()` (R4). Phần chênh giữa tổng và bốn bước (tách từ
bằng `underthesea`, gộp ứng viên, sigmoid, lọc ngưỡng) in ở dòng "khác".

BỎ LẦN GỌI ĐẦU: lần đầu gồm cả nạp model lười và khởi động, nên không vào p50/p95 (ghi riêng để đọc).

DỮ LIỆU (R2): chỉ văn bản pháp luật công khai trong `src/data/docs/` (đuôi `.docx`, `.md`), cùng 20 câu hỏi tự
viết ở dưới. Không đọc gì khác trong `src/data/`.

CHẠY (Colab; nạp model thật nên không chạy trong CI)
    python offline_training/do_tre_rag.py --device cpu  --lan 100 --json tre_rag_cpu.json
    python offline_training/do_tre_rag.py --device cuda --lan 100 --json tre_rag_gpu.json
Phần thuần (phân vị, đếm vượt ngưỡng, tóm tắt) có test trong `tests/test_do_tre_rag.py`.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCS = ROOT / "src" / "data" / "docs"
DUOI_PHAP_LUAT = (".docx", ".md")      # PDF trong thư mục là báo cáo ngành; .txt là chính sách cửa hàng mẫu
WS = "do_tre_rag"
NGUONG_CAT = 512                        # mức của ví dụ trên thẻ ViRanker (#119); ngưỡng thật đọc từ model

# 20 câu hỏi tự viết về đúng các văn bản trong kho. Không chứa dữ liệu khách (R2).
CAU_HOI = [
    "Thuế suất thuế thu nhập doanh nghiệp phổ thông là bao nhiêu phần trăm?",
    "Doanh nghiệp có doanh thu dưới 3 tỷ đồng được áp thuế suất ưu đãi nào?",
    "Khoản chi nào không được trừ khi xác định thu nhập chịu thuế?",
    "Doanh nghiệp được chuyển lỗ trong bao nhiêu năm?",
    "Thu nhập tính thuế được xác định theo công thức nào?",
    "Thu nhập từ chuyển nhượng bất động sản có phải kê khai riêng không?",
    "Hoá đơn điện tử phải có những nội dung bắt buộc nào?",
    "Thời điểm lập hoá đơn khi bán hàng hoá là lúc nào?",
    "Khi hoá đơn đã lập có sai sót thì xử lý ra sao?",
    "Ai phải đăng ký sử dụng hoá đơn điện tử có mã của cơ quan thuế?",
    "Hộ kinh doanh nộp thuế theo phương pháp khoán được hiểu thế nào?",
    "Thời hạn nộp hồ sơ khai thuế theo quý là khi nào?",
    "Chậm nộp tiền thuế thì bị tính tiền chậm nộp bao nhiêu mỗi ngày?",
    "Văn bản này có hiệu lực thi hành từ ngày nào?",
    "Chi phí khấu hao tài sản cố định được trừ khi nào?",
    "Thu nhập được miễn thuế thu nhập doanh nghiệp gồm những khoản nào?",
    "Doanh nghiệp mới thành lập được ưu đãi thuế trong bao lâu?",
    "Điều kiện để chi phí lãi vay được trừ là gì?",
    "Hồ sơ hoàn thuế gồm những giấy tờ gì?",
    "Cơ quan nào có thẩm quyền kiểm tra hoá đơn của doanh nghiệp?",
]
BUOC = ("nhung_cau_hoi", "chroma", "bm25", "xep_hang_lai")


# ---------------------------------------------------------------------------
# Phần thuần (có test)
# ---------------------------------------------------------------------------

def phan_vi(mau: list[float], q: float) -> float | None:
    """Nearest-rank (ceil(n×q)−1), cùng cách với `nguong_p95.p95`: n nhỏ thì p95 ≈ max, không tụt."""
    if not mau:
        return None
    if not 0 < q <= 1:
        raise ValueError(f"q={q} phải trong (0, 1]")
    xep = sorted(mau)
    return xep[min(len(xep) - 1, math.ceil(len(xep) * q) - 1)]


def tom_tat(mau: list[float], bo_dau: int = 1) -> dict[str, Any]:
    """p50/p95/max sau khi bỏ `bo_dau` mẫu đầu (khởi động). Lần đầu vẫn trả để đọc, không vào phân vị."""
    dung = mau[bo_dau:]
    return {
        "n": len(dung),
        "lan_dau": round(mau[0], 2) if mau and bo_dau else None,
        "p50": None if not dung else round(phan_vi(dung, 0.5), 2),     # type: ignore[arg-type]
        "p95": None if not dung else round(phan_vi(dung, 0.95), 2),    # type: ignore[arg-type]
        "max": None if not dung else round(max(dung), 2),
    }


def dem_vuot(do_dai: list[int], nguong: int) -> dict[str, Any]:
    """Bao nhiêu cặp DÀI HƠN `nguong` token (bằng thì không bị cắt)."""
    vuot = sum(1 for d in do_dai if d > nguong)
    return {
        "nguong": nguong,
        "n": len(do_dai),
        "vuot": vuot,
        "ti_le_pct": None if not do_dai else round(100 * vuot / len(do_dai), 2),
    }


class DoGio:
    """
    Bọc một đối tượng, bấm giờ đúng một phương thức, chuyển mọi thứ khác qua nguyên vẹn.

    Lần gọi nào cũng ghi vào `so[ten]` (mili giây). `khi_goi(args)` (nếu có) được gọi TRƯỚC phương thức thật,
    để ghi thêm thứ cần đo từ đầu vào (ví dụ độ dài cặp đưa vào reranker), và không tính vào thời gian.
    """

    def __init__(self, goc: Any, phuong_thuc: str, ten: str, so: dict[str, list[float]], khi_goi: Any = None):
        self._goc, self._pt, self._ten, self._so, self._khi_goi = goc, phuong_thuc, ten, so, khi_goi

    def __getattr__(self, name: str) -> Any:
        thuoc_tinh = getattr(self._goc, name)
        if name != self._pt:
            return thuoc_tinh

        def bam_gio(*args: Any, **kwargs: Any) -> Any:
            if self._khi_goi:
                self._khi_goi(*args, **kwargs)
            t0 = time.perf_counter()
            try:
                return thuoc_tinh(*args, **kwargs)
            finally:
                self._so[self._ten].append((time.perf_counter() - t0) * 1000)
        return bam_gio


# ---------------------------------------------------------------------------
# Phần nạp model (Colab)
# ---------------------------------------------------------------------------

def _may() -> dict[str, Any]:
    may: dict[str, Any] = {"python": platform.python_version(), "cpu_logic": os.cpu_count()}
    try:
        cpu = [d for d in Path("/proc/cpuinfo").read_text().splitlines() if d.startswith("model name")]
        may["cpu"] = cpu[0].split(":", 1)[1].strip() if cpu else platform.processor()
        mem = [d for d in Path("/proc/meminfo").read_text().splitlines() if d.startswith("MemTotal")]
        may["ram_gib"] = round(int(mem[0].split()[1]) / 2**20, 1) if mem else None
    except OSError:
        may["cpu"] = platform.processor()
    try:
        import torch
        may["torch"] = torch.__version__
        may["gpu"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except ImportError:
        may["torch"] = None
    return may


def _nap_kho(kb: Any) -> tuple[list[str], dict[str, Any]]:
    from src.core.chunking import chunk_document
    from src.core.doc_extract import extract

    doan: list[str] = []
    nap: dict[str, Any] = {}
    for p in sorted(DOCS.iterdir()):
        if p.suffix.lower() not in DUOI_PHAP_LUAT:
            continue
        van_ban = extract(p.read_bytes(), p.name).text
        t0 = time.perf_counter()
        kq = kb.add_document(WS, van_ban, p.name)
        nap[p.name] = {"doan": kq.chunks, "giay": round(time.perf_counter() - t0, 1),
                       "trung_voi": kq.duplicate_of}
        if kq.chunks:
            doan.extend(c.text for c in chunk_document(van_ban))
    return doan, nap


def chay(lan: int, device: str) -> dict[str, Any]:
    from src.core.knowledge import KnowledgeBase

    so: dict[str, list[float]] = defaultdict(list)
    do_dai_cap: list[int] = []
    kb = KnowledgeBase(persist_dir=tempfile.mkdtemp(prefix="do_tre_rag_"), device=device)

    t0 = time.perf_counter()
    _ = (kb.embedder, kb.reranker)    # nạp lười: tách giờ nạp model khỏi giờ truy vấn
    nap_model_s = round(time.perf_counter() - t0, 1)
    ce: Any = kb.reranker              # CrossEncoder thật, giữ lại trước khi bọc
    tok = ce.tokenizer

    def ghi_do_dai(cap: list[list[str]], **_: Any) -> None:
        do_dai_cap.extend(len(tok(q, d, truncation=False)["input_ids"]) for q, d in cap)

    t0 = time.perf_counter()
    doan, nap = _nap_kho(kb)
    nap_kho_s = round(time.perf_counter() - t0, 1)

    kb._embedder = DoGio(kb.embedder, "encode", "nhung_cau_hoi", so)
    kb._reranker = DoGio(kb.reranker, "predict", "xep_hang_lai", so, khi_goi=ghi_do_dai)
    kb._collection = DoGio(kb.collection, "query", "chroma", so)
    bm25, cap_bm25 = kb._bm25_for(WS)                # dựng một lần, rồi bọc trong cache
    kb._bm25_cache[WS] = (DoGio(bm25, "get_scores", "bm25", so), cap_bm25)

    so_ung_vien: list[int] = []
    for i in range(lan + 1):                          # +1: lần đầu bị bỏ khỏi phân vị
        cau = CAU_HOI[i % len(CAU_HOI)]
        truoc = len(do_dai_cap)
        t0 = time.perf_counter()
        kb.search(WS, cau)
        so["tong"].append((time.perf_counter() - t0) * 1000)
        so_ung_vien.append(len(do_dai_cap) - truoc)

    khac = [t - sum(so[b][i] for b in BUOC if i < len(so[b])) for i, t in enumerate(so["tong"])]

    # Ngưỡng cắt thật, đọc từ model, không đoán (PCBoiz 19/11 đoán 8192 từ config).
    max_len = getattr(ce, "max_length", None) or getattr(ce, "max_seq_length", None)
    nguong = {
        "crossencoder_max_length": max_len,
        "tokenizer_model_max_length": getattr(tok, "model_max_length", None),
        "config_max_position_embeddings": getattr(getattr(getattr(ce, "model", None), "config", None),
                                                  "max_position_embeddings", None),
    }
    # Mọi cặp (câu hỏi, đoạn) của kho, không chỉ cặp được chọn: đúng như #119 bước 2.
    moi_cap = [len(tok(q, d, truncation=False)["input_ids"]) for q in CAU_HOI for d in doan]

    return {
        "may": _may(), "device": device, "lan": lan,
        "nap_model_s": nap_model_s, "nap_kho_s": nap_kho_s, "nap_kho": nap, "so_doan": len(doan),
        "tre_ms": {**{b: tom_tat(so[b]) for b in (*BUOC, "tong")}, "khac": tom_tat(khac)},
        "ung_vien_moi_cau": tom_tat([float(x) for x in so_ung_vien]),
        "nguong_model": nguong,
        "cap_da_xep_hang": {"do_dai": tom_tat([float(x) for x in do_dai_cap], bo_dau=0),
                            "vuot_512": dem_vuot(do_dai_cap, NGUONG_CAT),
                            "vuot_max_length": dem_vuot(do_dai_cap, max_len) if max_len else None},
        "moi_cap_cua_kho": {"do_dai": tom_tat([float(x) for x in moi_cap], bo_dau=0),
                            "vuot_512": dem_vuot(moi_cap, NGUONG_CAT),
                            "vuot_max_length": dem_vuot(moi_cap, max_len) if max_len else None},
    }


def in_bang(kq: dict[str, Any]) -> None:
    print(f"\nMáy: {kq['may']}\nThiết bị: {kq['device']} | nạp model {kq['nap_model_s']} s | "
          f"nạp kho {kq['nap_kho_s']} s, {kq['so_doan']} đoạn")
    print(f"\n{'bước (ms)':<16}{'n':>5}{'lần đầu':>10}{'p50':>10}{'p95':>10}{'max':>10}")
    for b, t in kq["tre_ms"].items():
        print(f"{b:<16}{t['n']:>5}{str(t['lan_dau']):>10}{str(t['p50']):>10}{str(t['p95']):>10}{str(t['max']):>10}")
    print(f"\nỨng viên đưa vào xếp hạng lại mỗi câu: {kq['ung_vien_moi_cau']}")
    print(f"Ngưỡng cắt đọc từ model: {kq['nguong_model']}")
    for ten in ("cap_da_xep_hang", "moi_cap_cua_kho"):
        c = kq[ten]
        print(f"\n[{ten}] độ dài token {c['do_dai']}\n  vượt 512: {c['vuot_512']}\n  vượt max_length: {c['vuot_max_length']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", default=os.getenv("KB_DEVICE", "cpu"), help="cpu (mặc định production) hoặc cuda")
    ap.add_argument("--lan", type=int, default=100, help="số lần truy vấn tính vào phân vị (chưa kể lần đầu)")
    ap.add_argument("--json", default="", help="ghi kết quả đầy đủ ra file này")
    a = ap.parse_args(argv)
    if a.lan < 1:
        ap.error("--lan phải ≥ 1")
    kq = chay(a.lan, a.device)
    in_bang(kq)
    if a.json:
        Path(a.json).write_text(json.dumps(kq, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nĐã ghi {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
