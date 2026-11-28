# Bật toàn bộ demo trên MỘT máy: PostgreSQL cục bộ + cầu cho driver Neon, Brain (ENV=LOCAL, không GPU), Body (bản build production). Không cần Neon, không cần GPU, chỉ dữ liệu hư cấu.
# Token Brain-Body và khoá đăng nhập sinh ngẫu nhiên MỖI LẦN bật, chỉ nằm trong biến môi trường của tiến trình, không ghi ra tệp.
#   powershell -ExecutionPolicy Bypass -File offline_training\demo_mot_may\bat_demo.ps1     bật tất cả, gieo dữ liệu demo, tự kiểm (chạy cai_demo.ps1 trước, một lần)
#   ... bat_demo.ps1 -BuildLai    build lại Body (trang tổng quan là số tại lúc build: chạy cờ này vào sáng ngày demo)
#   ... bat_demo.ps1 -BrainColab <tệp>   CÓ MODEL THẬT: không bật Brain ở máy này, trỏ Body sang Brain trên Colab (offline_training\demo_colab.py). <tệp> chứa hai dòng BRAIN_URL, BRAIN_API_TOKEN ô Colab in ra, đặt NGOÀI repo.
#   powershell -ExecutionPolicy Bypass -File offline_training\demo_mot_may\tat_demo.ps1     tắt tất cả
param([string]$Goc = '', [int]$CongBody = 3100, [switch]$BuildLai, [string]$BrainColab = '')
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
# Đọc và kiểm tệp kết nối Colab TRƯỚC khi bật bất cứ thứ gì.
$tuXa = $null
if ($BrainColab) {
    if (-not (Test-Path $BrainColab)) { throw "Không thấy $BrainColab. Tạo tệp này với hai dòng ô Colab in ra." }
    $bien = @{}
    foreach ($dong in Get-Content $BrainColab -Encoding UTF8) { if ($dong -match '^\s*(BRAIN_URL|BRAIN_API_TOKEN)\s*=\s*"?([^"\s]+)"?\s*$') { $bien[$Matches[1]] = $Matches[2] } }
    $urlXa = [string]$bien['BRAIN_URL']; $tokenXa = [string]$bien['BRAIN_API_TOKEN']
    if ($urlXa -notmatch '^https://[A-Za-z0-9.-]+(:\d+)?/?$' -or $tokenXa.Length -lt 32) { throw "$BrainColab phải có BRAIN_URL=https://... và BRAIN_API_TOKEN=... (từ 32 ký tự), đúng như ô Colab in ra." }
    $tuXa = @{ url = $urlXa.TrimEnd('/'); token = $tokenXa; may = ([Uri]$urlXa).Host }
}
$cacCong = @(443, 5432, $CongBody); if (-not $tuXa) { $cacCong += 8000 }
foreach ($c in $cacCong) { if (Test-Cong $c) { throw "Cổng $c đang bận. Chạy tat_demo.ps1 trước (hoặc tắt chương trình đang dùng cổng đó)." } }
$trong = (Get-CimInstance Win32_OperatingSystem).FreeVirtualMemory / 1MB
if ($trong -lt 2) { Write-Host ("      CẢNH BÁO: bộ nhớ ảo còn trống {0:N1} GB. Bật hỏng thì đóng bớt trình duyệt, VS Code rồi chạy lại." -f $trong) }
$pids = @{}

# Tệp mẫu (Excel, ảnh hoá đơn, quy chế) luôn sinh lại từ đúng bản Brain đang chạy (rẻ), để đáp án trong tài liệu khớp tệp khách thấy.
New-Item -ItemType Directory -Force "$Goc\file_mau" | Out-Null
Push-Location $brain
try { python sample_data\make_sample_data.py | Out-Null; if ($LASTEXITCODE -ne 0) { throw 'Sinh tệp mẫu hỏng' } } finally { Pop-Location }
Copy-Item "$brain\sample_data\*_mau*.xlsx", "$brain\sample_data\*_mau*.png", "$brain\sample_data\*_mau*.txt" "$Goc\file_mau\" -Force

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

# 2. Brain: trên Colab (có model thật) hoặc ở máy này (không model, chỉ phần tính bằng mã).
$env:PYTHONUTF8 = '1'
if ($tuXa) {
    try { $h = Invoke-RestMethod "$($tuXa.url)/health" -Headers @{ 'ngrok-skip-browser-warning' = '1' } -TimeoutSec 60 }
    catch { throw "Không gọi được Brain ở $($tuXa.may). Ô Colab còn chạy không? Địa chỉ và token đổi mỗi lần chạy lại ô. ($($_.Exception.Message))" }
    if (-not $h.auth_enabled) { throw 'Brain ở xa không kiểm token: dừng, không nối.' }
    if ($h.status -ne 'ok') { Write-Host "      CẢNH BÁO: Brain báo status=$($h.status)" }
    $urlBrain = $tuXa.url; $token = $tuXa.token
    Write-Host "[2/4] Brain trên Colab sẵn sàng ($($tuXa.may)). CHỈ dùng dữ liệu hư cấu: câu hỏi, ảnh, tài liệu đi qua đường hầm của bên thứ ba."
} else {
    # KHÔNG nhận DATABASE_URL. Trỏ vào DB của Body thì /health báo degraded vì 6 bảng lịch sử chat của Brain không tồn tại ở đó (brain#19); các công cụ trong demo nhận dữ liệu qua yêu cầu.
    $dbUrl = $env:DATABASE_URL; Remove-Item Env:\DATABASE_URL
    $token = New-ChuoiNgauNhien
    $env:ENV = 'LOCAL'; $env:PYTHONUNBUFFERED = '1'; $env:API_AUTH_TOKEN = $token; $env:API_HMAC_MODE = 'off'
    # TẮT kho tri thức: nạp một tài liệu làm Brain nạp model nhúng bge-m3 trên CPU và CHẾT CẢ TIẾN TRÌNH trên Windows (đo 28/11, lỗi trong VCRUNTIME140.dll), kéo mọi chức năng AI theo.
    # Trỏ tới model không tồn tại và cấm tải mạng: nạp tài liệu chỉ báo lỗi, Brain sống.
    $env:KB_EMBEDDER_ID = 'demo-tat-kho-tri-thuc'; $env:KB_RERANKER_ID = 'demo-tat-kho-tri-thuc'; $env:HF_HUB_OFFLINE = '1'; $env:TRANSFORMERS_OFFLINE = '1'
    $p = Start-Process python -ArgumentList '-m uvicorn src.api.main:app --host 127.0.0.1 --port 8000' -WorkingDirectory $brain -WindowStyle Hidden -PassThru -RedirectStandardOutput "$log\brain.log" -RedirectStandardError "$log\brain.err.log"
    $pids.brain = $p.Id; Save-Pids
    Wait-Dieu-Kien { (Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 3).status -eq 'ok' } 150 'Brain'
    $env:DATABASE_URL = $dbUrl
    $urlBrain = 'http://127.0.0.1:8000'
    Write-Host '[2/4] Brain sẵn sàng (http://127.0.0.1:8000, không có mô hình: chat là câu giả)'
}

# 3. Body
$env:BRAIN_URL = $urlBrain; $env:BRAIN_API_TOKEN = $token; $env:BRAIN_CHAT_TIMEOUT_MS = '240000'; $env:ENABLE_STARTUP_SEED = 'true'
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
$thamSo = if ($tuXa) { @('--can-model', '--han-chat', '240') } else { @('--han-chat', '60') }
Push-Location $brain
try { python offline_training\kiem_tich_hop_body.py --url $urlBrain --voi-brain-ts --brain-ts-file "$web\src\server\brain.ts" @thamSo 2>&1 | ForEach-Object { "$_" }; Write-Host "kiem_tich_hop_body: ma thoat $LASTEXITCODE" } finally { Pop-Location }
Write-Host 'Kiểm qua chính API của Body (như màn hình sẽ gọi):'
$cheDo = if ($tuXa) { '--co-model' } else { '--thu-tai-lieu' }
python "$tools\kiem_qua_body.py" --url "http://127.0.0.1:$CongBody" $cheDo 2>&1 | ForEach-Object { "$_" }
Write-Host "kiem_qua_body: ma thoat $LASTEXITCODE"
