@echo off
cd /d "%~dp0"
set "PYTHON=%USERPROFILE%\Documents\PythonEnvs\pi-data-viewer\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Python interpreter not found: "%PYTHON%"
    pause
    exit /b 1
)

"%PYTHON%" "%~dp0app.py"
pause
