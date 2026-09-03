# 注册 Windows 任务计划程序（无需额外依赖，等价于规范里的三条 cron）
# 需以当前用户运行；如需管理员权限请以管理员打开 PowerShell。
$ErrorActionPreference = "Stop"

# 用 D:\anaconda 的 Python；若没有则回退系统 python
$py = "D:\anaconda\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Add-Task([string]$name, [string]$sc, [string]$d, [string]$st, [string]$job) {
    $cmd = "`"$py`" `"$dir\agent.py`" $job"
    schtasks /Create /F /TN $name /TR $cmd /SC $sc /D $d /ST $st
    Write-Host "已注册: $name  ($sc / $d / $st  -> $job)"
}

# 每日收盘后（工作日 15:30）
Add-Task "AshareDaily" "WEEKLY" "MON,TUE,WED,THU,FRI" "15:30" "daily"
# 双周：每月 1 日与 16 日 20:00
Add-Task "AshareBiweekly1" "MONTHLY" "1" "20:00" "biweekly"
Add-Task "AshareBiweekly16" "MONTHLY" "16" "20:00" "biweekly"
# 每周五 16:00
Add-Task "AshareWeeklyFri" "WEEKLY" "FRI" "16:00" "weekly"

Write-Host "全部注册完成。可分别用 tasklist / schtasks /Query /TN <任务名> 核对。"
