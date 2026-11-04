"""
tests/test_agent_middleware.py — lớp mỏng giữa CoderAgent và định dạng workflow.

VÌ SAO ĐÁNG VIẾT DÙ CHỈ 47 DÒNG
-------------------------------
File này từng TỰ ĐỊNH NGHĨA một danh mục node riêng (`google_sheet_read`,
`discord_notify`, khoá `params`, không có `position`) — định dạng THỨ BA trong
repo, mâu thuẫn với prompt (n8n) và với lớp validate (n8n). Workflow sinh ra
theo bản đó không import vào n8n được (ARCHITECTURE.md §11.1).

Bản 27/07/2026 gỡ sạch, chỉ còn chuyển tiếp sang `workflow_schema`. Nhưng
"chỉ còn chuyển tiếp" là một tính chất phải được GIỮ, không phải một sự thật
vĩnh viễn: thêm một `return {...}` viết tay vào đây là dựng lại đúng định dạng
thứ ba, và lần này không ai nhớ vì sao nó sai.

Nên các test dưới đây kiểm ĐỒNG NHẤT với nguồn sự thật, chứ không kiểm nội dung
trả về — nội dung là việc của `test_workflow_schema.py`.
"""

from __future__ import annotations

from src.core import workflow_schema
from src.core.agent_middleware import AgentMiddleware


def test_danh_muc_node_lay_tu_nguon_su_that():
    """Lệch một ký tự nghĩa là có nơi thứ hai định nghĩa danh mục node."""
    assert AgentMiddleware().get_workflow_tools() == workflow_schema.render_node_catalog()


def test_vi_du_few_shot_lay_tu_nguon_su_that():
    assert AgentMiddleware().get_workflow_examples() == workflow_schema.render_examples()


def test_json_schema_lay_tu_nguon_su_that():
    """
    Lược đồ này đi thẳng vào `guided_json` của vLLM. Một bản sao lệch ở đây ép
    model sinh đúng theo bản sao, rồi lớp validate lại chấm theo bản gốc — và
    mọi workflow đều trượt mà không ai hiểu vì sao.
    """
    assert AgentMiddleware().get_workflow_json_schema() == workflow_schema.build_workflow_schema()


def test_validate_dung_chung_ham_voi_route_chat():
    """
    `/chat` gọi `workflow_schema.validate_workflow`. Nếu middleware chấm bằng
    luật khác thì cùng một workflow sẽ hợp lệ ở chỗ này và hỏng ở chỗ kia.
    """
    hong = {"payload": {"nodes": []}}
    assert AgentMiddleware.validate(hong) == workflow_schema.validate_workflow(hong)


def test_bao_dung_dang_chay_catalog_du_phong_hay_khong():
    """
    False = `typeVersion` có thể lệch với n8n thật của Body, workflow import vào
    sẽ lỗi. Đây là thông tin chẩn đoán, không được đoán bừa.
    """
    assert AgentMiddleware().using_real_templates() is workflow_schema.is_using_real_templates()


def test_khong_giu_trang_thai():
    """
    Hai lần dựng phải cho cùng kết quả. Có trạng thái ở đây nghĩa là danh mục
    node phụ thuộc thứ tự gọi — thứ không thể lần ra khi nó sai.
    """
    a, b = AgentMiddleware(), AgentMiddleware()
    assert a.get_workflow_tools() == b.get_workflow_tools()
    assert a.__dict__ == {} == b.__dict__


def test_khong_dinh_nghia_lai_gi_trong_file_nay():
    """
    Chốt chặn thẳng vào mã nguồn: file này không được chứa tên node hay khoá
    định dạng nào. Có là dấu hiệu định dạng thứ ba đang quay lại.
    """
    import ast
    import inspect

    from src.core import agent_middleware

    # Bỏ MỌI docstring rồi mới soi. Tài liệu ở file này cố ý nhắc tên định dạng
    # cũ để giải thích vì sao không được làm thế — soi cả docstring thì chốt
    # chặn bắt nhầm chính lời cảnh báo của nó.
    cay = ast.parse(inspect.getsource(agent_middleware))
    for node in ast.walk(cay):
        than_node = getattr(node, "body", None)
        if isinstance(than_node, list) and than_node:
            dau = than_node[0]
            if (isinstance(dau, ast.Expr) and isinstance(dau.value, ast.Constant)
                    and isinstance(dau.value.value, str)):
                than_node.pop(0)
    than = ast.unparse(cay)

    for dau_hieu in ("google_sheet", "discord_notify", '"params"', "'params'",
                     '"nodes"', "typeVersion"):
        assert dau_hieu not in than, (
            f"{dau_hieu!r} xuất hiện trong agent_middleware.py — định dạng "
            "workflow phải chỉ được định nghĩa ở workflow_schema.py (P4)."
        )


# ---------------------------------------------------------------------------
# R4 — ba nơi AGENTS.md nói phải khớp nhau
# ---------------------------------------------------------------------------
# AGENTS.md §2 R4 liệt kê ba nơi: prompt dạy model định dạng, danh mục node đưa
# vào prompt, và lớp kiểm đầu ra. Trong mã nguồn hôm nay cả ba đã dựng TỪ MỘT
# nguồn (`workflow_schema`), nên chuyện "sửa một nơi quên hai nơi kia" không
# còn xảy ra được bằng cách sửa ba file.
#
# Nhưng nó VẪN xảy ra được bằng một cách khác, và chưa có test nào chặn: hai
# hàm cùng đọc catalog mà trình bày lệch nhau. `render_node_catalog()` viết ra
# thứ MODEL ĐƯỢC DẠY; `validate_workflow()` kiểm thứ MODEL PHẢI LÀM. Hai hàm đó
# ở cùng file nên trông như không thể lệch — nhưng chúng là hai vòng lặp riêng
# trên cùng một dict, và một lần lọc thêm điều kiện ở một trong hai là dạy model
# một định dạng mà lớp kiểm từ chối. Đó là đúng lớp lỗi R4 sinh ra để diệt, chỉ
# là ở quy mô nhỏ hơn ba file.
#
# `test_deterministic_core` đã kiểm grammar guided_json khớp `allowed_types()`.
# Hai test dưới đây kiểm chân còn lại: PROMPT khớp lớp KIỂM.


def test_prompt_day_dung_nhung_node_lop_kiem_cho_phep():
    """Tập node trong prompt == tập node `validate_workflow` nhận.

    Lệch một chiều nào cũng hỏng, theo hai cách khác nhau:
      - prompt có mà lớp kiểm không  -> model làm đúng lời dạy rồi bị từ chối
      - lớp kiểm có mà prompt không  -> mất một node dùng được, không ai biết
    """
    import re

    trong_prompt = set(
        re.findall(r"n8n-nodes-base\.[A-Za-z0-9_]+",
                   workflow_schema.render_node_catalog())
    )
    lop_kiem = set(workflow_schema.get_node_catalog())

    assert trong_prompt == lop_kiem, (
        f"prompt thừa: {sorted(trong_prompt - lop_kiem)}, "
        f"prompt thiếu: {sorted(lop_kiem - trong_prompt)}"
    )
    assert trong_prompt == set(workflow_schema.allowed_types())


def test_prompt_day_dung_typeVersion_lop_kiem_doi():
    """typeVersion trong prompt == typeVersion lớp kiểm báo khi node sai.

    `validate_workflow` chỉ đòi `typeVersion` là một con số, nhưng khi báo lỗi nó
    nói RÕ con số đúng là bao nhiêu, lấy từ catalog. Nếu prompt dạy một số khác,
    model sinh workflow import vào n8n của Body không chạy — mà lớp kiểm vẫn cho
    qua, vì nó chỉ kiểm kiểu. Không có test này thì lệch đó im lặng tới lúc
    workflow chạy thật.
    """
    import re

    cap_trong_prompt = dict(
        re.findall(r"(n8n-nodes-base\.[A-Za-z0-9_]+) \(typeVersion ([0-9.]+)\)",
                   workflow_schema.render_node_catalog())
    )
    catalog = workflow_schema.get_node_catalog()

    assert set(cap_trong_prompt) == set(catalog)
    for ntype, meta in catalog.items():
        assert cap_trong_prompt[ntype] == str(meta["typeVersion"]), ntype


def test_node_bi_chan_khong_nam_trong_danh_muc():
    """Node bị chặn KHÔNG được xuất hiện trong prompt, và phải bị lớp kiểm loại.

    `n8n-nodes-base.code` cho chạy mã tuỳ ý. Dạy model nó rồi chặn ở lớp sau là
    tạo ra một vòng retry chắc chắn thất bại; tệ hơn, nó dạy model rằng node đó
    hợp lệ, và dữ liệu fine-tune sinh từ prompt này mang theo điều đó.
    """
    # KHÔNG lặp suông trên tập rỗng. Đột biến thử nghiệm 04/11: đổi
    # `BLOCKED_NODE_TYPES` thành `set()` làm vòng lặp dưới đây không chạy lần
    # nào và test VẪN XANH — đúng lớp lỗi "test không thể đỏ". Chốt số lượng và
    # gọi tên node nguy hiểm nhất ra để nó không thể biến mất trong im lặng.
    assert len(workflow_schema.BLOCKED_NODE_TYPES) >= 3
    assert "n8n-nodes-base.code" in workflow_schema.BLOCKED_NODE_TYPES

    trong_prompt = workflow_schema.render_node_catalog()
    for xau in workflow_schema.BLOCKED_NODE_TYPES:
        assert xau not in trong_prompt
        assert xau not in workflow_schema.get_node_catalog()

        ok, ly_do = workflow_schema.validate_workflow({
            "action": "create_workflow",
            "name": "thử",
            "payload": {"nodes": [{
                "name": "N", "type": xau, "typeVersion": 1,
                "position": [0, 0], "parameters": {},
            }], "connections": {}},
        })
        assert not ok
        # Lý do phải NÓI RA node nào — nó đi thẳng vào feedback retry.
        assert xau in ly_do
