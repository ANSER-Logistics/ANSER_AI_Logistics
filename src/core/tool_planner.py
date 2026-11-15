"""
src/core/tool_planner.py — CHỌN TOOL BẰNG LUẬT, không để model chọn.

VÌ SAO
------
Benchmark đo khâu "model tự chọn tool" chỉ đúng 26–33%. Nhưng nhìn kỹ thì việc
chọn tool không phải việc cần đến model: "có nên nhập thêm hàng không" luôn ứng
với `forecast_reorder`, không có ngữ cảnh nào làm nó thành tool khác. Đây là ánh
xạ từ ý định sang tên hàm — đúng thứ một bảng luật làm tốt hơn và làm được 100%.

Nên ranh giới P1 dịch thêm một nấc. Model giờ chỉ còn HAI việc:
  1. điền tham số cho tool đã được chọn sẵn   (tiếng Việt -> struct)
  2. viết câu trả lời từ kết quả tool          (struct -> tiếng Việt)
Chọn tool, chạy tool, và lấy dữ liệu đều là code tất định.

TOOL NÀO CẦN DỮ LIỆU HỆ THỐNG
-----------------------------
Chỗ này quan trọng hơn cả bảng luật. `report` cần danh sách dòng bán hàng;
`inventory_audit` cần bảng tổng hợp tồn kho. Model KHÔNG có những thứ đó — bảo
nó điền `arguments` cho `report` là mời nó bịa ra doanh thu rồi hệ thống tính
toán tử tế trên số bịa, cho ra một báo cáo sai mà trông hoàn toàn bình thường.

Vì vậy `NEEDS_SYSTEM_DATA` không phải chú thích: vòng agentic bắt buộc lấy dữ
liệu cho các tool này từ nguồn tất định, và KHÔNG chạy nếu chưa có nguồn.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# KHỚP CẢ CÂU KHÔNG DẤU (16/11/2026)
#
# Người dùng thật hay gõ không dấu ("bao cao doanh thu thang nay", "khach nao no nhieu nhat"). Bảng luật
# viết có dấu nên bỏ lọt cả loạt: đo trên bộ câu nghiệp vụ hư cấu (`offline_training/do_nghiep_vu.py`),
# MỌI câu không dấu đều trượt.
#
# `_Mau` bọc một mẫu regex và có HAI dạng: dạng có dấu (nguyên bản) và dạng đã bỏ dấu. Câu CÓ dấu, dù chỉ một
# chữ, dùng dạng có dấu, nên hành vi với câu có dấu KHÔNG ĐỔI (quan trọng: "thuê" khác "thuế", và bảng luật
# được viết quanh khác biệt đó). Chỉ câu HOÀN TOÀN không dấu mới dùng dạng bỏ dấu.
#
# Giá của việc đó: khi bỏ dấu thì một số từ trùng nhau ("thuê"/"thuế", "vật"/"vat", "rà"/"ra"). Mỗi chỗ đã gặp
# được xử riêng (xem `khong_dau=` ở luật `vat` và `_bo_dau_mau`). Chỗ chưa gặp thì sẽ sai, và bộ đo là nơi
# phát hiện nó.
# ---------------------------------------------------------------------------

def _bo_dau(s: str) -> str:
    d = unicodedata.normalize("NFD", s)
    return "".join(c for c in d if unicodedata.category(c) != "Mn").replace("đ", "d").replace("Đ", "D")


def _la_khong_dau(q: str) -> bool:
    return _bo_dau(q) == q


def _bo_dau_mau(pattern: str) -> str:
    """Bỏ dấu trong NGUỒN regex; một nhánh trần "rà" thành "ra" (từ quá phổ biến: "ra kho lấy hàng") nên đổi
    thành "ra soat"."""
    return re.sub(r"(?<=[(|])ra(?=[|)])", "ra soat", _bo_dau(pattern))


class _Mau:
    """Mẫu regex có dạng có dấu và dạng bỏ dấu; chọn theo câu. Có đủ các phương thức mà module này dùng."""

    __slots__ = ("_co_dau", "_khong_dau")

    def __init__(self, pattern: str, flags: int = 0, *, khong_dau: str | None = None):
        self._co_dau = re.compile(pattern, flags)
        self._khong_dau = re.compile(khong_dau if khong_dau is not None else _bo_dau_mau(pattern), flags)

    def _chon(self, q: str) -> re.Pattern[str]:
        return self._khong_dau if _la_khong_dau(q) else self._co_dau

    def search(self, q: str):
        return self._chon(q).search(q)

    def finditer(self, q: str):
        return self._chon(q).finditer(q)

    def findall(self, q: str):
        return self._chon(q).findall(q)

    def sub(self, repl: str, q: str) -> str:
        return self._chon(q).sub(repl, q)


# Số tiền: "3 triệu", "3.500.000đ", "500k", "3tr5". Có nó thì câu hỏi thuế là câu TÍNH,
# không có thì là câu TRA LUẬT — hai đường đi khác hẳn nhau.
# Ngưỡng 5 chữ số cho số trần có chủ đích: 4 chữ số là NĂM. "Báo cáo thuế năm
# 2026" mà tính 2026 thành số tiền thì câu đó bị kéo vào tool `vat` với tham số
# vô nghĩa, trong khi nó chỉ là một câu hỏi báo cáo.
_SO_TIEN = _Mau(
    r"\d[\d.,]*\s*(triệu|tr(?=\d|\b)|tri\.?|nghìn|ngàn|tỷ|ty\b|đồng|đ\b|vnd|k\b)"
    r"|\d{1,3}([.,]\d{3}){1,3}\b"
    r"|\b\d{5,}\b",
    re.IGNORECASE,
)

# Câu SOÁT HOÁ ĐƠN: "hoá đơn/invoice" đứng gần một động từ soát (kiểm, soát,
# đối chiếu, xác minh) hoặc cụm nghi vấn ("hợp lệ", "có đúng", "có khớp").
#
# Không nằm trong `_RULES` vì nó không chỉ CHỌN tool mà còn PHỦ QUYẾT tool khác:
# hoá đơn dán kèm (OCR/VLM đọc ra) hay chứa "kho"/"tồn" trong TÊN DÒNG HÀNG
# ("phí kiểm đếm, lưu kho bãi"…) làm luật `inventory_audit` khớp nhầm — sự cố
# benchmark T4 (23/08/2026): người dùng hỏi soát hoá đơn mà nhận "chưa có bảng
# tồn kho". Bảng `_RULES` chỉ biết cộng thêm tool, không biết gạt tool, nên
# luật này sống riêng và được `plan_tools` áp SAU khi quét bảng.
#
# Cửa sổ 0-60 ký tự vì giữa "hoá đơn" và động từ thường chen vài mệnh đề
# ("hóa đơn sau, hãy kiểm tra tính hợp lệ"); DOTALL vì nội dung hoá đơn dán
# kèm hay có xuống dòng.
#
# MỘT MÌNH mẫu này KHÔNG đủ để phủ quyết hay cộng `vat` — nó khớp cả những câu
# soi KHO THẬT có nhắc hoá đơn bằng lời ("kiểm kê kho, đối chiếu với hóa đơn
# nhập hàng"). Điều kiện đủ nằm ở `la_cau_soat_hoa_don`: phải kèm DẤU HIỆU
# hoá đơn dán kèm — đúng đặc trưng của sự cố T4.
_HOA_DON_KIEM = _Mau(
    r"(kiểm|soát|đối chiếu|xác minh|validate|verify)"
    r".{0,60}(hoá đơn|hóa đơn|invoice)"
    r"|(hoá đơn|hóa đơn|invoice).{0,60}"
    r"(kiểm|soát|đối chiếu|xác minh|hợp lệ|có đúng|có khớp|validate|verify)",
    re.IGNORECASE | re.DOTALL,
)

# Dấu hiệu NỘI DUNG HOÁ ĐƠN DÁN KÈM (JSON do OCR/VLM đọc ra, hoặc bảng số
# liệu chép vào): ngoặc nhọn, hoặc tên trường quen thuộc của payload hoá đơn.
# Câu gõ tay bằng lời không chứa những thứ này.
_TU_KHOA_DAN_KEM = _Mau(
    r"[{}]|\b(items|total_amount|unit_price|subtotal)\b",
    re.IGNORECASE,
)

# Khối ngoặc nhọn = phần dán kèm tách được về mặt cấu trúc. Dùng để hỏi "bỏ
# phần dán kèm đi thì câu còn đòi soi kho không". Greedy `.*` cố ý: lấy từ
# '{' đầu đến '}' cuối, vì JSON hoá đơn lồng nhiều tầng ngoặc; nhánh hai vớt
# JSON bị cắt cụt (có mở không có đóng). Thay bằng MỘT khoảng trắng chứ không
# xoá trắng để hai vế câu không bị dính chữ vào nhau tạo match giả.
_KHOI_NGOAC = _Mau(r"\{.*\}|\{.*$", re.DOTALL)


def _co_dau_hieu_dan_kem(cau: str) -> bool:
    """
    Câu có mang theo NỘI DUNG hoá đơn (dán kèm) hay chỉ NHẮC hoá đơn bằng lời?

    Ba dấu hiệu, khớp một là đủ:
      1. ngoặc nhọn / tên trường JSON quen thuộc — VLM đọc hoá đơn ra JSON;
      2. >= 2 số tiền — bảng dòng hàng chép tay cũng có đơn giá lẫn tổng;
      3. dấu hai chấm dẫn vào phần có số tiền ("giúp tôi: tổng 3.500.000đ…")
         — cách người dùng chép số liệu của MỘT tờ hoá đơn cụ thể vào câu.
    Câu chỉ có MỘT số tiền trần và không dẫn nội dung ("kiểm tra hóa đơn tổng
    250 triệu có khớp sổ sách không") là câu hỏi thủ tục/đối chiếu sổ — không
    có dòng hàng nào để tính lại, cộng `vat` chỉ ép model bịa items=[] rồi ra
    "lệch 250 triệu" (sự cố nêu ở phản biện 23/08/2026).
    """
    if _TU_KHOA_DAN_KEM.search(cau):
        return True
    if sum(1 for _ in _SO_TIEN.finditer(cau)) >= 2:
        return True
    _truoc, hai_cham, sau = cau.partition(":")
    return bool(hai_cham) and bool(_SO_TIEN.search(sau))


def la_cau_soat_hoa_don(cau: str) -> bool:
    """
    Câu là Ý ĐỊNH SOÁT MỘT TỜ HOÁ ĐƠN CỤ THỂ (có dấu hiệu nội dung dán kèm)?

    Đây là hợp đồng công khai cho tầng trên: `src/api/routes/chat.py` import
    hàm này để rẽ nhánh câu soát hoá đơn. Điều kiện của nó ĐÚNG BẰNG điều kiện
    `plan_tools` cộng tool `vat` theo đường hoá đơn — hai nơi không được lệch
    nhau, nên cùng gọi một hàm.

    True  = có ý định soát (`_HOA_DON_KIEM`) VÀ có nội dung dán kèm
            (`_co_dau_hieu_dan_kem`) — có gì đó để tính lại thật.
    False = câu chỉ nhắc hoá đơn bằng lời (soi kho thật, hỏi thủ tục…) —
            đi đường cũ, không phủ quyết tool nào.
    """
    q = (cau or "").strip()
    return bool(q) and bool(_HOA_DON_KIEM.search(q)) and _co_dau_hieu_dan_kem(q)


# ---------------------------------------------------------------------------
# "BÁO GIÁ" LÀ BA Ý ĐỊNH KHÁC NHAU (chủ dự án chốt 28/10/2026, sau BR-05)
#
#   1. Khách XIN báo giá ("báo giá xe 5 tấn HN đi HP")      -> nhánh LOGISTICS/n8n
#   2. TÍNH GIÁ BÁN từ giá nhà xe đã có, kèm biên lợi nhuận -> agentic `quote`
#   3. SO NHIỀU LỜI CHÀO GIÁ của các nhà xe                -> agentic `carrier_selection`
#
# Ý định 1 thiếu giá nhà xe — phải tra bảng giá trong Sheet, nên đi n8n. Ý định
# 2 có sẵn mọi đầu vào của `/tools/quote` ngay trong câu; đưa nó qua n8n là vứt
# đi đúng con số người dùng vừa đưa. Trước bản này, ý định 2 và 3 không có
# đường nào: luật `report` bắt chữ trần "lợi nhuận" trong "BIÊN lợi nhuận", nên
# BR-05 đo được 6/6 câu tính giá bán bị trả về BÁO CÁO LÃI LỖ.
#
# Luật viết theo CỤM NGHIỆP VỤ ("nhà xe … chào … X đồng", "biên lợi nhuận"),
# không theo chữ của từng câu trong bộ đề — xem tests/test_tool_planner.py, phần
# câu viết mới không lấy từ bộ đề.
# ---------------------------------------------------------------------------

# Số tiền kèm đơn vị hoặc có dấu phân cách hàng nghìn. Hẹp hơn `_SO_TIEN` có chủ
# đích: không nhận số trần 5 chữ số (mã, số lượng) làm giá chào.
_TIEN = (
    r"(\d[\d.,]*\s*(triệu|tr(?=\d|\b)|nghìn|ngàn|đồng|đ\b|vnđ|vnd|k\b)"
    r"|\d{1,3}([.,]\d{3}){1,3}\b)"
)

# Giá NHÀ XE đưa ra: chủ thể là bên vận chuyển, động từ chào/báo/chốt, rồi một
# số tiền — trong cùng một mệnh đề (không vượt dấu chấm câu). "nhà xe nào rẻ
# nhất" không có số tiền nên không khớp: đó là câu chọn nhà xe chưa có giá.
_GIA_NHA_XE = _Mau(
    r"(nhà xe|nha xe|hãng xe|nhà thầu|bên xe|đơn vị vận chuyển|\bhọ\b)"
    r"[^.;?!\n]{0,60}?\b(chào|chao|báo chốt|chốt|báo)\b[^.;?!\n]{0,60}?" + _TIEN
    # "giá (cước) nhà xe 12 triệu", "nhà xe 6 triệu": giá đứng liền sau chủ thể, không có động từ chào/báo.
    + r"|(giá|cước)\s+(cước\s+)?(của\s+)?(nhà xe|nha xe|hãng xe)[^.;?!\n]{0,20}?" + _TIEN
    + r"|(nhà xe|nha xe|hãng xe)\s*(là|:)?\s*" + _TIEN,
    re.IGNORECASE,
)

# Biên lợi nhuận là THAM SỐ của phép tính giá bán, không phải yêu cầu báo cáo.
# "biên 10%", "lãi 12%", "lợi nhuận 8%" cũng là biên: người ta hiếm khi nói đủ "biên lợi nhuận".
_BIEN = _Mau(r"biên\s+(lợi nhuận|lãi)|biên\s*\d|(lãi|lời|lợi nhuận)\s*\d+([.,]\d+)?\s*%|\bmargin\b",
             re.IGNORECASE)

# Một LỜI CHÀO trong câu liệt kê nhiều nhà xe: số tiền đi kèm điều khoản
# (chiết khấu / công nợ) trong cùng vế, hoặc "chào" + số tiền.
_LOI_CHAO_KEM_DIEU_KHOAN = _Mau(
    _TIEN + r"[^;\n]{0,40}?(chiết khấu|chiet khau|công nợ|cong no)",
    re.IGNORECASE,
)
_CHAO_SO_TIEN = _Mau(r"\b(chào|chao)\s+(giá\s+)?" + _TIEN, re.IGNORECASE)


def la_cau_so_chao_gia(cau: str) -> bool:
    """
    Ý định 3: câu đưa ra TỪ HAI LỜI CHÀO GIÁ trở lên để so.

    Hợp đồng công khai cho `chat.py` (cùng nếp `la_cau_soat_hoa_don`): câu này
    có chữ "báo giá" thì router xếp LOGISTICS, nhưng nó phải vào vòng agentic.
    """
    q = cau or ""
    return max(len(_LOI_CHAO_KEM_DIEU_KHOAN.findall(q)),
               len(_CHAO_SO_TIEN.findall(q))) >= 2


def la_cau_tinh_gia_ban(cau: str) -> bool:
    """
    Ý định 2: có GIÁ NHÀ XE và BIÊN LỢI NHUẬN, và không phải câu so nhiều lời chào.

    Thiếu giá nhà xe ("biên 12%, giá dầu lên 26.000 thì sao") là KHÔNG: không có
    `carrier_cost` thì `quote` không chạy được, ép tool vào chỉ mời model bịa giá.
    Câu đó để trống kế hoạch, model hỏi lại.
    """
    q = cau or ""
    return (not la_cau_so_chao_gia(q)
            and bool(_GIA_NHA_XE.search(q)) and bool(_BIEN.search(q)))


# Yêu cầu RÕ về danh mục hàng / công nợ. Câu TÍNH thuế trên một số tiền ("mua dầu nhớt 3tr5 thuế 8%, tổng
# phải trả bao nhiêu") chứa tên hàng gần "8%" và cụm "phải trả bao nhiêu", nên khớp luật danh mục và luật
# công nợ dù không ai hỏi chuyện đó. Chỉ khi câu có số tiền VÀ tính thuế thì hai tool này bị gạt, trừ khi câu
# nói rõ mình hỏi danh mục / công nợ bằng các cụm dưới đây.
_MAU_DANH_MUC_RO = _Mau(
    r"danh mục|mã hàng|mặt hàng nào|cờ thuế|cờ giảm|toàn bộ (sản phẩm|hàng)|từng (mã|mặt hàng)",
    re.IGNORECASE,
)
_MAU_CONG_NO_RO = _Mau(r"công nợ|nhà cung cấp|khách (hàng )?(nợ|nào)|đối tác|dư nợ", re.IGNORECASE)


# Câu hỏi ĐỊNH NGHĨA ("doanh thu là gì, khác lợi nhuận chỗ nào", "công nợ là gì"): chứa từ nghiệp vụ nhưng
# người hỏi muốn được giải thích, không muốn chạy phân tích trên số liệu của họ.
_MAU_DINH_NGHIA = _Mau(r"\blà gì\b|khác (nhau )?(chỗ nào|ở đâu|gì)|nghĩa là gì|khái niệm", re.IGNORECASE)


# Mẫu SOI KHO tách ra thành hằng riêng vì được dùng ở HAI chỗ: trong `_RULES`
# (chọn tool) và trong `plan_tools` (kiểm lại trên phần câu ĐÃ BỎ khối dán kèm
# — xem chú thích phủ quyết ở đó). Hai chỗ phải cùng một mẫu, viết hai lần thì
# trôi nhau (P4).
_MAU_SOI_KHO = _Mau(
    r"(soi|rà|rà soát|soát|kiểm tra|kiểm|đối chiếu|audit)\s+.{0,12}(kho|tồn|sổ sách)"
    r"|tồn (kho )?âm|sai sổ sách|lệch sổ|hàng chết|hàng tồn lâu"
    r"|giá vốn.{0,15}(sai|lệch|bất thường)"
    # "tồn cuối kỳ có khớp với số nhập xuất không": đối chiếu tồn với sổ.
    r"|(tồn|kho).{0,30}(khớp|lệch).{0,20}(nhập xuất|sổ|thẻ kho)",
    re.IGNORECASE,
)

# Mỗi luật: (tên tool, mẫu nhận diện, có cần số tiền kèm theo không).
#
# Viết CHẶT có chủ đích. Luật bắt hụt thì câu đó đi tiếp vào nhánh cũ — vẫn trả
# lời được. Luật bắt thừa thì một câu chào hỏi bị kéo vào vòng gọi tool và trả
# về thứ chẳng liên quan. Sai kiểu thứ hai đắt hơn nhiều.
_RULES: list[tuple[str, _Mau, bool]] = [
    (
        "inventory_audit",
        _MAU_SOI_KHO,
        False,
    ),
    (
        # CỐ Ý không bắt "doanh thu"/"doanh số" trần. Hai lý do:
        #  - "hộ kinh doanh DOANH THU bao nhiêu thì phải đóng thuế" là câu hỏi
        #    LUẬT, không phải yêu cầu báo cáo.
        #  - "doanh thu hôm nay bao nhiêu" là một con số, nhánh DATA_INTERNAL
        #    trả thẳng từ DB. Kéo nó vào đây chỉ đổi một câu trả lời được thành
        #    "chưa nối được dữ liệu".
        # Ranh giới: DATA_INTERNAL lo một con số, `report` lo phân tích lãi/lỗ.
        "report",
        _Mau(
            r"báo cáo\s+(tài chính|kinh doanh|lãi|lỗ|lợi nhuận|doanh thu chi phí)"
            # "BIÊN lợi nhuận" là tham số giá bán, không phải yêu cầu báo cáo
            # — xem khối "BA Ý ĐỊNH" ở trên.
            r"|lãi (gộp|ròng|hay lỗ)|lỗ hay lãi|(?<!biên )lợi nhuận"
            r"|tổng kết (kinh doanh|quý|năm|tháng)"
            r"|(quý|tháng|năm|nửa năm) (này|nay|trước|vừa rồi|qua).{0,30}(lãi|lỗ)"
            r"|mặt hàng nào (lãi|lời) nhất|tuyến nào (lỗ|lãi)"
            r"|so sánh doanh (thu|số) (quý|tháng|năm)"
            # "báo cáo doanh thu" (có chữ báo cáo), và doanh thu đặt cạnh nhau hai kỳ: đó là phân tích,
            # khác "doanh thu hôm nay bao nhiêu" (một con số, nhánh DATA_INTERNAL lo).
            r"|báo cáo\s+doanh (thu|số)"
            r"|doanh (thu|số)\s+[^.?!\n]{0,30}so với",
            re.IGNORECASE,
        ),
        False,
    ),
    (
        "forecast_reorder",
        _Mau(
            r"nên nhập (thêm|hàng)|có nên nhập|cần nhập thêm|đặt hàng lại|đặt thêm hàng"
            r"|dự báo (nhu cầu|bán|tiêu thụ)|tồn an toàn|điểm đặt hàng"
            r"|sắp hết hàng|bao giờ hết hàng|nhập bao nhiêu"
            r"|(cần|nên|gợi ý|đề xuất).{0,25}đặt (thêm|hàng)|số lượng (cần |nên )?(đặt|nhập)"
            r"|bao lâu (nữa )?(thì )?(sẽ )?hết (hàng|tồn)?|(mặt hàng|hàng|sản phẩm)[^.?!\n]{0,20}sắp hết"
            r"|sắp hết (hàng|tồn)|cần đặt gấp",
            re.IGNORECASE,
        ),
        False,
    ),
    (
        "carrier_selection",
        _Mau(
            r"(nhà xe|hãng xe|đơn vị vận chuyển|nhà thầu) nào"
            r"|chọn (nhà xe|hãng xe|đơn vị vận chuyển)"
            r"|so sánh (các )?(nhà xe|hãng xe)|xếp hạng.{0,15}(nhà xe|hãng xe)"
            r"|ưu tiên (ai|nhà xe|hãng xe)|trong các (nhà xe|hãng xe)"
            r"|nên (thuê|dùng|giao cho) (nhà xe|hãng xe|ai)",
            re.IGNORECASE,
        ),
        False,
    ),
    (
        # CỐ Ý không bắt "công nợ" trần — cùng lý do với `report` và "doanh thu".
        # "quy định CÔNG NỢ thanh toán bao nhiêu ngày" và "chính sách CÔNG NỢ bên
        # mình" là câu tra TÀI LIỆU NỘI BỘ, không phải yêu cầu phân tích số dư.
        # Kéo chúng vào đây thì câu trả lời đúng ("30 ngày, theo quy định đã nạp")
        # bị thay bằng "tôi chưa có danh sách công nợ" — đổi một câu trả lời được
        # thành một câu từ chối.
        "partner_audit",
        _Mau(
            r"(soi|rà soát|rà|kiểm tra|kiểm|đối chiếu|phân tích|thống kê|tổng hợp)"
            r"\s+\S{0,15}\s*(công nợ|phải thu|phải trả)"
            r"|tổng (công nợ|phải thu|phải trả)"
            r"|(công nợ|phải thu|phải trả)\s+(hiện (tại|nay|giờ)|bây giờ|đang|còn lại)"
            r"|(công nợ|phải thu|phải trả) (là )?bao nhiêu"
            r"|khách (hàng )?nào (còn |đang )?nợ|ai (đang |còn )?nợ (mình|em|tôi|công ty)"
            r"|nợ (quá hạn|khó đòi|lâu (chưa|không) trả)"
            r"|thu hồi (công )?nợ|đòi nợ|khách nào nợ nhiều"
            r"|dư nợ (của |khách)|vốn lưu động"
            r"|số dư (của )?(khách|nhà cung cấp|đối tác)|có ai nợ|nợ quá (lớn|nhiều)"
            r"|công nợ (của )?khách|(công nợ|phải thu|phải trả).{0,25}tập trung"
            r"|chiếm bao nhiêu phần trăm.{0,20}(nợ|công nợ|phải thu|phải trả)"
            r"|(còn )?nợ nhà cung cấp"
            r"|(mã số thuế|mst)\s+\S{0,10}\s*(sai|trùng|không hợp lệ|kiểm)",
            re.IGNORECASE,
        ),
        False,
    ),
    (
        # Đặt TRƯỚC `vat` và viết chặt hơn hẳn: đây là câu về DANH MỤC hàng hoá
        # ("mặt hàng nào 8%"), còn `vat` là tính thuế trên một số tiền cụ thể.
        # Hai luật cùng khớp thì không sao — `_PIPELINE` cho cả hai chạy, và
        # chúng trả lời hai nửa khác nhau của cùng một câu hỏi.
        #
        # Mọi nhánh đều buộc phải có TỪ CHỈ HÀNG HOÁ. Thiếu ràng buộc đó thì
        # "doanh nghiệp nhỏ có được giảm thuế không" — một câu tra luật — bị kéo
        # vào tool đối chiếu danh mục.
        "vat_catalog_audit",
        _Mau(
            r"(thuế suất|thuế gtgt|vat)"
            r".{0,25}(mặt hàng|hàng hoá|hàng hóa|danh mục|mã hàng|sản phẩm)"
            r"|(mặt hàng|hàng hoá|hàng hóa|dầu nhớt|dầu nhờn|mã hàng|sản phẩm)"
            r".{0,30}(được giảm|mấy phần trăm|bao nhiêu phần trăm|8%|10%)"
            r"|8% hay 10%|10% hay 8%"
            r"|gắn cờ thuế|cờ thuế|áp (sai |nhầm )?thuế suất"
            r"|(soi|rà soát|rà|kiểm tra|đối chiếu).{0,15}(thuế suất|cờ thuế)"
            r"|cờ giảm|giảm 2%|(đối chiếu|rà|soát).{0,15}danh mục"
            r"|(danh mục|danh sách).{0,40}(giảm thuế|thuế suất)"
            r"|hàng nào.{0,40}(thuế|vat).{0,30}(không được giảm|sai)"
            r"|(thuế|vat) (8%|10%).{0,40}không được giảm",
            re.IGNORECASE,
        ),
        False,
    ),
    (
        "vat",
        _Mau(
            r"thuế|vat|gtgt", re.IGNORECASE,
            khong_dau=r"thue(?!\s*(xe|nha|kho|mat bang|van chuyen|dat\b|dia diem|xuong|may))"
                      r"|\bvat\b(?!\s*(tu|lieu|dung|nuoi|ly|chat))|gtgt",
        ),
        True,   # phải có số tiền, nếu không thì là câu tra luật -> RETRIEVAL
    ),
]

# Thứ tự chạy cố định, KHÔNG theo thứ tự chữ trong câu hỏi. "Có nên nhập thêm
# không, tháng này lãi bao nhiêu" phải chạy `report` trước `forecast_reorder`
# giống hệt câu hỏi ngược lại — cùng một ý định thì cùng một đường đi.
_PIPELINE = ["inventory_audit", "partner_audit", "vat_catalog_audit", "report",
             "forecast_reorder", "carrier_selection", "quote", "vat"]

# Trần số tool một câu hỏi được kích hoạt. `DEFAULT_MAX_STEPS` là 4 và bước cuối
# phải dành cho việc viết câu trả lời.
MAX_PLAN = 3

# Tool -> những TRƯỜNG mà hệ thống cấp, model không được đụng vào.
#
# Không chỉ để chặn bịa dữ liệu. Nó còn quyết định hình dạng JSON Schema đưa vào
# guided decoding: `arguments` bỏ trống hoàn toàn thì model ngồi viết ra nguyên
# mảng `sales` — thứ `data_provider` vứt đi ngay sau đó. Đo được 9/19 ca chạm
# trần 2048 token vì đúng chuyện này (05/08/2026), và cắt cụt thì JSON hỏng,
# `_parse` trả None, vòng lặp gãy -> người dùng nhận "tôi chưa hoàn thành được".
#
# Nghĩa là ta bắt model bịa ra dữ liệu, rồi vứt đi, rồi hỏng vì việc bịa đó.
SYSTEM_DATA_FIELDS: dict[str, tuple[str, ...]] = {
    "report": ("sales", "expenses"),
    "inventory_audit": ("lines",),
    "forecast_reorder": ("items",),
    "carrier_selection": ("carriers", "offers"),
    "partner_audit": ("customers", "suppliers"),
    "vat_catalog_audit": ("products",),
}

# Dẫn xuất, không viết tay lần hai (P4).
NEEDS_SYSTEM_DATA = frozenset(SYSTEM_DATA_FIELDS)


def system_data_fields(tool: str) -> tuple[str, ...]:
    """Trường do hệ thống cấp cho tool này. Rỗng = model điền toàn bộ."""
    return SYSTEM_DATA_FIELDS.get(tool, ())


def plan_tools(question: str, available: list[str] | None = None) -> list[str]:
    """
    Danh sách tool cần chạy, theo thứ tự. Rỗng = không luật nào khớp.

    `available` (thường là tên tool trong manifest) lọc bỏ tool chưa tồn tại —
    bảng luật không được phép nhắc tới một tool đã bị gỡ khỏi manifest (P4).
    """
    q = (question or "").strip()
    if not q:
        return []

    co_so_tien = bool(_SO_TIEN.search(q))
    if not co_so_tien and _MAU_DINH_NGHIA.search(q):
        return []
    khop = {
        tool
        for tool, mau, can_so in _RULES
        if mau.search(q) and (co_so_tien or not can_so)
    }
    # Soát hoá đơn CÓ NỘI DUNG DÁN KÈM là ý định về MỘT tờ hoá đơn — cộng
    # `vat` và gạt `inventory_audit` (mẫu kho khớp nhờ chữ "kho"/"tồn" trong
    # TÊN DÒNG HÀNG của hoá đơn, không phải nhờ một yêu cầu soi kho — sự cố
    # T4). Gạt hẳn thay vì chỉ xếp `vat` lên trước: còn nằm trong kế hoạch thì
    # vòng agentic vẫn chạm "chưa có bảng tồn kho" và câu đó vẫn đến tay người
    # dùng.
    #
    # Điều kiện là `la_cau_soat_hoa_don` chứ KHÔNG phải `_HOA_DON_KIEM` trần:
    # mẫu trần phủ quyết cả câu soi KHO THẬT có nhắc hoá đơn bằng lời ("kiểm kê
    # kho, đối chiếu với hóa đơn nhập hàng" từng ra [] thay vì inventory_audit
    # — phản biện 23/08/2026). Không có dấu hiệu dán kèm thì không có gì để
    # tính lại, câu đi đường cũ nguyên vẹn.
    if la_cau_soat_hoa_don(q):
        khop.add("vat")
        # CÂU GHÉP "soát hoá đơn <JSON> và rà soát sổ tồn kho": vế kho là yêu
        # cầu THẬT, không được nuốt. Chỉ phân xử được khi phần dán kèm tách ra
        # được về cấu trúc (có ngoặc nhọn): bỏ khối ngoặc đi mà câu VẪN đòi soi
        # kho thì giữ inventory_audit. Không có ngoặc thì không tách nổi trong/
        # ngoài — ưu tiên chống T4, phủ quyết (lựa chọn có chủ đích, có test
        # ghi nhận trong tests/test_tool_planner.py).
        van_doi_soi_kho = "{" in q and _MAU_SOI_KHO.search(_KHOI_NGOAC.sub(" ", q))
        if not van_doi_soi_kho:
            khop.discard("inventory_audit")

    # Câu TÍNH thuế trên số tiền: gạt danh mục và công nợ khớp nhờ từ chung chung (xem `_MAU_DANH_MUC_RO`).
    if "vat" in khop and co_so_tien:
        if not _MAU_DANH_MUC_RO.search(q):
            khop.discard("vat_catalog_audit")
        if not _MAU_CONG_NO_RO.search(q):
            khop.discard("partner_audit")

    # Ba ý định "báo giá" — xem khối "BA Ý ĐỊNH". Ý định 3 xét TRƯỚC: câu so
    # nhiều nhà xe cũng có chữ "chào". Cả hai gạt `report`: "biên lợi nhuận"
    # trong câu là tham số, và một câu hỏi giá bán không được nhận về báo cáo
    # lãi lỗ.
    if la_cau_so_chao_gia(q):
        khop.add("carrier_selection")
        khop -= {"report", "quote"}
    elif la_cau_tinh_gia_ban(q):
        khop.add("quote")
        khop.discard("report")

    if available is not None:
        khop &= set(available)

    return [t for t in _PIPELINE if t in khop][:MAX_PLAN]


def vao_vong_agentic(cat: str, plan: list[str], cau: str) -> bool:
    """
    Câu này có vào VÒNG AGENTIC (tool do luật chọn) không, hay đi luồng riêng của nhánh `cat`?

    `cat` là nhánh do `SemanticRouter` chọn, `plan` là kết quả `plan_tools(cau)`. Hàm thuần: cùng đầu vào
    cho cùng kết quả. Tách khỏi `chat.py` (16/11/2026) để bộ đo nghiệp vụ dùng CHÍNH định nghĩa này.

    Mặc định: có kế hoạch và nhánh không phải LOGISTICS hay TECHNICAL thì vào. LOGISTICS và TECHNICAL đã có
    luồng struct riêng (trích xuất báo giá -> n8n; sinh workflow -> validate), đều tất định và đang chạy được.

    Ba NGOẠI LỆ cho LOGISTICS, từng cái có sự cố đi kèm:

    NGOẠI LỆ HẸP cho LOGISTICS (sự cố tái hiện 23/08/2026): câu DÁN KÈM
    hoá đơn VẬN TẢI bị luật từ khoá của SemanticRouter bắt thành
    LOGISTICS (method=keyword, score=1.0) chỉ vì TÊN DÒNG HÀNG trong
    hoá đơn chứa chữ vận chuyển ("Cước vận chuyển HN-HP") — đó là DỮ
    LIỆU nằm trong tờ hoá đơn, không phải Ý ĐỊNH của người hỏi. Đứng
    ngoài vòng agentic khi ấy nghĩa là kế hoạch ["vat"] không bao giờ
    chạy: người dùng đòi SOÁT hoá đơn lại nhận về luồng BÁO GIÁ.

    Điều kiện mở cửa CỐ Ý gồm cả hai vế: kế hoạch phải chứa `vat` VÀ câu
    phải là soát-hoá-đơn-có-nội-dung-dán-kèm (`la_cau_soat_hoa_don` —
    cùng một hàm mà `plan_tools` dùng để cộng `vat`, hai nơi không lệch
    nhau được). Câu báo giá thật ("báo giá xe 5 tấn đi Hải Phòng") không
    thoả vế nào nên vẫn đi nguyên luồng n8n. TECHNICAL giữ nguyên.

    Cùng hình dạng, hai ý định nữa (chủ dự án chốt 28/10/2026, sau
    BR-05): câu TÍNH GIÁ BÁN từ giá nhà xe đã có ("nhà xe chào 12,5 triệu,
    biên 8%") và câu SO NHIỀU LỜI CHÀO GIÁ. Cả hai hay chứa "báo giá" nên
    router xếp LOGISTICS, nhưng luồng n8n chỉ nhận tuyến/xe/ngày — nó vứt
    đúng con số người dùng vừa đưa. Mỗi ngoại lệ cần CẢ tool trong kế
    hoạch LẪN hàm nhận diện của chính tool_planner, nên "nhà xe nào rẻ
    nhất" (chưa có giá) và "báo giá xe 5 tấn đi HP" vẫn đi n8n.
    """
    y_dinh_trong_logistics = cat == "LOGISTICS" and (
        ("vat" in plan and la_cau_soat_hoa_don(cau))
        or ("quote" in plan and la_cau_tinh_gia_ban(cau))
        or ("carrier_selection" in plan and la_cau_so_chao_gia(cau))
    )
    return bool(plan) and (cat not in ("LOGISTICS", "TECHNICAL") or y_dinh_trong_logistics)


def needs_system_data(tool: str) -> bool:
    """Tool này có cần dữ liệu từ hệ thống thay vì từ lời người dùng không?"""
    return tool in NEEDS_SYSTEM_DATA


__all__ = [
    "la_cau_soat_hoa_don",
    "la_cau_so_chao_gia",
    "la_cau_tinh_gia_ban",
    "plan_tools",
    "needs_system_data",
    "system_data_fields",
    "NEEDS_SYSTEM_DATA",
    "SYSTEM_DATA_FIELDS",
    "MAX_PLAN",
]
