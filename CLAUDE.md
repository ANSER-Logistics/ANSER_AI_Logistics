# CLAUDE.md — ANSER Brain

@AGENTS.md

AGENTS.md (imported above) is the source of truth for how to work here: rules R1–R5, the review protocol and the definition of done. This file only adds what is specific to Claude Code. If they conflict, AGENTS.md wins.

## Project skills (`.claude/skills/`)

| Skill | When |
|---|---|
| `anser-map` | Loaded automatically before exploring: which module owns what, what is stale, how to query the graph |
| `/anser-verify` | Before saying "done", before a PR, before any push: CI + pre-commit checks, R1–R4 questions, full-history secret scan |
| `async-data-miner`, `fastapi-background-tasker`, `ocr-invoice-parser`, `webhook-dispatcher` | v1 skills, partly outdated: read their ⚠️ block first |

The same skills live in `.agents/skills/` for Codex and Gemini. Edit one copy, then copy it to the other; `tests/test_skill_dong_bo.py` fails on drift (AGENTS.md §9).

## Save tokens: query the graph before reading files

If `graphify-out/graph.json` exists, run `graphify query "<question>"`, `graphify explain "<symbol>"` or `graphify path "A" "B"` first, then read only the line ranges it points to. `graphify-out/` is gitignored. Build it with `/graphify .` and refresh it with `graphify update .` (code only, no LLM).

`.graphifyignore` excludes `src/data/` (uploads, possible customer data). Never send that folder to any external LLM or extractor (R2).

## Habits for this repo

- Run tests with `ENV=LOCAL`. No GPU or model is needed.
- Architecture, SRS and roadmap live in the private repo `ANSER-Logistics/anser-brain-docs`. Link to them with absolute URLs; a relative link to a missing file fails `tests/test_tai_lieu_khop_ma.py`.
- `main` is production. Open PRs against the feature branch, never merge your own (AGENTS.md §6.0).
- Opening a PR or issue: fill every field at creation (assignee, label, Issue Type, Priority, Effort, Project `Brain — Giao viec` + Status, reviewers, links). Type and fields need `gh api`; commands in AGENTS.md §5.4.
- You may fix metadata on the user's own PRs and issues (author or assignee) without asking; report each change (AGENTS.md §5.5).
- Most docs and identifiers are Vietnamese. Reply in the language the user writes in.
- Body is another repo. Only propose changes there (PR or issue), never merge them (AGENTS.md §1).
- Ask the owner before moving any secret into env or changing how secrets are managed (AGENTS.md R2b).
