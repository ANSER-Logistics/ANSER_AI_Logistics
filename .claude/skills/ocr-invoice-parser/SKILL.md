---
name: ocr-invoice-parser
description: LEGACY v1 guidance for reading invoice images with a vision model and returning JSON. Use only when touching invoice OCR; check AGENTS.md first, parts are outdated.
---

> ⚠️ **Lỗi thời một phần (v1, trước AGENTS.md v2).** `ENV=COLAB`, A100 80GB, Qwen2-VL-7B and `src/server.py` are v1. Real code: `src/api/routes/documents.py` (`ocr_endpoint`, `ocr_freight_endpoint`), `src/agents/vision.py` (`VISION_MODEL_ID`, default Qwen2.5-VL-3B), sanitizing in `src/core/sanitize.py`, freight invoice checks in `src/core/freight_invoice.py`.

# Skill: OCR Invoice Parser (Qwen2-VL)

## Goal
Process physical supplier invoices via Vision-Language Models (VLMs) and return structured JSON data for the Body team to ingest.

## Dual-Environment Execution Constraints (CRITICAL)
You must respect the environment toggle (`ENV=LOCAL` vs `ENV=COLAB`) to prevent local hardware crashes.
* **Local Mode (`ENV=LOCAL`):** The host Windows machine has a strict 6GB VRAM limit. Do NOT attempt to load `Qwen2-VL-7B-Instruct`. You MUST mock the vision processing step. When an image is received, instantly return a static, pre-defined dummy JSON payload that perfectly matches the expected output schema.
* **Colab Mode (`ENV=COLAB`):** The Colab A100 has 80GB VRAM. Safely load `Qwen2-VL-7B-Instruct` via HuggingFace Transformers.

## Execution Steps
1.  Receive the uploaded invoice image via the `src/server.py` `/upload` endpoint.
2.  Check the environment variable (`ENV`).
3.  **If LOCAL:** Bypass inference. Return the dummy JSON array (item name, quantity, unit price, and expiry date).
4.  **If COLAB:** Pass the image to Qwen2-VL. Explicitly request layout and context comprehension to extract structured data.
5.  **Sanitization:** Strip the output of any potential prompt-injection text or system overrides before parsing.
6.  Format the output strictly as JSON, pass it through `json_repair`, and return the HTTP response.

## Verification
* Does the local mock data perfectly match the schema of the actual Colab model output?
* Are all file paths handling the image upload built with `pathlib`?
