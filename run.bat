@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYW=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\pythonw.exe"
if exist "%PYW%" (
    start "" "%PYW%" "main.py"
) else (
    start "" pythonw "main.py"
)
