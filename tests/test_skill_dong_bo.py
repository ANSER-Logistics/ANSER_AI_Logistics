"""
tests/test_skill_dong_bo.py — skill cho trợ lý AI phải giống hệt ở hai thư mục.

`.claude/skills/` cho Claude Code, `.agents/skills/` cho Codex và Gemini CLI. Hai bản sao
của cùng một thứ (R4): sửa một bên mà quên bên kia thì hai công cụ dạy hai luật khác nhau.
Và cả hai công cụ từ chối SKILL.md không có frontmatter `name` + `description` — đúng lỗi
"invalid frontmatter format" Gemini báo cho bốn skill cũ trước 18/11/2026.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLAUDE = ROOT / ".claude" / "skills"
AGENTS = ROOT / ".agents" / "skills"


def _skills(goc: Path) -> dict[str, bytes]:
    return {p.relative_to(goc).as_posix(): p.read_bytes() for p in goc.rglob("*") if p.is_file()}


def test_hai_thu_muc_skill_giong_het():
    claude, agents = _skills(CLAUDE), _skills(AGENTS)
    assert len(claude) >= 6, "chốt chống xanh suông: phải thấy đủ skill"
    assert claude.keys() == agents.keys(), "skill chỉ có ở một bên — chép sang bên kia"
    lech = [k for k in claude if claude[k] != agents[k]]
    assert not lech, f"nội dung lệch giữa .claude/skills và .agents/skills: {lech}"


@pytest.mark.parametrize("skill", sorted(p.parent for p in AGENTS.glob("*/SKILL.md")), ids=lambda p: p.name)
def test_frontmatter_hop_le(skill: Path):
    van_ban = (skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", van_ban, re.S)
    assert m, "thiếu khối frontmatter --- ... --- ở đầu file"
    truong = dict(dong.split(": ", 1) for dong in m.group(1).splitlines())
    assert truong.get("name") == skill.name, "name phải trùng tên thư mục"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", skill.name), "tên chỉ gồm chữ thường, số, gạch ngang"
    assert truong.get("description"), "thiếu description"
    assert ": " not in truong["description"], "': ' trong description làm hỏng YAML"
