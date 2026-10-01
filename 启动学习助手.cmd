@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -m study_app.launcher
if errorlevel 1 pause
