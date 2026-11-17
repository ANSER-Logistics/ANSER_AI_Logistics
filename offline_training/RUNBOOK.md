# RUNBOOK — chạy fine-tune v3 trên Colab

Tài liệu tra cứu đi kèm [`ANSER_train_v3_colab.ipynb`](ANSER_train_v3_colab.ipynb).
Notebook để **chạy**; file này để **tra khi có sự cố** và để **đọc kết quả**.

---

## 0. Trước khi mở Colab

| Việc | Ai làm | Ghi chú |
|---|---|---|
| Thêm `DEEPSEEK_API_KEY` vào Colab Secrets | Bạn | 🔑 bên trái Colab → *Add new secret* → bật *Notebook access*. **Không dán vào notebook** (R2b) |
| Dọn Drive còn ≥ 8GB trống | Bạn | Cell 1.4 in dung lượng từng thư mục; xoá được: `_backups` (234MB), `anser-qwen-lora`, `anser-qwen-distill-awq` (model **v1**) |
| Chọn runtime **L4 GPU** | Bạn | *Runtime → Change runtime type* |

Không cần token GitHub: notebook lấy mã **thẳng từ Drive**.

### Sơ đồ thư mục trên Drive

```
MyDrive/
├─ ANSER_AI_Logistics/          ← thư mục bạn đã đẩy lên
│  ├─ AI_ANSER/                 ← mã nguồn (notebook đọc từ đây)
│  ├─ generated/                ← dữ liệu sinh (notebook TỰ TẠO, giữ qua các phiên)
│  ├─ anser-v3-lora/            ← LoRA sau khi train
│  ├─ anser-v3-awq/             ← model cuối, trỏ TEXT_MODEL_ID vào đây
│  └─ *_report.txt              ← báo cáo benchmark
└─ ANSER_data/                  ← có sẵn từ trước (model v1/v2)
```

**Mã nguồn được chép sang `/content` để chạy**, không chạy thẳng trên Drive:
Drive gắn qua FUSE, mỗi thao tác file mất hàng chục ms — import vài trăm file và
ghi checkpoint sẽ chậm tới mức không dùng được. Mọi thứ **cần giữ** (dữ liệu
sinh, model, báo cáo) vẫn ghi thẳng ra Drive.

**Sửa mã nguồn thì làm ở máy bạn rồi đẩy lại lên Drive**, chạy lại cell 1.2 là
bản mới được chép sang. Sửa trực tiếp trong `/content` sẽ mất khi hết phiên.

Chi phí: DeepSeek **< 1 USD** cho toàn bộ bước sinh dữ liệu. Colab Pro tính theo
giờ GPU — cả quy trình khoảng **3–4 giờ**.

---

## 1. Thứ tự chạy

```
Giai đoạn 1  cài đặt → sinh dữ liệu → preflight        (~25 phút)
Giai đoạn 2  train → gộp LoRA → lượng tử hoá AWQ       (~2-3 giờ)
             ⚠ RESTART RUNTIME
Giai đoạn 3  benchmark baseline + benchmark model mới  (~40 phút)
```

**Không bỏ qua preflight.** Nó bắt các lỗi mà nếu để lọt sẽ chỉ lộ ra sau 2 giờ
train: thiếu file, nhãn sai schema, prompt trong data lệch runtime, hết chỗ Drive.

Mọi bước sinh dữ liệu đều **resume**: đứt mạng giữa chừng thì chạy lại đúng cell
đó, nó bỏ qua phần đã xong.

---

## 2. Đọc kết quả benchmark

Đọc theo đúng thứ tự này — trên xuống dưới là từ quan trọng nhất:

### 2.1 `sẵn sàng báo giá` (ready_rate)

Tỷ lệ tin nhắn khách gửi mà model trích xuất đủ **3 trường bắt buộc**
(điểm lấy, điểm giao, loại xe) → ra được báo giá **không cần hỏi lại**.

Đây là chỉ số sát nghiệp vụ nhất: chủ DN đang lái xe, mỗi lần phải hỏi lại là
một lần quy trình đứt.

### 2.2 `câu nối tiếp` vs `câu một lượt`

Nếu câu nối tiếp thấp hơn hẳn → **hội thoại nhiều lượt chưa dùng được**, dù
điểm chung có đẹp. "Thế xe 3 tấn thì sao?" sẽ hỏi lại tuyến đường — đúng thứ
làm khách khó chịu nhất.

### 2.3 `false_fill` — lỗi nguy hiểm nhất

Model **đoán bừa** một trường mà tin nhắn không hề nêu. Tệ hơn `miss` (bỏ sót)
nhiều lần:

- `miss` → hệ thống hỏi lại → phiền nhưng **an toàn**
- `false_fill` → hệ thống tạo báo giá **sai tuyến trong im lặng** → gửi khách sai giá

Chỉ số này cao thì **không được đưa vào chạy thật**, kể cả khi ready_rate đẹp.

### 2.4 `n8n hợp lệ`

Dưới 90% thì nhánh "khách tự tạo quy trình" chưa giao được.

### 2.5 So với baseline

Luôn đọc kèm baseline. Ví dụ:

| Trường hợp | Ý nghĩa |
|---|---|
| baseline 45% → tuned 88% | Fine-tune có tác dụng rõ. Dùng model mới |
| baseline 84% → tuned 88% | Cải thiện nhỏ. Cân nhắc dùng thẳng model gốc, dành tiền cho hạ tầng — guided decoding đã gánh phần lớn |
| baseline 84% → tuned 71% | **Overfit hoặc data hỏng.** Xem mục 4 |

---

## 3. Bảng sự cố

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `CUDA out of memory` khi train | seq 8192 + mẫu dài | Đặt `MAX_SEQ_LEN=4096` rồi chạy lại cell 2.1. Preflight có cảnh báo trước nếu nhiều mẫu vượt ngân sách |
| `pip install autoawq` xung đột version | autoawq đòi `transformers` khác bản train | *Runtime → Restart*, chạy lại cell 1.2, rồi chạy thẳng cell 2.4 (không cài lại thư viện train) |
| autoawq không hỗ trợ kiến trúc Qwen3 | Bản autoawq cũ | Dùng `llm-compressor` (định dạng compressed-tensors). Khi đó **bỏ** `quantization="awq"` trong `config.py` để vLLM tự nhận |
| `Thiếu train_v3.jsonl` | Chưa chạy cell 1.6e | Chạy `build_dataset_v3.py` |
| Preflight báo `Chỉ N mẫu train` với N nhỏ | Chưa chạy 1.6b/1.6c (thiếu API key) | Kiểm tra cell 1.5 in ra `✓ Đã nạp DEEPSEEK_API_KEY` |
| Preflight báo `Catalog node ĐÃ ĐỔI` | `N8N_TEMPLATES_DIR` khác lúc dựng dataset | Chạy lại `build_dataset_v3.py`. **Không bỏ qua**: `CODER_SYSTEM` dựng từ catalog, lệch là model học prompt không tồn tại lúc serve |
| Preflight báo có secret | Dữ liệu nguồn dính credential | **Dừng.** Không train, không đẩy lên Drive. Gỡ secret khỏi nguồn rồi dựng lại |
| Mất phiên Colab giữa chừng | Colab ngắt do idle | Dữ liệu sinh nằm trên Drive nên **không mất tiền API**. LoRA đã sao lưu ở cell 2.2 → chạy lại từ 2.3. Nếu mất trước 2.2 thì phải train lại |
| Benchmark thoát mã 1 | Dưới ngưỡng | Xem mục 4 |
| `Không tìm thấy repo trong Drive` | Thư mục đẩy lên thiếu `offline_training/` hoặc `src/` | Kiểm tra trên Drive có đủ hai thư mục đó không. Cell tự quét theo file mốc nên đổi tên thư mục vẫn chạy |
| Sửa code mà Colab vẫn chạy bản cũ | Đang chạy bản chép ở `/content` | Đẩy bản mới lên Drive → chạy lại cell 1.2 |

---

## 4. Điểm dưới ngưỡng — chỉnh gì

| Chỉ số kém | Chỉnh |
|---|---|
| `false_fill` cao | Tăng tỷ lệ seed thiếu trường: sửa `MISSING_PATTERNS` trong [`make_extraction_seeds.py`](make_extraction_seeds.py), sinh lại dữ liệu |
| Câu nối tiếp kém | Tăng `FOLLOWUP_RATIO` (mặc định 0.25) trong cùng file |
| `pickup_date` sai nhiều | Kiểm tra tỷ lệ cụm ngày mơ hồ; `AMBIGUOUS_DATE_PHRASES` nên chiếm ~15% |
| n8n hợp lệ thấp | Đối chiếu vân tay catalog (preflight mục 3). Nếu khớp mà vẫn thấp: tăng số mẫu n8n bằng cách nới `MAX_NODES` trong [`make_n8n_pairs.py`](make_n8n_pairs.py) |
| Narration bịa số | Chốt chặn đã lọc lúc sinh data; điểm thấp ở benchmark nghĩa là model **học được thói quen bịa từ nguồn khác** — giảm tỷ lệ `v2_report` (`V2_MAX_SHARE`) |
| Mọi chỉ số kém hơn baseline | Overfit: `EPOCHS=1` hoặc `LORA_R=16` |

---

## 5. Sau khi xong

```bash
# Trên máy chạy Brain (KHÔNG phải Colab — xem ARCHITECTURE §4.4)
export TEXT_MODEL_ID=/đường/dẫn/anser-v3-awq
```

`config.py` đọc biến này; `vllm_config` đã đặt sẵn `quantization="awq"`.

**Colab tuyệt đối không phục vụ traffic thật** — điều khoản Colab cấm dùng làm
web service. Colab chỉ để train / quantize / đo.

### Giữ lại để so sánh lần sau

Cell 3.4 sao lưu `baseline_report.txt` và `tuned_report.txt` lên Drive. Lần
train sau, so với hai file này để biết thay đổi có thật sự cải thiện không —
đây chính là điều mà bug #6 (`ai_metrics_log`) sinh ra để giải quyết.

---

## 6. So hai model trên cùng bộ đề, kèm mốc tham chiếu mạnh (#91)

Việc này trả lời đúng một câu: **v4 hỏng n8n vì model, hay vì cách đo?** Ba điều làm cho phép đo thỏa đáng:

1. **Cùng điều kiện.** Hai model chạy trong CÙNG phiên Colab, cùng bản vLLM, cùng commit, trên CÙNG bốn tập đo. Hai bảng ở hai ngày khác nhau không so chéo được: v3 n8n ra 25/34 ngày 16/11 (vLLM 0.10.2) và 33/34 ngày 17/11 (0.11.2).
2. **Cùng đường với production.** Chạy qua server vLLM (`openai:` trong `providers.py`, dựng body bằng chính `ChatRequest.to_payload`), không qua `vllm.LLM` trong tiến trình. Production gọi qua server, nên đo đúng đường đó bớt một biến. Chưa ai kiểm hai đường cho kết quả giống hệt nhau trên bốn tập đo; hai bảng 16/11 và 17/11 đều đo qua `vllm.LLM`.
3. **Có mốc tham chiếu.** Một model mạnh (Claude, DeepSeek) chạy trên cùng bộ đề cho biết câu nào bộ đề làm được. Câu mà MỌI bản đều sai là câu nghi đề bài, không phải model.

### 6.1 Chia VRAM trước khi bật server (không tốn GPU)

Chép cờ production (`--max-model-len=32768`, `--gpu-memory-utilization=0.62`) cho hai server là hết bộ nhớ ngay lúc server thứ hai khởi động. Tính trước:

```bash
python offline_training/ke_hoach_vram.py \
    --model /content/drive/.../anser-v3-awq --ten anser-v3 \
    --model /content/drive/.../anser-v4-awq --ten anser-v4
```

Công cụ đọc trọng số và KV cache từ file model, hỏi `nvidia-smi` dung lượng GPU, rồi in hai lệnh `vllm serve` (đúng cờ của `deploy/docker-compose.yml`) với `--max-model-len` lớn nhất còn vừa. Không vừa thì **từ chối**; khi đó chạy lần lượt từng model trong cùng phiên (mục 6.4) vẫn đạt điều kiện 1 và 2.

Hạ `--max-model-len` không đổi đầu ra, miễn mọi prompt cộng phần sinh ngắn hơn nó. Prompt dài hơn thì vLLM trả 400 và benchmark nổ rõ ràng. Hai con số overhead trong kế hoạch là **ước tính chưa đo**: nếu server báo thiếu bộ nhớ cho KV cache lúc khởi động, thêm `--overhead-gib 3.5` rồi tính lại.

### 6.2 Bật hai server, rồi đo song song

Bật LẦN LƯỢT (đợi server trước lên `/health` rồi mới bật server sau). Sau đó, ở hai ô lệnh riêng hoặc dùng `&`:

```bash
export ANSER_GENERATED_DIR=/content/drive/.../generated

python offline_training/benchmark_v3.py --model 'openai:http://127.0.0.1:8001/v1#anser-v3' \
    --no-gate --thu-lai-n8n --json v3.json --tho v3_tho.jsonl  > v3.log 2>&1 &
python offline_training/benchmark_v3.py --model 'openai:http://127.0.0.1:8002/v1#anser-v4' \
    --no-gate --thu-lai-n8n --json v4.json --tho v4_tho.jsonl  > v4.log 2>&1 &
wait
```

`--thu-lai-n8n` đo thêm n8n **sau một lần thử lại** như `/chat` (PR #138). Một GPU chia hai thì từng lần chạy chậm hơn, và tổng thời gian không ngắn hơn chạy lần lượt: lợi ích của "song song" là cùng điều kiện, không phải nhanh hơn.

### 6.3 Mốc tham chiếu từ model mạnh (API ngoài)

**R2.** Chỉ chạy trên bốn tập `generated/eval_*.jsonl` (kịch bản hoàn toàn hư cấu). Không chạy trên dữ liệu khách, kể cả bản đã ẩn danh. Chủ dự án cho phép gọi Claude và DeepSeek cho việc này (17/11/2026). Khoá API đọc từ biến môi trường (Colab Secrets), không ghi vào dòng lệnh hay file.

```bash
# Claude: provider có sẵn. Cần ANTHROPIC_API_KEY trong Colab Secrets.
python offline_training/benchmark_v3.py --model anthropic:claude-opus-5-5 \
    --no-gate --thu-lai-n8n --json claude.json --tho claude_tho.jsonl
```

Ràng buộc JSON của API ngoài khác grammar của vLLM (`rang_buoc` ghi trong file JSON, và `compare_runs` / `bang_nhieu_lan_chay` cảnh báo khi hai lần chạy lệch nhau). Vì vậy điểm của mốc tham chiếu là **cận để biết bộ đề có làm được**, không so ngang với model local như hai bản cùng cơ chế.

### 6.4 Chạy lần lượt (khi hai server không vừa GPU)

Cùng phiên, cùng commit, tắt server trước rồi mới bật server sau:

```bash
vllm serve .../anser-v3-awq --served-model-name=anser-v3 --max-model-len=32768 --gpu-memory-utilization=0.62 --port=8001 &
# đợi /health, chạy benchmark cho v3 như 6.2, rồi: kill %1 ; đợi GPU trống (nvidia-smi) ; bật v4 tương tự.
```

### 6.5 Đọc kết quả

```bash
python -m offline_training.bang_nhieu_lan_chay \
    --lan v3=v3.json --lan v4=v4.json --lan claude=claude.json \
    --tham-chieu claude --sau-thu-lai
```

Bảng cho từng nhánh: điểm có khoảng Wilson, rồi ba danh sách câu.

| Danh sách | Nghĩa | Làm gì |
|---|---|---|
| Mọi lần chạy đều **sai** | Nghi **đề bài** hoặc bộ kiểm | Đọc nguyên văn câu đó trong `*_tho.jsonl` trước khi kết tội model |
| Mốc đúng, mọi bản local sai | Khoảng cách thật của model | Ứng viên cho dữ liệu huấn luyện (v5) |
| Có bản local đúng, mốc sai | Ca lạ | Soát ràng buộc JSON hai bên |

Dòng "**v4 so với v3: LÀM HỎNG**" kèm "mốc tham chiếu làm được x/y" cho biết trong các câu v4 làm hỏng, bao nhiêu câu là câu làm được (lỗi của model) và bao nhiêu là câu cả Claude cũng sai (nghi đề bài). `--sau-thu-lai` chuyển nhánh n8n sang kết quả sau thử lại cho lần chạy có mục đó; lần chạy không có thì bảng nói thẳng là đang dùng lần đầu. Phép đo này không thay cổng của `benchmark_v3` và không đổi model đang chạy.
