# Tắt demo: Body, Brain, rồi cơ sở dữ liệu (dừng PostgreSQL đúng cách để lần sau bật lại không hỏng dữ liệu).
param([string]$Goc = '')
if (-not $Goc) { $Goc = if ($env:ANSER_DEMO) { $env:ANSER_DEMO } else { Join-Path $HOME 'anser-demo' } }
$log = Join-Path $Goc 'log'
$tep = "$log\pids.json"
# Chỉ tắt tiến trình ĐÚNG LÀ của demo: sau khi máy khởi động lại, số PID cũ trong pids.json có thể đã thuộc chương trình khác.
$dau = @{ body = 'next\\dist\\bin\\next start'; brain = 'uvicorn src\.api\.main:app'; db = 'chay_db\.mjs' }
function Stop-NeuLaCuaDemo([int]$id, [string]$ten) {
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
    if (-not $p) { return }
    if ($p.CommandLine -match $dau[$ten]) { taskkill /PID $id /T /F | Out-Null; Write-Host "Đã tắt $ten" }
    else { Write-Host "Bỏ qua PID $id ($($p.Name)): không còn là tiến trình $ten của demo" }
}
if (Test-Path $tep) {
    $pids = Get-Content $tep -Raw | ConvertFrom-Json
    foreach ($ten in 'body', 'brain') { if ($pids.$ten) { Stop-NeuLaCuaDemo $pids.$ten $ten } }
}
$pgctl = "$Goc\db\node_modules\@embedded-postgres\windows-x64\native\bin\pg_ctl.exe"
if (Test-Path "$Goc\pgdata\postmaster.pid") {
    & $pgctl stop -D "$Goc\pgdata" -m fast 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Write-Host 'Đã dừng PostgreSQL' } else { Write-Host 'PostgreSQL không chạy (tệp khoá cũ còn lại; bat_demo.ps1 tự gỡ)' }
}
if (Test-Path $tep) {
    $pids = Get-Content $tep -Raw | ConvertFrom-Json
    if ($pids.db) { Stop-NeuLaCuaDemo $pids.db 'db' }
    Remove-Item $tep
}
