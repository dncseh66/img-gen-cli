@echo off
setlocal
cd /d "%~dp0"

set "VENV_DIR=.venv"
set "STAMP=%VENV_DIR%\.installed"

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PY=python"
    ) else (
        echo Python is not installed or not on PATH.
        echo Please install Python 3 from https://www.python.org/downloads/ and re-run this file.
        pause
        exit /b 1
    )
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

if not exist "%STAMP%" (
    echo Installing dependencies...
    "%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
    "%VENV_DIR%\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Dependency installation failed.
        pause
        exit /b 1
    )
    echo installed > "%STAMP%"
)

"%VENV_DIR%\Scripts\python.exe" cli.py
set "EXITCODE=%ERRORLEVEL%"

echo.
pause
exit /b %EXITCODE%
