# Register Windows Scheduled Tasks for daily stock research reports.
# Runs as current user (only when logged on). Use an admin shell to run whether logged in or not.
$ErrorActionPreference = "Stop"
$py = "D:\anaconda\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $dir) { $dir = Get-Location }

function Add-Task([string]$name, [string]$sc, [string]$d, [string]$st, [string]$job) {
    $cmd = "`"$py`" `"$dir\agent.py`" $job"
    $res = schtasks /Create /F /TN $name /TR $cmd /SC $sc /D $d /ST $st 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Host "OK: $name ($sc / $d / $st -> $job)" }
    else { Write-Host "FAIL: $name -> $res" }
}

Add-Task "AshareMorning"    "WEEKLY"  "MON,TUE,WED,THU,FRI" "07:00" "morning"
Add-Task "AshareDaily"      "WEEKLY"  "MON,TUE,WED,THU,FRI" "20:00" "daily"
Add-Task "AshareBiweekly1"  "MONTHLY" "1"                   "20:00" "biweekly"
Add-Task "AshareBiweekly16" "MONTHLY" "16"                  "20:00" "biweekly"
Add-Task "AshareWeeklyFri"  "WEEKLY"  "FRI"                 "16:00" "weekly"
Write-Host "DONE. Check: schtasks /Query /FO LIST | findstr Ashare"