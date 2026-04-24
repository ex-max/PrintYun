@echo off
chcp 65001 >nul
setlocal

REM ======================================================
REM  云打印项目一键启动脚本
REM  - 自动激活 venv
REM  - .env 由 python-dotenv 自动加载（Flask 启动时）
REM  - 使用 waitress 多线程 WSGI 服务器（4 线程）
REM ======================================================

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo [x] 未找到 venv，正在创建...
    python -m venv venv
    if errorlevel 1 (
        echo [x] 创建 venv 失败，请检查 Python 是否已安装
        pause
        exit /b 1
    )
)

call venv\Scripts\activate.bat

REM 确保 python-dotenv 已安装（Flask 靠它自动读 .env）
python -c "import dotenv" 2>nul
if errorlevel 1 (
    echo [*] 安装 python-dotenv ...
    pip install python-dotenv
)

REM 确保 waitress 已安装
python -c "import waitress" 2>nul
if errorlevel 1 (
    echo [*] 安装 waitress ...
    pip install waitress
)

if not exist ".env" (
    echo [!] 未找到 .env 文件
    echo     请复制 .env.example 为 .env 并填入真实配置
    pause
    exit /b 1
)

echo [OK] 正在启动 Flask (waitress, 4 线程) ...
echo.
python -c "from waitress import serve; from app import app; print('Serving on http://0.0.0.0:8001'); serve(app, host='0.0.0.0', port=8001, threads=4)"

endlocal
pause
