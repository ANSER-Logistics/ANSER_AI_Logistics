import os

from src.core.prompts import Prompts

# Trần kích thước tệp tải lên (ảnh hoá đơn, tài liệu KB). Ở đây — tầng T1 — vì
# HAI tầng cùng cần: route nhận file (`api/routes`, T4) và client vision qua HTTP
# (`core/engine`, T3, #14) — engine không được import ngược lên `api`. Một chỗ
# khai, không hai bản mặc định (R4). `api/dependencies.py` re-export tên này.
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))

# Lịch sử hội thoại (S7, BR-38). Body gửi kèm `history` trong lời gọi `/chat` (hướng chủ dự án chốt
# 12/11, Body#28); Brain không lưu. Ở tầng T1 vì lược đồ request (`api`) và `memory` (`core`) cùng cần,
# và một con số không được tồn tại ở hai nơi (R4).
# Số tin lịch sử tối đa đưa lại vào prompt. 6 tin (3 cặp hỏi-đáp) đủ cho các câu nối tiếp thực tế
# ("thế xe 3 tấn thì sao?") mà không ăn hết ngân sách ngữ cảnh. TRƯỚC 17/11 núm này nằm ở engine.py;
# chuyển về đây vì engine, memory và route /chat cùng cần (R4: một định nghĩa). `engine.MAX_HISTORY_TURNS`
# vẫn dùng được: engine import lại tên này.
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", "6"))

# Model của kho tri thức (RAG). MỘT nơi đọc env và giữ mặc định (R4): trước 17/11 `Config` và `knowledge.py`
# mỗi nơi tự đọc `KB_EMBEDDER_ID` / `KB_RERANKER_ID` và viết cứng một bản mặc định, trong khi chỉ
# `knowledge.py` thật sự nạp model; đổi mặc định ở một nơi thì `Config` (dùng cho báo cáo đo) báo sai model.
# Là HÀM chứ không phải hằng số lúc import, để đổi env rồi nạp lại có hiệu lực và test gán env được.
# Cả hai model phải dùng thương mại được: bge-m3 (MIT), ViRanker (Apache-2.0, chuyên tiếng Việt, nền BGE-M3).
# KHÔNG dùng jina-reranker-v2: CC-BY-NC-4.0, cấm dùng thương mại (`tests/contracts/test_giay_phep_model.py` chặn).
KB_EMBEDDER_MAC_DINH = "BAAI/bge-m3"
KB_RERANKER_MAC_DINH = "namdp-ptit/ViRanker"


def kb_embedder_id() -> str:
    return os.getenv("KB_EMBEDDER_ID", KB_EMBEDDER_MAC_DINH)


def kb_reranker_id() -> str:
    return os.getenv("KB_RERANKER_ID", KB_RERANKER_MAC_DINH)


KB_RERANKER_MAX_LENGTH_TOI_THIEU = 64
KB_RERANKER_MAX_LENGTH_TOI_DA = 8192      # trần của bge-reranker/ViRanker; cao hơn là cấu hình sai


def kb_reranker_max_length() -> int:
    """
    `KB_RERANKER_MAX_LENGTH`: số token tối đa mỗi cặp (câu hỏi, đoạn) đưa vào reranker. 0 hoặc để trống = mặc định của model (8.192): hành vi như cũ.

    Đo 24/11/2026 (#214, Thành, Colab L4, CPU): đặt 384 hạ p95 của `search()` từ 12,7 xuống 7,3 giây và 20/20 câu hỏi trả về ĐÚNG tập đoạn như cũ (chỉ 3,4% cặp
    dài hơn 512 token, nhưng các cặp dài kéo p95 lên). 20 câu trên 6 văn bản luật; recall/MRR chưa đo (#34), nên mặc định vẫn là 0. Giá trị hỏng thì lỗi to,
    như `FUEL_PRICE_*`: cấu hình tối ưu sai không được chạy lặng lẽ.
    """
    tho = os.getenv("KB_RERANKER_MAX_LENGTH", "").strip()
    if not tho:
        return 0
    try:
        v = int(tho)
    except ValueError:
        raise ValueError(f"KB_RERANKER_MAX_LENGTH={tho!r} không phải số nguyên") from None
    if v == 0:
        return 0
    if not (KB_RERANKER_MAX_LENGTH_TOI_THIEU <= v <= KB_RERANKER_MAX_LENGTH_TOI_DA):
        raise ValueError(
            f"KB_RERANKER_MAX_LENGTH={v} phải là 0 (mặc định của model) hoặc từ {KB_RERANKER_MAX_LENGTH_TOI_THIEU} đến {KB_RERANKER_MAX_LENGTH_TOI_DA}")
    return v

LICH_SU_TOI_DA_TIN = 20          # Body gửi nhiều hơn thì 422, không cắt lặng lẽ
# Nhãn gắn vào mọi câu trả lời của `/chat` (kết quả của task và webhook về Body). Do mã gắn, không phải model sinh; Body hiển thị nguyên văn.
# Lý do: chủ dự án chốt 20/11/2026 không quảng bá "AI làm kế toán thay"; Luật AI 134/2025 Điều 11 yêu cầu người dùng biết đang dùng AI
# (nguồn thứ cấp, chờ luật sư, câu 9 trong bộ câu hỏi pháp lý).
AI_NOTICE = "Trợ lý AI"
# Kết quả engine gần nhất của mỗi hội thoại (`ket_qua_gan_nhat.py`), cho câu "vì sao ra con số này" ở lượt sau. Chỉ trong bộ nhớ, mất khi khởi động lại.
GIAI_THICH_TTL_GIAY = 1800       # 30 phút: hỏi "vì sao" thường ngay sau câu trả lời; lâu hơn thì số đã cũ và người dùng đã làm việc khác
GIAI_THICH_TOI_DA_MUC = 256      # số hội thoại giữ cùng lúc; đầy thì bỏ cái cũ nhất
GIAI_THICH_TOI_DA_KY_TU = 12_000  # một báo cáo bốn quý kèm mười mặt hàng cỡ 5.000 ký tự; to hơn thì không đưa vừa ngữ cảnh model, nên không lưu
LICH_SU_TOI_DA_KY_TU = 4196      # mỗi tin (cả `message` của /chat và mỗi tin của `history`); dài hơn thì 422. Chủ dự án chốt 21/11/2026; Body cắt ở 4000, nên vẫn khớp


class Config:
    """
    Cấu hình ANSER_AI (Brain) — tối ưu cho Google Colab Pro, GPU L4 22.5GB.
    Mọi con số VRAM dưới đây là ƯỚC TÍNH; phải đo lại bằng nvidia-smi /
    torch.cuda.memory_allocated() trên L4 thật rồi tinh chỉnh.
    """

    def __init__(self):
        # ----------------------------- Paths -----------------------------
        self.PROJECT_ROOT = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self.DATA_DIR = os.path.join(self.PROJECT_ROOT, "src", "data")
        self.DOCS_DIR = os.path.join(self.DATA_DIR, "docs")
        os.makedirs(self.DATA_DIR, exist_ok=True)
        os.makedirs(self.DOCS_DIR, exist_ok=True)

        # --------------------------- Database ----------------------------
        # Bản trước chỉ nhận đúng hai tiền tố viết thường, mọi thứ khác lùi IM LẶNG
        # về SQLite in-memory rỗng: `postgresql+psycopg2://…` (đúng dạng chính hàm này
        # sinh ra ở hai nhánh dưới), khoảng trắng đầu dòng khi copy-dán, `POSTGRES://`,
        # `postgresql+asyncpg://`, `sqlite:///file.db`. Đo 12/11/2026: cả sáu dạng đó
        # → `sqlite:///:memory:`. Brain chạy "khoẻ" trên một DB rỗng, lịch sử và báo
        # cáo trống, và không một dòng nào nói vì sao.
        #
        # CHỈ thiếu hẳn biến (rỗng) mới là chế độ dev CÓ CHỦ Ý. Có đặt mà không nhận
        # ra được thì đó là lỗi cấu hình: vẫn khởi động được (Config() dựng ở mỗi
        # request, ném lỗi ở đây là làm hỏng cả service), nhưng `DB_URL_LOI` được
        # đặt để /health báo — qua `memory.kiem_luoc_do`.
        import re

        raw_url = (os.getenv("DATABASE_URL", "") or "").strip()
        self.DB_URL_LOI = None
        thap = raw_url.lower()
        if thap.startswith("postgres://"):
            self.DB_URL = "postgresql+psycopg2://" + raw_url[len("postgres://"):]
        elif thap.startswith("postgresql://"):
            self.DB_URL = "postgresql+psycopg2://" + raw_url[len("postgresql://"):]
        elif thap.startswith(("postgresql+", "sqlite:")):
            # Đã là URL SQLAlchemy đầy đủ. Chỉ HẠ CHỮ THƯỜNG phần scheme: SQLAlchemy tra
            # dialect theo tên phân biệt hoa/thường, `SQLITE:///x` và `POSTGRESQL+PSYCOPG2://`
            # ném NoSuchModuleError lúc create_engine (Brain sập khi nạp DB thay vì báo
            # cấu hình sai). Phần sau dấu `:` (đường dẫn, mật khẩu) giữ nguyên.
            scheme, sep, phan_con_lai = raw_url.partition(":")
            self.DB_URL = scheme.lower() + sep + phan_con_lai
        else:
            self.DB_URL = "sqlite:///:memory:"
            if raw_url:
                # Chỉ nêu phần TRƯỚC `://`: URL có mật khẩu, và log là nơi nó nằm lại
                # (R2b). Không có `://` thì không nêu gì — có thể là `user:pass@host`.
                # CHỈ nêu scheme khi nó thật sự có hình dạng của một scheme. Bản đầu lấy
                # mọi thứ TRƯỚC `://` đầu tiên: URL `nguoi:MATKHAU@host/db?r=http://x` cho ra
                # "scheme 'nguoi:MATKHAU@host'" — mật khẩu vào log ERROR VÀ vào thân /health
                # (review độc lập 12/11/2026, tái hiện được). Một scheme hợp lệ chỉ gồm chữ,
                # số, `+`, `.`, `-` và không chứa `:`/`@`/`/`.
                truoc = raw_url.split("://", 1)[0] if "://" in raw_url else ""
                scheme = truoc if re.fullmatch(r"[A-Za-z][A-Za-z0-9+.\-]{0,19}", truoc) else "(không nhận ra)"
                self.DB_URL_LOI = (
                    f"DATABASE_URL được đặt nhưng không nhận ra dạng (scheme {scheme!r}; "
                    "chấp nhận postgres://, postgresql://, postgresql+<driver>://, sqlite:) — "
                    "Brain đang chạy trên SQLite in-memory RỖNG, lịch sử chat không lưu."
                )
                _bao_loi_db_mot_lan(self.DB_URL_LOI)

        # ------------------------ System context -------------------------
        self.SYSTEM_CONTEXT = Prompts.SYSTEM_CONTEXT

        # =================================================================
        #  NGÂN SÁCH VRAM — GPU L4 22.5GB (Colab Pro)
        #  Đệm an toàn ~19.5GB (chừa ~3GB cho CUDA context/driver/allocator).
        # -----------------------------------------------------------------
        #  Bảng ước lượng cũ (Qwen2-VL-2B, MiniLM) đã xoá 16/11/2026: các model
        #  trong đó không còn là mặc định. Số ĐO thật, text + vision cùng máy:
        #  VRAM đỉnh 21,1GB / 22,5GB ở TEXT_GPU_FRACTION=0.55 (BAO_CAO_BR04.md §6,
        #  repo tài liệu; số đo đó là của Qwen2.5-VL-3B ~7,5GB bf16, mặc định cũ).
        #  Vision mặc định nay là Qwen3-VL-2B (~4,3GB bf16, suy từ số tham số; xem dưới);
        #  embedder bge-m3 và reranker ViRanker chạy trên CPU mặc định (KB_DEVICE).
        # =================================================================

        # --- Brain: Text reasoning (chạy qua vLLM TRONG tiến trình) ---
        # Đường dẫn hoặc HF id của model AWQ, ví dụ thư mục `anser-v3-awq`.
        # Chỉ cần khi text_backend == "in_process"; đường server dùng VLLM_MODEL.
        #
        # KHÔNG có mặc định, cố ý (NFR-06, chu kỳ 01). Mặc định cũ là một đường
        # dẫn Google Drive tới `anser-retail-v2-awq`: vừa vi phạm R5, vừa là model
        # đã nghỉ hưu mà phiên đo 15/08 kết luận không dùng lại. Quên đặt biến
        # thì `ModelEngine` báo lỗi rõ ràng, không lặng lẽ nạp nhầm model.
        self.text_model_id = os.getenv("TEXT_MODEL_ID", "").strip()

        # --- Eye: Vision/VLM (load riêng qua transformers, ngoài vLLM) ---
        # GIẤY PHÉP QUYẾT ĐỊNH MẶC ĐỊNH (17/11/2026, chủ dự án chốt đổi model).
        # Mặc định cũ Qwen2.5-VL-3B-Instruct mang giấy phép `qwen-research`: chỉ
        # cho nghiên cứu và đánh giá phi thương mại, dùng thương mại phải xin
        # Alibaba Cloud (đọc văn bản giấy phép ngày 17/11). Chủ dự án không xin
        # được, nên mặc định là model Apache-2.0 cùng thế hệ với model văn bản.
        #
        # Vì sao bản 2B chứ không phải 4B: số đo VRAM duy nhất có sẵn (BR-04) là đỉnh
        # 21,1GB / 22,5GB với vision 3B ~7,5GB. Qwen3-VL-4B bf16 ~8,9GB sẽ đẩy tổng
        # tới sát trần và gần như chắc chắn tràn trên L4; 2B ~4,3GB còn dư. 4B là ứng
        # viên cần đo lại VRAM đỉnh, không phải mặc định.
        #
        # TẠM THỜI: chưa có số đo tiếng Việt của model này trên bộ hoá đơn hư cấu
        # (BR-33 / #98 / #114). Đo xong thì giữ hoặc đổi sang ứng viên Apache-2.0
        # hoặc MIT khác bằng env — không cần sửa mã.
        # `tests/contracts/test_giay_phep_model.py` chặn việc đưa một model phi thương mại
        # trở lại làm mặc định (config, .env.example, compose).
        self.vision_model_id = os.getenv("VISION_MODEL_ID", "Qwen/Qwen3-VL-2B-Instruct")

        # --- RAG: Embedding + Reranker ---
        # Đổi 03/08/2026, ba lý do — xem RAG_VLM_KE_HOACH.md §A.1.2 và §A.1.7:
        #  - MiniLM cũ giới hạn 128 token, cắt cụt IM LẶNG quá nửa mỗi đoạn.
        #  - ms-marco là model TIẾNG ANH, mà điểm của nó lại dùng làm ngưỡng lọc.
        #  - jina-reranker-v2 tốt nhưng CC-BY-NC-4.0: cấm dùng thương mại.
        # bge-m3 (MIT) + ViRanker (Apache-2.0) cùng nền BGE-M3, dùng thương mại được.
        self.embedding_model_id = kb_embedder_id()
        self.reranker_model_id = kb_reranker_id()

        # --- RAG: phạm vi kho tri thức ---
        # Hợp đồng, bảng giá cước, chính sách công nợ là của CẢ CÔNG TY, không
        # của riêng kho hàng nào. Nếu lấy `store_id` (kho đang chọn) làm khoá thì
        # tài liệu nạp lúc đứng ở kho A sẽ vô hình khi hỏi lúc đứng ở kho B —
        # và biểu hiện duy nhất là "không tìm thấy", không có lỗi nào cả.
        #
        # Nên khoá phạm vi tách hẳn khỏi `store_id`. Body dùng đúng giá trị này
        # ở đường nạp tài liệu; hai bên cùng mặc định "default" nên không cấu
        # hình gì thì vẫn khớp nhau.
        self.kb_workspace_id = os.getenv("KB_WORKSPACE_ID", "default").strip() or "default"

        # =================================================================
        #  vLLM CONFIG
        # -----------------------------------------------------------------
        #  gpu_memory_utilization = PHẦN TỔNG VRAM dành cho vLLM
        #     Đọc từ `TEXT_GPU_FRACTION`, mặc định 0.55. Con số dưới đây là
        #     phép tính CHO MẶC ĐỊNH TRÊN L4 22,5GB, không phải hằng số:
        #     0.55 × 22.5GB ≈ 12.4GB cho vLLM
        #       ├─ weights 7B-AWQ ........ ~5.5GB
        #       └─ KV-cache + activation . ~6.5GB
        #
        #  enforce_eager=True: tắt CUDA graphs — fix lỗi
        #  "Forward context is not set" của vLLM + Qwen trên Colab.
        # =================================================================
        #  quantization / dtype: ĐỂ vLLM TỰ NHẬN từ `quantization_config` trong
        #  config.json của model, thay vì khai cứng "awq" + "half".
        #
        #  Khai cứng vẫn CHẠY (float16 là dtype hợp lệ của nhân awq) nhưng ép
        #  vLLM xuống nhân chậm hơn — chính nó cảnh báo trong log:
        #
        #      Detected that the model can run with awq_marlin, however you
        #      specified quantization=awq explicitly, so forcing awq
        #
        #  Lý do đổi không phải để nhanh hơn, mà để benchmark và lúc serve chạy
        #  CÙNG MỘT nhân. benchmark_v3.py cũng đã bỏ ép (03/08/2026); nếu hai
        #  bên chọn nhân khác nhau thì con số đo được không nói gì về lúc chạy
        #  thật, mà đó lại là toàn bộ mục đích của việc đo.
        #
        #  Ép tay bằng env khi cần (GPU lạ, nhân mới lỗi): TEXT_QUANTIZATION=awq
        #  thì nhớ đặt luôn TEXT_DTYPE=half — nhân awq cũ chỉ nhận float16.
        #
        #  max_model_len 4096 -> TEXT_MAX_MODEL_LEN (mặc định 8192), 15/08/2026.
        #  Ba chỗ đang khai ba con số khác nhau cho cùng một model: engine trong
        #  tiến trình 4096, `deploy/docker-compose.yml` 8192, benchmark 8192.
        #  Nên thứ đo được trên Colab không phải thứ chạy trên máy khách.
        #
        #  Phải nâng, không chỉ để cho khớp: nhánh báo cáo vừa lên 2048 token
        #  ĐẦU RA. Trên cửa sổ 4096 thì system + ngữ cảnh + lịch sử còn đúng
        #  2048 — mà ngữ cảnh kế toán là danh sách phát hiện, dài theo số dòng
        #  sổ. Tràn ở đây không ném lỗi rõ ràng, nó cắt đầu vào; model trả lời
        #  trên nửa bảng số và không có gì cho thấy nửa kia đã mất.
        #
        #  Cùng tên biến với compose (P4): đổi một chỗ, cả hai đường đi theo.
        #
        #  8192 -> 32768, 28/10/2026 (BR-04, chủ dự án chốt). Đo trên L4 với
        #  vision đang nạp: dựng được ở cả ba mức 8192/16384/32768, bể KV cố
        #  định 36.176 token ở gpu_memory_utilization 0.55 — nâng max_model_len
        #  không làm request ngắn chạy kém song song (paged attention), p95 như
        #  nhau. Chỉ một chuỗi dài trọn 32k mới chiếm gần hết bể (1,1 chuỗi).
        #  Xem BAO_CAO_BR04.md.
        forced_quant = os.getenv("TEXT_QUANTIZATION", "").strip() or None
        self.vllm_config = {
            # R5: đọc từ env, mặc định 0.55 — KHÔNG hardcode phần cứng.
            #
            # Cùng TÊN BIẾN với `docker-compose.yml` (`TEXT_GPU_FRACTION`), vì
            # hai đường chạy cùng một tham số thì phải cùng một tên: đặt biến
            # một chỗ, cả đường server lẫn đường trong-tiến-trình đi theo.
            # Compose mặc định 0.62 (tách riêng container vision, 0.20); ở đây
            # 0.55 vì MỘT tiến trình giữ cả text lẫn vision.
            #
            # Trước 04/11/2026 dòng này là hằng số `0.55`, đo trên L4 22,5GB.
            # Nghiệm thu của R5 là "đổi sang máy tự sở hữu chỉ đổi .env, không
            # sửa dòng code nào" — mà chuyển sang 3090 24GB thì phải sửa đúng
            # dòng này. Đường server đã đọc được từ env từ trước; chỉ đường
            # trong-tiến-trình còn kẹt.
            "gpu_memory_utilization": float(
                os.getenv("TEXT_GPU_FRACTION", "0.55")
            ),
            "max_model_len":          int(os.getenv("TEXT_MAX_MODEL_LEN", "32768")),
            "dtype": os.getenv("TEXT_DTYPE", "").strip()
                     or ("half" if forced_quant == "awq" else "auto"),
            "quantization":           forced_quant,
            "enforce_eager":          True,   # fix vLLM + Qwen CUDA graph bug
        }

        # KHÔNG nạp ngưỡng p95 ở đây. Hai dòng cũ gọi `nguong_p95.doc_nguong()`
        # rồi gán vào `self.p95_nguong_ms` / `self.p95_ms_moi_token` — và soát
        # 04/11/2026 cho thấy KHÔNG NƠI NÀO đọc hai thuộc tính đó: không trong
        # `src/`, không trong `tests/`, không trong tài liệu. `metrics.py` tính
        # ra con số p95 nhưng không so với ngưỡng nào.
        #
        # Để lại thì `Config` trông như đã áp ngưỡng NFR-03, mà thực ra không.
        # Người đọc config sẽ tưởng p95 đang được kiểm — đúng loại tin sai mà
        # AGENTS §4.2 bảo xoá thay vì giữ.
        #
        # Ngưỡng vẫn sống ở `src/core/nguong_p95.py`, và có người dùng thật:
        # `offline_training/do_ngan_sach_ctx.py` gọi `danh_gia()` để kết luận
        # đạt/vượt trong phiên đo. Nối ngưỡng vào /health là việc riêng trên
        # bảng kanzo, không phải thứ xoá dòng này làm mất.


# Đặt ở cuối file, dùng lúc chạy: `Config()` gọi nó nên định nghĩa sau class vẫn được.
_DA_BAO_LOI_DB: set[str] = set()


def _bao_loi_db_mot_lan(thong_bao: str) -> None:
    """`Config()` được dựng ở MỖI request; log lỗi cấu hình một lần thôi, không spam."""
    if thong_bao in _DA_BAO_LOI_DB:
        return
    _DA_BAO_LOI_DB.add(thong_bao)
    import logging

    logging.getLogger("projecta.config").error(thong_bao)
