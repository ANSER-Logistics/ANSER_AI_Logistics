"""
src/core/memory.py — Lịch sử chat / session / attachment, lưu trên DB của Body.

⚠️ SCHEMA MAP (dưới): tên bảng/cột PHẢI khớp core/db/connection.py bên Body.
   Sửa quan trọng: bảng tin nhắn đổi 'chat_messages' -> 'ai_chat_history' (theo Body).
"""
import json
import logging

from sqlalchemy import create_engine, text

from src.core.config import Config

logger = logging.getLogger(__name__)

# =====================================================================
# SCHEMA MAP — đối chiếu Body/core/db/connection.py rồi chỉnh nếu cần
# =====================================================================
SESSIONS_TABLE = "chat_sessions"
ATTACHMENTS_TABLE = "chat_attachments"
MESSAGES_TABLE = "ai_chat_history"     # ⚠️ bản cũ dùng 'chat_messages'
# Cột bảng tin nhắn (kiểm tra lại tên cột với Body):
M_SESSION, M_ROLE, M_CONTENT, M_CREATED = "session_id", "role", "content", "created_at"
# =====================================================================

# Mọi bảng file này chạm tới. Dùng cho `kiem_luoc_do()`.
#
# ⚠️ SOÁT 04/11/2026: TOÀN BỘ danh sách này KHÔNG CÓ trong lược đồ Body.
#
# Không phải đổi tên — chưa bao giờ có. Đối chiếu cả 15 migration của Body
# (`Dgsonn/ANSER-logistics`, master, `frontend/src/server/db/migrations/`,
# `0000_dizzy_iron_man` → `0014_youthful_red_wolf`): tổng cộng tạo đúng 13 bảng,
# và không có chữ "chat", "message" hay "workspace" nào trong cả lịch sử.
#
#   automation_rules · categories · company_settings · customers · employees
#   inventory_transactions · invoice_payments · products · sales_invoice_items
#   sales_invoices · suppliers · users · warehouses
#
# Mà `Config.DB_URL` đọc `DATABASE_URL` — tức file này nối vào CHÍNH DB của
# Body. Nghĩa là S7 (hội thoại nhiều lượt, AGENTS §8 đánh dấu ✅ Xong) không
# lưu được gì khi chạy với DB thật.
#
# Chưa sửa hướng đi, vì ba hướng rất khác nhau và đều cần chủ dự án chọn: Body
# thêm bảng (thay đổi bên Body — AGENTS §1 chỉ cho ĐỀ XUẤT), Brain dùng DB
# riêng (thêm thứ phải vận hành — R3), hay bỏ lưu phía Brain để Body gửi kèm
# ngữ cảnh (nhất quán với `agent_middleware.get_db_schema`). Xem việc brain#24.
#
# Cái sửa được ngay mà không cần chọn hướng là `kiem_luoc_do()` bên dưới: cho
# lỗi NHÌN THẤY ĐƯỢC thay vì trả rỗng.
BANG_CAN_CO = (
    SESSIONS_TABLE,
    ATTACHMENTS_TABLE,
    MESSAGES_TABLE,
    "workspaces",
    "user_workspaces",
    "workflows",
)


class MemoryManager:
    def __init__(self):
        self.config = Config()
        try:
            self.engine = create_engine(self.config.DB_URL)
        except Exception:
            logger.error("Failed to create database engine", exc_info=True)
            self.engine = None
        # Nhớ kết quả kiểm lược đồ — `/health` gọi mỗi lần, DB chỉ hỏi một lần.
        self._luoc_do_da_kiem: bool = False
        self._luoc_do_loi: str | None = None

    def get_conn(self):
        if not self.engine:
            raise RuntimeError("Database engine is not configured")
        return self.engine.connect()

    def kiem_luoc_do(self) -> str | None:
        """
        Bảng nào thiếu, hoặc None khi đủ. Kết quả nhớ lại, chỉ hỏi DB một lần.

        VÌ SAO CẦN HÀM NÀY
        ------------------
        Mọi phương thức bên dưới đều bắt `Exception`, ghi log, rồi trả `[]` hoặc
        `""`. Log có — nhưng CHỖ GỌI không phân biệt được "không có dữ liệu" với
        "bảng không tồn tại". Nên `get_user_stores` trả `[]`, `ContextResolver`
        thấy không có cửa hàng nào, và người dùng đọc được "chưa có cửa hàng"
        trong khi sự thật là lược đồ sai.

        Hệ thống trông như đang chạy đúng với dữ liệu rỗng. Đúng loại lỗi mà
        AGENTS.md R1 gọi là tệ nhất: sai mà nghe có vẻ đúng, không ai phát hiện.

        Cùng lý lẽ với dòng `auth_enabled` ở `/health` — một dòng biến lỗi câm
        thành lỗi nhìn ra ngay.

        Trả chuỗi mô tả (để `/health` in thẳng ra) chứ không ném: `/health`
        không bao giờ được phép hỏng vì một phép kiểm chẩn đoán.
        """
        if self._luoc_do_da_kiem:
            return self._luoc_do_loi

        self._luoc_do_da_kiem = True
        # DATABASE_URL được đặt nhưng không nhận ra: báo thẳng. Đặt TRƯỚC nhánh sqlite
        # bên dưới, vì lúc đó `DB_URL` đã lùi về sqlite và nhánh đó sẽ trả "khoẻ".
        loi_cau_hinh = getattr(self.config, "DB_URL_LOI", None)
        if loi_cau_hinh:
            self._luoc_do_loi = loi_cau_hinh
            return self._luoc_do_loi
        if not self.engine:
            self._luoc_do_loi = "Chưa nối được DB (engine=None)"
            return self._luoc_do_loi

        # DB_URL lùi về sqlite in-memory khi thiếu DATABASE_URL. Lúc đó mọi bảng
        # đều thiếu, nhưng đó là CHƯA CẤU HÌNH chứ không phải lược đồ sai — báo
        # "thiếu 6 bảng" ở ENV=LOCAL là báo oan, và báo oan vài lần thì lần thật
        # cũng bị bỏ qua.
        if self.config.DB_URL.startswith("sqlite"):
            self._luoc_do_loi = None
            return None

        try:
            from sqlalchemy import inspect as _inspect
            thieu = [t for t in BANG_CAN_CO if not _inspect(self.engine).has_table(t)]
        except Exception:
            logger.warning("Không kiểm được lược đồ DB", exc_info=True)
            self._luoc_do_loi = None   # không kiểm được ≠ sai; đừng báo oan
            return None

        if thieu:
            self._luoc_do_loi = (
                f"Thiếu {len(thieu)}/{len(BANG_CAN_CO)} bảng trong DB: "
                f"{', '.join(thieu)}. Lịch sử hội thoại KHÔNG lưu được. "
                "Xem khối BANG_CAN_CO trong src/core/memory.py."
            )
            logger.error("Lược đồ DB không khớp: %s", self._luoc_do_loi)
        else:
            self._luoc_do_loi = None
        return self._luoc_do_loi

    def _get_active_session(self, conn, user_id, workspace_id="1"):
        """
        Lấy session mới nhất của user; nếu chưa có thì TẠO MỚI và COMMIT NGAY.

        FIX: trước đây INSERT session nhưng KHÔNG commit. Khi gọi từ hàm chỉ-đọc
        (get_context_string không commit), session vừa tạo bị rollback lúc đóng
        connection -> mỗi request lại tạo session mới liên tục. Commit ngay tại đây
        khiến session bền vững bất kể caller có commit hay không.
        """
        row = conn.execute(
            text(f"SELECT id FROM {SESSIONS_TABLE} WHERE user_id = :uid "
                 f"ORDER BY last_active DESC LIMIT 1"),
            {"uid": str(user_id)},
        ).fetchone()
        if row:
            return row[0]

        res = conn.execute(
            text(f"INSERT INTO {SESSIONS_TABLE} (user_id, workspace_id, title) "
                 f"VALUES (:uid, :wid, 'New Session') RETURNING id"),
            {"uid": str(user_id), "wid": str(workspace_id)},
        ).fetchone()
        conn.commit()  # <-- FIX: cố định session ngay, tránh bị rollback
        return res[0]

    def save_attachment(self, user_id, workspace_id, filename, filetype, analysis):
        try:
            with self.get_conn() as conn:
                sid = self._get_active_session(conn, user_id, workspace_id)
                logger.info("Saving attachment user_id=%s session=%s file=%s", user_id, sid, filename)
                conn.execute(
                    text(f"INSERT INTO {ATTACHMENTS_TABLE} "
                         f"(session_id, file_name, file_type, analysis_summary) "
                         f"VALUES (:sid, :f, :t, :a)"),
                    {"sid": sid, "f": filename, "t": filetype, "a": analysis},
                )
                conn.execute(
                    text(f"UPDATE {SESSIONS_TABLE} SET last_active = CURRENT_TIMESTAMP WHERE id = :sid"),
                    {"sid": sid},
                )
                conn.commit()
        except Exception:
            logger.error("DB error saving attachment user_id=%s file=%s", user_id, filename, exc_info=True)

    def add_message(self, user_id, workspace_id, role, content):
        try:
            with self.get_conn() as conn:
                sid = self._get_active_session(conn, user_id, workspace_id)
                conn.execute(
                    text(f"INSERT INTO {MESSAGES_TABLE} ({M_SESSION}, {M_ROLE}, {M_CONTENT}) "
                         f"VALUES (:sid, :role, :content)"),
                    {"sid": sid, "role": role, "content": str(content)},
                )
                conn.commit()
        except Exception:
            logger.error("DB error saving message user_id=%s role=%s", user_id, role, exc_info=True)

    def get_history_messages(self, user_id, limit=6) -> list:
        """
        Lịch sử hội thoại dạng [{"role": ..., "content": ...}] — ĐÚNG khe
        hội thoại của chat template.

        Khác `get_context_string` (ghép thành một chuỗi "user: ...\\nassistant:
        ..."): chuỗi ghép phải nhét vào system prompt hoặc user turn, khiến
        model coi lời của chính nó là chỉ thị hệ thống và dễ nhại lại định
        dạng "user:". Danh sách messages đi đúng chỗ của nó.

        Trả [] khi chưa có DB hoặc lỗi — hội thoại một lượt vẫn chạy được,
        chỉ mất ngữ cảnh (suy giảm mềm, không sập request).
        """
        if not self.engine:
            return []
        try:
            with self.get_conn() as conn:
                sid = self._get_active_session(conn, user_id)
                rows = conn.execute(
                    text(f"SELECT {M_ROLE}, {M_CONTENT} FROM {MESSAGES_TABLE} "
                         f"WHERE {M_SESSION} = :sid ORDER BY {M_CREATED} DESC LIMIT :lim"),
                    {"sid": sid, "lim": limit},
                ).fetchall()
            out = []
            for role, content in reversed(rows):
                role = (role or "").strip().lower()
                if role in ("bot", "ai", "model"):     # tên vai cũ của Body
                    role = "assistant"
                if role in ("user", "assistant") and content:
                    out.append({"role": role, "content": str(content)})
            return out
        except Exception:
            logger.error("DB error fetching history user_id=%s", user_id, exc_info=True)
            return []

    def get_context_string(self, user_id, limit=6):
        try:
            with self.get_conn() as conn:
                # 1. Visual context (attachment mới nhất trong session đang active)
                sid = self._get_active_session(conn, user_id)

                att_row = conn.execute(
                    text(f"SELECT file_name, analysis_summary FROM {ATTACHMENTS_TABLE} "
                         f"WHERE session_id = :sid ORDER BY created_at DESC LIMIT 1"),
                    {"sid": sid},
                ).fetchone()

                vision_context = ""
                if att_row:
                    vision_context = (
                        f"\n[SYSTEM: The user just uploaded an image named '{att_row[0]}'.]\n"
                        f"[IMAGE ANALYSIS]: {att_row[1]}\n"
                        f"(Use this analysis to answer questions about 'the image'.)\n"
                    )

                # 2. Text history
                rows = conn.execute(
                    text(f"SELECT {M_ROLE}, {M_CONTENT} FROM {MESSAGES_TABLE} "
                         f"WHERE {M_SESSION} = :sid ORDER BY {M_CREATED} DESC LIMIT :lim"),
                    {"sid": sid, "lim": limit},
                ).fetchall()
                history = "\n".join([f"{r[0]}: {r[1]}" for r in reversed(rows)])

                return vision_context + "\n" + history
        except Exception:
            logger.error("DB error fetching context user_id=%s", user_id, exc_info=True)
            return ""

    def get_user_workspaces(self, uid):
        if not self.engine:
            return []
        try:
            with self.get_conn() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT w.id, w.name
                        FROM workspaces w
                        JOIN user_workspaces uw ON uw.workspace_id = w.id
                        WHERE uw.user_id = :uid
                        ORDER BY w.id
                        """
                    ),
                    {"uid": str(uid)},
                ).fetchall()
            return [{"id": row[0], "name": row[1]} for row in rows]
        except Exception:
            logger.error("DB error fetching workspaces user_id=%s", uid, exc_info=True)
            return []

    def get_user_stores(self, uid):
        workspaces = self.get_user_workspaces(uid)
        return [
            {
                "id": ws.get("id"),
                "name": ws.get("name", f"Store {ws.get('id')}"),
                "industry": "Retail",
                "location": "Unknown",
            }
            for ws in workspaces
        ]

    def get_store_details(self, store_id):
        if not self.engine:
            return None
        try:
            with self.get_conn() as conn:
                row = conn.execute(
                    text(
                        """
                        SELECT id, name
                        FROM workspaces
                        WHERE id = :sid
                        LIMIT 1
                        """
                    ),
                    {"sid": store_id},
                ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "name": row[1] or f"Store {row[0]}",
                "industry": "Retail",
                "location": "Unknown",
                "lat": 10.8231,
                "lon": 106.6297,
            }
        except Exception:
            logger.error("DB error fetching store details store_id=%s", store_id, exc_info=True)
            return None

    def save_workflow(self, wid, name, data):
        if not self.engine:
            return None
        payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        try:
            with self.get_conn() as conn:
                row = conn.execute(
                    text(
                        """
                        INSERT INTO workflows (workspace_id, name, json_data)
                        VALUES (:wid, :name, CAST(:payload AS jsonb))
                        RETURNING id
                        """
                    ),
                    {"wid": wid, "name": name, "payload": payload},
                ).fetchone()
                conn.commit()
                return row[0] if row else None
        except Exception:
            logger.error("DB error saving workflow workspace_id=%s name=%s", wid, name, exc_info=True)
            return None
