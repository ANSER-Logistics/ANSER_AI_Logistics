---
name: anser-verify
description: Run the ANSER Brain "definition of done" checks exactly as CI and pre-commit do (ruff, mypy, pytest ENV=LOCAL, dataset preflight, Body contract check), answer the four R1-R4 review questions, and scan the full git history for secrets before any push. Use before claiming a task is done, before opening a PR, or before pushing.
---

# ANSER verify

AGENTS.md §5.3 and §7: run the checks, paste the result, say plainly what failed. The commands below mirror [ci.yml](../../../.github/workflows/ci.yml) and [.pre-commit-config.yaml](../../../.pre-commit-config.yaml). If either file changes, update this skill in the same PR.

## 1. Checks (same scope as CI)

From the repo root. PowerShell: `$env:ENV='LOCAL'` instead of the `ENV=LOCAL` prefix.

```bash
ruff check src tests offline_training launch_demo.py execute_backup_and_push.py
mypy src offline_training
ENV=LOCAL pytest -q
```

Tools missing: `pip install -r requirements-dev.txt`, then `pip install -c requirements.txt fastapi httpx pydantic numpy json_repair sqlalchemy requests ddgs python-multipart openpyxl redis python-docx pypdf` (the CI install line). Do not install the full `requirements.txt` (torch/vllm are not needed in LOCAL). Pytest is about 2,500 tests, one to two minutes.

CI runs pytest with `KIEM_SKIP_DA_KHAI=1` and `-rs`: the number of skips in each file must match `SKIP_DA_KHAI` in `tests/conftest.py`, or the run fails (#29). A dev machine usually differs from CI (other packages, no Redis), so leave the variable unset locally unless your environment matches the CI install line.

Run these too when the change touches them:

| Change touches | Run |
|---|---|
| prompts, `workflow_schema.py`, n8n catalog, `offline_training/` | `ENV=LOCAL python offline_training/make_extraction_seeds.py --n 60 --n-eval 10 && python offline_training/make_n8n_pairs.py && python offline_training/build_dataset_v3.py && python offline_training/preflight_check.py` |
| `src/api/routes/tools.py` input schemas, before anything reaches `main` | `python offline_training/doi_chieu_hop_dong_body.py` (exit 1 = Body sends a field Brain rejects) |
| a function that returns different shapes on the "missing data" path | `python offline_training/soat_hinh_dang_tra_ve.py`, then answer the AGENTS.md R1 table for each hit |
| any `.md` file | `ENV=LOCAL pytest tests/contracts/test_tai_lieu_khop_ma.py -q` (every relative link must resolve; docs links go to `anser-brain-docs` as absolute URLs) |

Report: paste the pytest summary line and every failure. Never describe a red test as green.

## 2. Four review questions (AGENTS.md §5.2)

Answer each in one line for the diff:

1. **R1:** if the model returns garbage, does any ledger number go wrong? Every number comes from deterministic code (`pricing.py`, `mcp_server.py`, `reporting.py`, `inventory.py`, `receivables.py`, `vat_catalog.py`...). Missing data is reported as missing, never 0.
2. **R2:** does any payload carry customer data, and where does it go? Only the internal vLLM endpoint. `providers.py` `anthropic:` runs only on fully fictional eval sets.
3. **R3:** extra GPU/infra cost in VNĐ/month. An increase needs cost + metric + who pays.
4. **R4:** does this definition already exist? n8n format: `workflow_schema.py` only. Prompts: `prompts.py` only. DB schema: Brain keeps no copy (Body sends it). Secret patterns: `build_dataset_v3.SECRET_PATTERNS` only.

Also R5: no GPU names, VRAM numbers or `/content/drive/...` in `src/`; env var names must be the real ones in AGENTS.md R5.

Docs: if the PR changes a route, a `src/core/` module, an env var or documented behaviour, say so in the PR description and open the matching PR in `anser-brain-docs` (AGENTS.md §4.2).

## 3. Secrets

Staged files (same as the pre-commit hook): `python offline_training/quet_secret_pre_commit.py <files>`.

Before pushing to a new or public remote, scan the **whole history** (R2b). This reuses the repo's own `scan_secrets`, so there is no second copy of the patterns:

```bash
git log --all -p --format='@@COMMIT %h %ad %s' --date=short | python -c "
import io, sys
sys.path.insert(0, '.')
from offline_training.build_dataset_v3 import scan_secrets
commit, hits = '?', {}
for line in io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace'):
    if line.startswith('@@COMMIT '):
        commit = line[9:].strip()
    elif line[:1] in '+-' and not line.startswith(('+++', '---')) and scan_secrets(line):
        hits[commit] = hits.get(commit, 0) + 1
for c, n in hits.items():
    print(f'{n:3d}  {c}')
print('commits with hits:', len(hits))
"
```

Known benign (checked 20/11/2026, 15 commits; the 15/11 history rewrite gave some commits a second hash, so each appears twice): `174bcb9`, `56cc452` (the move of the docs to the private repo: lines that describe the patterns), `65dd3e3`, `d0ec94a`, `57a594c`, `9f38780`, `0764f90`, `615c398`, `a57c7c6`, `0a33c80` (docs tables and tests that quote the patterns or use placeholder fixtures such as `postgres://u:p@h`), `26be70f`, `659ec27`, `7855e62` (test fixtures) and `01aba0b` (removal of the already-rotated Neon password). Checked without printing any value: every hit is a pattern description (regex text) or a placeholder fixture, none has a real host. Any other commit: stop, do not push, tell the owner. A leaked credential is dead: rotate first, clean git second. Never move a secret into env or change secret handling without asking the owner.

## 4. Where the PR goes

`main` is production (AGENTS.md §6.0). Open PRs against the feature branch the team integrates into (currently `feat/workflow-format-and-deterministic-core`), never merge your own PR, never push to `main`. Fill every GitHub field when you open it (assignee, label, Priority, Effort, Project `Brain — Giao viec`, reviewers, linked issue, draft state; issues also Type), then read them back: AGENTS.md §5.4.
