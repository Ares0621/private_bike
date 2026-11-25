@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe"
if exist "%PY%" (
    "%PY%" "main.py"
) else (
    python "main.py"
)
pause
