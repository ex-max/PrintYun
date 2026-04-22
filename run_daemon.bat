@echo off
chcp 65001 >nul
setlocal

REM ======================================================
REM  自动打印守护进程启动脚本
REM  - 轮询 Order 表，把已支付未打印的订单送到打印机
REM  - 需要先在 .env 里配置 PRINTER_NAME 和 SUMATRA_PATH
REM ======================================================

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo [x] 未找到 venv
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

if not exist ".env" (
    echo [!] 未找到 .env 文件，请先配置
    pause
    exit /b 1
)

echo [OK] 正在启动自动打印守护进程 ...
echo.
python printer_daemon.py

endlocal
pause
