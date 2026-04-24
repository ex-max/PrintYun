@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================
echo   云打印 - 本地打印拦截器
echo ============================
echo.
echo 监控目录: C:\PrintJobs
echo 启动中...
echo.
venv\Scripts\python.exe local_printer\main.py
pause
