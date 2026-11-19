@echo off
setlocal enabledelayedexpansion

title ServerGen AI -- Master Runner
color 0B

:: Ensure we are in script root directory
cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "RUFF=%~dp0.venv\Scripts\ruff.exe"

if not exist "%PYTHON%" (
    echo [ERROR] Virtual environment not found at %PYTHON%
    echo Please create and setup your virtual environment first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -e ".[dev]"
    echo.
    pause
    exit /b 1
)

:: Ensure .env exists
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] Initializing .env configuration from .env.example...
        copy /y ".env.example" ".env" >nul
        echo [OK] Created .env configuration file.
    )
)

:: Parse Command
if /i "%~1"=="check" goto :do_check
if /i "%~1"=="lint" goto :do_lint
if /i "%~1"=="test" goto :do_test
if /i "%~1"=="seed" goto :do_seed
if /i "%~1"=="diagrams" goto :do_diagrams
if /i "%~1"=="help" goto :do_help

:do_start
echo ======================================================================
echo                     SERVERGEN AI -- LOCAL RUNTIME
echo            Secure Enterprise AI Automation with Local LLM
echo ======================================================================
echo.

:: Check Ollama
echo [1/2] Checking Local Ollama Runtime...
curl.exe -s http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [INFO] Ollama service is not running on port 11434. Starting in background...
    set "OLLAMA_EXE="
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles%\Ollama\ollama.exe"
    
    if defined OLLAMA_EXE (
        start "Ollama Service" /min "!OLLAMA_EXE!" serve
        timeout /t 3 /nobreak >nul
    ) else (
        echo [WARNING] Ollama executable not found. Please start Ollama manually.
    )
) else (
    echo [OK] Ollama is active on http://127.0.0.1:11434
)
echo.

:: Start FastAPI
echo [2/2] Launching ServerGen AI FastAPI Backend...
echo.
echo * Test & Demo Playground : http://127.0.0.1:8000/test
echo * Interactive API Docs  : http://127.0.0.1:8000/docs
echo * Health Status Check   : http://127.0.0.1:8000/api/v1/health
echo.
"%PYTHON%" -m uvicorn src.app:app --host 127.0.0.1 --port 8000 --reload
exit /b %ERRORLEVEL%

:do_check
echo ======================================================================
echo          SERVERGEN AI -- SYSTEM VERIFICATION & CHECKS
echo ======================================================================
echo.
echo [1/3] Running Ruff Linter...
"%RUFF%" check src tests scripts
if errorlevel 1 (
    echo [FAIL] Ruff linter found issues.
    exit /b 1
)
echo [PASS] Linter checks passed cleanly.
echo.
echo [2/3] Verifying Database Seeding...
"%PYTHON%" -c "from src.core.database import get_engine; print('[OK] Database engine ready')"
echo.
echo [3/3] Running 5-Stage System Verification...
"%PYTHON%" scripts/verify_all_5_tests.py
exit /b %ERRORLEVEL%

:do_lint
"%RUFF%" check src tests scripts
exit /b %ERRORLEVEL%

:do_test
echo [INFO] Running Pytest Unit Test Suite...
"%PYTHON%" -m pytest tests/unit -v
exit /b %ERRORLEVEL%

:do_seed
echo [INFO] Seeding Database (roles, permissions, test accounts)...
"%PYTHON%" -m scripts.seed_db
exit /b %ERRORLEVEL%

:do_diagrams
echo [INFO] Generating High-Resolution System Architecture Diagrams...
"%PYTHON%" scripts/generate_diagrams.py
exit /b %ERRORLEVEL%

:do_help
echo ServerGen AI CLI Runner
echo Commands:
echo   run.bat          - Launch Ollama and start FastAPI backend server (default)
echo   run.bat check    - Run linting and 5-stage core platform verification
echo   run.bat test     - Run unit test suite
echo   run.bat seed     - Re-seed database with default roles and test accounts
echo   run.bat diagrams - Generate 7-page system architecture diagrams PDF
exit /b 0
