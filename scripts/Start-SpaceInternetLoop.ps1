# Manual workday cook. Do not register a scheduled task (PC-AUTOMATION-HOLD).
param(
    [int]$Hours = 9,
    [switch]$Publish
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path (Join-Path $Root "lab\WORKDAY.md"))) {
    $Root = Join-Path $env:USERPROFILE "vela"
}
$Stop = Join-Path $Root "lab\STOP"
$Py = "py"
$Deadline = (Get-Date).AddHours($Hours)
Set-Location $Root
$env:PYTHONPATH = $Root
$env:PYTHONDONTWRITEBYTECODE = "1"

Write-Host "[LOOP] space internet cook root=$Root until $Deadline"
Write-Host "[LOOP] PC stays ON + LOCKED + AC. Touch lab\\STOP to halt."

while ((Get-Date) -lt $Deadline) {
    if (Test-Path $Stop) {
        Write-Host "[LOOP] STOP file. Exit."
        break
    }
    & $Py -3 (Join-Path $Root "scripts\space_internet_loop.py") --once
    $code = $LASTEXITCODE
    if ($Publish) {
        & $Py -3 (Join-Path $Root "scripts\space_internet_loop.py") --publish
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[LOOP] publish sanitizer failed exit=$LASTEXITCODE. Skip deploy."
        } else {
            $deploy = Join-Path $env:USERPROFILE "orbitstack\deploy.ps1"
            if (Test-Path $deploy) {
                Write-Host "[LOOP] publish orbitstack progress"
                powershell -ExecutionPolicy Bypass -File $deploy
            }
        }
    }
    $backlog = Get-Content (Join-Path $Root "lab\BACKLOG.json") -Raw
    if ($backlog -notmatch '"status": "pending"') {
        Write-Host "[LOOP] no pending backlog items. Idle 20m."
        Start-Sleep -Seconds 1200
        continue
    }
    if ($code -ne 0) {
        Write-Host "[LOOP] tick failed exit=$code. Back off 10m."
        Start-Sleep -Seconds 600
        continue
    }
    Start-Sleep -Seconds 90
}

Write-Host "[LOOP] done. Read lab\\STATE.md"
