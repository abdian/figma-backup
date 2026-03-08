@echo off
REM Figma Backup -- Windows launcher
REM Usage: figma-backup.bat [options]

cd /d "%~dp0"

REM -- Find Python automatically --
set "PYTHON="

REM 1) Try 'py' launcher (most reliable on Windows)
py --version >nul 2>&1 && set "PYTHON=py" && goto :found

REM 2) Try 'python' in PATH
python --version >nul 2>&1 && set "PYTHON=python" && goto :found

REM 3) Try 'python3' in PATH
python3 --version >nul 2>&1 && set "PYTHON=python3" && goto :found

REM 4) Search common install locations
for %%V in (315 314 313 312 311 310 39 38) do (
    if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" (
        set "PYTHON=%LocalAppData%\Programs\Python\Python%%V\python.exe"
        goto :found
    )
    if exist "C:\Python%%V\python.exe" (
        set "PYTHON=C:\Python%%V\python.exe"
        goto :found
    )
    if exist "C:\Program Files\Python%%V\python.exe" (
        set "PYTHON=C:\Program Files\Python%%V\python.exe"
        goto :found
    )
)

REM 5) Search AppData (non-standard installs)
for /f "delims=" %%F in ('dir /b /s "%LocalAppData%\Python\*python.exe" 2^>nul') do (
    set "PYTHON=%%F"
    goto :found
)

REM Nothing found
echo.
echo  [ERROR] Python is required but not found anywhere.
echo.
echo  Install it from https://www.python.org/downloads/
echo  Make sure to check "Add Python to PATH" during installation.
echo.
goto :done

:found
echo  Found Python: & "%PYTHON%" --version

REM -- Create venv if needed --
if not exist ".venv\Scripts\activate.bat" (
    echo  Setting up virtual environment...
    "%PYTHON%" -m venv .venv
    if not exist ".venv\Scripts\activate.bat" (
        echo.
        echo  [ERROR] Failed to create virtual environment.
        echo.
        goto :done
    )
)

REM -- Activate venv --
call .venv\Scripts\activate.bat

REM -- Install dependencies --
echo  Installing dependencies...
"%PYTHON%" -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Failed to install dependencies.
    echo.
    goto :done
)

REM -- Check .env --
if not exist ".env" (
    echo.
    echo  [ERROR] No .env file found!
    echo  Copy .env.example to .env and fill in your values:
    echo    copy .env.example .env
    echo.
    goto :done
)

REM -- Run --
echo.
"%PYTHON%" -m figma_backup %*

:done
echo.
echo  Press any key to close...
pause >nul
