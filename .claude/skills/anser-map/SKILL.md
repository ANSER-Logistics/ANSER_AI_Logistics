---
name: anser-map
description: Where things live in the ANSER Brain repo and how to find them cheaply. Query the graphify knowledge graph before grepping or reading whole files; lists the real module for each concern (pricing, carrier choice, VAT, inventory, receivables, reporting, tool planner, n8n format, prompts, VLM sanitizing, serving, training) and which places are stale. Use before exploring, locating code, or tracing a flow in this repo.
user-invocable: false
---

# ANSER map

## 1. Ask the graph first (saves tokens)

If `graphify-out/graph.json` exists (gitignored, local), query it before broad Grep/Read:

```bash
graphify query "how is a freight quote computed" --budget 1500   # BFS, broad context
graphify query "<question>" --dfs                                # trace one path
graphify explain "compute_quote"                                 # one node + neighbours
graphify path "ManagerAgent" "plan_tools"                        # shortest link
```

Then read only the files and line ranges it returns (`src=... loc=L...`). Overview: `graphify-out/GRAPH_REPORT.md`. No graph yet: `/graphify .`. After code changes: `graphify update .` (AST only, no LLM, free).

`.graphifyignore` excludes `src/data/` (uploads, possible customer data, R2). Never send it to an extractor or external LLM.

## 2. Docs live elsewhere

Architecture, SRS, onboarding and roadmap are in the **private** repo `ANSER-Logistics/anser-brain-docs` (since 15/11/2026). This repo keeps only `AGENTS.md`, `.agents/` and per-folder `README.md`. Link to docs with absolute URLs; `tests/test_tai_lieu_khop_ma.py` fails on any broken relative link in a `.md`.

## 3. Module map (feature branch, verified 16/11/2026)

Deterministic core (`src/core/`, pure code, no LLM, R1):

| Concern | Module → main entry points |
|---|---|
| Freight quote | `pricing.py` → `compute_quote()`, `PricingRule`, `Surcharge`, fuel-price age thresholds |
| Carrier choice | `carrier_selection.py` → `select_carrier()`, `QuoteOffer`, `RouteRequest` |
| Calibrate against past quotes | `calibration.py` → `replay_pricing()`, `fit_pricing_rule()`, `fit_carrier_weights()` |
| VAT / invoice totals | `mcp_server.py` → `MCPServer.calculate_vat()`, `validate_invoice_total()`; 8% vs 10% rate: `vat_catalog.py` |
| Freight invoice check | `freight_invoice.py` → `FreightInvoice`, `verify()` |
| Inventory audit, COGS | `inventory.py` → `audit_inventory()`, `fill_missing_cogs()`; import: `inventory_import.py` |
| Receivables / payables | `receivables.py` → `audit_partners()`; partner import (MISA): `partner_import.py` |
| Revenue/cost/profit | `reporting.py` → `build_report()`, `product_profitability()` |
| Retroactive edits between two exports | `period_diff.py` → `doi_chieu_hai_lan_xuat()` |
| Forecast / reorder | `forecasting.py` → `forecast_demand()`, `croston()`, `reorder_point()` |
| Tax ID check | `tax_id.py` → `kiem_ma_so_thue()` |
| Numbers grounding guard | `grounding.py` → `narration_numbers_ok()`, `customer_leak()` |
| Tool inputs read from the user's sentence | `doc_dau_vao.py` (amounts like "3tr5", tax rate) |
| **Which tool runs** | `tool_planner.py` → `plan_tools()`, rule-based, the model does not choose. Backtest: `offline_training/do_nghiep_vu.py`, `tests/test_nghiep_vu_backtest.py` |
| **VLM output sanitizing** | `sanitize.py` → `lam_sach_chuoi()`, `lam_sach_cay()`, patterns in `_MAU_CHI_DAN` |
| Shared finding shape | `findings.py` → `finding()` |

Serving and agents:

| Concern | Where |
|---|---|
| HTTP tools | `src/api/routes/tools.py` (`_ToolIn` has `extra="forbid"`) |
| Chat entry | `src/api/routes/chat.py` → `chat_endpoint()` |
| Upload / OCR (sales + freight invoice) | `src/api/routes/documents.py` |
| Knowledge base (RAG) | `src/core/knowledge.py`, `chunking.py`, `retrieval_policy.py`; routes in `src/api/routes/knowledge.py` |
| Routing | `src/agents/manager.py` → `SemanticRouter`, `ManagerAgent` |
| Agentic loop | `src/agents/agentic.py` → `AgenticLoop`, `build_decision_schema()` (`anyOf`, not `oneOf`) |
| Backend choice | `src/core/engine.py` → `chon_backend()`, `ModelEngine` |
| vLLM client + backpressure | `src/core/serving.py` |
| Blocking work off the event loop | `src/api/chay_ngoai_loop.py` → `chay_ngoai_loop()`, `chay_tren_kho()` |
| n8n format (single source) | `src/core/workflow_schema.py` |
| Prompts (single source) | `src/core/prompts.py` → class `Prompts` |
| Metrics | `src/core/metrics.py`; p95 latency: `nguong_p95.py` |

Most connected in the graph: `audit_inventory`, `InventoryLine`, `Prompts`, `ModelEngine`, `audit_partners`, `select_carrier`, `compute_quote`. A change there ripples widely; check callers with `graphify explain`.

## 4. Coupling to remember

- `prompts.py` or `workflow_schema.py` change → training data can go stale → dataset preflight (`/anser-verify`).
- Training builders import runtime code (`render_tools`, `Prompts`, `QuoteExtraction`) on purpose so train = serve. Never copy them into `offline_training/`.
- `tools.py` input schemas are a contract with Body → `offline_training/doi_chieu_hop_dong_body.py`.

## 5. Stale or legacy

- `.agents/`: v1 setup (Gemini team, `ENV=COLAB`, A100, Qwen2-VL-7B). Kept in the repo but superseded by AGENTS.md v2.
- `src/archive/`, `src/evaluate_system.py`, `Prompts.DB_SCHEMA`, `offline_training/db_schema.txt`: deleted. Do not recreate.
- `Prompts.INVOICE_SYSTEM`: declared, never referenced (AGENTS.md R4).
- `reconciliation.py` does not exist yet (S5).
