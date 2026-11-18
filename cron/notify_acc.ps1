# Baca xlsx lokal, kirim notifikasi Windows bila ada lowongan baru di-ACC.
$ErrorActionPreference = "SilentlyContinue"
$py = "C:\Users\fathi\AppData\Local\hermes\installs\7a45bc3a55e1c6b9\environments\26ce6ee9888f4a5c85911b930b8eb6ee\venv\Scripts\python.exe"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$out = & $py (Join-Path $scriptDir "list_acc.py")
if (-not $out) { exit }

$total = 0
$lines = @()
foreach ($line in $out) {
    if ($line -match '^__TOTAL__(\d+)$') {
        $total = [int]$Matches[1]
        continue
    }
    $lines += $line
}

if ($total -eq 0) { exit }

$first = $lines[0] -split '\|'
$title = "JobBot: $total lowongan di-ACC"
$msg = "Contoh: $($first[0]) - $($first[1])"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.Visible = $true
$notify.BalloonTipTitle = $title
$notify.BalloonTipText = "$msg`nJalankan: python main.py apply-semua"
$notify.ShowBalloonTip(10000)
Start-Sleep -Seconds 12
$notify.Dispose()
