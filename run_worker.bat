@echo off
chcp 65001 >nul
setlocal

REM ======================================================
REM  Redis 队列转 PDF worker 启动脚本
REM  需要与 run.bat 分开开一个 cmd 窗口执行
REM ======================================================

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo [x] 未找到 venv
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [OK] 正在启动 PDF 转换 worker ...
echo.
python worker.py

endlocal
pause
