from src.core.context import ContextResolver
from src.core.memory import MemoryManager


class _FakeMemory:
    def __init__(self, stores):
        self._stores = stores

    def get_user_stores(self, user_id):
        return self._stores


def test_context_resolver_ready_when_single_store():
    memory = _FakeMemory(
        [{"id": 1, "name": "Store A", "industry": "Retail", "location": "HCM"}]
    )
    resolver = ContextResolver(memory)
    status, context = resolver.resolve_login(user_id=123)
    assert status == "READY"
    assert "Store A" in context


def test_context_resolver_ambiguous_when_multiple_stores():
    memory = _FakeMemory(
        [
            {"id": 1, "name": "Store A", "industry": "Retail", "location": "HCM"},
            {"id": 2, "name": "Store B", "industry": "Retail", "location": "HN"},
        ]
    )
    resolver = ContextResolver(memory)
    status, stores = resolver.resolve_login(user_id=123)
    assert status == "AMBIGUOUS"
    assert len(stores) == 2


def test_memory_manager_store_methods_safe_without_db():
    memory = MemoryManager()
    memory.engine = None
    assert memory.get_user_stores(uid=1) == []
    assert memory.get_store_details(store_id=1) is None
    assert memory.save_workflow(wid=1, name="wf", data={"a": 1}) is None


# ---------------------------------------------------------------------------
# kiem_luoc_do — biến lỗi câm thành lỗi nhìn ra ngay
#
# Mọi phương thức của MemoryManager bắt Exception rồi trả rỗng, nên thiếu bảng
# trông hệt như "chưa có dữ liệu". Người dùng đọc "chưa có cửa hàng" trong khi
# sự thật là lược đồ sai. Soát 04/11/2026: cả 6 bảng file đó chạm tới đều
# KHÔNG CÓ trong lược đồ Body, và chưa bao giờ có.
# ---------------------------------------------------------------------------


def _bo_nho_voi_bang(tmp_path, cac_bang):
    """MemoryManager trỏ vào một sqlite THẬT trên đĩa, có sẵn `cac_bang`."""
    import sqlalchemy

    duong = tmp_path / "thu.db"
    eng = sqlalchemy.create_engine(f"sqlite:///{duong}")
    with eng.begin() as conn:
        for ten in cac_bang:
            conn.execute(sqlalchemy.text(f"CREATE TABLE {ten} (id INTEGER)"))

    mem = MemoryManager()
    mem.engine = eng
    # Qua được cổng "sqlite thì bỏ qua" — đây là DB thật, không phải fallback
    # in-memory vì thiếu DATABASE_URL.
    mem.config.DB_URL = "postgresql+psycopg2://gia/thu"
    mem._luoc_do_da_kiem = False
    mem._luoc_do_loi = None
    return mem


def test_thieu_bang_thi_bao_ro_thieu_cai_nao(tmp_path):
    from src.core.memory import BANG_CAN_CO

    mem = _bo_nho_voi_bang(tmp_path, BANG_CAN_CO[:2])
    loi = mem.kiem_luoc_do()
    assert loi, "thiếu 4/6 bảng mà vẫn im lặng"
    for thieu in BANG_CAN_CO[2:]:
        assert thieu in loi, f"không nói rõ thiếu {thieu}"
    assert "KHÔNG lưu được" in loi, "phải nói hậu quả, không chỉ nói tên bảng"


def test_du_bang_thi_khong_bao_oan(tmp_path):
    from src.core.memory import BANG_CAN_CO

    mem = _bo_nho_voi_bang(tmp_path, BANG_CAN_CO)
    assert mem.kiem_luoc_do() is None


def test_chua_cau_hinh_DATABASE_URL_thi_KHONG_bao_thieu_bang():
    """
    `DB_URL` lùi về sqlite in-memory khi thiếu `DATABASE_URL`. Lúc đó mọi bảng
    đều thiếu — nhưng đó là CHƯA CẤU HÌNH, không phải lược đồ sai.

    Báo oan ở ENV=LOCAL vài lần thì lần thật cũng bị bỏ qua.
    """
    mem = MemoryManager()
    assert mem.config.DB_URL.startswith("sqlite"), "ca này chỉ đúng khi không có DATABASE_URL"
    assert mem.kiem_luoc_do() is None


def test_khong_co_engine_thi_noi_that():
    mem = MemoryManager()
    mem.engine = None
    mem._luoc_do_da_kiem = False
    assert "engine=None" in (mem.kiem_luoc_do() or "")


def test_chi_hoi_DB_mot_lan(tmp_path):
    """`/health` gọi mỗi lần — không được thêm một truy vấn mỗi lần."""
    from src.core.memory import BANG_CAN_CO

    mem = _bo_nho_voi_bang(tmp_path, BANG_CAN_CO[:1])
    lan_1 = mem.kiem_luoc_do()
    mem.engine = None          # phá engine: nếu hỏi lại DB thì kết quả sẽ đổi
    assert mem.kiem_luoc_do() == lan_1


def test_khong_kiem_duoc_thi_im_chu_khong_bao_oan():
    """Engine hỏng giữa chừng ≠ lược đồ sai. Đoán bừa là báo oan."""
    class _EngineHong:
        pass

    mem = MemoryManager()
    mem.engine = _EngineHong()
    mem.config.DB_URL = "postgresql+psycopg2://gia/thu"
    mem._luoc_do_da_kiem = False
    assert mem.kiem_luoc_do() is None
