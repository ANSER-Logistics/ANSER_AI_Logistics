// Đi đúng kịch bản demo bằng giao diện thật (Chrome ẩn, hồ sơ tạm riêng), chụp ảnh từng bước vào <gốc demo>/anh (đổi bằng biến ANH).
// Cần Google Chrome đã cài trên máy; tệp mẫu đọc từ <gốc demo>/file_mau (cai_demo.ps1 sinh).
// Đăng nhập MỘT lần bằng nút "Người dùng demo" (Body giới hạn 10 lần/15 phút).
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

const GOC = process.env.ANSER_DEMO ?? path.join(os.homedir(), 'anser-demo');
const URL_BODY = process.env.URL_BODY ?? 'http://localhost:3100';
const req = createRequire(path.join(GOC, 'ui', 'package.json'));
const { chromium } = req('playwright-core');
const ANH = path.join(GOC, process.env.ANH ?? "anh");
fs.mkdirSync(ANH, { recursive: true });
const MAU = path.join(GOC, 'file_mau');

const loiConsole = [];
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'vi-VN' })).newPage();
page.on('console', (m) => { if (m.type() === 'error') loiConsole.push(`${page.url()}: ${m.text().slice(0, 200)}`); });
page.on('pageerror', (e) => loiConsole.push(`${page.url()}: PAGEERROR ${String(e).slice(0, 200)}`));
const chup = async (ten) => { await page.screenshot({ path: path.join(ANH, `${ten}.png`), fullPage: true }); console.log(`ảnh: ${ten}.png  (${page.url()})`); };
const vanBan = async () => (await page.locator('body').innerText()).replace(/\s+/g, ' ');

try {
  await page.goto(`${URL_BODY}/login`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: /demo/i }).click();
  await page.getByRole('button', { name: /^Đăng nhập$/ }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 30000 });
  await page.waitForLoadState('networkidle');
  await chup('1-tong-quan');

  await page.goto(`${URL_BODY}/dashboard/inventory`, { waitUntil: 'networkidle' });
  await page.getByText('Kiểm sổ từ Excel', { exact: true }).click();
  await page.locator('input[type=file][accept*=".xlsx"]').first().setInputFiles(path.join(MAU, 'ton_kho_mau.xlsx'));
  await page.getByRole('button', { name: 'Kiểm sổ', exact: true }).click();
  await page.getByText('DN-BR-18').first().waitFor({ timeout: 30000 });
  await chup('2-soi-ton-kho');
  const t2 = await vanBan();
  console.log('tồn kho có đủ 7 mã:', ['DN-TL-200', 'KM-4T-08', 'DN-BR-18', 'LC-COOL-200', 'DN-CAT-20', 'DN-GL5-18', 'MO-EP2-15'].every((m) => t2.includes(m)));

  await page.goto(`${URL_BODY}/dashboard/reports`, { waitUntil: 'networkidle' });
  await page.locator('select').first().selectOption({ label: 'Tháng' });
  await page.getByRole('button', { name: 'Tính lãi gộp' }).click();
  await page.getByText(/độ tin cậy/i).first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(800);
  await chup('3-bao-cao');
  const t3 = await vanBan();
  console.log('báo cáo, đoạn quanh "độ tin cậy":', (t3.match(/.{0,200}[Đđ]ộ tin cậy.{0,200}/) ?? ['?'])[0]);

  await page.goto(`${URL_BODY}/dashboard/audit`, { waitUntil: 'networkidle' });
  const o = page.locator('input[type=file][accept=".xlsx,.xls"]');
  await o.nth(0).setInputFiles(path.join(MAU, 'ton_kho_mau.xlsx'));
  await o.nth(1).setInputFiles(path.join(MAU, 'ton_kho_mau_ban_sau.xlsx'));
  await page.getByRole('button', { name: 'So hai bản' }).click();
  await page.getByText('DN-SG-18').first().waitFor({ timeout: 30000 });
  await page.waitForTimeout(800);
  await chup('4-so-hai-ban');
  const t4 = await vanBan();
  console.log('so hai bản: đủ 3 mã', ['DN-SG-18', 'DN-CF4-200', 'DN-PHANH-1'].every((m) => t4.includes(m)), '| có mã nhận DN-TL-46:', t4.includes('DN-TL-46'));

  for (const [ten, url] of [['5-ton-quy', '/dashboard/cashflow'], ['6-tai-lieu', '/dashboard/documents']]) {
    await page.goto(`${URL_BODY}${url}`, { waitUntil: 'networkidle' });
    await chup(ten);
  }
} catch (e) {
  console.log('HỎNG:', String(e).slice(0, 400));
  await chup('loi').catch(() => {});
  process.exitCode = 1;
} finally {
  console.log(`lỗi console trình duyệt: ${loiConsole.length}`);
  for (const l of loiConsole.slice(0, 10)) console.log('  ', l);
  await browser.close();
}
