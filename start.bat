@echo off
cd /d "%~dp0"
set "PYTHON=%USERPROFILE%\Documents\PythonEnvs\pi-data-viewer\Scripts\python.exe"
set "PI_CONFIG=%~dp0PIReader\config.txt"
set "PI_READER_EXE=%~dp0PIReader\PIReader.exe"

if not exist "%PYTHON%" (
    echo Python interpreter not found: "%PYTHON%"
    pause
    exit /b 1
)

if not exist "%PI_READER_EXE%" (
    echo PI mode requires PIReader\build.bat first: "%PI_READER_EXE%"
)

"%PYTHON%" "%~dp0app.py"
pause
