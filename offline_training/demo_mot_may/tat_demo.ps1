# Tắt demo: Body, Brain, rồi cơ sở dữ liệu (dừng PostgreSQL đúng cách để lần sau bật lại không hỏng dữ liệu).
param([string]$Goc = '')
if (-not $Goc) { $Goc = if ($env:ANSER_DEMO) { $env:ANSER_DEMO } else { Join-Path $HOME 'anser-demo' } }
$log = Join-Path $Goc 'log'
$tep = "$log\pids.json"
if (Test-Path $tep) {
    $pids = Get-Content $tep -Raw | ConvertFrom-Json
    foreach ($ten in 'body', 'brain') {
        $id = $pids.$ten
        if ($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) { taskkill /PID $id /T /F | Out-Null; Write-Host "Đã tắt $ten" }
    }
}
$pgctl = "$Goc\db\node_modules\@embedded-postgres\windows-x64\native\bin\pg_ctl.exe"
if (Test-Path "$Goc\pgdata\postmaster.pid") { & $pgctl stop -D "$Goc\pgdata" -m fast | Out-Null; Write-Host 'Đã dừng PostgreSQL' }
if (Test-Path $tep) {
    $pids = Get-Content $tep -Raw | ConvertFrom-Json
    if ($pids.db -and (Get-Process -Id $pids.db -ErrorAction SilentlyContinue)) { taskkill /PID $pids.db /T /F | Out-Null; Write-Host 'Đã tắt cầu cơ sở dữ liệu' }
    Remove-Item $tep
}
