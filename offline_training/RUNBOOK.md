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

```bash
# DeepSeek: cần DEEPSEEK_API_KEY trong Colab Secrets (đã có, dùng cho các script sinh dữ liệu).
python offline_training/benchmark_v3.py --model deepseek:deepseek-v4-pro \
    --no-gate --thu-lai-n8n --json deepseek.json --tho deepseek_tho.jsonl
```

Provider `deepseek:` viết theo tài liệu công khai của DeepSeek đọc ngày 17/11/2026, **chưa chạy trên API thật**. Ba điều cần biết trước khi tin con số của nó:

- JSON mode của DeepSeek chỉ đảm bảo JSON **hợp lệ**, không ép lược đồ. Lược đồ được đưa vào tin nhắn hệ thống bằng lời; `rang_buoc` ghi `json_object`. Model làm sai lược đồ thì bị chấm trượt; bên vLLM (grammar) và bên Claude (structured output) lỗi kiểu đó không xảy ra vì lược đồ được ép.
- Suy nghĩ BẬT mặc định bên DeepSeek và token suy nghĩ ăn vào `max_tokens`. Provider gửi `reasoning_effort=none`; đổi bằng `BENCH_DEEPSEEK_EFFORT`. Nếu cấu hình đó sai thì chốt chặn `smoke_test_guided` (câu hỏi 64 token) dừng phiên ngay từ đầu, không đo tiếp một phép đo hỏng.
- Tên model lấy từ tài liệu: `deepseek-flash` (rẻ hơn) và `deepseek-v4-pro`. Các trang tài liệu đó không còn nhắc `deepseek-chat` và `deepseek-reasoner`, tên mà vài script sinh dữ liệu trong `offline_training/` còn dùng; chưa kiểm API còn nhận chúng không.

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

---

## 7. Làm `anser-v5` (#91, chủ dự án chốt 19/11/2026)

**Vì sao.** `anser-v4` sửa bóc yêu cầu (62 lên 94/98) và diễn giải (14 lên 24/27, hết cắt cụt) nhưng làm hỏng n8n (33 xuống 22/34), thử lại không cứu được câu nào, và DeepSeek làm đúng cả 34: lỗi ở model. 8 trong 12 lỗi là nhánh "không" của IF nối tới một node `noOp` không tồn tại. Đo trên dữ liệu có thể kiểm: 36 workflow mẫu thật có 36 node IF, **tất cả là mệnh đề bảo vệ** (`Valid?`, `Authorized?` rồi `Trả 400`), 31 trong 36 có cả hai nhánh nối. Đề đo thì phần lớn là **bộ lọc nghiệp vụ** ("Có hàng nào dưới ngưỡng?", rồi dựng, rồi gửi) nơi kế hoạch không có bước nào cho nhánh "không". Dữ liệu chưa bao giờ dạy: *kế hoạch im lặng về nhánh không thì để nó trống*.

**Hai việc dữ liệu đã làm sẵn trong mã:**
1. `make_n8n_pairs.py --bo-loc N`: thêm N mẫu "bộ lọc nghiệp vụ" (`make_n8n_bo_loc.py`), 70% nhánh không **trống**, 30% nhánh không **có bước riêng** để model học phép đối chiếu hai chiều. Mẫu hoàn toàn hư cấu, qua `validate_workflow`, không dùng lại bước nào của bộ đo (assert, không phải cảnh báo). **Khuyến nghị N = 60**: 90 làm mẫu tổng hợp chiếm 75% số mẫu đúng khuôn runtime; liều này là một siêu tham số, ghi lại giá trị đã dùng.
2. `build_dataset_v3.py` tự **loại dòng `train_extraction` có nhãn rò** (nhãn `null` mà tin nhắn nhắc tới trường đó, như EX0034 và EX0110) và in danh sách.

Đã thử và bỏ: bỏ node lá khỏi workflow thật. 14 trong 15 node lá đó là `Respond 400`; dạy bỏ nó là dạy một webhook không trả lời khi bị từ chối.

### 7.0 Ba việc rẻ trước khi tốn giờ GPU

1. **Đọc 5 ca v4 chạm trần token** (`finish=length`, "Unterminated string"): dán lên #91 trường nào chứa chuỗi bị lặp. Nghi lỗ hở grammar (`parameters` và `connections` không giới hạn độ dài chuỗi); chưa kiểm. Nếu chuỗi lặp nằm ở một trường cụ thể thì có cách chặn không cần train.
2. **Chạy bộ dò nhãn rò trên dữ liệu thật** để có tỷ lệ: `python -m offline_training.ro_ri_truong_thieu --json ro_ri.json` (đọc `generated/train_extraction.jsonl` và `eval_extraction.jsonl`). Dán tỷ lệ theo trường. Số này là **cận dưới**.
3. **Chép danh sách 11 mẫu narration cắt giữa chữ** đã bỏ tay khi dựng v4 (mã hoặc cách nhận biết), để v5 bỏ cùng những mẫu đó. Chưa có luật máy cho việc này.

### 7.1 Dựng dữ liệu

```bash
export ANSER_GENERATED_DIR=/content/drive/.../generated_v5
# chép từ generated_v4: train_extraction, train_narration, train_agent (đã bỏ tay 11 mẫu narration như v4) và cả bốn eval_*.jsonl
python offline_training/make_n8n_pairs.py --bo-loc 60
python offline_training/build_dataset_v3.py          # in "loại N dòng trích xuất có nhãn rò"
python offline_training/preflight_check.py
```
Đọc `dataset_manifest.json`: `n8n_bo_loc` phải là 60. So `by_source` với v4: số `v2_report` không được phình lên (thêm mẫu v3 nâng trần 55% cho mẫu v2, nên một phần mẫu v2 bị trần giữ lại có thể được nạp).

### 7.2 Huấn luyện, gộp, lượng tử hoá

Cùng cấu hình v3 và v4 (Qwen3-8B, QLoRA r=32, lr 1e-4, 2 epoch, seq 8192, lô hiệu dụng 16, `liger-kernel==0.5.10` đã ghim ở #137): **chỉ dữ liệu đổi**. Ghi seed. Gộp và AWQ như v4. Ước tính 4-5 giờ Colab L4 (train khoảng 1,9, gộp và lượng tử hoá khoảng 0,5, đo khoảng 0,7, cộng cài đặt); không gọi API ngoài.

### 7.3 Đo (cùng điều kiện với bảng 18/11: cùng phiên, cùng bản vLLM, cùng commit)

Làm theo mục 6, thêm `anser-v5`. **Không chạy lại v3, v4 và DeepSeek** nếu bốn tập đo không đổi: dùng `v3.json`, `v4.json`, `deepseek.json` đã có. Hai câu đề đã biết là nhãn sai bỏ khi đọc, không sửa tệp:

```bash
cat > bo_ma.txt <<'EOT'
EX0034  # tin nhắn "ship về HP" có nơi đến nhưng nhãn destination là null
EX0110  # tin nhắn "giao nội thành HN" có nơi đến nhưng nhãn destination là null
EOT
python -m offline_training.bang_nhieu_lan_chay --lan v3=v3.json --lan v4=v4.json --lan v5=v5.json \
    --lan deepseek=deepseek.json --tham-chieu deepseek --sau-thu-lai --bo-ma-tep bo_ma.txt
```
Thêm vào `bo_ma.txt` mọi mã eval mà bộ dò gắn cờ **sau khi đọc nguyên văn từng dòng**, mỗi dòng một lý do.

### 7.4 Cổng nhận v5 (chủ dự án vẫn là người đổi model production)

1. **n8n:** v5 đạt ít nhất 32/34 **và** làm hỏng không quá 1 câu mà v3 làm đúng (so theo cặp). Nêu cả bảng lần đầu và bảng sau thử lại.
2. **Bóc yêu cầu và diễn giải:** không tệ hơn v4 theo hướng ngược (p dưới 0,05 cho chiều "v5 tệ hơn"); diễn giải 0 câu cắt cụt ở trần 2.048.
3. **Agentic:** không tệ hơn v3.
4. **Chi phí vận hành:** cùng 8 tỷ tham số, cùng AWQ 4-bit (R3, mục tiêu T0 khoảng 750.000đ/tháng).

### 7.5 Nếu n8n của v5 vẫn thua v3

Theo thứ tự rẻ đến đắt: (a) đọc 5 ca chạm trần (mục 7.0) và nếu là lỗ hở grammar thì chặn bằng giới hạn độ dài chuỗi, đo trước; (b) hai LoRA trên một model gốc (n8n dùng adapter v3 đóng băng; chưa xác minh LoRA trên nền AWQ); (c) train lại **cùng dữ liệu, seed khác** để tách phương sai huấn luyện khỏi hiệu ứng dữ liệu. Lý do của (c): v3 đo ra 25/34 trên vLLM 0.10.2 và 33/34 trên 0.11.2, tức một lần đo đã dao động cỡ 8 câu vì bản backend; một lần huấn luyện cũng có thể dao động như vậy. Đừng so v5 với bảng đo ở bản vLLM khác.

---

## 8. Chọn model thị giác cho L4 (#124, chủ dự án chốt 19/11/2026)

**Vì sao.** Mặc định hiện nay `Qwen3-VL-2B` chỉ đúng hết 3/28 ca: 18/18 ca sai tổng và 20 ca có lỗi lũy thừa của 10 (đọc `55.192.500` thành `55192`). Đáp án thật xác nhận (chấm lại bằng `vlm_hoadon.cham` khớp 28/28 với số của Thành): `Qwen2.5-VL-7B` (bf16) không có ca nào lệch lũy thừa của 10; `Qwen3-VL-4B` có 1 ca (VH0019).

### 8.1 Ba con số quyết định chọn gì (tính ngày 19/11/2026 từ API công khai của Hugging Face)

| Model | Trọng số | Ghi chú |
|---|---|---|
| `Qwen/Qwen2.5-VL-7B-Instruct-AWQ` | 6,45 GiB | bản bf16 là 15,45 GiB. Thẻ Qwen: DocVQA 94,9 xuống 94,6, MMMU 58,4 xuống 55,6 sau lượng tử hoá |
| `Qwen/Qwen3-VL-4B-Instruct-FP8` | 5,61 GiB | bản bf16 là 8,27 GiB. L4 là Ada (sm_89): FP8 W8A8 gốc; RTX 3090 (Ampere): W8A16 weight-only qua Marlin (tài liệu vLLM 0.11.2) |
| `5CD-AI/Vintern-1B-v3_5` | 3,5 GiB tệp (fp32), khoảng 1,8 GiB khi nạp bf16 | MIT; chuyên tiếng Việt (vi-MTVQA 41,9) nhưng DocVQA 78,8 thấp hơn bản gốc 84,8; **cần `trust_remote_code`**; thẻ không xác nhận vLLM |

Đồng host với server text (Qwen3-8B AWQ, 5,68 GiB) trên một GPU: `python offline_training/ke_hoach_vram.py` (đã hiểu ngữ cảnh cố định và overhead riêng cho server thị giác). Ngữ cảnh TỐI ĐA còn lại cho server text, vision `--max-model-len=8192`, và **overhead của vision là ĐOÁN (2,5 / 3,5 / 4,5 GiB), chưa đo**:

| | L4 22,5 GiB | RTX 3090 24 GiB |
|---|---|---|
| Qwen2.5-VL-7B AWQ | 20.480 / 12.288 / 6.144 | 30.720 / 22.528 / 16.384 |
| Qwen3-VL-4B FP8 | 20.480 / 14.336 / 8.192 | 32.768 / 24.576 / 18.432 |
| Qwen3-VL-4B bf16 | 4.096 / không vừa / không vừa | 12.288 / 6.144 / không vừa |
| Qwen2.5-VL-7B bf16, Qwen3-VL-8B FP8 | **không vừa** | **không vừa** |
| Vintern-1B | 32.768 | 32.768 |

Đo 18/11 chạy 0 lỗi 400 ở ngữ cảnh text 14.336; compose production đặt 32.768. Hai ứng viên lượng tử hoá đồng host được nhưng **sát trên L4**: con số then chốt là overhead thật của bộ mã hoá ảnh, chỉ biết khi chạy.

### 8.2 Thứ tự chạy (khoảng 2-2,5 giờ Colab L4)

Mỗi model **một mình trên GPU**, qua **vLLM server** (đường production), cùng bản vLLM và cùng commit, cùng 28 ảnh (`make_vlm_invoice_eval.py --n 28` với seed mặc định cho ra đúng bộ 28 ca của bảng 18/11).

| # | Model | Vai trò |
|---|---|---|
| 1 | `Qwen/Qwen2.5-VL-7B-Instruct-AWQ` | **ứng viên chính** |
| 2 | `Qwen/Qwen3-VL-4B-Instruct-FP8` | ứng viên phụ |
| 3 | `Qwen/Qwen2.5-VL-7B-Instruct` (bf16) | **đối chứng đường chạy**: 26/28 đo trong tiến trình bằng transformers; chạy qua server để tách "đổi đường" khỏi "lượng tử hoá" |
| 4 | `Qwen/Qwen3-VL-4B-Instruct` (bf16) | đối chứng như trên (18/28 trong tiến trình) |
| 5 | `5CD-AI/Vintern-1B-v3_5` | **tuỳ chọn**: nếu `vllm serve --trust-remote-code` không khởi động được sau 15 phút thì ghi lại lỗi và bỏ |

Không chạy: `Qwen3-VL-8B-FP8` và các bản bf16 ở cột đồng host (không vừa); `Qwen3-VL-2B` (đã loại bằng 3/28).

```bash
python offline_training/make_vlm_invoice_eval.py --n 28 --out /content/vlm_hoadon
T=q25vl7b_awq   # đổi theo từng model
vllm serve Qwen/Qwen2.5-VL-7B-Instruct-AWQ --served-model-name anser-vision --max-model-len 8192 \
    --gpu-memory-utilization 0.85 --limit-mm-per-prompt '{"image":2}' --port 8002 --disable-log-requests > vllm_$T.log 2>&1 &
until curl -sf localhost:8002/health; do sleep 5; done
nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -l 1 > vram_$T.csv &    # VRAM đỉnh = số lớn nhất trong tệp
ENV=LOCAL VLLM_VISION_BASE_URL=http://127.0.0.1:8002 VLLM_VISION_MODEL=anser-vision \
    python offline_training/do_vlm_hoa_don.py --dir /content/vlm_hoadon --json $T.json
```
Cờ `--disable-log-requests` ở lệnh trên đã bị đánh dấu lỗi thời ở vLLM 0.11.2 (đọc `vllm/utils/argparse_utils.py` và `vllm/engine/arg_utils.py` ở tag v0.11.2: bản này chỉ in cảnh báo, và ghi rõ "sẽ bị gỡ ở v0.12.0"). Mặc định vLLM không ghi request, nên bỏ cờ này khỏi lệnh đo thì không đổi gì. `deploy/docker-compose.yml` vẫn dùng nó vì lý do dữ liệu khách (P2) và đã ghim `v0.11.2`: **khi nâng vLLM lên 0.12 trở lên thì phải đổi cờ đó ở compose**, nếu không container không khởi động. Đây là suy ra từ mã nguồn, chưa chạy thử trên 0.12.

`ENV=LOCAL` là có chủ ý: có `VLLM_VISION_BASE_URL` thì vision đi qua server ở mọi ENV, còn tiến trình đo không nạp model nào (đã kiểm với một server giả, 19/11). Hết mỗi model thì tắt server (`kill %1`) và đợi `nvidia-smi` về gần 0 trước khi bật cái sau. Với Vintern thêm `--trust-remote-code --dtype bfloat16 --revision <mã commit đã đọc code>`: **đọc mã tuỳ chỉnh trong repo của nó trước khi chạy** (chạy mã từ xa), và chỉ trong Colab.

### 8.3 Đọc kết quả

```bash
python -m offline_training.phan_loai_loi_vlm --de /content/vlm_hoadon/eval_vlm_hoadon.jsonl \
    --ket-qua q25vl7b_awq.json --ket-qua q3vl4b_fp8.json --ket-qua q25vl7b_bf16_server.json --ket-qua q3vl4b_bf16_server.json --chan
python offline_training/so_sanh_vlm.py q25vl7b_bf16_server=q25vl7b_bf16_server.json q25vl7b_awq=q25vl7b_awq.json ...
```
`phan_loai_loi_vlm` chấm theo ĐÁP ÁN THẬT: lệch lũy thừa của 10 (`x10^k`), nhầm cột Thành tiền thành Đơn giá, điền 0 hoặc điền số vào trường đáp án null. Danh sách `LECH_LUY_THUA_10` là cổng R1: lỗi này lọt qua `validate_invoice_total` vì mọi số lệch cùng lúc.

Ca model bị cắt ở 1024 token (Brain PR #155) không còn ra số cụt: kết quả là `error` có chữ "cụt", và `phan_loai_loi_vlm` xếp nó vào `khong_doc_duoc`. Khi đọc bảng, đếm riêng số ca đó cho từng model (`grep -c cụt q25vl7b_awq.json`): đó là số đo tần suất cắt thật, chưa ai có. Model nào cụt nhiều thì đó là một lý do loại riêng, không nằm trong sáu cổng dưới đây.

### 8.4 Cổng nhận (ghi TRƯỚC khi đo, để khỏi cãi sau)

1. **`LECH_LUY_THUA_10` rỗng.** Bất kỳ ca nào lệch lũy thừa của 10 là loại, bất kể điểm tổng.
2. **Chính xác:** đúng hết ít nhất 22/28 và không tệ hơn mốc 3B theo hướng ngược (McNemar, `so_sanh_vlm.py`). Bản lượng tử hoá không tệ hơn bản bf16 của chính nó chạy qua server (đối chứng 3 và 4).
3. **Đồng host:** server text và server thị giác khởi động cùng lúc trên L4 (kế hoạch mục 8.5), ngữ cảnh text **ít nhất 14.336** và vision ít nhất 8.192, cả hai trả lời đồng thời 10 phút không OOM và không lỗi 400, VRAM đỉnh dưới 92%.
4. **Tốc độ:** p95 giây mỗi ảnh (in cuối `do_vlm_hoa_don.py`) không quá 30 giây qua server trên L4.
5. **Giấy phép:** đọc tệp `LICENSE` gốc của đúng model được chọn (mới đọc thẻ tag trên Hugging Face), và ghi lại.
6. **Chọn:** trong các model qua đủ năm cổng, chọn trọng số nhỏ hơn; ngang nhau thì chọn model có số ca đúng hết cao hơn.

**Chưa có luật cho trường hợp "không model nào qua"**: nếu vậy `Qwen2.5-VL-7B` bf16 (không đồng host được) cho thấy năng lực nhưng cần GPU thứ hai hoặc xử lý ảnh theo lô ngoài giờ cao điểm; chủ dự án quyết, không tự suy ra.

### 8.5 Thử đồng host thật (sau khi có kết quả 8.3, với ứng viên qua cổng 1 và 2)

```bash
huggingface-cli download <text AWQ> --local-dir /content/models/text
huggingface-cli download <ứng viên vision> --local-dir /content/models/vision
python offline_training/ke_hoach_vram.py --model /content/models/text --ten anser-v3 \
    --model /content/models/vision --ten anser-vision \
    --ctx-co-dinh anser-vision=8192 --overhead-rieng anser-vision=2.8 --ctx-can-thiet 4096
```
Bật hai server **lần lượt** theo lệnh in ra (text trước). Server vision báo thiếu bộ nhớ lúc khởi động thì tăng `--overhead-rieng anser-vision=3.5` rồi tính lại. Ghi overhead thật = (VRAM đỉnh đo bằng `nvidia-smi`) trừ trọng số trừ KV: số này thay cho con số đoán trong bảng 8.1. **Đo 20/11/2026 (#124):** overhead thật của text khoảng 1,64 GiB và của vision 7B AWQ khoảng 2,78 GiB; mặc định `--tran-tong` nay là 0,88 vì 0,92 đẩy `nvidia-smi` lên 92,2%, vượt cổng 92%.

**Hai chỗ cần sửa trong `deploy/docker-compose.yml` nếu chọn một trong hai ứng viên** (compose chưa từng được chạy): `--limit-mm-per-prompt=image=2` là cú pháp cũ, tài liệu vLLM 0.11.2 chỉ cho thấy dạng JSON `'{"image":2}'`; và `VISION_GPU_FRACTION=0.25` (5,6 GiB) quá nhỏ cho cả hai ứng viên (cần khoảng 0,44-0,47 theo bảng trên).


## 9. Chọn hướng sau v5: hai LoRA trên nền AWQ, hay hai server (#91, 20/11/2026)

Chủ dự án (20/11): "kiểm kĩ lại trên nền AWQ". Mục này ghi cái đã xác minh bằng ĐỌC NGUỒN (chưa chạy GPU) và phép kiểm rẻ nhất để quyết.

### 9.1 Đã xác minh từ nguồn (vLLM tag v0.11.2, Hugging Face, `train_v3.py`)

| Điều | Kết quả | Nguồn |
|---|---|---|
| Qwen3 hỗ trợ LoRA | Có: `Qwen3ForCausalLM(nn.Module, SupportsLoRA, ...)`, có `packed_modules_mapping` | `vllm/model_executor/models/qwen3.py` |
| LoRA chạy trên lớp tuyến tính lượng tử | Có, ở mức mã: lớp LoRA gọi `base_layer.quant_method.apply`, không riêng kiểu lượng tử nào; `awq_marlin.py` không có đoạn nào chặn LoRA | `vllm/lora/layers/base_linear.py`, `awq_marlin.py` |
| Có test upstream cho AWQ + LoRA | Có, nhưng chỉ TinyLlama-1.1B với `quantization="awq"` tường minh. **Không** có Qwen3, **không** có `awq_marlin` | `tests/lora/test_quant_model.py` |
| Hạng LoRA | `--max-lora-rank` mặc định **16**; adapter v3 và v5 train `LORA_R=32`. Quên cờ này thì server từ chối adapter | `vllm/config/lora.py`, `train_v3.py:58` |
| Nền AWQ có sẵn | `Qwen/Qwen3-8B-AWQ` (Apache-2.0, AWQ 4-bit, `group_size` 128, `version: gemm`) là AWQ của bản GỐC, không phải bản đã gộp | API Hugging Face |
| Adapter train trên nền nào | NF4 của bitsandbytes (`train_v3.py`, `BitsAndBytesConfig`), rồi production **gộp vào bf16 rồi mới AWQ** (`merge_and_quantize.py`) | mã |

**Điều chưa ai biết, và là điều quyết định:** adapter rời đặt lên nền AWQ-của-bản-gốc là một tổ hợp lượng tử hoá KHÁC cả lúc train (NF4) lẫn lúc production đang chạy (gộp rồi AWQ). Hai nền lệch nhau một nhiễu lượng tử; v3 đạt 33/34 ở dạng gộp rồi AWQ, và không có lý do để chắc adapter rời giữ được con số đó. Đọc nguồn không trả lời được câu này, chỉ chạy được.

**Brain cũng phải đổi:** `VLLMServerClient` chỉ có một `model` (`serving.py:666`, từ `VLLM_MODEL`) cho mọi lời gọi text. Hai LoRA nghĩa là chọn tên model theo tác vụ (n8n dùng adapter v3, còn lại dùng v5): một biến env tuỳ chọn cho nhánh n8n, mặc định bằng `VLLM_MODEL`, nhỏ và giữ R5. **Chưa làm**, vì chỉ có nghĩa khi phép kiểm dưới đây qua.

### 9.2 Phép kiểm rẻ nhất (Colab L4, khoảng 30 đến 40 phút, không train)

Bước 1, khởi động (cờ `--max-lora-rank 32` bắt buộc; thử với `--quantization awq` tường minh VÀ để vLLM tự chọn, vì để vLLM tự chọn có thể lên `awq_marlin` (suy ra từ cách vLLM nâng cấp kernel AWQ, mình chưa kiểm ở v0.11.2), tổ hợp upstream không test):

```bash
vllm serve Qwen/Qwen3-8B-AWQ --served-model-name base --enable-lora --max-lora-rank 32     --lora-modules v3=/content/drive/.../anser-v3-lora v5=/content/drive/.../anser-v5-lora     --max-model-len 14336 --gpu-memory-utilization 0.60 --port 8003
```

Qua bước 1 khi: server lên không lỗi, `GET /v1/models` liệt kê `base`, `v3`, `v5`. Lỗi ở đây (từ chối `awq_marlin`, hoặc hạng) là kết quả hợp lệ: ghi nguyên văn và dừng, hướng hai LoRA đóng.

Bước 2, chất lượng: chạy `benchmark_v3` nhánh n8n (34 câu, cùng cách như mục 6) với `--model v3` trên server này, và so theo cặp với `v3.json` đã có (bản gộp rồi AWQ, 33/34). **Qua** khi adapter v3 rời trên nền AWQ làm hỏng không quá 1 câu so với `v3.json`. Chạy tiếp nhánh bóc yêu cầu và diễn giải với `--model v5` để biết v5 rời có còn 91/95 và 26/27 không.

Bước 3 (không bắt buộc): VRAM và độ trễ lúc phục vụ hai adapter cùng lúc (`--max-loras 2`), p95 ms mỗi token so với server gộp.

### 9.3 Phương án không cần LoRA: hai server

Thành đã chạy v3, v4 và DeepSeek cạnh nhau trên một L4 (mục 6: `--max-model-len=14336 --gpu-memory-utilization=0.46`), nên hai server 8B AWQ trên cùng GPU là đường đã chạy được, không phải phỏng đoán. Brain gọi n8n vào server giữ v3, phần còn lại vào server giữ v5. Cái giá: trọng số 5,7 GiB mỗi bản, và ngữ cảnh mỗi server nhỏ hơn compose hiện nay (32.768); n8n và bóc yêu cầu không cần dài, nhưng phải đo cái nào cần. `python offline_training/ke_hoach_vram.py` tính trước. Cần cùng thay đổi nhỏ ở Brain (chọn địa chỉ và tên model theo tác vụ) và không có rủi ro chất lượng của bước 9.2.

**Khuyến nghị của agent (chủ dự án quyết):** chạy 9.2 bước 1 trước. Nó rẻ, và kết quả đóng hoặc mở cả hướng hai LoRA. Nếu bước 1 hay bước 2 trượt thì chọn 9.3, không cần train gì thêm.

## 10. Dữ liệu v6 (#91): hai họ rút từ ca hỏng thật của v5

`make_n8n_pairs.py --bo-loc 60 --v6 40` thêm hai họ mẫu từ `make_n8n_v6.py` (hư cấu, qua `validate_workflow`, không dùng lại bước nào của bộ đo, có test):

| Họ | Nhắm vào | Vì sao |
|---|---|---|
| C `tinh_roi_loc`: lấy, TÍNH, IF, dựng, gửi | `gia_canh_bao_bien_mong`, `no_bao_cao_tap_trung` (nhánh "không" nối tới `noOp` không có) | Cả hai đề có bước tính nằm giữa lấy dữ liệu và IF. Họ `bo_loc` của v5 luôn là lấy rồi IF ngay, nên model chưa thấy khuôn này |
| B `gui_tung`: bước có chữ "từng" là MỘT node | `no_doi_chieu_ncc` (trùng tên node) | n8n chạy mỗi node trên từng dòng dữ liệu, nên "gửi từng X" là một node; model sinh hai node cùng tên |

**Hai lỗi còn lại KHÔNG sửa bằng dữ liệu v6:** `hd_luu_tru_hoa_don` (model lặp trong chuỗi tự do của `parameters`: lỗ hở grammar, xem #91) và `gia_cap_nhat_bang_gia_khach` (nối tới `Trả 200` không có). Lỗi sau cần biết n8n làm gì khi nhánh thành công của webhook không có node Respond; chưa kiểm trên n8n thật, nên chưa có mẫu dạy (dạy một hành vi n8n chưa kiểm là dạy bừa). Việc kiểm giao Sơn (có instance n8n) ở #91.

**Liều và đo.** Cùng cấu hình v3, v4, v5, chỉ dữ liệu đổi; ghi `n8n_v6` trong `dataset_manifest.json`. Liều 40 là điểm xuất phát, không phải kết quả đo: `bo_loc` 60 cộng v6 40 là 100 mẫu hư cấu trong khoảng 1.230 mẫu train của v6 (v5: 1.188), nên theo dõi `by_source` như mục 7.1. Đo như mục 7.3 và nêu bảng so với v3, v4, v5 theo cặp.

**Chấm n8n từ 20/11/2026 có bước sửa liên kết `noOp`** (chủ dự án đồng ý): `/chat` bỏ liên kết tới node `noOp` không tồn tại trước khi kiểm (`workflow_schema.sua_lien_ket_noop`), và `benchmark_v3` chấm theo cách đó (cờ `--khong-sua-noop` tái tạo cách chấm cũ). Bảng v3, v4, v5 cũ chấm trước đó, nên **chấm lại đầu ra thô, không cần GPU**: `python offline_training/cham_lai_n8n.py v3_tho.jsonl v4_tho.jsonl v5_tho.jsonl`. Nó in cho mỗi file số câu hợp lệ theo cách cũ và cách mới, các câu được cứu, và các câu còn hỏng kèm lý do. Chỉ so v6 với v3, v4, v5 khi cả bốn cùng một cách chấm. Bộ đo chỉ đo cấu trúc, không đo workflow có đúng việc không.
