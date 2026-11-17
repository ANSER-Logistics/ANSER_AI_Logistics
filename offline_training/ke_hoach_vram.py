"""
offline_training/ke_hoach_vram.py — chia VRAM cho một hay nhiều server vLLM trên CÙNG MỘT GPU, trước khi chạy.

VÌ SAO CÓ FILE NÀY
------------------
Đo hai model cạnh nhau trên cùng bộ đề (v3 và v4 của #91) bằng hai server vLLM chạy đồng thời thì phép đo giống
nhau tuyệt đối ở những thứ hay làm lệch: cùng phiên, cùng bản vLLM, cùng commit, và đi qua đúng đường production
(`/v1/chat/completions` với `ChatRequest.to_payload`). Cái giá là VRAM: hai bản 8B AWQ cùng một GPU 22,5 GiB. Con số
mặc định của production (`--max-model-len=32768`, `--gpu-memory-utilization=0.62`) dành cho MỘT server; chép sang hai
server là hết bộ nhớ ngay lúc khởi động, và phát hiện ra ở phút thứ ba của một phiên Colab tính giờ.

Công cụ này tính trước, từ chính các file của model (không từ con số nhớ):
  - trọng số: tổng dung lượng file `*.safetensors` (hoặc `*.bin`) trong thư mục model;
  - KV cache cho một token: `2 x số lớp x số đầu KV x head_dim x 2 byte`, đọc từ `config.json`;
  - dung lượng GPU: hỏi `nvidia-smi`, hoặc nhận `--gpu-gib` (R5: không ghim tên GPU hay số VRAM).

Rồi tìm độ dài ngữ cảnh `--max-model-len` lớn nhất vẫn vừa, in từng lệnh `vllm serve` đúng cờ production
(`deploy/docker-compose.yml`), hoặc TỪ CHỐI và bảo chạy lần lượt.

ĐÂY LÀ ƯỚC TÍNH, KHÔNG PHẢI PHÉP ĐO
-----------------------------------
`--overhead-gib` (kích hoạt, đồ thị CUDA, ngữ cảnh CUDA) là con số đoán, mặc định 2,5 GiB, chưa đo trên đúng GPU
này. Đặt thấp quá thì server khởi động sẽ báo lỗi rõ của vLLM ("không đủ bộ nhớ cho KV cache"), không phải OOM giữa
chừng: vLLM cấp phát KV cache một lần ngay lúc khởi động. Gặp lỗi đó thì tăng `--overhead-gib` hoặc hạ `--ctx-toi-da`.

HẠ NGỮ CẢNH CÓ LÀM ĐỔI PHÉP ĐO KHÔNG
-------------------------------------
Không đổi đầu ra, miễn là mọi prompt cộng phần sinh vẫn nhỏ hơn `--max-model-len`. Prompt dài hơn thì vLLM trả 400,
`benchmark_v3` nổ rõ ràng (không lặng lẽ cắt). `--ctx-can-thiet` là sàn: không hạ xuống dưới nó.

CHẠY (không cần GPU để tính, chỉ cần thư mục model)
---------------------------------------------------
    python offline_training/ke_hoach_vram.py --model .../anser-v3-awq --model .../anser-v4-awq
    python offline_training/ke_hoach_vram.py --model ... --model ... --gpu-gib 22.5     # không có nvidia-smi
"""

from __future__ import annotations

import argparse
import json
import math
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

GIB = 1024 ** 3

# Phần GPU tối đa cho tổng các server. Phần còn lại là chỗ cho ngữ cảnh CUDA ngoài sổ sách của từng server và cho
# phân mảnh. Con số này cũng là đoán; chỗ hở nằm về phía an toàn.
TRAN_TONG_MAC_DINH = 0.92
BUOC_NGU_CANH = 2048
SAN_NGU_CANH_MAC_DINH = 12288
TRAN_NGU_CANH_MAC_DINH = 32768          # = TEXT_MAX_MODEL_LEN của production


class KeHoachLoi(Exception):
    """Đầu vào hỏng hay không xếp vừa. Thông báo nói thẳng cần làm gì."""


@dataclass(frozen=True)
class DacTaMoHinh:
    thu_muc: Path
    trong_so_gib: float
    kv_byte_moi_token: int


@dataclass(frozen=True)
class MotServer:
    thu_muc: Path
    cong: int
    ten: str
    phan_gpu: float
    nhu_cau_gib: float


@dataclass(frozen=True)
class KeHoach:
    gpu_gib: float
    max_model_len: int
    servers: tuple[MotServer, ...]
    tong_phan: float
    du_gib: float


# ---------------------------------------------------------------------------
# Đọc đặc tả từ file của model — hàm thuần trên thư mục, test được bằng thư mục giả
# ---------------------------------------------------------------------------

def doc_dac_ta(thu_muc: Path) -> DacTaMoHinh:
    cfg_path = thu_muc / "config.json"
    if not cfg_path.is_file():
        raise KeHoachLoi(f"{thu_muc} không có config.json — đây có phải thư mục model không?")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    # Một số model đa phương thức đặt cấu hình ngôn ngữ trong `text_config`.
    cfg = cfg.get("text_config", cfg)

    try:
        lop = int(cfg["num_hidden_layers"])
        dau_attn = int(cfg["num_attention_heads"])
        dau_kv = int(cfg.get("num_key_value_heads", dau_attn))
        head_dim = int(cfg.get("head_dim") or int(cfg["hidden_size"]) // dau_attn)
    except KeyError as exc:
        raise KeHoachLoi(f"{cfg_path} thiếu khoá {exc} — không tính được KV cache") from exc

    # KV cache giữ dtype của model (fp16/bf16 = 2 byte). KHÔNG tính fp8: chạy fp8 là đổi phép đo.
    kv_byte = 2 * lop * dau_kv * head_dim * 2

    file_trong_so = [p for p in thu_muc.iterdir() if p.suffix in (".safetensors", ".bin") and p.is_file()]
    if not file_trong_so:
        raise KeHoachLoi(f"{thu_muc} không có file *.safetensors hay *.bin — chưa tải xong model?")
    trong_so = sum(p.stat().st_size for p in file_trong_so) / GIB
    return DacTaMoHinh(thu_muc, trong_so, kv_byte)


def kv_can_gib(dac_ta: DacTaMoHinh, ngu_canh: int) -> float:
    """vLLM đòi KV đủ cho ÍT NHẤT một chuỗi dài đúng `max_model_len`; dưới mức đó nó không khởi động."""
    return dac_ta.kv_byte_moi_token * ngu_canh / GIB


def nhu_cau_gib(dac_ta: DacTaMoHinh, ngu_canh: int, overhead_gib: float) -> float:
    return dac_ta.trong_so_gib + overhead_gib + kv_can_gib(dac_ta, ngu_canh)


# ---------------------------------------------------------------------------
# Xếp chỗ
# ---------------------------------------------------------------------------

def lap_ke_hoach(
    dac_ta: list[DacTaMoHinh],
    gpu_gib: float,
    *,
    ctx_toi_da: int = TRAN_NGU_CANH_MAC_DINH,
    ctx_can_thiet: int = SAN_NGU_CANH_MAC_DINH,
    overhead_gib: float = 2.5,
    tran_tong: float = TRAN_TONG_MAC_DINH,
    cong_dau: int = 8001,
    ten: list[str] | None = None,
) -> KeHoach:
    """
    Tìm `max_model_len` lớn nhất (bước 2048, trong [ctx_can_thiet, ctx_toi_da]) mà TỔNG nhu cầu các server
    không vượt `tran_tong` x GPU. Không vừa ở ngay `ctx_can_thiet` thì ném `KeHoachLoi`: không có kế hoạch nào
    tốt hơn "chạy lần lượt".
    """
    if not dac_ta:
        raise KeHoachLoi("cần ít nhất một --model")
    if gpu_gib <= 0:
        raise KeHoachLoi(f"dung lượng GPU phải dương, nhận {gpu_gib}")
    if ctx_can_thiet > ctx_toi_da:
        raise KeHoachLoi(f"--ctx-can-thiet ({ctx_can_thiet}) lớn hơn --ctx-toi-da ({ctx_toi_da})")
    if ten is not None and len(ten) != len(dac_ta):
        raise KeHoachLoi("số --ten phải bằng số --model")

    def phan_toi_thieu(d: DacTaMoHinh, nc_len: int) -> float:
        # Làm tròn LÊN hai chữ số: `--gpu-memory-utilization` nhận hai chữ số, và làm tròn xuống sẽ cho server ít bộ
        # nhớ hơn mức nó cần. Trừ 1e-9 để 0,45 không thành 0,46 vì sai số dấu phẩy động.
        return math.ceil(nhu_cau_gib(d, nc_len, overhead_gib) / gpu_gib * 100 - 1e-9) / 100

    ngu_canh = ctx_toi_da
    chon = None
    while ngu_canh >= ctx_can_thiet:
        co_so = [phan_toi_thieu(d, ngu_canh) for d in dac_ta]
        if sum(co_so) <= tran_tong + 1e-9:
            chon = (ngu_canh, co_so)
            break
        ngu_canh -= BUOC_NGU_CANH
    if chon is None:
        ngu_canh = ctx_can_thiet
        tong = sum(nhu_cau_gib(d, ngu_canh, overhead_gib) for d in dac_ta)
        raise KeHoachLoi(
            f"{len(dac_ta)} server không vừa trong GPU {gpu_gib:.1f} GiB ngay cả ở ngữ cảnh tối thiểu "
            f"{ngu_canh}: cần khoảng {tong:.1f} GiB, ngân sách {tran_tong * gpu_gib:.1f} GiB "
            f"({tran_tong:.0%} GPU). Chạy LẦN LƯỢT từng model trong cùng phiên Colab (cùng bản vLLM, cùng commit) "
            f"thì vẫn đạt điều kiện đo giống nhau; hoặc hạ --ctx-can-thiet nếu chắc mọi prompt ngắn hơn."
        )

    ngu_canh, co_so = chon
    # Phần dư chia đều làm KV cache thêm (nhiều chuỗi chạy song song hơn), cũng làm tròn XUỐNG để không vượt trần.
    them = math.floor((tran_tong - sum(co_so)) / len(dac_ta) * 100 + 1e-9) / 100
    servers = []
    for i, (d, base) in enumerate(zip(dac_ta, co_so)):
        servers.append(MotServer(
            thu_muc=d.thu_muc,
            cong=cong_dau + i,
            ten=(ten[i] if ten else f"model-{i + 1}"),
            phan_gpu=round(base + them, 2),
            nhu_cau_gib=nhu_cau_gib(d, ngu_canh, overhead_gib),
        ))
    tong_phan = sum(s.phan_gpu for s in servers)
    return KeHoach(gpu_gib, ngu_canh, tuple(servers), tong_phan, (tran_tong - tong_phan) * gpu_gib)


def lenh_serve(s: MotServer, ngu_canh: int) -> str:
    """Đúng cờ production (`deploy/docker-compose.yml`, service `vllm-text`); chỉ đổi cổng và hai con số VRAM."""
    return " ".join([
        "vllm", "serve", shlex.quote(str(s.thu_muc)),
        f"--served-model-name={s.ten}",
        f"--max-model-len={ngu_canh}",
        f"--gpu-memory-utilization={s.phan_gpu:.2f}",
        f"--port={s.cong}",
        "--disable-log-requests",
    ])


def dung_luong_gpu_gib() -> float:
    """Hỏi nvidia-smi, KHÔNG ghim con số. Không có thì ném lỗi, nói cách đưa tay."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20, check=True,
        ).stdout.strip().splitlines()
    except (OSError, subprocess.SubprocessError) as exc:
        raise KeHoachLoi(
            "không chạy được nvidia-smi để biết dung lượng GPU. Truyền --gpu-gib <số GiB> bằng tay "
            "(Colab: !nvidia-smi rồi đổi MiB sang GiB, chia 1024)."
        ) from exc
    if len(out) != 1:
        raise KeHoachLoi(
            f"nvidia-smi thấy {len(out)} GPU; công cụ này chia VRAM của MỘT GPU. Truyền --gpu-gib cho GPU định dùng."
        )
    return float(out[0]) / 1024


def in_ke_hoach(kh: KeHoach, dac_ta: list[DacTaMoHinh], overhead_gib: float) -> str:
    dong = [
        f"GPU: {kh.gpu_gib:.1f} GiB   ngữ cảnh chọn: --max-model-len={kh.max_model_len}   "
        f"tổng phần GPU: {kh.tong_phan:.2f}   dư: {kh.du_gib:.1f} GiB",
        f"(ƯỚC TÍNH: overhead {overhead_gib:.1f} GiB mỗi server là đoán, chưa đo; vLLM sẽ báo lỗi rõ ở khởi động nếu thiếu)",
        "",
    ]
    for s, d in zip(kh.servers, dac_ta):
        dong.append(
            f"- {s.ten}: trọng số {d.trong_so_gib:.2f} GiB + KV {kv_can_gib(d, kh.max_model_len):.2f} GiB "
            f"(một chuỗi dài {kh.max_model_len}) + overhead = {s.nhu_cau_gib:.2f} GiB -> {s.phan_gpu:.2f} GPU"
        )
    dong += ["", "Khởi động LẦN LƯỢT (đợi server trước lên rồi mới bật server sau, kẻo hai bên cùng đo bộ nhớ trống):", ""]
    for s in kh.servers:
        dong.append("  " + lenh_serve(s, kh.max_model_len) + " &")
        dong.append(f"  # đợi: until curl -sf localhost:{s.cong}/health; do sleep 5; done")
    return "\n".join(dong)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", action="append", required=True, help="thư mục model; lặp lại cho mỗi server")
    p.add_argument("--ten", action="append", help="tên `--served-model-name`, theo thứ tự --model (mặc định model-1..)")
    p.add_argument("--gpu-gib", type=float, help="dung lượng GPU (GiB); mặc định hỏi nvidia-smi")
    p.add_argument("--ctx-toi-da", type=int, default=TRAN_NGU_CANH_MAC_DINH)
    p.add_argument("--ctx-can-thiet", type=int, default=SAN_NGU_CANH_MAC_DINH,
                   help="sàn ngữ cảnh: prompt dài nhất + phần sinh phải nhỏ hơn số này")
    p.add_argument("--overhead-gib", type=float, default=2.5)
    p.add_argument("--tran-tong", type=float, default=TRAN_TONG_MAC_DINH)
    p.add_argument("--cong-dau", type=int, default=8001)
    a = p.parse_args(argv)

    try:
        dac_ta = [doc_dac_ta(Path(m)) for m in a.model]
        gpu = a.gpu_gib if a.gpu_gib else dung_luong_gpu_gib()
        kh = lap_ke_hoach(
            dac_ta, gpu, ctx_toi_da=a.ctx_toi_da, ctx_can_thiet=a.ctx_can_thiet,
            overhead_gib=a.overhead_gib, tran_tong=a.tran_tong, cong_dau=a.cong_dau, ten=a.ten,
        )
    except KeHoachLoi as exc:
        print(f"KHÔNG LẬP ĐƯỢC KẾ HOẠCH: {exc}", file=sys.stderr)
        return 2
    print(in_ke_hoach(kh, dac_ta, a.overhead_gib))
    return 0


if __name__ == "__main__":
    sys.exit(main())
