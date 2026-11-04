"""
tests/test_deploy_config.py — khoá hợp đồng giữa FILE TRIỂN KHAI và CODE.

VÌ SAO CÓ FILE NÀY
------------------
Ngày 13/08/2026, chạy test nội bộ qua HTTP thật phát hiện: `deploy/docker-compose.yml`
đặt biến `API_TOKEN`, còn `dependencies.py` đọc `API_AUTH_TOKEN`. Và
`require_api_token` BỎ QUA mọi kiểm tra khi biến nó đọc rỗng.

Hậu quả nếu triển khai đúng theo README: một Brain **không kiểm token nào**, đưa
thẳng ra Internet qua Cloudflare tunnel, trong khi người vận hành vừa bị `:?` bắt
điền token nên đinh ninh đã khoá. Không log nào kêu, không test nào đỏ — vì mọi
test đều chạy TestClient trong cùng tiến trình, nơi file compose không tồn tại.

Đây là loại lỗi mà test đơn vị về bản chất không thấy được: hai tạo tác đúng
riêng lẻ, sai khi ghép. Nên phải có một test đọc CẢ HAI và đối chiếu.
"""

from __future__ import annotations

import pathlib
import re

import pytest

GOC = pathlib.Path(__file__).resolve().parent.parent
COMPOSE = GOC / "deploy" / "docker-compose.yml"
ENV_MAU = GOC / "deploy" / ".env.example"

# Biến compose đặt cho `brain` mà code CỐ Ý chưa đọc, kèm lý do. Danh sách này
# tồn tại để một biến chưa nối phải được KHAI BÁO, thay vì nằm im trông như đã
# chạy. Nối xong thì xoá khỏi đây.
CHUA_NOI: dict[str, str] = {
    "REDIS_URL": (
        "Redis đã có container nhưng TASK_REGISTRY vẫn là OrderedDict trong RAM "
        "(src/core/engine.py). Tác vụ nền vẫn mất khi restart, và vẫn sai nếu "
        "chạy nhiều worker."
    ),
    "VLLM_VISION_BASE_URL": (
        "Chưa có client HTTP cho vision — serving.py mới chỉ có đường text. "
        "Từ BR-03, ENV=SERVER nghĩa là vision TẮT CÓ TUYÊN BỐ (vision_backend "
        "= 'none', generate_vision ném BackendUnavailable), thay vì nạp CUDA "
        "trong container Brain. Nối qua HTTP thuộc chu kỳ 02."
    ),
    "VLLM_VISION_MODEL": "Cùng lý do với VLLM_VISION_BASE_URL.",
}

# Biến đọc qua f-string nên quét bằng regex không thấy:
#     os.getenv(f"{prefix}MAX_CONCURRENT")  với prefix = f"ANSER_{name.upper()}_"
DOC_QUA_FSTRING = {
    "ANSER_TEXT_MAX_CONCURRENT",
    "ANSER_TEXT_MAX_QUEUE",
    "ANSER_TEXT_WAIT_TIMEOUT_S",
    "ANSER_VISION_MAX_CONCURRENT",
    "ANSER_VISION_MAX_QUEUE",
    "ANSER_VISION_WAIT_TIMEOUT_S",
}

# Biến do thư viện/hệ điều hành đọc, không phải code mình.
NGOAI_CODE = {"ENV", "PYTHONPATH", "PYTHONUNBUFFERED", "TZ"}


def _env_cua_brain() -> list[str]:
    """Tên biến trong khối `environment:` của service `brain`."""
    text = COMPOSE.read_text(encoding="utf-8")
    m = re.search(r"^  brain:.*?^    environment:\n(.*?)(?=^\s{4}\w|\Z)", text, re.S | re.M)
    assert m, "không tìm thấy khối environment của service 'brain' trong compose"
    return re.findall(r"^\s{6}([A-Z_][A-Z0-9_]*):", m.group(1), re.M)


def _env_code_doc() -> set[str]:
    """Mọi tên biến môi trường code đọc bằng chuỗi tường minh."""
    ra: set[str] = set()
    mau = (
        re.compile(r"getenv\(\s*[\"']([A-Z_][A-Z0-9_]*)[\"']"),
        re.compile(r"environ\.get\(\s*[\"']([A-Z_][A-Z0-9_]*)[\"']"),
        re.compile(r"environ\[\s*[\"']([A-Z_][A-Z0-9_]*)[\"']\s*\]"),
    )
    for p in (GOC / "src").rglob("*.py"):
        noi_dung = p.read_text(encoding="utf-8")
        for rx in mau:
            ra |= set(rx.findall(noi_dung))
    return ra | DOC_QUA_FSTRING


# ---------------------------------------------------------------------------
# Xác thực — chỗ đã hỏng thật
# ---------------------------------------------------------------------------

def test_compose_dat_dung_ten_bien_token_ma_code_doc():
    """
    Đây là ca đã hỏng thật. Sai tên biến này không làm gì đổ — nó chỉ lặng lẽ
    TẮT xác thực trên một dịch vụ đang mở ra Internet.
    """
    from src.api import dependencies

    ten_code_doc = re.search(
        r"API_AUTH_TOKEN = os\.getenv\(\s*[\"'](\w+)[\"']",
        (GOC / "src" / "api" / "dependencies.py").read_text(encoding="utf-8"),
    )
    assert ten_code_doc, "không đọc được tên biến token trong dependencies.py"
    ten = ten_code_doc.group(1)
    assert ten in _env_cua_brain(), (
        f"compose phải đặt biến '{ten}' cho service brain — đó là tên code đọc. "
        f"Đặt tên khác là tắt xác thực mà không có dấu hiệu nào."
    )
    assert hasattr(dependencies, "API_AUTH_TOKEN")


def test_khong_kiem_token_khi_chua_dat_thi_health_phai_noi_ra():
    """
    `require_api_token` cho qua khi token rỗng — hợp lý lúc chạy máy mình. Nhưng
    trạng thái đó PHẢI nhìn thấy được từ ngoài, nếu không thì một lần đặt sai tên
    biến là mở toang mà không ai biết.
    """
    from fastapi.testclient import TestClient

    from src.api.main import app

    body = TestClient(app).get("/health").json()
    assert "auth_enabled" in body, "/health phải cho biết xác thực đang bật hay tắt"
    assert isinstance(body["auth_enabled"], bool)


def test_env_mau_co_khoa_token():
    assert "API_TOKEN=" in ENV_MAU.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Không để biến nào nằm im trông như đã chạy
# ---------------------------------------------------------------------------

def test_moi_bien_compose_dat_deu_duoc_code_doc_hoac_khai_bao_la_chua_noi():
    """
    Một biến compose đặt mà code không đọc là lời hứa suông: nó làm file triển
    khai đọc như thể tính năng đã có. Chưa nối thì phải ghi vào `CHUA_NOI` kèm
    lý do — người đọc compose có quyền biết cái gì thật, cái gì mới là dự định.
    """
    doc = _env_code_doc()
    treo = [x for x in _env_cua_brain()
            if x not in doc and x not in CHUA_NOI and x not in NGOAI_CODE]
    assert not treo, (
        f"compose đặt {treo} nhưng không chỗ nào trong src/ đọc. Nối vào code, "
        f"hoặc thêm vào CHUA_NOI kèm lý do."
    )


@pytest.mark.parametrize("ten", sorted(CHUA_NOI))
def test_bien_khai_bao_chua_noi_thi_dung_la_chua_noi(ten):
    """
    Chiều ngược lại: nối xong rồi mà quên xoá khỏi `CHUA_NOI` thì danh sách đó
    thành sai lệch, và lần sau không ai tin nó nữa.
    """
    assert ten not in _env_code_doc(), (
        f"'{ten}' nay đã được code đọc — xoá khỏi CHUA_NOI trong file test này."
    )
    assert CHUA_NOI[ten].strip(), f"'{ten}' phải kèm lý do vì sao chưa nối"


# Biến mà phép quét regex ở trên KHÔNG đủ để tin. Chúng nằm trong `getenv` của
# `serving.py` từ lâu, trong khi không caller nào gọi `VLLMServerClient`: đọc
# khác dùng (SRS chu kỳ 01 §BR-03). Mỗi biến trỏ tới phép thử chứng minh nó
# THỰC SỰ được dùng — server giả trên socket thật phải nhận được request.
NOI_CO_PHEP_THU: dict[str, str] = {
    "VLLM_BASE_URL": "tests/test_engine_backend.py::test_generate_chat_thuc_su_goi_toi_vllm_server",
    "VLLM_MODEL": "tests/test_engine_backend.py::test_generate_chat_thuc_su_goi_toi_vllm_server",
}


@pytest.mark.parametrize("ten", sorted(NOI_CO_PHEP_THU))
def test_bien_vllm_da_noi_co_phep_thu_thi_hanh(ten):
    """Phép thử được trỏ tới phải còn tồn tại và còn nhắc tới đúng biến đó."""
    duong, ten_test = NOI_CO_PHEP_THU[ten].split("::")
    noi_dung = (GOC / duong).read_text(encoding="utf-8")
    assert f"def {ten_test}(" in noi_dung, f"{NOI_CO_PHEP_THU[ten]} không còn"
    assert ten in noi_dung, f"{duong} không còn đặt {ten}"
    assert ten not in CHUA_NOI


def test_cau_hinh_compose_that_ra_dung_backend():
    """
    BR-03 yêu cầu 7. Trước đây `ENV: SERVER` rơi vào nhánh nạp model lên CUDA
    trong container Brain, vì mã chỉ rẽ ở `== "LOCAL"`. Đọc CHÍNH giá trị trong
    compose rồi cho qua `chon_backend`: text phải đi server, vision tắt có
    tuyên bố, và không có gì nạp trong tiến trình.
    """
    from src.core.engine import chon_backend

    text = COMPOSE.read_text(encoding="utf-8")

    def gia_tri(ten: str) -> str:
        m = re.search(rf"^\s{{6}}{ten}:\s*(\S+)", text, re.M)
        assert m, f"compose không đặt {ten} cho brain"
        return m.group(1)

    assert chon_backend(gia_tri("ENV"), gia_tri("VLLM_BASE_URL")) == ("server", "none")


def test_redis_chay_nhung_task_registry_van_trong_RAM():
    """
    Khoá lại một sự thật khó chịu để nó không bị quên: compose dựng Redis và
    ghi chú rằng đó là chỗ giữ trạng thái tác vụ nền, nhưng code chưa dùng.
    Restart Brain là mất sạch task đang chạy.

    Test này sẽ ĐỎ ngay khi ai đó nối Redis vào — lúc ấy sửa cả nó lẫn CHUA_NOI.
    """
    from src.core.engine import TASK_REGISTRY

    assert type(TASK_REGISTRY).__name__ == "TaskRegistry"
    assert not any(
        "redis" in p.read_text(encoding="utf-8").lower()
        for p in (GOC / "src").rglob("*.py")
    ), "đã có code dùng Redis — cập nhật CHUA_NOI và xoá test này"


# ---------------------------------------------------------------------------
# R5 — danh sách biến trong AGENTS.md phải là tên THẬT
# ---------------------------------------------------------------------------
# AGENTS.md §2 R5 liệt kê các biến "tham số phần cứng đọc từ biến môi trường".
# Soát 04/11/2026: BA trong TÁM tên đó không tồn tại trong code —
# `GPU_MEMORY_UTILIZATION`, `MAX_MODEL_LEN`, `QUANTIZATION`. Tên thật là
# `TEXT_GPU_FRACTION`, `TEXT_MAX_MODEL_LEN`, `TEXT_QUANTIZATION`.
#
# Một cái tên sai trong tài liệu cấu hình tệ hơn không ghi gì: ai đặt
# `GPU_MEMORY_UTILIZATION` trong .env sẽ thấy KHÔNG CÓ GÌ xảy ra và tin rằng
# mình đã cấu hình xong. Không ghi thì người ta đi đọc code.

AGENTS_MD = GOC / "AGENTS.md"

_MO_KHOI_R5 = "Mọi tham số phần cứng đọc từ biến môi trường"


def _bien_trong_khoi_r5() -> list[str]:
    """Tên biến trong khối mã của mục R5 trong AGENTS.md."""
    text = AGENTS_MD.read_text(encoding="utf-8")
    i = text.find(_MO_KHOI_R5)
    assert i != -1, "không tìm thấy mục R5 trong AGENTS.md"
    dau = text.find("```python", i)
    assert dau != -1, "mục R5 không còn khối ```python"
    cuoi = text.find("```", dau + len("```python"))
    khoi = text[dau + len("```python"):cuoi]
    return re.findall(r"^([A-Z_][A-Z0-9_]*)", khoi, re.M)


def test_moi_bien_r5_trong_agents_la_ten_that():
    """Mỗi tên trong khối R5 phải thực sự được `src/` đọc.

    Đây là phép kiểm mà nếu có từ trước thì ba cái tên sai kia không sống nổi
    tới 04/11/2026.
    """
    doc = _env_code_doc()
    treo = [x for x in _bien_trong_khoi_r5() if x not in doc]
    assert not treo, (
        f"AGENTS.md §R5 hứa {treo} nhưng không chỗ nào trong src/ đọc. "
        f"Sửa tên trong AGENTS.md cho khớp code, hoặc nối vào code."
    )


def test_khoi_r5_khong_rong():
    """Chốt chặn cho chính phép kiểm trên: nó lặp trên một danh sách.

    Khối R5 rỗng (hoặc regex không khớp nữa) làm `test_moi_bien_r5...` xanh
    suông. Đã gặp đúng lớp lỗi này ngày 04/11 ở một test khác — xem
    `tests/test_agent_middleware.py::test_node_bi_chan_khong_nam_trong_danh_muc`.
    """
    bien = _bien_trong_khoi_r5()
    assert len(bien) >= 6, bien
    assert "TEXT_GPU_FRACTION" in bien
    assert "TEXT_MODEL_ID" in bien


def test_phan_vram_doc_tu_env_khong_hardcode(monkeypatch):
    """`gpu_memory_utilization` đến từ env, mặc định 0.55, và ĐỔI được.

    Tiêu chí nghiệm thu của R5: "chuyển từ GPU thuê sang máy tự sở hữu chỉ đổi
    .env, không sửa dòng code nào". Trước 04/11/2026 dòng này là hằng số 0.55 —
    con số đo trên L4 22,5GB — nên chuyển sang 3090 24GB thì phải sửa code.

    Kiểm cả hai chiều: thiếu biến thì giữ nguyên 0.55 (không đổi hành vi), và
    đặt biến thì giá trị phải đi theo (đọc rồi bỏ cũng là một cách hỏng).
    """
    import importlib

    from src.core import config as mod_config

    monkeypatch.delenv("TEXT_GPU_FRACTION", raising=False)
    importlib.reload(mod_config)
    assert mod_config.Config().vllm_config["gpu_memory_utilization"] == 0.55

    monkeypatch.setenv("TEXT_GPU_FRACTION", "0.80")
    importlib.reload(mod_config)
    assert mod_config.Config().vllm_config["gpu_memory_utilization"] == 0.80


def test_ten_phan_vram_giong_compose():
    """Cùng một tham số thì cùng một tên ở cả hai đường chạy (R4).

    Compose truyền `--gpu-memory-utilization=${TEXT_GPU_FRACTION:-0.62}` cho
    container vLLM. Nếu đường trong-tiến-trình đọc một tên KHÁC thì đặt biến
    một chỗ chỉ sửa được một nửa hệ thống, mà nửa còn lại không báo gì.
    """
    assert "TEXT_GPU_FRACTION" in COMPOSE.read_text(encoding="utf-8")
    assert "TEXT_GPU_FRACTION" in _env_code_doc()


# ---------------------------------------------------------------------------
# .env.example — mỗi khoá phải thực sự tới được một chỗ nào đó
# ---------------------------------------------------------------------------
# `.env.example` là thứ người triển khai COPY rồi điền. Một khoá nằm trong đó mà
# không đi tới đâu là lời hứa suông ở mức tệ nhất: người ta đặt giá trị, khởi
# động lại, và không có gì đổi — không lỗi, không cảnh báo.
#
# Soát 04/11/2026 tìm thấy đúng một ca như vậy, và nó đứt ở HAI chỗ cùng lúc:
# `P95_NGUONG_MS` / `P95_MS_MOI_TOKEN` được `src/core/nguong_p95.py` đọc và
# `Config.__init__` gán vào `self.p95_*`, nhưng (1) compose không truyền hai biến
# đó vào container `brain`, và (2) không nơi nào đọc `self.p95_*`. Chuỗi có bốn
# khâu và hỏng ở khâu 3 lẫn khâu 4.
#
# Phép kiểm cũ ở trên không thấy được: nó soi KHOÁ trong khối `environment:` của
# service `brain` — tức tên biến mà tiến trình Brain nhận. Đúng cho mục đích của
# nó, nhưng `.env.example` là một không gian tên KHÁC (những gì người ta gõ vào
# `.env`), và không có phép kiểm nào cho không gian tên đó.

# Khoá `.env.example` mà compose CỐ Ý không truyền, kèm nơi nó thật sự có tác
# dụng. Danh sách này là lời khai, không phải ngoại lệ miễn phí: mỗi dòng phải
# nói ai đọc biến đó.
ENV_MAU_NGOAI_COMPOSE: dict[str, str] = {
    "P95_MS_MOI_TOKEN": (
        "Chỉ offline_training/do_ngan_sach_ctx.py dùng, đọc từ env của phiên "
        "Colab. Service đang chạy không so p95 với ngưỡng nào."
    ),
    "P95_NGUONG_MS": "Cùng lý do với P95_MS_MOI_TOKEN.",
}


def _khoa_env_mau() -> list[str]:
    """Tên khoá trong deploy/.env.example."""
    return re.findall(r"^([A-Z_][A-Z0-9_]*)=", ENV_MAU.read_text(encoding="utf-8"), re.M)


def _khoa_compose_thay_the() -> set[str]:
    """Khoá .env mà compose thay thế vào, tức `${TEN}` ở bất kỳ service nào."""
    return set(re.findall(r"\$\{([A-Z_][A-Z0-9_]*)", COMPOSE.read_text(encoding="utf-8")))


def test_moi_khoa_env_mau_den_duoc_mot_cho():
    """Khoá trong `.env.example` phải được compose truyền đi, hoặc được khai báo.

    Chú ý: đây là `${TEN}` ở MỌI service, không riêng `brain` — `TEXT_GPU_FRACTION`
    đi vào `command:` của container vLLM, và đó là một đích đến hợp lệ.
    """
    treo = [k for k in _khoa_env_mau()
            if k not in _khoa_compose_thay_the() and k not in ENV_MAU_NGOAI_COMPOSE]
    assert not treo, (
        f".env.example dạy người ta đặt {treo} nhưng compose không truyền đi đâu. "
        f"Nối vào compose, hoặc thêm vào ENV_MAU_NGOAI_COMPOSE kèm nơi nó có tác dụng."
    )


def test_moi_khoa_compose_can_deu_co_trong_env_mau():
    """Chiều ngược lại: compose đòi một khoá mà `.env.example` không khai.

    Với khoá dùng `${TEN:?...}` thì thiếu nó làm `docker compose up` chết ngay —
    đỡ hơn im lặng, nhưng người triển khai chỉ biết sau khi đã thử dựng.
    """
    thieu = [k for k in sorted(_khoa_compose_thay_the()) if k not in _khoa_env_mau()]
    assert not thieu, f"compose cần {thieu} nhưng .env.example không khai"


@pytest.mark.parametrize("ten", sorted(ENV_MAU_NGOAI_COMPOSE))
def test_khoa_khai_ngoai_compose_dung_la_ngoai_compose(ten):
    """Nối vào compose rồi mà quên xoá khỏi danh sách thì danh sách thành sai."""
    assert ten not in _khoa_compose_thay_the(), (
        f"'{ten}' nay đã được compose truyền — xoá khỏi ENV_MAU_NGOAI_COMPOSE."
    )
    assert ENV_MAU_NGOAI_COMPOSE[ten].strip(), f"'{ten}' phải kèm nơi nó có tác dụng"


def test_khong_con_thuoc_tinh_nguong_p95_chet_trong_config():
    """`Config` không được gán ngưỡng p95 mà không ai đọc.

    Trước 04/11/2026 `Config.__init__` gán `self.p95_nguong_ms` và
    `self.p95_ms_moi_token`, và không nơi nào trong repo đọc chúng. Để lại thì
    `Config` trông như đã áp ngưỡng NFR-03 trong khi service không kiểm gì.

    Test này đỏ theo CẢ HAI chiều, và chiều thứ hai mới là chiều đáng giá: nối
    ngưỡng vào /health thật thì nó cũng đỏ, buộc người làm quay lại xoá nó đi
    thay vì để một phép kiểm lỗi thời chặn việc đúng.
    """
    import inspect

    from src.core import config as mod_config

    nguon = inspect.getsource(mod_config)
    gan = [d for d in nguon.splitlines()
           if "self.p95_" in d and not d.lstrip().startswith("#")]
    assert not gan, (
        f"Config gán {gan}. Nếu p95 nay ĐƯỢC dùng thật thì xoá test này và ghi "
        f"rõ chỗ đọc; nếu chưa, đừng gán."
    )


# ---------------------------------------------------------------------------
# Biến ĐỔI HÀNH VI phải có mặt trong .env.example
# ---------------------------------------------------------------------------
# Chiều ngược của phép kiểm ở trên. Hai chiều, hai lớp lỗi khác nhau:
#
#   .env.example dạy đặt một biến không đi tới đâu  -> người ta đặt, không gì đổi
#   code đọc một biến triển khai không bao giờ đặt  -> tính năng chết, không ai biết
#
# Đo 04/11/2026: `src/` đọc 31 biến môi trường, 22 trong số đó không xuất hiện ở
# compose lẫn .env.example. Nhưng KHÔNG phải cả 22 đều đáng khai: phần lớn là núm
# tinh chỉnh có mặc định an toàn (`LOG_LEVEL`, `MAX_HISTORY_TURNS`, `KB_DEVICE`,
# `TEXT_REPETITION_PENALTY`). Đòi khai hết 22 là việc bận tay, không phải phép
# kiểm.
#
# Quy tắc hẹp hơn, và là quy tắc thật sự bắt lỗi: biến mà THIẾU NÓ ĐỔI HÀNH VI
# theo cách người vận hành không đoán được thì phải có trong .env.example.
#
# Không có cách máy móc nào phân biệt "núm tinh chỉnh" với "công tắc tính năng",
# nên đây là danh sách KHAI BÁO. Nó trung thực chừng nào mỗi dòng nói rõ thiếu nó
# thì hỏng cái gì.
DOI_HANH_VI: dict[str, str] = {
    "N8N_QUOTE_WEBHOOK_URL": (
        "Thiếu thì nhánh LOGISTICS trả lời 'Hệ thống báo giá chưa được nối với "
        "n8n' — nghiệp vụ ƯU TIÊN 1 (AGENTS §8) chết."
    ),
    "KB_WORKSPACE_ID": (
        "Phải khớp BRAIN_KB_WORKSPACE bên Body. Lệch thì Brain tra một kho, Body "
        "nạp vào kho khác, và không có lỗi nào — chỉ 'không tìm thấy tài liệu'."
    ),
    "N8N_TEMPLATES_DIR": (
        "Thiếu thì dùng catalog dự phòng; typeVersion có thể không khớp n8n của "
        "Body, và lỗi đó chỉ lộ ra lúc import workflow."
    ),
    "BODY_CALLBACK_URL": (
        "Đặt URL là BẬT một lời gọi ra ngoài mang theo câu trả lời của AI. Rỗng "
        "là tắt. Phải tài liệu hoá vì hậu quả của việc điền nó không hiển nhiên."
    ),
}


@pytest.mark.parametrize("ten", sorted(DOI_HANH_VI))
def test_bien_doi_hanh_vi_co_trong_env_mau(ten):
    """Biến đổi hành vi phải có trong `.env.example`, và phải tới được container.

    Chỉ một trong hai là chưa đủ: có trong `.env.example` mà compose không truyền
    thì người ta đặt rồi không gì đổi (đúng lớp lỗi sửa ở 07131e6); compose
    truyền mà `.env.example` không ghi thì không ai biết tên biến mà đặt.
    """
    assert ten in _khoa_env_mau(), (
        f"'{ten}' đổi hành vi thật nhưng .env.example không ghi: "
        f"{DOI_HANH_VI[ten]}"
    )
    assert ten in _khoa_compose_thay_the(), (
        f"'{ten}' có trong .env.example nhưng compose không truyền đi đâu"
    )


@pytest.mark.parametrize("ten", sorted(DOI_HANH_VI))
def test_bien_doi_hanh_vi_duoc_code_doc(ten):
    """Và code phải thực sự đọc nó.

    Chiều này chặn việc danh sách trên thành nơi chứa tên biến đã bỏ: xoá tính
    năng mà quên xoá khỏi đây thì `.env.example` dạy người ta đặt một biến vô
    nghĩa, và phép kiểm còn lại vẫn xanh.
    """
    assert ten in _env_code_doc(), (
        f"'{ten}' nằm trong DOI_HANH_VI nhưng không chỗ nào trong src/ đọc. "
        f"Tính năng đã bỏ thì xoá khỏi đây, khỏi .env.example và khỏi compose."
    )


def test_danh_sach_doi_hanh_vi_khong_rong():
    """Chốt chống xanh suông cho hai phép kiểm tham số hoá ở trên.

    `parametrize` trên một dict rỗng sinh ra ZERO test và pytest vẫn xanh. Đã gặp
    đúng lớp lỗi này hai lần trong ngày 04/11 — xem 0c11d8f và 9efad94.
    """
    assert len(DOI_HANH_VI) >= 4
    assert all(ly_do.strip() for ly_do in DOI_HANH_VI.values())
