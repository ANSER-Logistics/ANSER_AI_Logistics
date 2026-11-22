"""
src/core/saas_api.py — Tra cứu dữ liệu nghiệp vụ trực tiếp từ DB của Body.

⚠️ SCHEMA MAP (ngay dưới): tên bảng/cột PHẢI khớp frontend/src/server/db/schema.ts bên Body.
   Nếu Body đặt tên khác, CHỈ sửa khối hằng số dưới đây — toàn bộ SQL tự đúng theo.
   (Bản cũ truy vấn bảng 'items' + cột JSON 'metadata' — KHÔNG tồn tại trong Body.
    Soát 04/11/2026: 5/10 định danh sai, đã sửa — chi tiết ở khối SCHEMA MAP.)
"""
import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from src.core.config import Config
from src.core.utils import bo_dau, hom_nay_vn, loai_loi

logger = logging.getLogger(__name__)

# =====================================================================
# SCHEMA MAP — đối chiếu với lược đồ THẬT của Body
# ---------------------------------------------------------------------
# Nguồn: `Dgsonn/ANSER-logistics`, nhánh `master`, commit `d389c68` (01/11/2026),
# `frontend/src/server/db/schema.ts`. Đã chọn `master` vì nó MỚI HƠN cả hai
# nhánh tính năng (`chore/merge-feat-database-application` 26/10,
# `feat/database-application` 18/09).
#
# Soát lại 04/11/2026: 5 trong 10 định danh ở bản trước SAI. Không phải sai
# vặt — SQL dựng từ chúng sẽ hỏng ở bảng không tồn tại hoặc trả cột không có:
#
#   bản cũ              lược đồ thật       hậu quả nếu chạy
#   ------------------  -----------------  ---------------------------------
#   sales               sales_invoices     bảng không tồn tại
#   amount              total              cột không tồn tại
#   stock_quantity      stock              cột không tồn tại
#   workspace_id        warehouse_id       KHÁI NIỆM không tồn tại
#
# `workspace` là chỗ nặng nhất: Body KHÔNG có khái niệm workspace nào cả — tìm
# cả file không ra một chữ. Thứ Body có là `warehouse` (kho). Và lược đồ của họ
# ghi hẳn một dòng cho Brain ngay tại `sales_invoices.warehouse_id`:
#
#   "B6 — Brain nhận `X-Store-Id` (là warehouse) và cần lọc doanh số theo kho.
#    Không có cột này thì báo cáo doanh thu theo kho không dựng được."
#
# Tức Body đã dựng sẵn cột này CHO Brain, còn Brain vẫn gọi nó bằng tên cũ.
#
# Đây là bản sao mô tả thứ gì đó thuộc về Body (AGENTS.md §1). Nó lệch được, và
# đã lệch. Trước khi tin nó, đối chiếu lại schema.ts.
# =====================================================================
PRODUCTS_TABLE = "products"
P_ID = "id"
P_NAME = "name"
P_PRICE = "price"               # integer, VNĐ
P_STOCK = "stock"               # numeric(14,3) — KHÔNG phải 'stock_quantity'
P_WAREHOUSE = "warehouse_id"    # uuid -> warehouses.id, NOT NULL

SALES_TABLE = "sales_invoices"  # KHÔNG phải 'sales' — bảng đó không tồn tại
S_AMOUNT = "total"              # integer, tổng tiền 1 hoá đơn
S_DATE = "created_at"           # timestamptz, NOT NULL
S_WAREHOUSE = "warehouse_id"    # uuid -> warehouses.id (xem ghi chú B6 ở trên); NULL được (hoá đơn cũ)
S_ID = "id"

# Dòng hoá đơn — nguồn của báo cáo doanh thu/giá vốn (`get_report_lines`). Đối chiếu với
# `schema.ts` của Body ngày 22/11/2026 (nhánh tích hợp), cùng chỗ `collectSaleLines` của Body.
SALE_ITEMS_TABLE = "sales_invoice_items"
SI_INVOICE = "invoice_id"       # uuid -> sales_invoices.id, NOT NULL
SI_PRODUCT = "product_id"       # uuid -> products.id, NULL được (xoá sản phẩm thì `set null`)
SI_NAME = "product_name"        # snapshot lúc bán, NOT NULL
SI_QTY = "quantity"             # numeric(14,3), NOT NULL, khác 0
SI_UNIT_COST = "unit_cost"      # integer, NULL = chưa biết giá vốn LÚC BÁN
SI_LINE_TOTAL = "line_total"    # integer, NOT NULL, tiền thu về của dòng
P_COST = "cost"                 # integer, NULL được: giá vốn HIỆN TẠI của sản phẩm

# Tên cũ, giữ để không vỡ chỗ gọi chưa kịp đổi. Trỏ vào cùng giá trị đúng —
# KHÔNG phải vào giá trị cũ, vì giá trị cũ là sai, không phải là một bí danh.
P_WORKSPACE = P_WAREHOUSE
S_WORKSPACE = S_WAREHOUSE
# =====================================================================


def _period_filter(period: str) -> str:
    """
    Trả về điều kiện WHERE theo kỳ (PostgreSQL — môi trường production Neon).
    SQLite (dev) không có date_trunc/INTERVAL; chỉ 'today' chạy được trên SQLite.
    """
    period = (period or "today").lower()
    # "Hôm nay" tính ở ĐÂY theo giờ Việt Nam rồi đưa vào SQL như một hằng ngày, KHÔNG dùng
    # `CURRENT_DATE`: nó tính theo múi giờ của phiên DB (thường UTC), nên 00:00-07:00 sáng giờ
    # Việt Nam báo cáo "hôm nay" và "tuần này" còn là hôm qua. Hằng này là `date.isoformat()`
    # do mã tự sinh, không có chữ nào của người dùng trong đó.
    iso = hom_nay_vn().isoformat()
    if period == "week":
        return f"{S_DATE} >= date_trunc('week', CAST('{iso}' AS date))"
    if period == "month":
        return f"{S_DATE} >= date_trunc('month', CAST('{iso}' AS date))"
    # mặc định / 'today': chuỗi ISO trần, KHÔNG `CAST(... AS date)`: SQLite (dev) đọc CAST AS date
    # thành số (ra 2026) nên phép so sánh hỏng; PostgreSQL tự ép chuỗi ISO về date.
    return f"date({S_DATE}) = '{iso}'"


# =====================================================================
#  ĐỌC KỲ TỪ CÂU HỎI
# ---------------------------------------------------------------------
#  Đặt CẠNH `_period_filter` có chủ đích: danh sách kỳ đọc được và danh
#  sách kỳ truy vấn được phải luôn khớp nhau. Tách ra hai file thì thêm
#  một kỳ ở bên này mà quên bên kia, và biểu hiện là số của kỳ SAI —
#  loại lỗi không có triệu chứng.
# =====================================================================

SUPPORTED_PERIODS = ("today", "week", "month")

# Kỳ KHÔNG truy vấn được — phải khớp TRƯỚC, vì "tháng vừa rồi" và "tháng
# này" chỉ khác nhau một từ mà ra hai con số hoàn toàn khác.
_KY_CHUA_CO = (
    ("hôm qua", re.compile(r"hôm qua|ngày hôm qua|bữa qua", re.I)),
    ("tuần trước", re.compile(r"tuần (trước|rồi|vừa rồi|qua)", re.I)),
    ("tháng trước", re.compile(r"tháng (trước|rồi|vừa rồi|qua)", re.I)),
    ("quý", re.compile(r"quý\s*(này|trước|vừa rồi|rồi|[1-4]|i{1,3}v?|iv)", re.I)),
    ("năm", re.compile(r"năm (nay|ngoái|trước|vừa rồi|qua)|cả năm", re.I)),
)

_KY_CO = (
    ("today", "hôm nay", re.compile(r"hôm nay|bữa nay|ngày hôm nay", re.I)),
    ("week", "tuần này", re.compile(r"tuần (này|nay)", re.I)),
    ("month", "tháng này", re.compile(r"tháng (này|nay)", re.I)),
)


@dataclass(frozen=True)
class KyHoi:
    """Kỳ người dùng đang hỏi. `ho_tro=False` -> chưa truy vấn được kỳ đó."""

    period: str        # khoá đưa vào `_period_filter`; rỗng khi chưa hỗ trợ
    nhan: str          # tên tiếng Việt để dán vào ngữ cảnh và câu trả lời
    ho_tro: bool


def parse_period(question: str) -> KyHoi:
    """
    Đọc kỳ từ câu hỏi. Không nhắc kỳ nào -> hôm nay.

    VÌ SAO CẦN: `chat.py` từng đóng cứng `period="today"` bất kể người dùng hỏi
    kỳ nào. Hỏi "tháng trước bán được bao nhiêu" thì model chỉ nhận được số HÔM
    NAY, và chốt chặn neo số liệu KHÔNG bắt được — con số ấy có thật trong ngữ
    cảnh. Đúng số, sai câu hỏi: loại sai tệ nhất vì không có dấu hiệu gì.
    """
    q = question or ""
    for nhan, mau in _KY_CHUA_CO:
        if mau.search(q):
            return KyHoi("", nhan, False)
    for period, nhan, mau in _KY_CO:
        if mau.search(q):
            return KyHoi(period, nhan, True)
    return KyHoi("today", "hôm nay", True)


# =====================================================================
#  TÌM HÀNG THEO TỪ KHOÁ TRONG CÂU HỎI
# ---------------------------------------------------------------------
#  `lookup_product` từng đưa NGUYÊN câu hỏi vào `LIKE '%câu hỏi%'`, nên "còn bao nhiêu thùng dầu động cơ CF-4 15W40" không khớp tên hàng nào
#  (tên hàng không chứa nguyên câu). Cũng không bỏ dấu: người dùng gõ "thuy luc" thì không thấy "thuỷ lực". Ở đây rút từ khoá bằng LUẬT (không
#  model, R1), so khớp KHÔNG DẤU trong mã (SQL chung cho SQLite lẫn PostgreSQL không có `unaccent`), rồi xếp hạng theo độ phủ.
# =====================================================================

# Từ chức năng và từ hỏi, đã bỏ dấu. KHÔNG có "co" (có/cơ) và "tai" (tại/tải: "lốp xe tải"), vì bỏ dấu làm chúng lẫn nhau; không có đơn vị (thùng, lít, kg...) vì
# tên hàng chứa chúng ("Dầu động cơ thùng 18 lít").
_TU_BO_TIM_HANG = frozenset(
    "con bao nhieu gia cua cho toi minh em anh chi la the nao khong ko k may ban hang hoa san pham mat loai kho ton "
    "so luong dang hien xin vui long giup kiem tra xem check hoi biet tim tu o trong va voi hay hoac thi se da "
    "can muon lay mua nhap xuat nhe nha a oi vay day di roi ha ak duoc "
    "hom nay tuan thang nam qua truoc doanh thu".split()
)
_NGUONG_PHU = 0.5          # tỉ lệ trọng số từ khoá phải khớp tên hàng; thấp hơn thì coi là trùng ngẫu nhiên ("xe" trong "lốp xe tải" và "nhớt xe máy")
_NGUONG_SO_VOI_TOT_NHAT = 0.6
TOI_DA_HANG_TRA = 20
TOI_DA_HANG_DOC = 5000     # trần số hàng đọc để so khớp trong mã; vượt thì lùi về LIKE theo cụm từ khoá


@dataclass(frozen=True)
class TuKhoa:
    """Từ khoá tìm hàng của một câu: `co_so` là các từ (không dấu), `noi` là mã nối từ cặp chữ-ngắn + số liền kề ("aw 68" -> aw68 = (aw, 68))."""

    co_so: frozenset
    noi: dict

    def __bool__(self) -> bool:
        return bool(self.co_so)

    def hien_thi(self) -> frozenset:
        return self.co_so | frozenset(self.noi)


def _tach(chuoi, bo: frozenset = frozenset()):
    """(từ dài từ 2 ký tự, các mã nối) của `chuoi` không dấu. Chỉ nối hai từ liền kề, và không nối khi một trong hai là từ thừa ở `bo`."""
    tu = re.findall(r"[a-z0-9]+", bo_dau(chuoi))
    noi = {}
    for a, b in zip(tu, tu[1:]):
        if a in bo or b in bo:
            continue
        if (a.isalpha() and len(a) <= 3 and b.isdigit()) or (a.isdigit() and b.isalpha() and len(b) <= 3):
            noi[a + b] = (a, b)
    return {t for t in tu if len(t) >= 2}, noi


def tu_khoa_tim_hang(cau: str) -> TuKhoa:
    """Từ khoá tìm hàng trong câu hỏi (không dấu, đã bỏ từ hỏi và từ chức năng). Rỗng (`bool` False) = câu không nhắc mặt hàng nào."""
    tu, noi = _tach(cau, _TU_BO_TIM_HANG)
    return TuKhoa(frozenset(t for t in tu if t not in _TU_BO_TIM_HANG), noi)


def _trong_so(t: str) -> float:
    """Mã hàng và số hiệu (15w40, aw68, cf4) nói nhiều hơn từ thường: khớp "cf4" đáng giá hơn khớp "dau"."""
    return 1.0 + (1.5 if any(c.isdigit() for c in t) else 0.0) + (0.5 if len(t) >= 5 else 0.0)


def diem_khop_hang(tu_khoa: TuKhoa, ten_hang: str) -> float:
    """
    Độ phủ của từ khoá lên tên hàng, trong [0, 1]: tổng trọng số từ khoá khớp / tổng trọng số mọi từ khoá.

    Một từ khoá khớp khi bằng một từ của tên, hoặc (từ dài từ 3 ký tự) là tiền tố của một từ trong tên. Mã nối khớp thì cả hai phần của nó
    được tính là khớp ("aw 68" khớp "AW68"), nhưng mã nối KHÔNG khớp thì không bị trừ điểm: nó chỉ để cứu, không để phạt.
    """
    if not tu_khoa:
        return 0.0
    tu_ten, noi_ten = _tach(ten_hang)
    ten = tu_ten | set(noi_ten)
    khop = {
        t for t in tu_khoa.co_so
        if t in ten or (len(t) >= 3 and any(n.startswith(t) for n in ten))
    }
    for ma, (a, b) in tu_khoa.noi.items():
        if ma in ten:
            khop |= {x for x in (a, b) if x in tu_khoa.co_so}
    return sum(_trong_so(t) for t in khop) / sum(_trong_so(t) for t in tu_khoa.co_so)


# =====================================================================
#  DÒNG BÁN HÀNG CHO BÁO CÁO (nhánh REPORT của /chat, tool `report`)
# =====================================================================
SO_QUY_BAO_CAO = 4          # khớp `ReportRequest.periods_back` mặc định: quý hiện tại + 3 quý trước
DONG_TOI_DA = 200_000       # trần số dòng đọc một lần; vượt thì BÁO LỖI, không cắt (cắt = báo cáo thiếu doanh thu mà trông đủ)


def _dau_ky_bao_cao(hom_nay: date, so_quy: int) -> date:
    """Ngày đầu của quý cách quý hiện tại `so_quy - 1` quý. Lấy TRÒN quý để quý đầu của báo cáo không bị cụt."""
    thang_dau_quy = ((hom_nay.month - 1) // 3) * 3          # 0, 3, 6, 9
    tong_thang = hom_nay.year * 12 + thang_dau_quy - (so_quy - 1) * 3
    return date(tong_thang // 12, tong_thang % 12 + 1, 1)


def _thoi_diem(gia_tri) -> datetime:
    """`created_at` của Body là timestamptz (driver trả datetime có múi giờ); SQLite dev trả chuỗi. Không rõ múi giờ thì coi là UTC."""
    if isinstance(gia_tri, str):
        gia_tri = datetime.fromisoformat(gia_tri)
    if not isinstance(gia_tri, datetime):
        raise ValueError("created_at không đọc được thành thời điểm")
    return gia_tri if gia_tri.tzinfo else gia_tri.replace(tzinfo=timezone.utc)


def _so_huu_han(gia_tri) -> float:
    so = float(gia_tri)
    if not math.isfinite(so):
        raise ValueError("số tiền/số lượng không hữu hạn")
    return so


class SaasAPI:
    def __init__(self):
        self.config = Config()
        try:
            self.engine = create_engine(self.config.DB_URL)
        except Exception:
            logger.error("Không thể khởi tạo kết nối CSDL loi=%s", loai_loi())
            self.engine = None

    def _require_engine(self):
        if not self.engine:
            raise RuntimeError("Kết nối CSDL chưa sẵn sàng")

    def lookup_product(self, query, workspace_id=1):
        """
        Hàng của kho `workspace_id` khớp câu hỏi `query`, chuỗi JSON (tối đa `TOI_DA_HANG_TRA` hàng, khớp nhất trước) hoặc một câu tiếng Việt nói rõ vì sao không có.

        `query` là NGUYÊN VĂN tin nhắn người dùng. Từ khoá rút bằng luật (`tu_khoa_tim_hang`), so khớp không dấu trong mã trên toàn bộ hàng của kho
        (một truy vấn, tham số hoá, không nối chuỗi người dùng vào SQL). Kho quá lớn (trên `TOI_DA_HANG_DOC` hàng) thì lùi về `LIKE` theo từ khoá dài nhất.
        """
        self._require_engine()
        tu_khoa = tu_khoa_tim_hang(query)
        if not tu_khoa:
            return (
                "Câu hỏi không nhắc tên hay mã mặt hàng nào nên chưa tra kho. "
                "Hỏi lại kèm tên hoặc mã hàng (ví dụ: dầu động cơ CF-4 15W40) thì tôi tra ngay."
            )
        try:
            with self.engine.connect() as conn:
                sql = text(f"""
                    SELECT {P_ID}, {P_NAME}, {P_PRICE}, {P_STOCK}
                    FROM {PRODUCTS_TABLE}
                    WHERE {P_WAREHOUSE} = :ws_id
                    LIMIT :gioi_han
                """)
                rows = conn.execute(
                    sql, {"ws_id": workspace_id, "gioi_han": TOI_DA_HANG_DOC + 1}
                ).fetchall()
                if len(rows) > TOI_DA_HANG_DOC:
                    # LOWER(...) LIKE LOWER(...) thay cho ILIKE (ILIKE chỉ có ở PostgreSQL; DB trống thì Config lùi về SQLite).
                    # Không bỏ dấu được ở đường này: kho lớn hãy gõ có dấu.
                    goc = [t for t in re.findall(r"\w+", str(query).lower()) if bo_dau(t) in tu_khoa.co_so]
                    cum = max(goc, key=len)
                    rows = conn.execute(
                        text(f"""
                            SELECT {P_ID}, {P_NAME}, {P_PRICE}, {P_STOCK}
                            FROM {PRODUCTS_TABLE}
                            WHERE {P_WAREHOUSE} = :ws_id AND LOWER({P_NAME}) LIKE LOWER(:query)
                            LIMIT {TOI_DA_HANG_TRA}
                        """),
                        {"ws_id": workspace_id, "query": f"%{cum}%"},
                    ).fetchall()
                    xep = [(1.0, r) for r in rows]
                else:
                    xep = [(diem_khop_hang(tu_khoa, r[1] or ""), r) for r in rows]
                    tot_nhat = max((d for d, _ in xep), default=0.0)
                    nguong = max(_NGUONG_PHU, _NGUONG_SO_VOI_TOT_NHAT * tot_nhat)
                    xep = sorted(
                        ((d, r) for d, r in xep if d >= nguong),
                        key=lambda x: (-x[0], str(x[1][1])),
                    )[:TOI_DA_HANG_TRA]

                if not xep:
                    return f"Không tìm thấy sản phẩm '{str(query).strip()[:120]}' trong kho."

                results = []
                for _, r in xep:
                    price = f"{r[2]:,.0f} VND" if r[2] is not None else "N/A"
                    results.append({
                        "id": r[0],
                        "name": r[1],
                        "price": price,
                        "stock": r[3] if r[3] is not None else "N/A",
                    })
                return json.dumps(results, ensure_ascii=False, indent=2)
        except SQLAlchemyError:
            logger.error(
                "Lỗi truy vấn sản phẩm workspace_id=%s loi=%s",
                workspace_id, loai_loi(),
            )
            return "Lỗi hệ thống khi tìm sản phẩm."

    def get_sales_report(self, workspace_id=1, period="today"):
        self._require_engine()
        try:
            with self.engine.connect() as conn:
                sql = text(f"""
                    SELECT COALESCE(SUM({S_AMOUNT}), 0), COUNT(*)
                    FROM {SALES_TABLE}
                    WHERE {S_WAREHOUSE} = :ws_id
                      AND {_period_filter(period)}
                """)
                res = conn.execute(sql, {"ws_id": workspace_id}).fetchone()

                revenue = res[0] if res and res[0] else 0
                orders = res[1] if res and res[1] else 0
                return {
                    "period": (period or "today").lower(),
                    "revenue": f"{revenue:,.0f} VND",
                    "orders": orders,
                }
        except SQLAlchemyError:
            logger.error(
                "Lỗi truy vấn báo cáo bán hàng workspace_id=%s period=%s loi=%s",
                workspace_id, period, loai_loi(),
            )
            # `orders: 0` ở đây là một câu NÓI DỐI: nó đi thẳng vào ngữ cảnh của
            # model (chat.py dựng `[DOANH SỐ …]` từ JSON này) và model đọc "0 đơn".
            # Truy vấn hỏng thì số đơn là CHƯA BIẾT. Giữ `revenue: "Lỗi"` (chỗ đọc
            # hiện có dựa vào nó) và thêm một câu nói thẳng để model không suy diễn.
            return {
                "period": period, "revenue": "Lỗi", "orders": None,
                "ghi_chú": "KHÔNG LẤY ĐƯỢC số liệu — đây không phải 0 đơn.",
            }

    def get_report_lines(self, workspace_id=1, so_quy=SO_QUY_BAO_CAO):
        """
        Dòng bán hàng THÔ của `so_quy` quý gần nhất, cho `reporting.build_report` tính (R1).

        Trả `{"sales": [...], "expenses": []}`, mỗi dòng bán là `{date, revenue, product, quantity, cogs}`.
        Chỉ ĐỌC. Lỗi DB thì ném lỗi lên để `chat._fetch_report_lines` nói "chưa lấy được số liệu":
        trả danh sách rỗng ở đây sẽ thành báo cáo doanh thu 0, một con số trông như kết quả đo.

        Ba quyết định, đều theo cách Body tự làm trong `collectSaleLines` (brainReport.ts):
        - Giá vốn = `unit_cost` (lúc bán) rồi tới `products.cost` (hiện tại) rồi `None`. KHÔNG BAO GIỜ 0:
          giá vốn trống mà coi là 0 thì lãi gộp bằng doanh thu. Engine tự tính `cogs_coverage_pct`.
        - Dòng của sản phẩm đã xoá (`product_id` NULL) vẫn có mặt, qua LEFT JOIN: mất dòng là mất doanh thu.
          Body làm INNER JOIN nên bỏ sót chúng (Body#37); Brain không chép lỗi đó.
        - Ngày của dòng tính theo giờ Việt Nam (`hom_nay_vn`), không theo múi giờ của DB hay UTC.
          Hoá đơn lúc 02:00 sáng 01/10 giờ Việt Nam là 19:00 ngày 30/09 UTC, và thuộc quý 4.

        Chi phí vận hành để trống cho tới khi Body có bảng chi phí (Body#23): engine báo cảnh báo
        "chưa có chi phí", không điền 0.
        """
        self._require_engine()
        if not isinstance(so_quy, int) or isinstance(so_quy, bool) or not 1 <= so_quy <= 40:
            raise ValueError("so_quy phải là số nguyên từ 1 đến 40")
        tu_ngay = _dau_ky_bao_cao(hom_nay_vn(), so_quy)
        # Lọc thô trong SQL lùi một ngày (múi giờ phiên DB có thể lệch tới nửa ngày), rồi lọc đúng theo giờ VN trong mã.
        tu_sql = (tu_ngay - timedelta(days=1)).isoformat()
        sql = text(f"""
            SELECT i.{S_DATE}, it.{SI_NAME}, it.{SI_QTY}, it.{SI_LINE_TOTAL}, it.{SI_UNIT_COST}, p.{P_COST}
            FROM {SALE_ITEMS_TABLE} it
            JOIN {SALES_TABLE} i ON i.{S_ID} = it.{SI_INVOICE}
            LEFT JOIN {PRODUCTS_TABLE} p ON p.{P_ID} = it.{SI_PRODUCT}
            WHERE (i.{S_WAREHOUSE} = :ws_id
                   OR (i.{S_WAREHOUSE} IS NULL AND p.{P_WAREHOUSE} = :ws_id))
              AND i.{S_DATE} >= :tu
            ORDER BY i.{S_DATE}
            LIMIT :gioi_han
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(
                    sql, {"ws_id": workspace_id, "tu": tu_sql, "gioi_han": DONG_TOI_DA + 1}
                ).fetchall()
        except SQLAlchemyError:
            logger.error(
                "Lỗi truy vấn dòng bán hàng workspace_id=%s loi=%s", workspace_id, loai_loi(),
            )
            raise
        if len(rows) > DONG_TOI_DA:
            raise RuntimeError(f"hơn {DONG_TOI_DA} dòng bán trong {so_quy} quý: không đọc đủ thì không dựng báo cáo")

        sales = []
        for ngay_gio, ten, so_luong, tien, gia_von_ban, gia_von_sp in rows:
            ngay = hom_nay_vn(_thoi_diem(ngay_gio))
            if ngay < tu_ngay:
                continue
            sl = _so_huu_han(so_luong)
            gia_von = gia_von_ban if gia_von_ban is not None else gia_von_sp
            sales.append({
                "date": ngay.isoformat(),
                "revenue": _so_huu_han(tien),
                "product": ten or "",
                "quantity": sl,
                "cogs": None if gia_von is None else _so_huu_han(gia_von) * sl,
            })
        return {"sales": sales, "expenses": []}
