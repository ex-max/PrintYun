# Redmon 虚拟打印机安装 — 详细日志版
# 所有输出写到 C:\PrintJobs\install_log.txt

$ErrorActionPreference = "Continue"
$logFile = "C:\PrintJobs\install_log.txt"
New-Item -ItemType Directory -Path "C:\PrintJobs" -Force | Out-Null

function Log($msg) {
    $line = "$(Get-Date -Format 'HH:mm:ss') $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

Set-Content -Path $logFile -Value "=== 安装开始 ===" -Encoding UTF8

# 1. 已有驱动
Log "--- 已安装的打印机驱动 ---"
Get-PrinterDriver | ForEach-Object { Log "  驱动: $($_.Name)" }

# 2. 更新 PAYPRINT: 端口
Log "--- 更新 PAYPRINT: 端口 ---"
$portPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Print\Monitors\Redirected Port\Ports\PAYPRINT:"
try {
    Set-ItemProperty -Path $portPath -Name "Command" -Value "E:\Project\Print\printyun-master\venv\Scripts\python.exe" -Type String
    Set-ItemProperty -Path $portPath -Name "Arguments" -Value """E:\Project\Print\printyun-master\local_printer\install\save_job.py""" -Type String
    Log "  OK 端口已更新"
} catch {
    Log "  ERROR: $($_.Exception.Message)"
}

# 3. 重启 Spooler
Log "--- 重启 Spooler ---"
Restart-Service Spooler -Force
Start-Sleep 3
Log "  OK Spooler 已重启"

# 4. 检查端口是否被识别
Log "--- 检查端口 ---"
$allPorts = Get-PrinterPort
$allPorts | ForEach-Object { Log "  端口: $($_.Name) | $($_.Description)" }
$payPort = $allPorts | Where-Object { $_.Name -eq "PAYPRINT:" }
if ($payPort) {
    Log "  OK PAYPRINT: 端口已被识别"
} else {
    Log "  WARN PAYPRINT: 未出现在端口列表中"
}

# 5. 添加打印机（使用 rundll32 方式，兼容性最好）
Log "--- 添加打印机 ---"
$printerName = "云打印-付费打印"
Remove-Printer -Name $printerName -ErrorAction SilentlyContinue

# 方法1: 用 rundll32 printui.dll
Log "  方法1: rundll32 printui.dll"
$infPath = "$env:windir\inf\ntprint.inf"
$cmd = "rundll32 printui.dll,PrintUIEntry /if /b `"$printerName`" /f `"$infPath`" /r `"PAYPRINT:`" /m `"Microsoft PS Class Driver`" /z"
Log "  CMD: $cmd"
try {
    $result = cmd /c $cmd 2>&1
    Log "  结果: $result"
} catch {
    Log "  ERROR: $($_.Exception.Message)"
}

# 检查是否成功
Start-Sleep 2
$p = Get-Printer -Name $printerName -ErrorAction SilentlyContinue
if ($p) {
    Log "  SUCCESS! 打印机已安装: $($p.Name) | $($p.PortName) | $($p.DriverName)"
} else {
    Log "  方法1 失败，尝试方法2"
    
    # 方法2: PowerShell Add-Printer
    $drivers = @("Microsoft PS Class Driver", "Microsoft Print To PDF", "Generic / Text Only")
    foreach ($dn in $drivers) {
        Log "  方法2 尝试驱动: $dn"
        try {
            $drv = Get-PrinterDriver -Name $dn -ErrorAction SilentlyContinue
            if (-not $drv) {
                Log "    驱动不存在，尝试安装..."
                Add-PrinterDriver -Name $dn -ErrorAction Stop
            }
            Add-Printer -Name $printerName -PortName "PAYPRINT:" -DriverName $dn -ErrorAction Stop
            Log "  SUCCESS! 使用驱动 $dn"
            break
        } catch {
            Log "    ERROR: $($_.Exception.Message)"
        }
    }
}

# 最终检查
Log "--- 最终打印机列表 ---"
Get-Printer | ForEach-Object { Log "  $($_.Name) | $($_.PortName) | $($_.DriverName)" }

Log "=== 安装结束 ==="
Read-Host "按 Enter 退出"
