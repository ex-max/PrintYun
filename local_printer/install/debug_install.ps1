# 调试安装脚本 - 以管理员运行
$ErrorActionPreference = "Continue"

Write-Host "=== 已安装驱动 ===" -ForegroundColor Cyan
Get-PrinterDriver | Select-Object Name | Format-Table

Write-Host "=== 已有端口 ===" -ForegroundColor Cyan
Get-PrinterPort | Where-Object { $_.Name -like "*PAY*" -or $_.Name -like "*RPT*" -or $_.Name -like "*Redirect*" } | Format-Table Name, Description

Write-Host "=== 更新 PAYPRINT: 端口 ===" -ForegroundColor Yellow
$portPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Print\Monitors\Redirected Port\Ports\PAYPRINT:"
Set-ItemProperty -Path $portPath -Name "Command" -Value "E:\Project\Print\printyun-master\venv\Scripts\python.exe" -Type String
Set-ItemProperty -Path $portPath -Name "Arguments" -Value """E:\Project\Print\printyun-master\local_printer\install\save_job.py""" -Type String
Write-Host "  OK 端口已更新" -ForegroundColor Green

Write-Host "=== 重启 Spooler ===" -ForegroundColor Yellow
Restart-Service Spooler -Force
Start-Sleep 3
Write-Host "  OK" -ForegroundColor Green

Write-Host "=== 尝试添加打印机 ===" -ForegroundColor Yellow

# 先尝试 Microsoft PS Class Driver
$drivers = @(
    "Microsoft PS Class Driver",
    "Microsoft Print To PDF",
    "Generic / Text Only"
)

$printerName = "云打印-付费打印"
Remove-Printer -Name $printerName -ErrorAction SilentlyContinue

foreach ($driverName in $drivers) {
    Write-Host "  尝试驱动: $driverName" -ForegroundColor Cyan
    try {
        $existing = Get-PrinterDriver -Name $driverName -ErrorAction SilentlyContinue
        if (-not $existing) {
            Add-PrinterDriver -Name $driverName -ErrorAction Stop
        }
        Add-Printer -Name $printerName -PortName "PAYPRINT:" -DriverName $driverName -ErrorAction Stop
        Write-Host "  SUCCESS! 使用驱动: $driverName" -ForegroundColor Green
        break
    } catch {
        Write-Host "  失败: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== 最终打印机列表 ===" -ForegroundColor Cyan
Get-Printer | Format-Table Name, PortName, DriverName -AutoSize

Read-Host "按 Enter 退出"
