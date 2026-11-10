@echo off
cd /d "%~dp0"
python app.pyw
if errorlevel 1 pause
