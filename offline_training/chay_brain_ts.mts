// offline_training/chay_brain_ts.mts — chạy CHÍNH `brain.ts` của Body (tải về nguyên văn) để gọi Brain; in một khối JSON, không gì khác.
//
// Không chạy tay: `kiem_tich_hop_body.py --voi-brain-ts` tải brain.ts về cùng thư mục tạm, đặt BRAIN_URL / BRAIN_API_TOKEN rồi gọi file này.
// Cần Node >= 22.18 (gỡ kiểu TypeScript có sẵn); brain.ts không import gì và chỉ dùng cú pháp xoá được nên chạy thẳng, không build, không cài gói.
//
// Vì sao chạy mã Body thay vì viết lại lời gọi bằng Python: bản Python (kiem_tich_hop_body.py) chứng minh Brain trả đúng; chỉ chạy chính mã Body mới chứng minh
// RẰNG BODY ĐỌC ĐƯỢC câu trả lời đó (tên trường, kiểu lỗi, vòng hỏi task). Hai lần lệch đã biết đều là kiểu "Brain đúng, Body đọc sai".
// Dữ liệu dưới đây hoàn toàn hư cấu (R2).
import * as fs from "node:fs";
import { askBrain, buildReport, checkBrainHealth, comparePeriods, importInventoryFile, BrainError } from "./brain.ts";

const ket: Record<string, unknown> = {};
const dinhDanh = { userId: "6f1c2a52-5a0e-4f55-9d0a-1d6f0f0f0f01", warehouseId: "0b1c2a52-5a0e-4f55-9d0a-1d6f0f0f0f02" };

async function buoc(ten: string, f: () => Promise<Record<string, unknown>>): Promise<void> {
  const t0 = Date.now();
  try {
    const r = await f();
    ket[ten] = { ok: true, giay: (Date.now() - t0) / 1000, ...r };
  } catch (e) {
    ket[ten] = { ok: false, giay: (Date.now() - t0) / 1000, kind: e instanceof BrainError ? e.kind : "khac", loi: String(e).slice(0, 200) };
  }
}

await buoc("health", async () => {
  const r = await checkBrainHealth();
  if (!r.ok) throw new BrainError(r.kind, r.message);
  return { degraded: r.health.degraded, auth_enabled: r.health.auth_enabled, engine_ready: r.health.engine_ready, vision_ready: r.health.vision_ready };
});

await buoc("report", async () => {
  const r = await buildReport({
    granularity: "month",
    periods_back: 3,
    sales: [
      { date: "2026-09-10", revenue: 10000000, product: "Dầu AW46", quantity: 10, cogs: 7000000 },
      { date: "2026-10-12", revenue: 12000000, product: "Dầu AW46", quantity: 12, cogs: 8400000 },
      { date: "2026-10-20", revenue: 5000000, product: "Mỡ chịu nhiệt", quantity: 5, cogs: null },
    ],
    expenses: [{ date: "2026-10-05", amount: 2000000, category: "Lương" }],
  });
  const t10 = r.periods.find((p) => p.period === "2026-10");
  return { so_ky: r.periods.length, lai_gop_10: t10?.gross_profit ?? null, phu_gia_von: r.explain.cogs_coverage_pct, tin_cay: r.explain.confidence };
});

await buoc("ton_kho", async () => {
  const noiDung = fs.readFileSync(process.argv[2]);
  const r = await importInventoryFile(new File([noiDung], "ton_kho_mau.xlsx"));
  const ma = (r.audit?.findings ?? []).map((f: { code: string }) => f.code);
  return { so_dong: r.import.rows_parsed, so_phat_hien: ma.length, ma: [...new Set(ma)].sort(), ly_do_bo_qua: r.audit_skipped_reason };
});

// Y như route `/api/ai/period-diff` của Body: nạp hai bản xuất cùng kỳ, rồi so bằng `lines`, kho và kỳ của chính từng bản.
await buoc("so_hai_ban", async () => {
  const doc = (duong: string) => importInventoryFile(new File([fs.readFileSync(duong)], "ban_xuat.xlsx"));
  const [a, b] = await Promise.all([doc(process.argv[2]), doc(process.argv[3])]);
  const canh = (x: typeof a) => ({ lines: x.import.lines, warehouse: x.import.warehouse, period_start: x.import.period_start, period_end: x.import.period_end });
  const diff = await comparePeriods(canh(a), canh(b));
  const phatHien: Record<string, string> = {};
  for (const f of diff.findings) phatHien[String(f.code)] = f.kind;
  return { khong_so_duoc: diff.warnings.length, hoi_to: diff.summary["có_sửa_hồi_tố"] ?? null, phat_hien: phatHien };
});

// Token sai: Body PHẢI nhận ra kiểu lỗi "unauthorized" (hiện đúng câu "BRAIN_API_TOKEN sai hoặc thiếu"), không phải "server_error" chung chung.
const tokenDung = process.env.BRAIN_API_TOKEN;
process.env.BRAIN_API_TOKEN = "token-sai-co-chu-y";
await buoc("token_sai", async () => {
  try {
    await buildReport({ sales: [{ date: "2026-10-12", revenue: 1, cogs: 1 }] });
  } catch (e) {
    if (e instanceof BrainError) return { kind_nhan_duoc: e.kind, status: e.status ?? null };
    throw e;
  }
  return { kind_nhan_duoc: "KHONG_LOI" };
});
if (tokenDung === undefined) delete process.env.BRAIN_API_TOKEN;
else process.env.BRAIN_API_TOKEN = tokenDung;

await buoc("chat", async () => {
  const r = await askBrain("Xin chào, bạn giúp được gì cho kho của tôi?", dinhDanh);
  return { task_id: r.taskId, tra_loi: r.answer.slice(0, 200), do_dai: r.answer.length };
});

console.log(JSON.stringify(ket));
