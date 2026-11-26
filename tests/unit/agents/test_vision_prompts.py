"""
tests/unit/agents/test_vision_prompts.py — prompt của model thị giác sống ở MỘT nơi (AGENTS §4.1 quy tắc 7, BR-19 phần 2a).

Trước 16/11/2026 bốn prompt này nằm inline trong `src/agents/vision.py`. Chuyển sang `Prompts` là dọn
chỗ, KHÔNG đổi chữ nào (đã so từng chữ với bản cũ khi chuyển); đổi nội dung prompt đọc ảnh là đổi hành
vi trích xuất và phải đo trên ảnh, nên test này canh NƠI Ở của prompt chứ không khoá nội dung.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.agents.vision import VisionAgent
from src.core.prompts import Prompts

_TEN = {"caption": "VLM_CAPTION", "ocr": "VLM_OCR", "invoice": "VLM_INVOICE", "freight": "VLM_FREIGHT"}


@pytest.mark.parametrize("tac_vu,hang", sorted(_TEN.items()))
def test_bang_tra_cua_vision_tro_thang_vao_prompts(tac_vu, hang):
    assert VisionAgent.PROMPTS[tac_vu] is getattr(Prompts, hang), (
        f"VisionAgent.PROMPTS[{tac_vu!r}] phải CHÍNH LÀ Prompts.{hang}, không phải một bản chép"
    )


def test_vision_py_khong_con_chuoi_prompt_dai_inline():
    """Không chuỗi dài nào trong vision.py ngoài docstring và log: prompt mới thêm vào phải vào prompts.py."""
    cay = ast.parse(Path("src/agents/vision.py").read_text(encoding="utf-8"))
    docstring = {id(n.body[0].value) for n in ast.walk(cay)
                 if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.body and isinstance(n.body[0], ast.Expr)
                 and isinstance(n.body[0].value, ast.Constant) and isinstance(n.body[0].value.value, str)}
    dai = [n.value[:50] for n in ast.walk(cay)
           if isinstance(n, ast.Constant) and isinstance(n.value, str)
           and id(n) not in docstring and len(n.value) > 80]
    assert not dai, f"chuỗi dài inline trong vision.py (prompt phải ở prompts.py): {dai}"


def test_prompt_cuoc_van_tai_van_cam_dien_0():
    """Đây là R1 ở phía prompt: trường không đọc được thì null, không điền 0. Canh để không ai gỡ nhầm."""
    assert "không điền 0" in Prompts.VLM_FREIGHT and "null" in Prompts.VLM_FREIGHT
