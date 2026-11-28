"""
offline_training/demo_colab.py — chạy toàn bộ phần CẦN MÔ HÌNH của buổi demo trên Google Colab Pro, tự thử, rồi mở đường hầm cho Body ở máy nhà.

DÙNG: notebook Colab mới, runtime GPU L4 hoặc A100, MỘT ô:

    from google.colab import drive; drive.mount("/content/drive")
    !rm -rf /content/ANSER_AI && git clone -q --depth 1 -b feat/tich-hop-body https://github.com/ANSER-Logistics/ANSER_AI_Logistics.git /content/ANSER_AI
    %run -i /content/ANSER_AI/offline_training/demo_colab.py

Ô chạy khoảng 15 đến 25 phút lần đầu (cài thư viện, chép trọng số, nạp model) rồi in hai dòng BRAIN_URL, BRAIN_API_TOKEN và GIỮ PHIÊN SỐNG. Bấm dừng ô khi xong: đóng đường hầm, tắt server.
Máy nhà chỉ chạy Body và cơ sở dữ liệu (offline_training/demo_mot_may/README.md, mục "Có model thật").

GỒM GÌ (cấu hình đã đo: PR #277, RUNBOOK §8.6 và §9)
  vLLM 0.11.2 text  : anser-v5-awq (Drive)             cổng 8001, 43% GPU, ngữ cảnh 14336
  vLLM 0.11.2 vision: q25vl7b-w4a16-tu-luong-tu (Drive) cổng 8002, 44% GPU, ngữ cảnh 8192
  Brain (ENV=SERVER, không nạp model; kho tri thức bge-m3 + ViRanker trên CPU) cổng 8000, chỉ nghe 127.0.0.1
  Đường hầm: ngrok nếu có NGROK_AUTHTOKEN trong Colab Secrets, không thì cloudflared (bản ghim, đối chiếu SHA-256).
  GPU nhỏ (T4 15 GB, khi L4/A100 hết): chế độ CHỈ CHỮ — một server text (nhân awq, float16, 90% GPU, ngữ cảnh 8192), không đọc ảnh. Cấu hình này CHƯA đo chất lượng.
  GPU lớn (A100): hai server bị bó trong ngân sách VRAM của một L4 (production tối đa L4 24 GB) và đo đỉnh VRAM so với 92% ngân sách đó; DEMO_NGAN_SACH_VRAM_MIB=0 để dùng cả GPU.

GIỚI HẠN PHẢI BIẾT
  - Colab dành cho tính toán tương tác; FAQ cấm "web service offerings not related to interactive compute" và "connecting to remote proxies" (đọc 28/11/2026). Chạy để thử và demo do chính bạn điều khiển,
    không đưa địa chỉ cho người khác, tắt khi xong; không dùng làm chỗ phục vụ khách (AGENTS.md §3.1).
  - CHỈ dữ liệu HƯ CẤU (R2): câu hỏi, ảnh và tài liệu đi qua đường hầm của bên thứ ba.
  - Token sinh ngẫu nhiên mỗi phiên, chỉ nằm trong bộ nhớ notebook và ô kết quả; không ghi vào Drive. Đừng chia sẻ notebook còn kèm kết quả chạy.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional

REPO = Path(os.getenv("ANSER_REPO_DIR", "/content/ANSER_AI"))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if not (REPO / "src").is_dir():       # chạy từ bản clone khác (hoặc test trên máy dev)
    REPO = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(REPO))

from offline_training.kiem_tich_hop_body import (  # noqa: E402
    BO_QUA,
    CANH_BAO,
    DAT,
    TRUOT,
    Brain,
    chat_cho_xong,
    chay_kiem,
    in_bang,
    ket_luan,
)
from sample_data.make_sample_data import (  # noqa: E402
    CAU_HOI_QUY_CHE,
    DAP_AN_QUY_CHE,
    HOA_DON_CUOC,
    LECH_HOA_DON,
    QUY_CHE,
    TEN_QUY_CHE,
    ghi_anh_hoa_don,
)

DRIVE = Path(os.getenv("ANSER_DRIVE_DIR", "/content/drive/MyDrive/ANSER_AI_Logistics"))
THU_MUC_MODEL = Path(os.getenv("ANSER_MODELS_DIR", "/content/models"))
RA = Path(os.getenv("ANSER_DEMO_KQ", "/content/demo_kq"))
BAN_VLLM = "0.11.2"
GPU_TOI_THIEU_MIB = 22_000      # đủ cho cả text lẫn vision (L4 22,5 GB, A100)
GPU_CHI_CHU_MIB = 14_000        # T4 15 GB: chỉ text, không đọc ảnh
NGAN_SACH_L4_MIB = 23_034       # tổng VRAM một L4 đo được (bat_lai_brain.py). Production tối đa là GPU này (chủ dự án, 28/11)
TRAN_SU_DUNG = 0.92             # cổng đồng host: đỉnh dùng không quá 92% VRAM (RUNBOOK §8.6, #124)
CONG_BRAIN = 8000
FILE_TOKENIZER = ("tokenizer.json", "tokenizer_config.json", "vocab.json", "merges.txt", "special_tokens_map.json", "added_tokens.json")
REPO_TOKENIZER_TEXT = "Qwen/Qwen3-8B"
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/download/2026.11.2/cloudflared-linux-amd64"
CLOUDFLARED_SHA256 = "56f13335143ec0e22772963290683a84a04114a35ec64cbc794a4d39ff9bb8cf"
CAU_HOI_VAT = "Tính thuế GTGT 8% cho đơn hàng trị giá 2.000.000 đồng."
DAP_AN_VAT = ("160.000", "160,000", "160000")


@dataclass(frozen=True)
class MayChu:
    ten: str                 # --served-model-name, cũng là VLLM_MODEL / VLLM_VISION_MODEL của Brain
    nguon: str               # thư mục trọng số trên Drive
    cong: int
    phan_gpu: str
    ngu_canh: str
    them: tuple[str, ...] = ()


def che_do_gpu(mib: int) -> Optional[str]:
    """`day_du` (text + vision), `chi_chu` (GPU nhỏ: chỉ text), hoặc None nếu không đủ cho cả text."""
    if mib >= GPU_TOI_THIEU_MIB:
        return "day_du"
    return "chi_chu" if mib >= GPU_CHI_CHU_MIB else None


def cac_may_chu(env: Mapping[str, str], chi_chu: bool = False) -> list[MayChu]:
    """Server cần bật (text đứng đầu), tên biến như compose (R5): đổi cấu hình bằng env, không sửa mã."""
    nguon = env.get("DEMO_TEXT_MODEL", "anser-v5-awq")
    if chi_chu:
        # T4 (Turing): không có bfloat16 và nhân awq_marlin, nên ép nhân `awq` kèm float16 (ghi ở ô "dùng model" của notebook train và compose). CHƯA ĐO chất lượng trên cấu hình này.
        return [MayChu("anser-v5", nguon, 8001, env.get("TEXT_GPU_FRACTION", "0.90"), env.get("TEXT_MAX_MODEL_LEN", "8192"), ("--quantization=awq", "--dtype=half"))]
    return [
        MayChu("anser-v5", nguon, 8001, env.get("TEXT_GPU_FRACTION", "0.43"), env.get("TEXT_MAX_MODEL_LEN", "14336")),
        MayChu("anser-vision", env.get("DEMO_VISION_MODEL", "q25vl7b-w4a16-tu-luong-tu"), 8002, env.get("VISION_GPU_FRACTION", "0.44"), env.get("VISION_MAX_MODEL_LEN", "8192"),
               ("--limit-mm-per-prompt", '{"image":2}')),
    ]


def theo_ngan_sach(may_chu: list[MayChu], mib: int, ngan_sach: int) -> list[MayChu]:
    """GPU to hơn đích production (A100) thì thu các tỉ lệ để mỗi server chiếm đúng số MiB như trên đích: chạy được ở đây mới là bằng chứng vừa một L4. `ngan_sach` 0 = tắt."""
    if ngan_sach <= 0 or mib <= ngan_sach:
        return may_chu
    return [replace(m, phan_gpu=f"{float(m.phan_gpu) * ngan_sach / mib:.4f}") for m in may_chu]


def dinh_vram(tep: Path) -> Optional[int]:
    """Đỉnh MiB đang dùng từ tệp `nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -l 1`. Không có mẫu nào thì None (chưa đo, không phải 0)."""
    try:
        mau = [int(d) for d in tep.read_text(encoding="utf-8").split() if d.isdigit()]
    except OSError:
        return None
    return max(mau) if mau else None


def cham_vram(dinh: Optional[int], ngan_sach: int) -> tuple[str, str]:
    """Đỉnh VRAM lúc tự thử so với trần 92% của GPU đích. Vượt hay không đo được là CẢNH BÁO: không chặn demo, nhưng không được kết luận là vừa L4."""
    if dinh is None:
        return CANH_BAO, "không đo được VRAM"
    tran = int(ngan_sach * TRAN_SU_DUNG)
    ghi = f"đỉnh {dinh} MiB, trần {tran} MiB (92% của {ngan_sach} MiB)"
    return (DAT, f"{ghi}: vừa GPU đích") if dinh <= tran else (CANH_BAO, f"{ghi}: VƯỢT, chưa kết luận được là chạy vừa GPU đích")


def lenh_vllm(m: MayChu, thu_muc: Path) -> list[str]:
    # --disable-log-requests (P2): nội dung hỏi và ảnh không được rơi vào log server.
    return ["vllm", "serve", str(thu_muc), f"--served-model-name={m.ten}", f"--max-model-len={m.ngu_canh}", f"--gpu-memory-utilization={m.phan_gpu}",
            f"--port={m.cong}", "--host=127.0.0.1", "--disable-log-requests", *m.them]


def env_brain(nen: Mapping[str, str], token: str, repo: Path, may_chu: list[MayChu]) -> dict[str, str]:
    """Brain không nạp model (ENV=SERVER), gọi hai server trên 127.0.0.1 (qua được `kiem_url_noi_bo`, R2). Không DATABASE_URL: phiên demo không có lịch sử chat phía Brain."""
    bo = ("DATABASE_URL", "VLLM_N8N_BASE_URL", "REDIS_URL", "BODY_CALLBACK_URL", "VLLM_VISION_BASE_URL", "VLLM_VISION_MODEL")
    env = {k: v for k, v in nen.items() if k not in bo}
    text = may_chu[0]
    env.update({
        "ENV": "SERVER",
        "VLLM_BASE_URL": f"http://127.0.0.1:{text.cong}", "VLLM_MODEL": text.ten,
        "API_AUTH_TOKEN": token, "API_HMAC_MODE": "off",
        "KB_WORKSPACE_ID": "default",       # khớp mặc định BRAIN_KB_WORKSPACE của Body
        "PYTHONPATH": str(repo), "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1",
        "AI_METRICS_PATH": str(RA / "ai_metrics.jsonl"),
    })
    if len(may_chu) > 1:        # không có server vision thì ENV=SERVER khai `vision_backend: none` (tắt có tuyên bố)
        vision = may_chu[1]
        env.update({"VLLM_VISION_BASE_URL": f"http://127.0.0.1:{vision.cong}", "VLLM_VISION_MODEL": vision.ten})
    return env


# ---------------------------------------------------------------------------
# Chuẩn bị: máy, thư viện, trọng số
# ---------------------------------------------------------------------------
def thong_tin_gpu() -> tuple[str, int]:
    r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, check=True)
    ten, mib = r.stdout.strip().splitlines()[0].rsplit(",", 1)
    return ten.strip(), int(mib.strip())


def kiem_dau_vao(may_chu: list[MayChu]) -> list[str]:
    return [f"Không thấy {DRIVE / m.nguon}/config.json — đã mount Drive (dòng đầu của ô) và đúng tài khoản chưa?"
            for m in may_chu if not (DRIVE / m.nguon / "config.json").is_file()]


def chay_lenh(lenh: list[str], cho_phep_loi: bool = False, **kw: Any) -> None:
    r = subprocess.run(lenh, **kw)
    if r.returncode != 0 and not cho_phep_loi:
        raise RuntimeError(f"lệnh hỏng (mã {r.returncode}): {' '.join(lenh[:6])} …")


def cai_thu_vien() -> None:
    os.environ["USE_TORCH"] = "1"
    os.environ["USE_TF"] = "0"          # transformers kéo TensorFlow của Colab là vỡ (phiên đo #176)
    chay_lenh([sys.executable, "-m", "pip", "install", "-q", f"vllm=={BAN_VLLM}", "-r", str(REPO / "requirements-gpu.txt")], cwd=str(REPO))
    chay_lenh([sys.executable, "-m", "pip", "uninstall", "-y", "-q", "tensorflow", "tf-keras"], cho_phep_loi=True)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for khoi in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(khoi)
    return h.hexdigest()


def chep_thu_muc(nguon: Path, dich: Path) -> int:
    """Chép các tệp ở gốc `nguon` sang `dich` (bỏ thư mục con); tệp đã có đúng cỡ thì bỏ qua. Trả số tệp đã chép."""
    dich.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(nguon.iterdir()):
        d = dich / f.name
        if f.is_file() and not (d.is_file() and d.stat().st_size == f.stat().st_size):
            shutil.copy2(f, d)
            n += 1
    return n


def kiem_manifest(thu_muc: Path) -> list[str]:
    """Đối chiếu `MANIFEST.sha256` (định dạng sha256sum, RUNBOOK §8.6). Không có tệp đó thì không kết luận gì (danh sách rỗng)."""
    m = thu_muc / "MANIFEST.sha256"
    if not m.is_file():
        return []
    loi = []
    for dong in m.read_text(encoding="utf-8").splitlines():
        if not dong.strip():
            continue
        ma, ten = dong.split(maxsplit=1)
        f = thu_muc / ten.strip().lstrip("*")
        if not f.is_file():
            loi.append(f"thiếu {f.name}")
        elif sha256(f) != ma.lower():
            loi.append(f"sai mã băm {f.name}")
    return loi


def va_tokenizer(thu_muc: Path, goc: Path) -> None:
    """Tokenizer do transformers 5 ghi lúc lượng tử hoá không đọc được bằng 4.x: dùng bản của model gốc, bỏ `chat_template.jinja` (ô 1.4 của các notebook đo)."""
    for f in FILE_TOKENIZER:
        if (goc / f).is_file():
            shutil.copy2(goc / f, thu_muc / f)
    j = thu_muc / "chat_template.jinja"
    if j.is_file():
        j.replace(thu_muc / "chat_template.jinja.bak")


def chuan_bi_model(may_chu: list[MayChu]) -> dict[str, Path]:
    from huggingface_hub import snapshot_download

    ra: dict[str, Path] = {}
    for m in may_chu:
        dich = THU_MUC_MODEL / m.nguon
        t0 = time.time()
        n = chep_thu_muc(DRIVE / m.nguon, dich)
        print(f"  {m.ten}: chép {n} tệp từ Drive ({time.time() - t0:.0f}s) -> {dich}")
        cfg = json.loads((dich / "config.json").read_text(encoding="utf-8"))
        if not cfg.get("quantization_config"):
            raise RuntimeError(f"{m.nguon}/config.json thiếu quantization_config: nạp như bản đầy đủ sẽ hết VRAM")
        ra[m.ten] = dich
    for vision in may_chu[1:]:
        loi = kiem_manifest(ra[vision.ten])
        if loi:
            raise RuntimeError(f"trọng số vision lệch MANIFEST: {', '.join(loi)}")
    goc = Path(snapshot_download(REPO_TOKENIZER_TEXT, allow_patterns=list(FILE_TOKENIZER)))
    va_tokenizer(ra[may_chu[0].ten], goc)
    return ra


# ---------------------------------------------------------------------------
# Tiến trình
# ---------------------------------------------------------------------------
def duoi_log(p: Path, n: int = 3000) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")[-n:]
    except OSError:
        return "(không đọc được log)"


def don_cu() -> None:
    """Tắt server của lần chạy trước. vLLM sinh tiến trình engine riêng, nên giết cả PID mà nvidia-smi còn thấy giữ VRAM (bat_lai_brain.py, phiên 23/08)."""
    for mau in ("uvicorn src.api.main:app", "vllm serve", "cloudflared tunnel", "nvidia-smi --query-gpu=memory.used"):
        subprocess.run(["pkill", "-f", mau])
    for _ in range(30):
        r = subprocess.run(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"], capture_output=True, text=True)
        pids = [int(x) for x in r.stdout.split() if x.isdigit() and int(x) != os.getpid()]
        if not pids:
            return
        for pid in pids:
            try:
                os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(2)
    raise RuntimeError("GPU vẫn bị giữ: Runtime > Restart runtime rồi chạy lại ô.")


def bat(ten: str, lenh: list[str], env: Optional[Mapping[str, str]] = None) -> subprocess.Popen:
    log = open(RA / f"{ten}.log", "w", encoding="utf-8")  # noqa: SIM115 — sống cùng tiến trình
    return subprocess.Popen(lenh, stdout=log, stderr=subprocess.STDOUT, cwd=str(REPO), env=dict(env) if env else None, start_new_session=True)


def cho_health(ten: str, cong: int, proc: subprocess.Popen, giay: int) -> float:
    t0 = time.time()
    while time.time() - t0 < giay:
        if proc.poll() is not None:
            raise RuntimeError(f"{ten} chết lúc khởi động (mã {proc.returncode}):\n{duoi_log(RA / f'{ten}.log')}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{cong}/health", timeout=5) as r:  # noqa: S310
                if r.status == 200:
                    return time.time() - t0
        except OSError:
            pass
        time.sleep(5)
    raise RuntimeError(f"{ten} chưa sẵn sàng sau {giay}s:\n{duoi_log(RA / f'{ten}.log')}")


def tat(procs: Mapping[str, subprocess.Popen]) -> None:
    for p in reversed(list(procs.values())):
        if p.poll() is None:
            killpg = getattr(os, "killpg", None)      # chỉ có trên Linux; máy dev Windows chạy test thì dùng terminate()
            try:
                if killpg is None:
                    p.terminate()
                else:
                    killpg(p.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                p.terminate()


# ---------------------------------------------------------------------------
# Tự thử phần CẦN MÔ HÌNH (đáp án có sẵn; dữ liệu hư cấu)
# ---------------------------------------------------------------------------
def cham_tra_loi(task: Any, phai_co: tuple[str, ...]) -> tuple[str, str]:
    if not isinstance(task, dict) or task.get("status") != "completed":
        return TRUOT, f"task không xong: {str(task)[:160]}"
    tho = task.get("result")
    res: dict[str, Any] = tho if isinstance(tho, dict) else {}
    tl = str(res.get("answer") or "")
    if "mock_response" in tl:
        return TRUOT, "câu trả lời mock: Brain không gọi được model"
    if not any(c in tl for c in phai_co):
        return TRUOT, f"không thấy {phai_co[0]!r} trong câu trả lời: {tl[:200]!r}"
    return DAT, tl[:200].replace("\n", " ")


def cham_doc_hoa_don(ma: int, r: Any, tong_in: int, phai_duyet: bool) -> tuple[str, str]:
    """Mô hình phải đọc đúng số IN trên tờ; mã quyết định có cần người xem lại (R1)."""
    if ma != 200 or not isinstance(r, dict) or not r.get("success"):
        return TRUOT, f"http={ma} {str(r)[:200]}"
    inv = r.get("invoice") or {}
    tong = inv.get("total")
    co = bool(r.get("needs_manual_review"))
    ghi = f"tổng đọc được {tong}, in trên tờ {tong_in}; cần người xem={co} (mong {phai_duyet})"
    if tong is None or abs(float(tong) - tong_in) >= 0.5 or co is not phai_duyet:
        issues = (r.get("validation") or {}).get("issues")
        return TRUOT, f"{ghi}; vấn đề: {str(issues)[:200]}"
    return DAT, ghi


def cham_tim_tai_lieu(ma: int, r: Any, phai_co: str) -> tuple[str, str]:
    doan = (r or {}).get("passages") if isinstance(r, dict) else None
    if ma != 200 or not doan:
        return TRUOT, f"http={ma}, không có đoạn nào: {str(r)[:160]}"
    if not any(phai_co in str(p.get("text", "")) for p in doan):
        return TRUOT, f"{len(doan)} đoạn, không đoạn nào chứa {phai_co!r}"
    return DAT, f"{len(doan)} đoạn, đoạn đầu từ {doan[0].get('source')}"


def tu_thu_model(b: Brain, thu_muc: Path, han: float = 900.0, co_anh: bool = True) -> list[dict[str, Any]]:
    ra: list[dict[str, Any]] = []

    def buoc(ten: str, f: Any) -> None:
        t0 = time.perf_counter()
        try:
            tt, ct = f()
        except Exception as e:  # noqa: BLE001 — một bước hỏng không được làm mất kết quả các bước khác
            tt, ct = TRUOT, f"ngoại lệ {type(e).__name__}: {str(e)[:160]}"
        ra.append({"ten": ten, "trang_thai": tt, "bat_buoc": True, "chi_tiet": ct, "giay": round(time.perf_counter() - t0, 2)})

    buoc("chat_tinh_vat", lambda: cham_tra_loi(chat_cho_xong(b, han, CAU_HOI_VAT)[0], DAP_AN_VAT))
    if co_anh:
        dung = ghi_anh_hoa_don(thu_muc / "hoa_don_cuoc_mau.png")
        sai = ghi_anh_hoa_don(thu_muc / "hoa_don_cuoc_mau_sai_tong.png", LECH_HOA_DON)
        tong = int(HOA_DON_CUOC["total"])
        for ten, anh, so, duyet in (("doc_hoa_don_dung", dung, tong, False), ("doc_hoa_don_sai_tong", sai, tong + LECH_HOA_DON, True)):
            buoc(ten, lambda a=anh, s=so, d=duyet: cham_doc_hoa_don(*b.goi("POST", "/ocr/freight", multipart=(a.name, a.read_bytes()), han=han), s, d))
    else:
        ra.append({"ten": "doc_hoa_don", "trang_thai": BO_QUA, "bat_buoc": False, "chi_tiet": "GPU nhỏ: không có mô hình đọc ảnh, đừng demo đọc hoá đơn", "giay": 0.0})
    ws = {"workspace_id": "default"}

    def nap() -> tuple[str, str]:
        ma, r = b.goi("POST", "/knowledge/documents", multipart=(TEN_QUY_CHE, QUY_CHE.encode("utf-8")), truong=ws, han=han)
        if ma != 200 or not isinstance(r, dict) or not r.get("chunks"):
            return TRUOT, f"http={ma} {str(r)[:200]}"
        return DAT, f"{r['chunks']} đoạn (lần đầu gồm tải model nhúng)"

    buoc("kho_tri_thuc_nap", nap)
    buoc("kho_tri_thuc_tim", lambda: cham_tim_tai_lieu(
        *b.goi("POST", "/knowledge/search", {**ws, "query": CAU_HOI_QUY_CHE, "top_k": 3}, han=han), f"{DAP_AN_QUY_CHE} ngày"))
    buoc("chat_hoi_quy_che", lambda: cham_tra_loi(chat_cho_xong(b, han, CAU_HOI_QUY_CHE)[0], (DAP_AN_QUY_CHE,)))

    def xoa() -> tuple[str, str]:
        ma, r = b.goi("DELETE", "/knowledge/documents?" + urllib.parse.urlencode({**ws, "source": TEN_QUY_CHE}), han=han)
        return (DAT, "đã xoá, kho trống để nạp trực tiếp khi demo") if ma == 200 else (TRUOT, f"http={ma} {r}")

    buoc("kho_tri_thuc_xoa", xoa)
    return ra


# ---------------------------------------------------------------------------
# Đường hầm, báo cáo
# ---------------------------------------------------------------------------
def _bi_mat_colab(ten: str) -> str:
    try:
        from google.colab import userdata  # type: ignore[import-not-found]

        return (userdata.get(ten) or "").strip()
    except Exception:  # noqa: BLE001 — chưa tạo secret hoặc chưa cấp quyền: coi như không có
        return ""


def _ham_cloudflared(cong: int, procs: dict[str, subprocess.Popen]) -> str:
    dich = Path("/content/bin/cloudflared")
    if not (dich.is_file() and sha256(dich) == CLOUDFLARED_SHA256):
        dich.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(CLOUDFLARED_URL, dich)  # noqa: S310 — địa chỉ ghim, kiểm SHA-256 ngay dưới
        if sha256(dich) != CLOUDFLARED_SHA256:
            dich.unlink()
            raise RuntimeError("cloudflared tải về sai SHA-256")
        dich.chmod(0o755)
    procs["cloudflared"] = bat("cloudflared", [str(dich), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{cong}"])
    for _ in range(60):
        m = re.search(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com", duoi_log(RA / "cloudflared.log", 20_000))
        if m:
            return m.group(0)
        time.sleep(1)
    raise RuntimeError(f"cloudflared không cho địa chỉ:\n{duoi_log(RA / 'cloudflared.log')}")


def mo_ham(cong: int, procs: dict[str, subprocess.Popen]) -> str:
    tok = _bi_mat_colab("NGROK_AUTHTOKEN")
    if tok:
        try:
            from pyngrok import conf, ngrok  # type: ignore[import-not-found]

            ngrok.set_auth_token(tok)
            conf.get_default().region = "ap"
            ngrok.kill()
            return str(ngrok.connect(cong).public_url)
        except Exception as e:  # noqa: BLE001
            print(f"  ngrok hỏng ({type(e).__name__}), chuyển sang cloudflared")
    return _ham_cloudflared(cong, procs)


def ghi_bao_cao(thong_tin: dict[str, Any]) -> Optional[Path]:
    """Ghi kết quả + log lên Drive để xem lại. Không có token trong bất kỳ trường nào."""
    thu_muc = DRIVE / f"demo_colab_{datetime.now():%Y%m%d_%H%M}_{thong_tin.get('commit', 'x')}"
    try:
        thu_muc.mkdir(parents=True, exist_ok=True)
        (thu_muc / "ket_qua.json").write_text(json.dumps(thong_tin, ensure_ascii=False, indent=1), encoding="utf-8")
        for f in RA.glob("*.log"):
            shutil.copy2(f, thu_muc / f.name)
        return thu_muc
    except OSError as e:
        print(f"  không ghi được báo cáo lên Drive: {e}")
        return None


def khoi_ket_noi(url: str, token: str) -> str:
    return "\n".join([
        "=" * 78,
        "  TẠO TỆP  D:\\anser-demo\\brain_colab.env  VỚI ĐÚNG HAI DÒNG SAU (đừng gửi cho ai):",
        "=" * 78,
        f"BRAIN_URL={url}",
        f"BRAIN_API_TOKEN={token}",
        "=" * 78,
        "  rồi chạy ở máy nhà:",
        "  powershell -ExecutionPolicy Bypass -File D:\\anser-demo\\brain\\offline_training\\demo_mot_may\\bat_demo.ps1 -Goc D:\\anser-demo -BrainColab D:\\anser-demo\\brain_colab.env",
        "=" * 78,
    ])


def giu_phien(b: Brain, procs: Mapping[str, subprocess.Popen], nhip: int = 60) -> None:
    print(f"\nGiữ phiên sống (in trạng thái mỗi {nhip}s). Bấm nút dừng của ô khi demo xong: đóng hầm, tắt server.")
    try:
        while True:
            time.sleep(nhip)
            ma, h = b.goi("GET", "/health", han=20.0)
            chet = [t for t, p in procs.items() if p.poll() is not None]
            tt = h.get("status") if isinstance(h, dict) else h
            print(f"  [{datetime.now():%H:%M:%S}] health http={ma} status={tt}" + (f"  TIẾN TRÌNH CHẾT: {chet}" if chet else ""))
    except KeyboardInterrupt:
        print("\nDừng: đóng đường hầm và tắt server.")
    finally:
        try:
            from pyngrok import ngrok  # type: ignore[import-not-found]

            ngrok.kill()
        except Exception:  # noqa: BLE001
            pass
        tat(procs)


def main() -> None:
    t_dau = time.time()
    RA.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--format=%h"], capture_output=True, text=True).stdout.strip()
    tt: dict[str, Any] = {"commit": commit, "bat_dau": datetime.now().isoformat(timespec="seconds"), "vllm": BAN_VLLM}
    try:
        ten_gpu, mib = thong_tin_gpu()
    except (OSError, subprocess.CalledProcessError):
        ten_gpu, mib = "không có", 0
    che_do = che_do_gpu(mib)
    if che_do is None:
        print(f"KHÔNG BẮT ĐẦU ĐƯỢC: GPU {ten_gpu} {mib} MiB, cần từ {GPU_CHI_CHU_MIB}. Runtime > Change runtime type > L4, A100 hoặc T4.")
        return
    chi_chu = che_do == "chi_chu"
    ngan_sach = int(os.getenv("DEMO_NGAN_SACH_VRAM_MIB", str(NGAN_SACH_L4_MIB)))
    may_chu = theo_ngan_sach(cac_may_chu(os.environ, chi_chu), mib, ngan_sach)
    loi = kiem_dau_vao(may_chu)
    if loi:
        print("KHÔNG BẮT ĐẦU ĐƯỢC:\n  - " + "\n  - ".join(loi))
        return
    tt.update({"gpu": f"{ten_gpu} {mib} MiB", "che_do": che_do, "ngan_sach_vram_mib": ngan_sach, "phan_gpu": {m.ten: m.phan_gpu for m in may_chu}})
    if chi_chu:
        print("GPU NHỎ: chạy chế độ CHỈ CHỮ (chat, kho tri thức). KHÔNG đọc ảnh hoá đơn; cấu hình này chưa được đo chất lượng.")
    elif 0 < ngan_sach < mib:
        print(f"GPU {mib} MiB lớn hơn đích production: bó hai mô hình trong ngân sách {ngan_sach} MiB (một L4). Dùng cả GPU thì đặt DEMO_NGAN_SACH_VRAM_MIB=0.")
    procs: dict[str, subprocess.Popen] = {}
    try:
        print(f"[1/6] Cài thư viện (vLLM {BAN_VLLM}, 3-8 phút) — GPU {tt['gpu']}, commit {commit}")
        cai_thu_vien()
        print("[2/6] Chép trọng số từ Drive và kiểm")
        thu_muc = chuan_bi_model(may_chu)
        print(f"[3/6] Bật {len(may_chu)} server vLLM (mỗi cái 2-5 phút)")
        don_cu()
        procs["vram"] = bat("vram", ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-l", "1"])    # lấy mẫu suốt phiên
        for m in may_chu:
            procs[m.ten] = bat(m.ten, lenh_vllm(m, thu_muc[m.ten]))
            print(f"      {m.ten} sẵn sàng sau {cho_health(m.ten, m.cong, procs[m.ten], 1200):.0f}s")
        print("[4/6] Bật Brain")
        token = os.environ.get("API_AUTH_TOKEN") or secrets.token_hex(32)
        os.environ["API_AUTH_TOKEN"] = token
        procs["brain"] = bat("brain", [sys.executable, "-m", "uvicorn", "src.api.main:app", "--host", "127.0.0.1", "--port", str(CONG_BRAIN)],
                             env_brain(os.environ, token, REPO, may_chu))
        cho_health("brain", CONG_BRAIN, procs["brain"], 600)
        b = Brain(f"http://127.0.0.1:{CONG_BRAIN}", token, han=120.0)
        print("[5/6] Tự thử (lần đầu tải model nhúng của kho tri thức, vài phút)")
        hang = chay_kiem(b, "default", can_model=True, bo_chat=False, han_chat_s=900.0) + tu_thu_model(b, RA / "mau", co_anh=not chi_chu)
        if not chi_chu and ngan_sach > 0:
            dinh = dinh_vram(RA / "vram.log")
            tt["vram_dinh_mib"] = dinh
            tt_vram, ct_vram = cham_vram(dinh, ngan_sach)
            hang.append({"ten": "vua_gpu_dich", "trang_thai": tt_vram, "bat_buoc": False, "chi_tiet": ct_vram, "giay": 0.0})
        ma_kl, kl = ket_luan(hang)
        in_bang(hang, kl)
        tt.update({"hang": hang, "ket_luan": kl, "ma": ma_kl})
        print("[6/6] Mở đường hầm")
        url = mo_ham(CONG_BRAIN, procs)
        tt["may_ham"] = urllib.parse.urlparse(url).hostname
        for _ in range(30):
            if Brain(url, token).goi("GET", "/health", han=10.0)[0] == 200:
                break
            time.sleep(3)
        else:
            print("  CẢNH BÁO: chưa gọi được Brain qua đường hầm từ chính Colab; đợi một phút rồi thử ở máy nhà.")
        tt["phut_dung"] = round((time.time() - t_dau) / 60, 1)
        noi = ghi_bao_cao(tt)
        print(f"\n{kl} — dựng mất {tt['phut_dung']} phút. Báo cáo trên Drive: {noi}")
        print(khoi_ket_noi(url, token))
        if os.getenv("DEMO_GIU", "1") != "0":
            giu_phien(b, procs)
    except Exception as e:  # noqa: BLE001 — `%run` làm hỏng traceback khi ném SystemExit; in rõ rồi dừng
        tt["loi"] = f"{type(e).__name__}: {e}"[:4000]
        noi = ghi_bao_cao(tt)
        print(f"\nHỎNG: {tt['loi']}\nLog đã chép lên Drive: {noi}")
        tat(procs)


if __name__ == "__main__":
    main()
