@echo off
cd /d "%~dp0"
python -m uvicorn main:app --port 8896 --host 0.0.0.0
pause
