# 云打印虚拟打印机 — 卸载脚本
# 以管理员身份运行

#Requires -RunAsAdministrator

$ErrorActionPreference = "SilentlyContinue"

$PrinterName = "云打印-付费打印"
$PortName = "RPT_CloudPrint"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  云打印虚拟打印机 - 卸载程序" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 删除打印机
$printer = Get-Printer -Name $PrinterName -ErrorAction SilentlyContinue
if ($printer) {
    Remove-Printer -Name $PrinterName
    Write-Host "  ✓ 打印机 '$PrinterName' 已删除" -ForegroundColor Green
} else {
    Write-Host "  ⓘ 打印机不存在，跳过" -ForegroundColor Cyan
}

# 删除端口
$port = Get-PrinterPort -Name $PortName -ErrorAction SilentlyContinue
if ($port) {
    Remove-PrinterPort -Name $PortName
    Write-Host "  ✓ 端口 $PortName 已删除" -ForegroundColor Green
} else {
    Write-Host "  ⓘ 端口不存在，跳过" -ForegroundColor Cyan
}

# 清理注册表
$portRegPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Print\Monitors\Redirected Port\Ports\$PortName"
if (Test-Path $portRegPath) {
    Remove-Item -Path $portRegPath -Recurse -Force
    Write-Host "  ✓ 注册表已清理" -ForegroundColor Green
}

# 重启 Spooler
Restart-Service Spooler -Force -ErrorAction SilentlyContinue
Write-Host "  ✓ 打印后台处理程序已重启" -ForegroundColor Green

Write-Host ""
Write-Host "  卸载完成！" -ForegroundColor Green
Write-Host "  注意：C:\PrintJobs 目录未删除，如不需要可手动删除" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Read-Host "按 Enter 退出"
