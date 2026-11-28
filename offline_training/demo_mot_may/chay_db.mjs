// Chạy PostgreSQL cục bộ (binary từ gói npm embedded-postgres) + cầu WebSocket TLS để driver Neon của Body nói chuyện được với nó, KHÔNG sửa mã Body.
// Driver @neondatabase/serverless mặc định nối tới wss://<host>/v2 và gửi thẳng giao thức Postgres bên trong WebSocket; ở đây host = 127.0.0.1, cầu chuyển nguyên byte sang cổng 5432.
// Chỉ nghe trên 127.0.0.1. Dữ liệu hư cấu. Mật khẩu DB sinh ngẫu nhiên, chỉ nằm trong tệp cục bộ ngoài mọi repo.
import crypto from 'node:crypto';
import fs from 'node:fs';
import https from 'node:https';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const GOC = process.env.ANSER_DEMO ?? path.join(os.homedir(), 'anser-demo');
const MIGRATIONS = path.join(GOC, 'body', 'frontend', 'src', 'server', 'db', 'migrations');
const DU_LIEU = path.join(GOC, 'pgdata');
const TEP_MAT_KHAU = path.join(GOC, 'pg.pass');
const CONG_PG = 5432;
const DB = 'anser_demo';

const req = createRequire(path.join(GOC, 'db', 'package.json'));
const { default: EmbeddedPostgres } = await import(pathToFileURL(req.resolve('embedded-postgres')).href);
const { WebSocketServer } = req('ws');
const pgLib = req('pg');

if (!fs.existsSync(TEP_MAT_KHAU)) fs.writeFileSync(TEP_MAT_KHAU, crypto.randomBytes(18).toString('base64url'));
const matKhau = fs.readFileSync(TEP_MAT_KHAU, 'utf8').trim();

const loi = [];
const pg = new EmbeddedPostgres({
  databaseDir: DU_LIEU, user: 'postgres', password: matKhau, port: CONG_PG, authMethod: 'password', persistent: true,
  initdbFlags: ['--encoding=UTF8', '--locale=C'], postgresFlags: ['-c', 'listen_addresses=127.0.0.1'],
  onLog: () => {}, onError: (e) => loi.push(String(e).slice(0, 300)),
});
if (!fs.existsSync(path.join(DU_LIEU, 'PG_VERSION'))) await pg.initialise();
await pg.start();
try { await pg.createDatabase(DB); } catch (e) { if (!/already exists/i.test(String(e))) throw e; }

const c = new pgLib.Client({ host: '127.0.0.1', port: CONG_PG, user: 'postgres', password: matKhau, database: DB });
await c.connect();
await c.query('create table if not exists demo_migrations (tag text primary key, chay_luc timestamptz default now())');
const daChay = new Set((await c.query('select tag from demo_migrations')).rows.map((r) => r.tag));
const journal = JSON.parse(fs.readFileSync(path.join(MIGRATIONS, 'meta', '_journal.json'), 'utf8'));
let soMoi = 0;
for (const e of journal.entries) {
  if (daChay.has(e.tag)) continue;
  const sql = fs.readFileSync(path.join(MIGRATIONS, `${e.tag}.sql`), 'utf8');
  await c.query('begin');
  try {
    for (const cau of sql.split('--> statement-breakpoint')) if (cau.trim()) await c.query(cau);
    await c.query('insert into demo_migrations(tag) values ($1)', [e.tag]);
    await c.query('commit');
    soMoi += 1;
  } catch (err) {
    await c.query('rollback');
    console.error(`MIGRATION HỎNG ${e.tag}: ${err.message}`);
    process.exit(1);
  }
}
const soBang = (await c.query("select count(*)::int n from information_schema.tables where table_schema='public'")).rows[0].n;
await c.end();

const server = https.createServer({ key: fs.readFileSync(path.join(GOC, 'cert', 'key.pem')), cert: fs.readFileSync(path.join(GOC, 'cert', 'cert.pem')) });
const wss = new WebSocketServer({ server });
wss.on('connection', (ws) => {
  const tcp = net.connect(CONG_PG, '127.0.0.1');
  ws.on('message', (d) => tcp.write(d));
  tcp.on('data', (d) => { if (ws.readyState === ws.OPEN) ws.send(d); });
  ws.on('close', () => tcp.end());
  tcp.on('close', () => ws.close());
  ws.on('error', () => tcp.destroy());
  tcp.on('error', () => ws.close());
});
await new Promise((ok, hong) => { server.once('error', hong); server.listen(443, '127.0.0.1', ok); });
console.log(`SẴN SÀNG: Postgres 127.0.0.1:${CONG_PG}/${DB} (${soBang} bảng, ${soMoi} migration mới chạy), cầu wss://127.0.0.1:443/v2`);

let dangDung = false;
async function dung() {
  if (dangDung) return;
  dangDung = true;
  server.close();
  await pg.stop();
  process.exit(0);
}
process.on('SIGINT', dung);
process.on('SIGTERM', dung);
