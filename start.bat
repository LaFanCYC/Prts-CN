@echo off
cd /d "%~dp0"
echo ================================================
echo GradeAI - Auto Start
echo ================================================
echo.

echo Stopping previous processes...
taskkill /f /im python.exe 2>nul

echo.
echo Starting service...
start "GradeAI" cmd /k "python run.py"

echo.
echo Please visit: http://127.0.0.1:5000
echo ================================================
