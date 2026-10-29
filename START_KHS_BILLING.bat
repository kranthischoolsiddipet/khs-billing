@echo off
title Kranthi High School - Billing & Receipt Software
cd /d "%~dp0"

echo ==========================================================
echo        KRANTHI HIGH SCHOOL - BILLING & RECEIPT PORTAL
echo ==========================================================
echo.

:: 1. Fast Silent Cloud Update Check (Takes 1-2 seconds if online)
if exist "%~dp0cloud_updater.py" (
    "%~dp0pyruntime\python.exe" "%~dp0cloud_updater.py"
)

echo Starting local server on http://localhost:8000 ...
echo Close this window to stop the server.
echo.

start "" "http://localhost:8000"
"%~dp0pyruntime\python.exe" main.py
pause
