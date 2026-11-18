---
name: webhook-dispatcher
description: LEGACY v1 guidance for pushing results to another service with httpx.AsyncClient and retries. Use only when adding an outbound webhook; check AGENTS.md first, parts are outdated.
---

> ⚠️ **Lỗi thời một phần (v1, trước AGENTS.md v2).** `BODY_WEBHOOK_SECRET` and pushing back to Body do not exist in the code. The real outbound webhook goes to n8n: `N8N_QUOTE_WEBHOOK_URL` with retry in `src/api/routes/chat.py`.

# Skill: Webhook Dispatcher

## Goal
Enable the Brain to proactively push completed AI inference results back to the Body module via secure asynchronous HTTP POST requests.

## Execution Requirements
1.  **Library:** Use the asynchronous `httpx` library (`httpx.AsyncClient`). Do not use the synchronous `requests` library.
2.  **Payload Wrapper:** Wrap the final `json_repair`-validated output in a standard JSON envelope containing the original `job_id` and a `timestamp`.
3.  **Security Header:** Always inject the internal API key (loaded via `os.getenv("BODY_WEBHOOK_SECRET")`) into the headers of the outgoing request.
4.  **Retry Logic:** Implement an exponential backoff retry mechanism (max 3 retries) in case the Hostinger VPS is temporarily unreachable.
5.  **Non-Blocking:** This dispatch must happen at the very end of a Background Task and must never block the primary event loop.

## Verification
* Is `httpx.AsyncClient` used inside an `async with` block?
* Are failed webhooks gracefully logged rather than crashing the Colab runtime?
