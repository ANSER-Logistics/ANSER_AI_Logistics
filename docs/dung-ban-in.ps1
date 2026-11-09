# docs/dung-ban-in.ps1 — dựng lại bản HTML và PDF từ file .md nguồn.
#
#     powershell -NoProfile -ExecutionPolicy Bypass -File docs/dung-ban-in.ps1
#
# Chạy từ thư mục gốc repo. Cần Microsoft Edge (hoặc Chrome). Có pandoc thì
# dùng pandoc; không có thì dùng docs/md2html.py (chỉ thư viện chuẩn Python).
#
# VÌ SAO CÓ SCRIPT NÀY
# --------------------
# File .md là nguồn sự thật; .html và .pdf là bản dẫn xuất. Sửa .md rồi quên
# dựng lại thì bản PDF người ta cầm đi họp nói một đằng, repo nói một nẻo —
# đúng kiểu lệch mà AGENTS.md R4 sinh ra để chặn. Chạy script này trong cùng
# PR với mọi lần sửa hai file .md dưới đây.
#
# Hình vẽ nằm ở docs/hinh/*.svg, viết tay, KHÔNG sinh tự động. Sửa sơ đồ thì
# sửa thẳng file .svg.

# KHONG dat ErrorActionPreference = "Stop" o pham vi script, va KHONG dung
# `2>&1` tren lenh native. Windows PowerShell 5.1 boc moi dong stderr cua mot
# .exe thanh ErrorRecord, nen Edge in mot canh bao vo hai ve renderer la ca
# script dung lai du PDF da tao xong. Script tu kiem ket qua bang Test-Path.
$ErrorActionPreference = "Continue"

# Khoa = duong dan .md tinh tu goc repo. Ban in ra docs\ban-in\<ten file>.
# Ghi DUONG DAN chu khong chi ten: tai lieu da doi vao docs/chu-ky-01/ (11/2026)
# va script cu tim o goc repo nen bo qua im lang moi file.
$TaiLieu = [ordered]@{
    "SO_TAY_NGUOI_MOI.md"                    = "ANSER Brain - So tay cho nguoi moi"
    "docs\chu-ky-01\GIAO_VIEC_BRAIN.md"      = "ANSER Brain - Ho so ban giao"
    "docs\chu-ky-01\SRS_CHU_KY_01.md"        = "ANSER - SRS chu ky 01"
    "docs\chu-ky-01\PHAN_VIEC_CHU_KY_01.md"  = "ANSER - Phan viec chu ky 01"
    "docs\chu-ky-01\BAO_CAO_BR04.md"         = "ANSER - Bao cao BR-04"
    "docs\chu-ky-01\BAO_CAO_BR05.md"         = "ANSER - Bao cao BR-05"
    "docs\chu-ky-01\BIEN_BAN_CHU_KY_01.md"   = "ANSER - Bien ban chu ky 01"
}

function Tim-Lenh([string[]]$duongDan, [string]$ten, [bool]$batBuoc = $true) {
    foreach ($p in $duongDan) { if (Test-Path $p) { return $p } }
    $c = Get-Command $ten -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    if ($batBuoc) { throw "Khong tim thay $ten. Cai dat roi chay lai." }
    return $null
}

$pandoc = Tim-Lenh @(
    "$env:LOCALAPPDATA\Pandoc\pandoc.exe",
    "C:\Program Files\Pandoc\pandoc.exe"
) "pandoc" $false
if (-not $pandoc) {
    $python = Tim-Lenh @() "python"
    Write-Host "Khong co pandoc -> dung docs\md2html.py"
}

$trinhDuyet = Tim-Lenh @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) "msedge"

$goc = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $goc
New-Item -ItemType Directory -Force -Path "docs\ban-in" | Out-Null

foreach ($nguon in $TaiLieu.Keys) {
    $md = Join-Path $goc $nguon
    $ten = [System.IO.Path]::GetFileNameWithoutExtension($md)
    if (-not (Test-Path $md)) { Write-Warning "Bo qua: khong thay $nguon"; continue }
    $tieuDe = $TaiLieu[$nguon]

    $html = Join-Path $goc "docs\ban-in\$ten.html"
    $pdf  = Join-Path $goc "docs\ban-in\$ten.pdf"

    # --embed-resources nhung SVG thang vao HTML -> file tu chay duoc, gui di duoc.
    # --resource-path: hinh trong .md tro tuong doi theo thu muc CUA FILE DO
    # (vd ../hinh/05-thu-tu-viec.svg trong docs/chu-ky-01/), khong theo goc repo.
    if ($pandoc) {
        & $pandoc $md -f gfm -t html5 --standalone --embed-resources `
            --resource-path="$(Split-Path $md -Parent)" `
            --toc --toc-depth=3 -V pagetitle="$tieuDe" `
            --css docs/in-pdf.css -o $html
    } else {
        & $python -I docs\md2html.py $md $html $tieuDe docs\in-pdf.css
    }

    if (Test-Path $pdf) { Remove-Item $pdf -Force }
    $url = "file:///" + ($html -replace '\\', '/')
    & $trinhDuyet --headless --disable-gpu --no-pdf-header-footer `
        --print-to-pdf="$pdf" $url 2>$null

    # Edge ghi file xong SAU khi tien trinh tra quyen dieu khien, nen mot
    # Start-Sleep co dinh lam script bao "khong tao ra" trong khi PDF da nam
    # day. Cho tung buoc den khi kich thuoc file thoi tang.
    $truoc = -1
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if (-not (Test-Path $pdf)) { continue }
        $nay = (Get-Item $pdf).Length
        if ($nay -gt 0 -and $nay -eq $truoc) { break }
        $truoc = $nay
    }

    if (Test-Path $pdf) {
        $kb = [math]::Round((Get-Item $pdf).Length / 1KB)
        Write-Host "OK  $ten.html + $ten.pdf ($kb KB)"
    } else {
        Write-Warning "$ten.pdf khong duoc tao ra"
    }
}

Write-Host ""
Write-Host "Ban in nam o: docs\ban-in\"
