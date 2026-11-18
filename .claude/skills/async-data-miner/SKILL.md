---
name: async-data-miner
description: LEGACY v1 guidance for parallel web scraping (asyncio.gather + Semaphore) in offline data generation. Use only when writing an offline_training/ scraper; check AGENTS.md first, parts are outdated.
---

> ⚠️ **Lỗi thời một phần (v1, trước AGENTS.md v2).** `ENV=COLAB` batch rules and `merge_datasets.py` are v1. Real examples: `offline_training/legal_miner.py`, `day1_test_batch.py` (Semaphore). Scraping is allowed only for public sources (R2).

# Skill: Async Data Miner (Tavily/Firecrawl)

## Goal
Perform high-speed, parallelized web scraping and unstructured data extraction for the offline Teacher-Student Distillation pipeline.

## Execution Requirements
1.  **Concurrency:** Utilize `asyncio.gather()` to process multiple URLs or Tavily search queries simultaneously.
2.  **Rate Limiting:** Implement a local semaphore (e.g., `asyncio.Semaphore(5)`) to prevent rate-limiting bans from external APIs like DeepSeek or Firecrawl.
3.  **Dual-Environment Safety:** If `ENV=LOCAL`, strictly limit the batch size to a maximum of 2 URLs to prevent local memory exhaustion. If `ENV=COLAB`, allow batch sizes up to 50.
4.  **Format Export:** Save all aggregated, cleaned text into a `.jsonl` file formatted specifically for ChatML ingestion (`merge_datasets.py`).

## Verification
* Is a semaphore correctly implemented to throttle API calls?
* Does the batch size respect the `ENV` toggle?
