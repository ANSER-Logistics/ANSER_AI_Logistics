# Cài bộ demo một máy, chạy MỘT LẦN: clone Body, cài thư viện của Body (đúng pnpm-lock), PostgreSQL portable + cầu WebSocket, chứng chỉ TLS tạm cho 127.0.0.1, tệp Excel mẫu.
# Mọi thứ nằm trong một thư mục NGOÀI repo (mặc định ~\anser-demo, đổi bằng -Goc hay biến ANSER_DEMO). Cần: git, Node >= 22.18 (kèm corepack, npm), Python đã cài requirements.txt của Brain, openssl (có sẵn trong Git for Windows).
#   powershell -ExecutionPolicy Bypass -File offline_training\demo_mot_may\cai_demo.ps1
param([string]$Goc = '')
$ErrorActionPreference = 'Stop'
if (-not $Goc) { $Goc = if ($env:ANSER_DEMO) { $env:ANSER_DEMO } else { Join-Path $HOME 'anser-demo' } }
$brain = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
foreach ($d in 'db', 'ui', 'cert', 'log', 'file_mau') { New-Item -ItemType Directory -Force (Join-Path $Goc $d) | Out-Null }

function Invoke-Lenh([scriptblock]$lenh, [string]$ten) {
    $ErrorActionPreference = 'Continue'
    & $lenh 2>&1 | ForEach-Object { "$_" } | Select-Object -Last 6 | Write-Host
    if ($LASTEXITCODE -ne 0) { throw "$ten hỏng (mã $LASTEXITCODE)" }
}

Write-Host '[1/5] Body'
if (-not (Test-Path "$Goc\body\frontend\package.json")) { Invoke-Lenh { git clone --depth 1 https://github.com/ANSER-Logistics/ANSER-logistics-body.git "$Goc\body" } 'git clone Body' }
$env:COREPACK_HOME = Join-Path $Goc 'corepack'; $env:COREPACK_ENABLE_DOWNLOAD_PROMPT = '0'
Push-Location "$Goc\body\frontend"
try { Invoke-Lenh { corepack pnpm install --frozen-lockfile --store-dir "$Goc\pnpm-store" } 'pnpm install' } finally { Pop-Location }

Write-Host '[2/5] PostgreSQL portable và cầu WebSocket'
if (-not (Test-Path "$Goc\db\package.json")) { '{"name":"anser-demo-db","private":true,"type":"module"}' | Set-Content -Encoding ascii "$Goc\db\package.json" }
Push-Location "$Goc\db"
try { Invoke-Lenh { npm install --no-audit --no-fund embedded-postgres@17.12.0-beta.19 ws@8.23.1 pg@8.23.1 } 'npm install (db)' } finally { Pop-Location }

Write-Host '[3/5] playwright-core cho chụp màn hình (dùng Chrome đã cài, không tải trình duyệt)'
if (-not (Test-Path "$Goc\ui\package.json")) { '{"name":"anser-demo-ui","private":true,"type":"module"}' | Set-Content -Encoding ascii "$Goc\ui\package.json" }
Push-Location "$Goc\ui"
try { Invoke-Lenh { npm install --no-audit --no-fund playwright-core@1.56.1 } 'npm install (ui)' } finally { Pop-Location }

Write-Host '[4/5] Chứng chỉ TLS tạm (14 ngày, chỉ cho 127.0.0.1, khoá nằm ngoài repo)'
$openssl = (Get-Command openssl -ErrorAction SilentlyContinue).Source
if (-not $openssl) {
    $git = (Get-Command git).Source
    foreach ($ung in 'usr\bin\openssl.exe', 'mingw64\bin\openssl.exe') {
        $thu = Join-Path (Split-Path (Split-Path $git)) $ung
        if (Test-Path $thu) { $openssl = $thu; break }
    }
}
if (-not $openssl) { throw 'Không tìm thấy openssl (cài Git for Windows hoặc thêm openssl vào PATH).' }
if (-not (Test-Path "$Goc\cert\cert.pem")) {
    Invoke-Lenh { & $openssl req -x509 -newkey rsa:2048 -nodes -days 14 -keyout "$Goc\cert\key.pem" -out "$Goc\cert\cert.pem" -subj '/CN=anser-demo-cuc-bo' -addext 'subjectAltName=IP:127.0.0.1,DNS:localhost' } 'openssl'
}

Write-Host '[5/5] Tệp Excel mẫu (hư cấu)'
Push-Location $brain
try { Invoke-Lenh { python sample_data\make_sample_data.py } 'sinh tệp mẫu' } finally { Pop-Location }
Copy-Item "$brain\sample_data\*_mau*.xlsx" "$Goc\file_mau\" -Force
Write-Host "Xong. Bật demo: powershell -ExecutionPolicy Bypass -File $PSScriptRoot\bat_demo.ps1"
