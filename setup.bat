---

### 2. `setup.bat`

Save this as `setup.bat` in the project root (`one-care-hms\setup.bat`):

```bat
@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"
echo ========================================================
echo   OneCare HMS - Local Setup, Migrations and Test Runner
echo ========================================================

set "PY_CMD="
if exist "env\Scripts\python.exe" (
    set "PY_CMD=env\Scripts\python.exe"
) else if exist "..\env\Scripts\python.exe" (
    set "PY_CMD=..\env\Scripts\python.exe"
) else (
    where py >nul 2>&1 && set "PY_CMD=py"
    if not defined PY_CMD (
        where python >nul 2>&1 && set "PY_CMD=python"
    )
)

if not defined PY_CMD (
    echo [ERROR] Python executable not found. Activate your virtual environment or install Python.
    exit /b 1
)

echo Using Python: %PY_CMD%

if exist "backend\requirements.txt" (
    echo [1/5] Installing/verifying Python dependencies...
    "%PY_CMD%" -m pip install -r backend\requirements.txt
    if errorlevel 1 exit /b 1
) else (
    echo [1/5] No backend\requirements.txt found, skipping pip install.
)

echo [2/5] Making migrations for all OneCare HMS apps...
"%PY_CMD%" backend\manage.py makemigrations core accounts tenants licensing clinic pharmacy laboratory --settings=config.settings.dev
if errorlevel 1 exit /b 1

echo [3/5] Applying database migrations...
"%PY_CMD%" backend\manage.py migrate --settings=config.settings.dev
if errorlevel 1 exit /b 1

echo [4/5] Running Django system check...
"%PY_CMD%" backend\manage.py check --settings=config.settings.dev
if errorlevel 1 exit /b 1

echo [5/5] Running pytest suite...
"%PY_CMD%" -m pytest
if errorlevel 1 exit /b 1

echo.
echo ========================================================
echo   Setup complete! Start server with:
echo   %PY_CMD% backend\manage.py runserver --settings=config.settings.dev
echo ========================================================
pause