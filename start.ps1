# GradeAI 一键启动脚本 (PowerShell版)

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "GradeAI 智能成绩分析系统 - 一键启动脚本" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# 结束之前的Python进程
Write-Host "[1/3] 结束之前的Python进程..." -ForegroundColor Yellow

# 查找占用5000端口的进程
$process = Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | Where-Object {$_.State -eq "Listen"}

if ($process) {
    $pid = $process.OwningProcess
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Write-Host "已结束旧进程 (PID: $pid)" -ForegroundColor Green
} else {
    Write-Host "没有发现旧进程" -ForegroundColor Green
}

# 结束所有 python run.py 进程
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 1

# 启动服务
Write-Host ""
Write-Host "[2/3] 启动服务..." -ForegroundColor Yellow

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; python run.py"

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "服务已启动！" -ForegroundColor Green
Write-Host "请访问: http://127.0.0.1:5000" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

Read-Host "按回车键退出"
