@echo off
setlocal enabledelayedexpansion
title Setup KHS Billing Shortcuts
cd /d "%~dp0"

echo ==========================================================
echo        KRANTHI HIGH SCHOOL - SHORTCUT SETUP WIZARD
echo ==========================================================
echo.

:: 1. Ensure khs_logo.ico exists
if not exist "%~dp0khs_logo.ico" (
    echo Generating high-resolution school logo icon...
    if exist "%~dp0pyruntime\python.exe" (
        "%~dp0pyruntime\python.exe" "%~dp0ensure_icon.py"
    )
)

:: 2. Execute PowerShell script for robust shortcut creation
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_shortcuts.ps1"

echo.
echo ==========================================================
echo [SUCCESS] Shortcuts configured with Kranthi High School Logo!
echo.
echo - Desktop Shortcut: 'KHS Billing'
echo - Start Menu Shortcut: 'Kranthi High School \ KHS Billing'
echo.
echo * Tip: You can also right-click the Desktop shortcut 
echo        and click 'Pin to taskbar' anytime!
echo ==========================================================
echo.
pause
