@echo off
setlocal
cd /d "%~dp0"

set "ENV_DIR=%USERPROFILE%\Documents\PythonEnvs\pi-data-viewer"
set "PYTHON=%ENV_DIR%\Scripts\python.exe"
set "PI_CONFIG=%~dp0PIReader\config.txt"
set "PI_READER_EXE=%~dp0PIReader\PIReader.exe"
set "PORT=8050"

if exist "config\config.yaml" for /f "tokens=2" %%P in ('findstr /r /c:"^[ ]*port:" "config\config.yaml" 2^>nul') do set "PORT=%%P"
set "APP_URL=http://127.0.0.1:%PORT%/"

set "SYSTEM_PYTHON="
where python >nul 2>&1
if not errorlevel 1 set "SYSTEM_PYTHON=python"
if defined SYSTEM_PYTHON goto :check_system_python

where py >nul 2>&1
if not errorlevel 1 set "SYSTEM_PYTHON=py -3"
if defined SYSTEM_PYTHON goto :check_system_python
goto :python_missing

:check_system_python
%SYSTEM_PYTHON% --version >nul 2>&1
if errorlevel 1 goto :python_missing

if exist "%PYTHON%" goto :check_dependencies

echo Creating shared Python environment...
%SYSTEM_PYTHON% -m venv "%ENV_DIR%"
if errorlevel 1 goto :venv_failed
if not exist "%PYTHON%" goto :venv_failed

:check_dependencies
if not exist "requirements.txt" goto :requirements_missing

echo Checking Python dependencies...
"%PYTHON%" -c "import dash, pandas, numpy, plotly, openpyxl" >nul 2>&1
if not errorlevel 1 goto :check_pi_reader

echo Installing Python dependencies...
"%PYTHON%" -m pip install -r "requirements.txt"
if errorlevel 1 goto :dependencies_failed

"%PYTHON%" -c "import dash, pandas, numpy, plotly, openpyxl" >nul 2>&1
if errorlevel 1 goto :dependencies_failed

:check_pi_reader
if exist "%PI_READER_EXE%" goto :start_app
echo.
echo PIReader.exe not found.
echo Please build PIReader before using PI Server mode.

:start_app
echo.
echo Starting PI Data Viewer...
echo Open this URL if the browser does not open automatically:
echo %APP_URL%

start "" powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "$url='%APP_URL%'; for($i=0; $i -lt 120; $i++){ try { $response=Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 1; if($response.StatusCode -ge 200 -and $response.StatusCode -lt 400){ Start-Process $url; exit 0 } } catch {}; Start-Sleep -Milliseconds 250 }; Write-Error ('Web service did not become ready: ' + $url); exit 1"

"%PYTHON%" "%~dp0app.py"
set "APP_EXIT=%errorlevel%"
pause
exit /b %APP_EXIT%

:python_missing
echo Python interpreter was not found.
echo.
echo Please install Python 3.10 or later,
echo then run this script again.
pause
exit /b 1

:venv_failed
echo Failed to create the shared Python environment:
echo %ENV_DIR%
pause
exit /b 1

:requirements_missing
echo requirements.txt was not found in the project directory.
pause
exit /b 1

:dependencies_failed
echo Failed to install or verify Python dependencies.
pause
exit /b 1
