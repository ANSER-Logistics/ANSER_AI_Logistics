'use strict';
/*
 * ky_hmac_v1.js — ký một yêu cầu tới Brain theo giao thức ANSER-HMAC-V1 (đặc tả ở docstring đầu src/api/hmac_auth.py, issue #193).
 *
 * BẢN SAO phía JavaScript của `hmac_auth.chuoi_can_ky` và `hmac_auth.ky`, để n8n (node Code) và Body (Node/TypeScript) không phải tự đoán giao thức.
 * Bản sao thì lệch được: `tests/integration/workflows/test_hmac_ky_js.py` chạy file này bằng Node trên bốn vector vàng của Python và cho Python kiểm lại chữ ký do file này
 * tạo ra; đổi giao thức ở Python mà không đổi ở đây thì test đỏ.
 *
 * DÙNG TRONG n8n (node Code, "Run Once for Each Item"):
 *   - Cần `require('crypto')`: n8n chặn module có sẵn của Node theo mặc định; phải đặt biến môi trường của n8n NODE_FUNCTION_ALLOW_BUILTIN=crypto.
 *     CHƯA KIỂM trên n8n thật (máy dev không có n8n): nếu bị chặn thì dùng node Crypto của n8n để tính hai bước băm/HMAC (xem issue #225).
 *   - Thân phải là CHÍNH XÁC chuỗi/byte được gửi đi. Dựng thân thành chuỗi JSON MỘT LẦN, ký chuỗi đó, rồi gửi HTTP Request ở dạng Raw đúng chuỗi đó.
 *     Để n8n tự tuần tự hoá lại thân thì byte có thể khác và Brain trả 401 sai_chu_ky.
 *   - Gọi lại hàm này CHO TỪNG LẦN GỬI, kể cả lần thử lại: nonce dùng lại bị Brain từ chối (phat_lai).
 *
 * KHOÁ: lấy từ credential/biến của n8n, KHÔNG viết khoá vào workflow hay nhật ký (AGENTS.md R2b). Khoá là chuỗi UTF-8 >= 32 ký tự, dùng nguyên văn.
 */
const crypto = require('crypto');

const PHIEN_BAN = 'ANSER-HMAC-V1';

function sha256Hex(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function thanBytes(body) {
  if (body === undefined || body === null) return Buffer.alloc(0);
  return Buffer.isBuffer(body) ? body : Buffer.from(String(body), 'utf8');
}

/** Chuỗi cần ký: 8 dòng nối "\n", không có "\n" cuối. `rawQuery` là chuỗi truy vấn THÔ như đã gửi, không có dấu "?". */
function chuoiCanKy({ keyId, timestamp, nonce, method, path, rawQuery = '', body }) {
  return [PHIEN_BAN, keyId, timestamp, nonce, String(method).toUpperCase(), path, rawQuery, sha256Hex(thanBytes(body))].join('\n');
}

/** Chữ ký hex thường (không kèm "v1="). */
function ky({ key, ...yeuCau }) {
  return crypto.createHmac('sha256', Buffer.from(key, 'utf8')).update(chuoiCanKy(yeuCau), 'utf8').digest('hex');
}

/**
 * Bốn header cần gửi. `nowMs` và `nonce` chỉ để test; mặc định lấy giờ hiện tại và 16 byte ngẫu nhiên mới cho MỖI lần gọi.
 * Trả `{ 'X-Key-Id', 'X-Timestamp', 'X-Nonce', 'X-Signature' }`. Gửi thân Raw đúng `body` đã truyền vào đây.
 */
function taoHeader({ keyId, key, method, path, rawQuery = '', body, nowMs = Date.now(), nonce = crypto.randomBytes(16).toString('hex') }) {
  const timestamp = String(Math.floor(nowMs / 1000));
  const chuKy = ky({ key, keyId, timestamp, nonce, method, path, rawQuery, body });
  return { 'X-Key-Id': keyId, 'X-Timestamp': timestamp, 'X-Nonce': nonce, 'X-Signature': `v1=${chuKy}` };
}

module.exports = { chuoiCanKy, ky, taoHeader };

// Dùng cho test: `node ky_hmac_v1.js` đọc JSON từ stdin, in JSON ra stdout. Không dùng trong n8n.
//   {"chuoi": [{...tham số chuoiCanKy..., "bodyHex": "..."}], "ky": [{ "key": "...", ...,"bodyHex": "..."}], "header": [{...taoHeader..., "bodyHex": "..."}]}
if (require.main === module) {
  let raw = '';
  process.stdin.on('data', (d) => { raw += d; });
  process.stdin.on('end', () => {
    const vao = JSON.parse(raw);
    const lo = (o) => ({ ...o, body: o.bodyHex !== undefined ? Buffer.from(o.bodyHex, 'hex') : o.body });
    process.stdout.write(JSON.stringify({
      chuoi: (vao.chuoi || []).map((o) => chuoiCanKy(lo(o))),
      ky: (vao.ky || []).map((o) => ky(lo(o))),
      header: (vao.header || []).map((o) => taoHeader(lo(o))),
    }));
  });
}
