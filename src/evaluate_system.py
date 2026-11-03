"""
src/evaluate_system.py — ĐÃ BỊ THAY THẾ. Chặn chạy từ 04/11/2026.

Dùng `offline_training/benchmark_v3.py` thay cho file này.

VÌ SAO CHẶN
-----------
File này vẫn chạy được, và đó mới là vấn đề: nó sinh ra những con số trông như
kết quả đo nhưng không đo thứ mà dự án đang làm. Bốn điểm, soát 04/11/2026:

1. ĐO SAI ĐỊNH DẠNG (R4). Prompt chấm điểm của judge viết nguyên văn: "grade an
   AI-generated **Make.com** JSON workflow against a Ground Truth blueprint."
   Nhưng R4 chốt "Định dạng workflow duy nhất: n8n. Make.com và engine nội bộ
   Body không phải đích sinh code." Tức nó chấm đầu ra n8n bằng thước Make.com.
   Mọi điểm số nó đưa ra đều vô nghĩa — và vô nghĩa theo kiểu nhìn vẫn có vẻ
   hợp lý, loại tệ nhất.

2. DỮ LIỆU TIỀN-v3. Nó đọc `src/data/training_dataset.jsonl` — bản 27/07/2026,
   trước pipeline v3. Ground truth trong đó cũng thuộc thời Make.com.

3. DÁN NHÃN PHẦN CỨNG SAI (R5). Báo cáo in "⚡ Hardware Efficiency (A100)" bất
   kể chạy trên gì. AGENTS.md v2.0 mở đầu bằng việc tuyên bố giả định A100 80GB
   "không còn đúng". Một con số độ trễ dán nhãn A100 mời gọi so sánh sai.

4. RỦI RO R2 KHÔNG CÓ RÀO. Nó gửi prompt + ground truth + đầu ra model tới
   DeepSeek API. AGENTS.md §R2 ghi "Chỉ được chạy trên dữ liệu tổng hợp/mẫu,
   tuyệt đối không trên dữ liệu khách thật" — nhưng câu đó chỉ nằm trong tài
   liệu, không có gì trong chính file này nói ra, và không có gì chặn.

Thêm vào đó, nó tuyên bố "🟢 STATUS: PRODUCTION READY" dựa trên điểm của một
LLM judge. Một model chấm điểm không phải là quyết định phát hành.

`benchmark_v3.py` thay thế cả bốn: đo đúng ba việc model làm trong kiến trúc
mới (extraction / n8n / narration), chấm n8n bằng chính `validate_workflow()`
của runtime, và chấm narration bằng `src/core/grounding.py` — tức phép kiểm lúc
đo và phép kiểm lúc chạy là MỘT (R4).

CÒN GIỮ FILE ĐỂ LÀM GÌ
----------------------
Chưa xoá vì đó là quyết định của chủ dự án (việc brain trên bảng kanzo). Giữ ở
đây thì còn đối chiếu được rubric cũ nếu cần. Chặn chạy thì không ai vô tình
sinh ra một bảng số sai nữa.

Thật sự cần chạy (ví dụ để tái hiện một kết quả cũ) thì đặt biến môi trường
`ANSER_CHAY_EVAL_CU=1`. Tên biến dài và xấu là có chủ ý.
"""

import json
import os
import sys
import time

# Rào đặt TRƯỚC mọi import nặng, có chủ ý.
#
# Bản đầu của rào này nằm ở `__main__`, sau `from openai import OpenAI`. Trên
# máy không cài `openai` thì file chết bằng `ModuleNotFoundError` — người chạy
# đọc được một lỗi thiếu thư viện thay vì lý do thật là "file này đã bị thay
# thế". Lỗi sai chỗ cũng tệ như không có lỗi.
if __name__ == "__main__" and os.environ.get("ANSER_CHAY_EVAL_CU") != "1":
    print(
        "src/evaluate_system.py đã bị thay thế bởi "
        "offline_training/benchmark_v3.py.\n\n"
        "Chạy file này sinh ra số liệu KHÔNG đo thứ dự án đang làm:\n"
        "  - judge chấm theo định dạng Make.com, trong khi đích sinh code là "
        "n8n (R4)\n"
        "  - đọc training_dataset.jsonl bản 27/07/2026, trước pipeline v3\n"
        "  - in \"Hardware Efficiency (A100)\" bất kể chạy trên phần cứng gì "
        "(R5)\n"
        "  - gửi prompt + ground truth + đầu ra model tới DeepSeek API, không\n"
        "    rào nào chặn việc lỡ chạy trên dữ liệu khách thật (R2)\n\n"
        "Dùng cái này:\n"
        "  python offline_training/benchmark_v3.py --model <AWQ_DIR>\n\n"
        "Thật sự cần chạy bản cũ (tái hiện một kết quả cũ):\n"
        "  ANSER_CHAY_EVAL_CU=1 python src/evaluate_system.py\n\n"
        "Lý do đầy đủ nằm ở docstring đầu file.",
        file=sys.stderr,
    )
    raise SystemExit(1)

from json_repair import repair_json  # noqa: E402
from openai import OpenAI  # noqa: E402

# --- PATH FIXER (CRITICAL FOR COLAB) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# ---------------------------------------

from src.agents.coder import CoderAgent
from src.agents.manager import ManagerAgent
from src.core.engine import ModelEngine
from src.core.memory import MemoryManager

# --- CONFIGURATION ---
DATASET_PATH = os.path.join(project_root, "src", "data", "training_dataset.jsonl")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
TEST_LIMIT = 10 # Number of workflows to test per run to save time/API costs

class DeepSeekJudge:
    def __init__(self):
        if not DEEPSEEK_API_KEY:
            print("⚠️ WARNING: DEEPSEEK_API_KEY not found in environment. The Judge will be disabled.")
            self.client = None
        else:
            self.client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

    def grade_workflow(self, prompt: str, expected_json: str, actual_json: str) -> dict:
        if not self.client:
            return {"score": 0, "rationale": "DeepSeek API Key missing. Grading skipped."}

        system_prompt = """You are a Senior Retail Automation Engineer acting as an impartial judge.
Your job is to grade an AI-generated Make.com JSON workflow against a Ground Truth blueprint.

CRITERIA:
5 = Perfect. Logically identical to the ground truth and solves the user's prompt.
4 = Good. Minor structural differences, but functionally correct.
3 = Acceptable. Needs minor manual fixing by the user to work.
2 = Poor. Major logic flaws, missing critical nodes, or hallucinated tools.
1 = Fail. Invalid JSON, completely wrong intent, or empty.

OUTPUT FORMAT:
You must output ONLY a valid JSON object with two keys: "score" (integer 1-5) and "rationale" (short string explaining why)."""

        user_prompt = f"""USER REQUEST: {prompt}

GROUND TRUTH BLUEPRINT:
{expected_json}

AI GENERATED WORKFLOW:
{actual_json}"""

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={'type': 'json_object'},
                temperature=0.0
            )

            result = json.loads(response.choices[0].message.content)
            return result
        except Exception as e:
            return {"score": 0, "rationale": f"Judge API Error: {e}"}

def load_test_data(filepath: str, limit: int):
    """Automatically loads test cases from the fine-tuning JSONL dataset."""
    dataset: list[dict] = []
    if not os.path.exists(filepath):
        print(f"❌ Dataset not found at: {filepath}")
        return dataset

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            # The format is: system (0), user (1), assistant (2)
            user_msg = data['messages'][1]['content']
            expected_json = data['messages'][2]['content']
            dataset.append({
                "prompt": user_msg,
                "expected": expected_json
            })
            if len(dataset) >= limit:
                break
    return dataset

def evaluate_pipeline():
    print("🎓 Booting Production Evaluation Suite...\n" + "="*60)

    # 1. Initialize Components
    try:
        engine = ModelEngine()
        memory = MemoryManager()
        manager = ManagerAgent(engine, memory)
        coder = CoderAgent(engine, memory)
        judge = DeepSeekJudge()
    except Exception as e:
        print(f"❌ Failed to load AI Engine: {e}")
        return

    # 2. Load Data
    test_cases = load_test_data(DATASET_PATH, TEST_LIMIT)
    if not test_cases:
        return
    print(f"📂 Loaded {len(test_cases)} real test cases from {DATASET_PATH}")

    # 3. Metrics Tracking
    metrics = {
        "total_runs": 0,
        "valid_json_count": 0,
        "total_latency_sec": 0.0,
        "total_approx_tokens": 0,
        "total_business_score": 0
    }

    print("\n" + "="*60)
    print("🚀 RUNNING BATCH EVALUATION")
    print("="*60)

    for i, test in enumerate(test_cases, 1):
        print(f"\n▶️ Test {i}/{len(test_cases)}")
        print(f"   Prompt: '{test['prompt'][:80]}...'")

        # --- TIMED EXECUTION ---
        start_time = time.time()

        # Routing & Planning
        manager.analyze_task(test['prompt'])
        plan = manager.plan_or_ask(test['prompt'])

        # Generation
        raw_code = coder.write_code(test['prompt'], plan)

        latency = time.time() - start_time
        # Rough token approximation for Vietnamese/Code (1 token ~= 3.5 chars)
        approx_tokens = len(raw_code) / 3.5
        tps = approx_tokens / latency

        # --- JSON VALIDATION ---
        is_valid = False
        final_json_str = raw_code
        try:
            parsed_data = json.loads(raw_code)
            is_valid = True
        except json.JSONDecodeError:
            try:
                parsed_data = repair_json(raw_code, return_objects=True)
                if parsed_data:
                    final_json_str = json.dumps(parsed_data)
                    is_valid = True
            except (TypeError, ValueError):
                pass

        # --- DEEPSEEK JUDGE ---
        print("   ⚖️  Calling DeepSeek Judge...")
        evaluation = judge.grade_workflow(test['prompt'], test['expected'], final_json_str)
        score = evaluation.get("score", 0)
        rationale = evaluation.get("rationale", "No rationale provided.")

        # --- LOGGING ---
        metrics["total_runs"] += 1
        metrics["total_latency_sec"] += latency
        metrics["total_approx_tokens"] += approx_tokens
        if is_valid:
            metrics["valid_json_count"] += 1
        metrics["total_business_score"] += score

        print(f"   ⏱️  Performance: {latency:.2f}s | {tps:.1f} Tokens/Sec")
        print(f"   ✅  JSON Valid:  {is_valid}")
        print(f"   ⭐  Judge Score: {score}/5")
        print(f"   🧠  Rationale:   {rationale}")

    # --- FINAL REPORT ---
    print("\n" + "="*60)
    print("📊 FINAL EVALUATION REPORT")
    print("="*60)

    avg_latency = metrics["total_latency_sec"] / metrics["total_runs"]
    avg_tps = metrics["total_approx_tokens"] / metrics["total_latency_sec"]
    validity_rate = (metrics["valid_json_count"] / metrics["total_runs"]) * 100
    avg_score = metrics["total_business_score"] / metrics["total_runs"]

    # Bản trước in nguyên văn "Hardware Efficiency (A100)" bất kể chạy trên gì.
    # Dự án chưa bao giờ chạy trên A100 — AGENTS.md v2.0 mở đầu bằng việc tuyên
    # bố giả định đó không còn đúng. Một con số độ trễ dán nhãn A100 mời gọi so
    # sánh sai, và không ai đọc báo cáo mà đi kiểm lại nhãn (R5).
    print(f"⚡ Hardware Efficiency ({_mo_ta_phan_cung()}):")
    print(f"   - Average Latency per Task: {avg_latency:.2f} seconds")
    print(f"   - Average Throughput:       {avg_tps:.1f} Tokens/Second")

    print("\n🧩 Software Reliability:")
    print(f"   - JSON Validity Rate:       {validity_rate:.1f}%")

    print("\n🧠 Business Accuracy (DeepSeek Judge):")
    print(f"   - Average Score:            {avg_score:.1f} / 5.0")

    if avg_score >= 4.0:
        print("\n🟢 STATUS: PRODUCTION READY. The model understands retail logic.")
    elif avg_score >= 3.0:
        print("\n🟡 STATUS: NEEDS PROMPT TUNING. The model works but makes minor mistakes.")
    else:
        print("\n🔴 STATUS: NEEDS FINE-TUNING. The model is failing to grasp the workflow logic.")

def _mo_ta_phan_cung() -> str:
    """Phần cứng ĐANG chạy, hoặc nói thẳng là không biết. Không đoán."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
        return "CPU"
    except Exception:
        # Thiếu torch là chuyện bình thường ở ENV=LOCAL. Không biết thì nói
        # không biết — đó chính là lỗi đang sửa, đừng lặp lại nó.
        return "phần cứng không xác định"


def main() -> int:
    # Rào đã chạy ở ĐẦU FILE, trước mọi import nặng. Tới được đây nghĩa là
    # người chạy đã đặt ANSER_CHAY_EVAL_CU=1 — vẫn nhắc lại cái họ sắp nhận.
    print(
        "⚠️  Đang chạy bản eval CŨ theo yêu cầu (ANSER_CHAY_EVAL_CU=1).\n"
        "⚠️  Judge chấm theo Make.com, KHÔNG phải n8n — số liệu không so được\n"
        "⚠️  với benchmark_v3. Và nó gửi dữ liệu tới DeepSeek: CHỈ dùng dữ liệu\n"
        "⚠️  tổng hợp/mẫu, tuyệt đối không dùng dữ liệu khách thật (R2).\n",
        file=sys.stderr,
    )
    evaluate_pipeline()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
