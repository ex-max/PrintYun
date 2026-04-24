@echo off
chcp 65001 >nul
title 云打印虚拟打印机安装

echo ========================================
echo   云打印虚拟打印机 - 安装程序
echo ========================================
echo.

:: 创建目录
echo [1] 创建输出目录...
if not exist "C:\PrintJobs" mkdir "C:\PrintJobs"
if not exist "C:\PrintJobs\temp" mkdir "C:\PrintJobs\temp"
echo   OK

:: 更新 PAYPRINT: 端口指向我们的脚本
echo [2] 配置 Redmon 端口 PAYPRINT: ...
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Print\Monitors\Redirected Port\Ports\PAYPRINT:" /v Command /t REG_SZ /d "E:\Project\Print\printyun-master\venv\Scripts\python.exe" /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Print\Monitors\Redirected Port\Ports\PAYPRINT:" /v Arguments /t REG_SZ /d "\"E:\Project\Print\printyun-master\local_printer\install\save_job.py\"" /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Print\Monitors\Redirected Port\Ports\PAYPRINT:" /v Output /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Print\Monitors\Redirected Port\Ports\PAYPRINT:" /v ShowWindow /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Print\Monitors\Redirected Port\Ports\PAYPRINT:" /v RunUser /t REG_DWORD /d 0 /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Print\Monitors\Redirected Port\Ports\PAYPRINT:" /v Delay /t REG_DWORD /d 300 /f >nul 2>&1
if %errorlevel% equ 0 (echo   OK 端口已配置) else (echo   ERROR 端口配置失败)

:: 重启 Spooler
echo [3] 重启打印服务...
net stop spooler >nul 2>&1
timeout /t 2 /nobreak >nul
net start spooler >nul 2>&1
timeout /t 3 /nobreak >nul
echo   OK

:: 添加打印机 (使用 rundll32 printui.dll)
echo [4] 添加打印机 "云打印-付费打印" ...
rundll32 printui.dll,PrintUIEntry /dl /n "云打印-付费打印" /q >nul 2>&1
timeout /t 1 /nobreak >nul
rundll32 printui.dll,PrintUIEntry /if /b "云打印-付费打印" /f "%windir%\inf\ntprint.inf" /r "PAYPRINT:" /m "Microsoft PS Class Driver" /z
if %errorlevel% equ 0 (
    echo   OK 打印机已安装
) else (
    echo   方法1失败，尝试其他驱动...
    rundll32 printui.dll,PrintUIEntry /if /b "云打印-付费打印" /f "%windir%\inf\ntprint.inf" /r "PAYPRINT:" /m "Generic / Text Only" /z
    if %errorlevel% equ 0 (
        echo   OK 使用 Generic 驱动
    ) else (
        echo   ERROR 添加打印机失败
    )
)

echo.
echo ========================================
echo   检查结果：
echo ========================================
echo.
echo 已安装的打印机:
wmic printer get name,portname /format:list 2>nul | findstr /i "Name Port"
echo.
echo ========================================
pause
