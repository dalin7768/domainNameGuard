@echo off
timeout /t 2 /nobreak > nul
cd /d "%~dp0"
python src/main.py
pause