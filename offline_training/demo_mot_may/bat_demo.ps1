# Bật toàn bộ demo trên MỘT máy: PostgreSQL cục bộ + cầu cho driver Neon, Brain (ENV=LOCAL, không GPU), Body (bản build production). Không cần Neon, không cần GPU, chỉ dữ liệu hư cấu.
# Token Brain-Body và khoá đăng nhập sinh ngẫu nhiên MỖI LẦN bật, chỉ nằm trong biến môi trường của tiến trình, không ghi ra tệp.
#   powershell -ExecutionPolicy Bypass -File offline_training\demo_mot_may\bat_demo.ps1     bật tất cả, gieo dữ liệu demo, tự kiểm (chạy cai_demo.ps1 trước, một lần)
#   ... bat_demo.ps1 -BuildLai    build lại Body (trang tổng quan là số tại lúc build: chạy cờ này vào sáng ngày demo)
#   powershell -ExecutionPolicy Bypass -File offline_training\demo_mot_may\tat_demo.ps1     tắt tất cả
param([string]$Goc = '', [int]$CongBody = 3100, [switch]$BuildLai)
$ErrorActionPreference = 'Stop'
if (-not $Goc) { $Goc = if ($env:ANSER_DEMO) { $env:ANSER_DEMO } else { Join-Path $HOME 'anser-demo' } }
$env:ANSER_DEMO = $Goc
$tools = $PSScriptRoot
$brain = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$log = Join-Path $Goc 'log'
$web = Join-Path $Goc 'body\frontend'
New-Item -ItemType Directory -Force $log | Out-Null

function New-ChuoiNgauNhien {
    $b = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    [Convert]::ToBase64String($b).Replace('+', '-').Replace('/', '_').TrimEnd('=')
}
function Test-Cong([int]$cong) { [bool](Get-NetTCPConnection -LocalPort $cong -State Listen -ErrorAction SilentlyContinue) }
function Wait-Dieu-Kien([scriptblock]$kiem, [int]$giay, [string]$ten) {
    $het = (Get-Date).AddSeconds($giay)
    while ((Get-Date) -lt $het) { try { if (& $kiem) { return } } catch { }; Start-Sleep -Milliseconds 800 }
    throw "Quá $giay giây mà $ten chưa sẵn sàng. Xem log trong $log."
}
function Save-Pids { $pids | ConvertTo-Json | Out-File "$log\pids.json" -Encoding utf8 }
function Invoke-BuildBody {
    # Build cần database đang chạy: trang /dashboard của Body được dựng sẵn lúc build bằng truy vấn DB (số trên trang tổng quan là số tại thời điểm build).
    Write-Host '      Build Body (khoảng 1-3 phút)...'
    if (Test-Path "$web\.next") { Remove-Item -Recurse -Force "$web\.next" }
    $env:NODE_OPTIONS = '--max-old-space-size=2048'
    Push-Location $web
    try { cmd /c "node node_modules\next\dist\bin\next build > `"$log\build.log`" 2>&1"; if ($LASTEXITCODE -ne 0) { throw "Build Body hỏng, xem $log\build.log" } }
    finally { Pop-Location; Remove-Item Env:\NODE_OPTIONS -ErrorAction SilentlyContinue }
    New-Item -ItemType File -Force "$web\.next\anser_build_ok" | Out-Null
}
function Start-Body {
    $p = Start-Process node -ArgumentList ('node_modules\next\dist\bin\next start -H 127.0.0.1 -p ' + $CongBody) -WorkingDirectory $web -WindowStyle Hidden -PassThru -RedirectStandardOutput "$log\body.log" -RedirectStandardError "$log\body.err.log"
    $pids.body = $p.Id; Save-Pids
    Wait-Dieu-Kien { (Invoke-WebRequest "http://127.0.0.1:$CongBody/login" -UseBasicParsing -TimeoutSec 30).StatusCode -eq 200 } 180 'Body'
}

if (-not (Test-Path "$web\node_modules\next") -or -not (Test-Path "$Goc\cert\cert.pem")) { throw "Chưa cài: chạy cai_demo.ps1 trước." }
foreach ($c in 443, 5432, 8000, $CongBody) { if (Test-Cong $c) { throw "Cổng $c đang bận. Chạy tat_demo.ps1 trước (hoặc tắt chương trình đang dùng cổng đó)." } }
$pids = @{}

# Tệp Excel mẫu luôn sinh lại từ đúng bản Brain đang chạy (rẻ, vài trăm ms), để đáp án trong tài liệu khớp tệp khách thấy.
New-Item -ItemType Directory -Force "$Goc\file_mau" | Out-Null
Push-Location $brain
try { python sample_data\make_sample_data.py | Out-Null; if ($LASTEXITCODE -ne 0) { throw 'Sinh tệp mẫu hỏng' } } finally { Pop-Location }
Copy-Item "$brain\sample_data\*_mau*.xlsx" "$Goc\file_mau\" -Force

# Máy tắt đột ngột để lại tệp khoá của PostgreSQL; nếu PID trong đó giờ là chương trình khác, PostgreSQL từ chối khởi động. Chỉ gỡ khi PID đó không phải postgres.
$khoa = "$Goc\pgdata\postmaster.pid"
if (Test-Path $khoa) {
    $pidCu = [int](Get-Content $khoa -TotalCount 1)
    $pr = Get-Process -Id $pidCu -ErrorAction SilentlyContinue
    if (-not $pr -or $pr.ProcessName -ne 'postgres') { Remove-Item $khoa -Force; Write-Host "      Gỡ tệp khoá cũ của PostgreSQL (PID $pidCu không còn là postgres)" }
}

# 1. Cơ sở dữ liệu + cầu
Remove-Item "$log\db.log" -ErrorAction SilentlyContinue
$p = Start-Process node -ArgumentList "`"$tools\chay_db.mjs`"" -WorkingDirectory $tools -WindowStyle Hidden -PassThru -RedirectStandardOutput "$log\db.log" -RedirectStandardError "$log\db.err.log"
$pids.db = $p.Id; Save-Pids
Wait-Dieu-Kien { (Test-Path "$log\db.log") -and (Select-String -Path "$log\db.log" -Pattern 'SẴN SÀNG' -Encoding UTF8 -Quiet) } 120 'cơ sở dữ liệu'
$mk = (Get-Content "$Goc\pg.pass" -Raw).Trim()
# Mật khẩu database cục bộ là chuỗi ngẫu nhiên trong <gốc demo>\pg.pass (ngoài repo), ghép vào URL lúc chạy.
$u = New-Object System.UriBuilder; $u.Scheme = 'postgresql'; $u.UserName = 'postgres'; $u.Password = $mk; $u.Host = '127.0.0.1'; $u.Port = 5432; $u.Path = 'anser_demo'
$env:DATABASE_URL = $u.Uri.AbsoluteUri
$env:NODE_EXTRA_CA_CERTS = "$Goc\cert\cert.pem"
$env:NEXT_TELEMETRY_DISABLED = '1'
$env:JWT_SECRET = New-ChuoiNgauNhien
Write-Host '[1/4] Cơ sở dữ liệu sẵn sàng (127.0.0.1:5432, dữ liệu hư cấu)'

if ($BuildLai -or -not (Test-Path "$web\.next\anser_build_ok")) { Invoke-BuildBody }

# 2. Brain: KHÔNG nhận DATABASE_URL. Trỏ vào DB của Body thì /health báo degraded vì 6 bảng lịch sử chat của Brain không tồn tại ở đó (brain#19); các công cụ trong demo nhận dữ liệu qua yêu cầu.
$dbUrl = $env:DATABASE_URL; Remove-Item Env:\DATABASE_URL
$token = New-ChuoiNgauNhien
$env:ENV = 'LOCAL'; $env:PYTHONUTF8 = '1'; $env:PYTHONUNBUFFERED = '1'; $env:API_AUTH_TOKEN = $token; $env:API_HMAC_MODE = 'off'
# TẮT kho tri thức: nạp một tài liệu làm Brain nạp model nhúng bge-m3 trên CPU và CHẾT CẢ TIẾN TRÌNH trên Windows (đo 28/11, lỗi trong VCRUNTIME140.dll), kéo mọi chức năng AI theo.
# Trỏ tới model không tồn tại và cấm tải mạng: nạp tài liệu chỉ báo lỗi, Brain sống.
$env:KB_EMBEDDER_ID = 'demo-tat-kho-tri-thuc'; $env:KB_RERANKER_ID = 'demo-tat-kho-tri-thuc'; $env:HF_HUB_OFFLINE = '1'; $env:TRANSFORMERS_OFFLINE = '1'
$p = Start-Process python -ArgumentList '-m uvicorn src.api.main:app --host 127.0.0.1 --port 8000' -WorkingDirectory $brain -WindowStyle Hidden -PassThru -RedirectStandardOutput "$log\brain.log" -RedirectStandardError "$log\brain.err.log"
$pids.brain = $p.Id; Save-Pids
Wait-Dieu-Kien { (Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 3).status -eq 'ok' } 150 'Brain'
$env:DATABASE_URL = $dbUrl
Write-Host '[2/4] Brain sẵn sàng (http://127.0.0.1:8000, không có mô hình: chat là câu giả)'

# 3. Body
$env:BRAIN_URL = 'http://127.0.0.1:8000'; $env:BRAIN_API_TOKEN = $token; $env:BRAIN_CHAT_TIMEOUT_MS = '240000'; $env:ENABLE_STARTUP_SEED = 'true'
Start-Body
Write-Host '[3/4] Body sẵn sàng'

# 4. Dữ liệu demo (không nhân đôi nếu đã có); gieo mới thì build lại để trang tổng quan hiện số mới
$ErrorActionPreference = 'Continue'
$ra = python "$tools\gieo_du_lieu_demo.py" --url "http://127.0.0.1:$CongBody" 2>&1 | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) { $ra | Write-Host; throw 'Gieo dữ liệu demo hỏng' }
$ra | Write-Host
if (($ra -match '^Đã gieo') -or -not (Test-Path "$log\build_sau_gieo.ok")) {
    $ErrorActionPreference = 'Stop'
    taskkill /PID $pids.body /T /F | Out-Null
    Wait-Dieu-Kien { -not (Test-Cong $CongBody) } 30 'cổng Body trống'
    Invoke-BuildBody
    Start-Body
    New-Item -ItemType File -Force "$log\build_sau_gieo.ok" | Out-Null
    $ErrorActionPreference = 'Continue'
}
Write-Host "[4/4] Sẵn sàng: http://localhost:$CongBody  (bấm 'Người dùng demo' ở trang đăng nhập; Body chỉ cho đăng nhập 10 lần trong 15 phút)"

Write-Host 'Kiểm chỗ nối Brain-Body (từ phía Brain):'
Push-Location $brain
try { python offline_training\kiem_tich_hop_body.py --url http://127.0.0.1:8000 --voi-brain-ts --brain-ts-file "$web\src\server\brain.ts" --han-chat 60 2>&1 | ForEach-Object { "$_" }; Write-Host "kiem_tich_hop_body: ma thoat $LASTEXITCODE" } finally { Pop-Location }
Write-Host 'Kiểm qua chính API của Body (như màn hình sẽ gọi):'
python "$tools\kiem_qua_body.py" --url "http://127.0.0.1:$CongBody" --thu-tai-lieu 2>&1 | ForEach-Object { "$_" }
Write-Host "kiem_qua_body: ma thoat $LASTEXITCODE"
