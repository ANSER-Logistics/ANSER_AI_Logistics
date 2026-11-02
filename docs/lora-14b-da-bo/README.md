# LoRA 14B — nhánh đã bỏ

Đây là cấu hình LoRA của bản fine-tune **cũ**, dựng trên
`unsloth/qwen2.5-coder-14b-instruct-bnb-4bit`.

**Nhánh này đã bỏ.** AGENTS.md v2.0 ghi rõ giả định Qwen2.5-Coder không còn
đúng; dự án hiện chạy Qwen3-8B (pipeline v3, `offline_training/`).

## Vì sao vẫn giữ file này

`_backups/` (226MB, ba bản sao giống hệt nhau từng byte, không đụng tới từ
27/07/2026) đã xoá ngày 03/11/2026. Đối chiếu từng file cho thấy mọi thứ
trong đó đều lấy lại được từ git hoặc tải lại được từ HuggingFace — **trừ**
`adapter_config.json` này. Nó là bản ghi duy nhất về cách siêu tham số của
lần train đó được đặt.

Những file khác trong `adapters_backup/` không giữ:

- `tokenizer.json`, `vocab.json`, `merges.txt`, `added_tokens.json`,
  `special_tokens_map.json`, `tokenizer_config.json`, `chat_template.jinja`
  — tokenizer chuẩn của Qwen, tải lại từ HuggingFace.
- `README.md` — model card template tự sinh, chưa ai điền chữ nào.
- **Không có `adapter_model.safetensors`.** Trọng số thật chưa bao giờ nằm
  trong bản sao này, nên không có gì để khôi phục kể cả khi muốn.

## Siêu tham số đáng nhớ

`r = 16`, `lora_alpha = 16`, `lora_dropout = 0`, `use_rslora = false`,
7 module đích: `q_proj` `k_proj` `v_proj` `o_proj` `gate_proj` `up_proj`
`down_proj` (tức phủ cả attention lẫn MLP).

Dùng làm mốc so sánh nếu cần đặt lại siêu tham số cho bản train Qwen3-8B.
