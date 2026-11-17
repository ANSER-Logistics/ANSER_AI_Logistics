"""
do_router_dung_chung_embedder.py — đo rủi ro router dùng chung embedder với kho tri thức (#85).

VÌ SAO CÓ PHÉP ĐO NÀY
    Sau BR-27 (PR #78) mọi thao tác `KnowledgeBase` chạy trên MỘT worker riêng (`chay_tren_kho`),
    ngoài event loop. Nhưng `SemanticRouter.route_with_score` vẫn chạy TRÊN event loop và, khi kho đã
    nạp embedder, nó DÙNG CHUNG embedder đó (`ManagerAgent.__init__` -> `kb.loaded_embedder()`).
    Tức là hai thread có thể gọi `encode` trên cùng một `SentenceTransformer` cùng lúc. Tokenizer
    nhanh của HuggingFace từng báo `RuntimeError: Already borrowed` trong tình huống đó.

    Máy dev không có embedder thật (ENV=LOCAL không nạp model), nên phép đo chạy trên Colab có GPU.
    Đặt ở `offline_training/`, không ở `tests/`: cần model thật, không chạy trong CI.

ĐO GÌ
    1. TUẦN TỰ: định tuyến từng câu một và tìm kiếm từng câu một -> kết quả chuẩn.
    2. Độ trễ router khi kho RẢNH.
    3. ĐỒNG THỜI: router chạy trên loop (đúng như `chat.py`) trong khi worker kho liên tục
       `search` và `add_document`. Ghi lại:
         - ngoại lệ (đếm theo loại, giữ một traceback mẫu mỗi loại)
         - kết quả định tuyến khác với lúc tuần tự (nhánh, cách quyết định, điểm lệch > 1e-4)
         - kết quả tìm kiếm khác với lúc tuần tự (nguồn + số đoạn)
         - độ trễ p50/p95 của router khi kho đang bận
         - số lượt router chạy CHỒNG LÊN lúc worker đang `encode`: nếu bằng 0 thì phép đo
           không chạm được rủi ro, và kết luận "không thấy vấn đề" là vô nghĩa

    Chỉ những câu router quyết định bằng EMBEDDING mới được dùng: câu khớp từ khoá trả lời ở lớp 1,
    không gọi `encode`, nên không chạm rủi ro. Danh sách câu lấy từ chính câu ví dụ của router (do
    team viết). Tài liệu nạp vào kho là văn bản hư cấu sinh ngay trong script. Không có dữ liệu khách,
    không gọi ra ngoài trừ việc tải model từ HuggingFace (R2).

HAI ĐƯỜNG (`--duong`, thêm 17/11/2026 sau PR #116)
    moi  (mặc định) đúng như `chat.py` hôm nay: `chat._phan_loai` -> câu cần embedding chạy trên
         worker DUY NHẤT của kho (`manager.cach_chay` == "kho"), nên hai lời gọi `encode` không chồng
         nhau và loop không bị chặn. Trễ router giờ GỒM thời gian xếp hàng sau việc của kho.
    cu   đường trước PR #116: `manager.analyze_task` phân loại NGAY TRÊN LOOP. Giữ để so với số đo
         16/11 (trễ router khi kho bận p95 230–277 ms) và để test chứng minh script bắt được lỗi.
    Cả hai đường đều đo thêm ĐỘ TRỄ CỦA EVENT LOOP khi kho bận (`tre_loop_ms`): một nhịp ngủ 10 ms,
    lệch bao nhiêu là loop bị chặn bấy nhiêu. #116 nhắm đúng con số này, không phải trễ router.

CHẠY (Colab, sau khi clone repo và cài requirements)
    ENV=GPU python offline_training/do_router_dung_chung_embedder.py --luot 3000 --out /content/r85.json
    # Kho mặc định chạy embedder trên CPU (KB_DEVICE, như production). Đo thêm trên GPU:
    ENV=GPU python offline_training/do_router_dung_chung_embedder.py --device cuda --out /content/r85_cuda.json
    # Đường trước #116, để so: thêm --duong cu

MÃ THOÁT
    0  không thấy vấn đề, và có đủ lượt chạy chồng
    1  CÓ vấn đề (ngoại lệ hoặc kết quả lệch)
    2  KHÔNG ĐO ĐƯỢC (không nạp được embedder, không có câu nào đi tới embedding, hoặc không lượt
       nào chạy chồng). Không phải "đạt".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import tempfile
import threading
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WS_DO = "ws-do-85"        # kho để TÌM: nội dung không đổi suốt phép đo, nên kết quả phải ổn định
WS_TAI = "ws-tai-85"      # kho để GHI: nạp lại liên tục, tạo tải `encode` trên worker
LECH_DIEM = 1e-4
LUOT_CHONG_TOI_THIEU = 50
NHIP_LOOP_S = 0.010

# Câu hỏi tìm kiếm — khớp với tài liệu hư cấu bên dưới.
CAU_TIM = [
    "phụ phí giao hàng ban đêm là bao nhiêu",
    "quy định đền bù hàng hư hỏng",
    "thời gian lưu kho miễn phí",
    "xe container 40 feet chở được bao nhiêu tấn",
    "chính sách huỷ chuyến trước giờ xuất phát",
    "điều kiện thanh toán công nợ",
]


def tai_lieu_hu_cau(so: int, phien_ban: int = 0) -> str:
    """Văn bản quy định vận tải HƯ CẤU, đủ dài để thành nhiều đoạn. `phien_ban` đổi nội dung."""
    muc = [
        ("Phụ phí ban đêm", f"Giao hàng từ 22 giờ đến 5 giờ sáng cộng thêm {15 + so + phien_ban}% cước."),
        ("Đền bù hư hỏng", "Hàng hư hỏng do vận chuyển được đền theo giá trị khai báo, tối đa "
                           f"{10 + so} lần cước chuyến."),
        ("Lưu kho", f"Miễn phí lưu kho {2 + so % 3} ngày đầu, sau đó tính theo ngày."),
        ("Loại xe", "Xe container 40 feet chở tối đa 26 tấn; xe tải 8 tấn dùng cho tuyến nội tỉnh."),
        ("Huỷ chuyến", "Huỷ trước giờ xuất phát 24 giờ không mất phí; muộn hơn tính 30% cước."),
        ("Thanh toán", f"Công nợ thanh toán trong {30 + so} ngày kể từ ngày xuất hoá đơn."),
    ]
    than = []
    for tieu_de, noi_dung in muc:
        than.append(f"## {tieu_de}\n\n{noi_dung} " + " ".join(
            f"Điều khoản phụ {k} của mục {tieu_de.lower()} áp dụng cho hợp đồng mẫu số {so}."
            for k in range(1, 6)
        ))
    return f"# Quy định vận tải mẫu số {so} (bản {phien_ban})\n\n" + "\n\n".join(than)


class DemTrenWorker:
    """Đếm số thao tác kho đang chạy trên worker, để biết router có thật sự chạy chồng không."""

    def __init__(self) -> None:
        self._khoa = threading.Lock()
        self._dang_chay = 0

    def boc(self, fn):
        def chay(*a, **kw):
            with self._khoa:
                self._dang_chay += 1
            try:
                return fn(*a, **kw)
            finally:
                with self._khoa:
                    self._dang_chay -= 1
        return chay

    @property
    def dang_ban(self) -> bool:
        return self._dang_chay > 0


class SoLoi:
    def __init__(self) -> None:
        self.dem: Counter[str] = Counter()
        self.mau: dict[str, str] = {}

    def ghi(self, noi: str, exc: BaseException) -> None:
        khoa = f"{noi}: {type(exc).__name__}: {str(exc)[:120]}"
        self.dem[khoa] += 1
        self.mau.setdefault(khoa, "".join(traceback.format_exception(exc))[-2000:])


def p(x: list[float], q: float) -> float | None:
    if not x:
        return None
    x = sorted(x)
    return x[min(len(x) - 1, int(round(q * (len(x) - 1))))]


def tom_tat_tim(passages) -> list[tuple[str, int]]:
    return [(ps.source, ps.chunk_index) for ps in passages]


async def do(args) -> tuple[int, dict[str, Any]]:
    from src.agents.manager import ManagerAgent
    from src.api.chay_ngoai_loop import chay_tren_kho
    from src.api.routes.chat import _phan_loai
    from src.core.knowledge import EMBEDDER_ID, KnowledgeBase

    duong = getattr(args, "duong", "moi")
    bao_cao: dict[str, Any] = {"embedder": EMBEDDER_ID, "device": args.device, "luot": args.luot,
                               "duong": duong}
    kb = KnowledgeBase(tempfile.mkdtemp(prefix="kb85-"), device=args.device)
    try:
        t0 = time.perf_counter()
        _ = kb.embedder                         # ép nạp TRƯỚC khi dựng ManagerAgent, để router dùng chung
        bao_cao["nap_embedder_s"] = round(time.perf_counter() - t0, 1)
    except Exception as exc:                    # noqa: BLE001 — báo rõ, thoát mã 2
        bao_cao["khong_do_duoc"] = f"không nạp được embedder: {type(exc).__name__}: {exc}"
        return 2, bao_cao

    manager = ManagerAgent(engine=None, memory=None, kb=kb)
    if manager.router.embedder is not kb.loaded_embedder():
        bao_cao["khong_do_duoc"] = "router KHÔNG dùng chung embedder với kho — không phải cấu hình cần đo"
        return 2, bao_cao
    bao_cao["dung_chung_embedder"] = True

    async def phan_loai(c: str) -> dict:
        if duong == "cu":
            return await manager.analyze_task(c)        # trước #116: encode NGAY TRÊN LOOP
        return await _phan_loai(manager, c)             # như chat.py hôm nay

    for so in range(args.so_tai_lieu):
        kb.add_document(WS_DO, tai_lieu_hu_cau(so), f"quy-dinh-{so}.md")
    kb.add_document(WS_TAI, tai_lieu_hu_cau(99), "nap-lai.md")

    # ---- 1. Tuần tự: kết quả chuẩn -----------------------------------------------------
    ung_vien = sorted({c for vd in manager.router.routes.values() for c in vd})
    chuan_router: dict[str, dict] = {}
    phan_bo: Counter[str] = Counter()
    for c in ung_vien:
        kq = manager.router.route_with_score(c)
        phan_bo[kq["method"]] += 1
        if kq["method"] not in ("keyword", "empty", "keyword_only_degraded"):
            chuan_router[c] = kq
    bao_cao["phan_bo_method_ung_vien"] = dict(phan_bo)
    bao_cao["so_cau_di_toi_embedding"] = len(chuan_router)
    if not chuan_router:
        bao_cao["khong_do_duoc"] = "không câu ví dụ nào đi tới lớp embedding — phép đo không chạm encode"
        return 2, bao_cao
    cau_router = list(chuan_router)

    chuan_tim = {q: tom_tat_tim(kb.search(WS_DO, q)) for q in CAU_TIM}
    bao_cao["tim_co_ket_qua"] = sum(1 for v in chuan_tim.values() if v)

    # ---- 2. Độ trễ khi kho rảnh --------------------------------------------------------
    tre_ranh = []
    for i in range(min(300, args.luot)):
        t = time.perf_counter()
        await phan_loai(cau_router[i % len(cau_router)])
        tre_ranh.append((time.perf_counter() - t) * 1000)

    # ---- 3. Đồng thời ----------------------------------------------------------------
    loi = SoLoi()
    dem = DemTrenWorker()
    tim_boc = dem.boc(kb.search)
    nap_boc = dem.boc(kb.add_document)
    lech_router: Counter[str] = Counter()
    lech_tim: Counter[str] = Counter()
    mau_lech: list[dict] = []
    tre_ban: list[float] = []
    luot_chong = 0
    so_tim = so_nap = 0
    xong = asyncio.Event()
    rng = random.Random(85)

    async def mot_thao_tac_kho(i: int) -> None:
        nonlocal so_tim, so_nap
        if i % args.nap_moi == 0:
            so_nap += 1
            try:
                await chay_tren_kho(nap_boc, WS_TAI, tai_lieu_hu_cau(99, phien_ban=i), "nap-lai.md")
            except Exception as exc:            # noqa: BLE001 — đếm, không nuốt
                loi.ghi("add_document", exc)
            return
        q = rng.choice(CAU_TIM)
        so_tim += 1
        try:
            kq = tom_tat_tim(await chay_tren_kho(tim_boc, WS_DO, q))
        except Exception as exc:                # noqa: BLE001
            loi.ghi("search", exc)
            return
        if kq != chuan_tim[q]:
            lech_tim[q] += 1
            if len(mau_lech) < 10:
                mau_lech.append({"loai": "search", "cau": q, "chuan": chuan_tim[q], "dong_thoi": kq})

    async def bom_tai_kho() -> None:
        """Giữ hàng đợi worker luôn có việc cho tới khi router chạy xong."""
        i = 0
        dang: set[asyncio.Task] = set()
        while not xong.is_set():
            while len(dang) < args.hang_doi:
                i += 1
                dang.add(asyncio.create_task(mot_thao_tac_kho(i)))
            _, dang = await asyncio.wait(dang, return_when=asyncio.FIRST_COMPLETED)
        if dang:
            await asyncio.wait(dang)

    async def chay_router() -> None:
        nonlocal luot_chong
        for i in range(args.luot):
            c = cau_router[i % len(cau_router)]
            chong = dem.dang_ban
            t = time.perf_counter()
            try:
                kq = await phan_loai(c)
            except Exception as exc:            # noqa: BLE001
                loi.ghi("router", exc)
                await asyncio.sleep(0)
                continue
            tre = (time.perf_counter() - t) * 1000
            if chong or dem.dang_ban:
                luot_chong += 1
                tre_ban.append(tre)
            ch = chuan_router[c]
            if (kq["category"] != ch["route"] or kq.get("method") != ch["method"]
                    or abs(kq["score"] - ch["score"]) > LECH_DIEM):
                lech_router[c] += 1
                if len(mau_lech) < 10:
                    mau_lech.append({"loai": "router", "cau": c, "chuan": ch, "dong_thoi": kq})
            # Nhường loop để worker được nạp việc mới — giống request thật xen kẽ nhau.
            await asyncio.sleep(0)
        xong.set()

    tre_loop: list[float] = []

    async def do_tre_loop() -> None:
        """Nhịp ngủ 10 ms: dậy muộn bao nhiêu là loop bị việc khác chặn bấy nhiêu."""
        while not xong.is_set():
            t = time.perf_counter()
            await asyncio.sleep(NHIP_LOOP_S)
            tre_loop.append(max(0.0, (time.perf_counter() - t - NHIP_LOOP_S) * 1000))

    t_dt = time.perf_counter()
    await asyncio.gather(bom_tai_kho(), chay_router(), do_tre_loop())
    bao_cao["dong_thoi_s"] = round(time.perf_counter() - t_dt, 1)

    bao_cao.update({
        "luot_router": args.luot,
        "luot_router_chay_chong": luot_chong,
        "luot_search": so_tim,
        "luot_add_document": so_nap,
        "ngoai_le": dict(loi.dem),
        "ngoai_le_mau": loi.mau,
        "router_lech": sum(lech_router.values()),
        "search_lech": sum(lech_tim.values()),
        "mau_lech": mau_lech,
        "tre_router_ms": {
            "ranh_p50": p(tre_ranh, 0.5), "ranh_p95": p(tre_ranh, 0.95),
            "ban_p50": p(tre_ban, 0.5), "ban_p95": p(tre_ban, 0.95),
            "ban_tb": statistics.fmean(tre_ban) if tre_ban else None,
        },
        "tre_loop_ms": {
            "so_nhip": len(tre_loop), "p50": p(tre_loop, 0.5), "p95": p(tre_loop, 0.95),
            "max": max(tre_loop) if tre_loop else None,
        },
    })

    co_van_de = bool(loi.dem) or bao_cao["router_lech"] or bao_cao["search_lech"]
    if co_van_de:
        bao_cao["ket_luan"] = "CÓ VẤN ĐỀ"
        return 1, bao_cao
    if luot_chong < LUOT_CHONG_TOI_THIEU:
        bao_cao["ket_luan"] = (f"KHÔNG ĐO ĐƯỢC: chỉ {luot_chong} lượt router chạy chồng lên worker "
                               f"(cần >= {LUOT_CHONG_TOI_THIEU})")
        return 2, bao_cao
    bao_cao["ket_luan"] = "KHÔNG THẤY VẤN ĐỀ"
    return 0, bao_cao


def in_bao_cao(bc: dict[str, Any]) -> None:
    print("=" * 64)
    print(f"  #85 — router dùng chung embedder ({bc.get('embedder')}, device={bc.get('device')}, "
          f"đường={bc.get('duong')})")
    print("=" * 64)
    if "khong_do_duoc" in bc:
        print(f"KHÔNG ĐO ĐƯỢC: {bc['khong_do_duoc']}")
        return
    print(f"câu đi tới embedding : {bc['so_cau_di_toi_embedding']}  (phân bố ứng viên: "
          f"{bc['phan_bo_method_ung_vien']})")
    print(f"router               : {bc['luot_router']} lượt, {bc['luot_router_chay_chong']} lượt chạy chồng")
    print(f"kho (worker)         : {bc['luot_search']} search, {bc['luot_add_document']} add_document")
    print(f"ngoại lệ             : {sum(bc['ngoai_le'].values())}")
    for k, v in bc["ngoai_le"].items():
        print(f"    {v:6d} × {k}")
    print(f"kết quả lệch         : router {bc['router_lech']}, search {bc['search_lech']}")
    t = bc["tre_router_ms"]

    def f(x):
        return "—" if x is None else f"{x:.1f}"

    print(f"trễ router (ms)      : rảnh p50 {f(t['ranh_p50'])} / p95 {f(t['ranh_p95'])}   "
          f"bận p50 {f(t['ban_p50'])} / p95 {f(t['ban_p95'])}")
    lp = bc["tre_loop_ms"]
    print(f"loop bị chặn (ms)    : p50 {f(lp['p50'])} / p95 {f(lp['p95'])} / max {f(lp['max'])}  "
          f"({lp['so_nhip']} nhịp, khi kho bận)")
    print(f"\nKẾT LUẬN: {bc['ket_luan']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--luot", type=int, default=3000, help="số lượt router trong pha đồng thời")
    ap.add_argument("--device", default=None, help="thiết bị embedder của kho; mặc định KB_DEVICE (cpu)")
    ap.add_argument("--so-tai-lieu", type=int, default=4)
    ap.add_argument("--hang-doi", type=int, default=4, help="số thao tác kho chờ sẵn trên worker")
    ap.add_argument("--nap-moi", type=int, default=5, help="cứ N thao tác kho thì 1 lần add_document")
    ap.add_argument("--out", default="", help="ghi báo cáo JSON")
    ap.add_argument("--duong", choices=["moi", "cu"], default="moi",
                    help="moi = như chat.py sau PR #116 (mặc định); cu = phân loại ngay trên loop như trước")
    args = ap.parse_args()
    if args.device is None:
        import os
        args.device = os.getenv("KB_DEVICE", "cpu")

    ma, bc = asyncio.run(do(args))
    in_bao_cao(bc)
    if args.out:
        Path(args.out).write_text(json.dumps(bc, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(f"\nBáo cáo JSON: {args.out}")
    sys.exit(ma)


if __name__ == "__main__":
    main()
