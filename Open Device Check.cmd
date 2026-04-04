@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "ROOT_LAUNCHER=%PROJECT_ROOT%\src\occams_beard\root_launcher.py"
set "PROJECT_PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"

if exist "%PROJECT_PYTHON%" (
  "%PROJECT_PYTHON%" "%ROOT_LAUNCHER%" --project-root "%PROJECT_ROOT%" --shutdown-on-browser-close %*
  exit /b %errorlevel%
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%ROOT_LAUNCHER%" --project-root "%PROJECT_ROOT%" --shutdown-on-browser-close %*
  exit /b %errorlevel%
)

python "%ROOT_LAUNCHER%" --project-root "%PROJECT_ROOT%" --shutdown-on-browser-close %*
exit /b %errorlevel%
