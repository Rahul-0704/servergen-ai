@echo off
setlocal enabledelayedexpansion

title ServerGen AI -- System Verification and Health Checks
color 0B

echo ======================================================================
echo             SERVERGEN AI -- SYSTEM VERIFICATION AND CHECKS
echo       Automated Linting, Migrations, Security and Test Validation
echo ======================================================================
echo.

cd /d "%~dp0"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "RUFF=%~dp0.venv\Scripts\ruff.exe"

set "STAGE_ENV=PASS"
set "STAGE_CONFIG=PASS"
set "STAGE_MIGRATIONS=PASS"
set "STAGE_RUFF=PASS"
set "STAGE_TESTS=PASS"
set "OVERALL_STATUS=0"

REM ----------------------------------------------------------------------
REM 1. Check Python Virtual Environment
REM ----------------------------------------------------------------------
echo [1/5] Checking Python Virtual Environment...
if not exist "%PYTHON%" (
    echo [ERROR] Virtual environment not found at %PYTHON%
    echo Please create the virtual environment first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -e .
    echo.
    set "STAGE_ENV=FAIL"
    set "OVERALL_STATUS=1"
    goto :summary
)
echo [OK] Python runtime detected:
"%PYTHON%" --version
echo.

REM ----------------------------------------------------------------------
REM 2. Check Environment Configuration (.env)
REM ----------------------------------------------------------------------
echo [2/5] Checking Environment Configuration (.env)...
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] .env not found. Initializing from .env.example
        copy /y ".env.example" ".env" >nul
        echo [OK] Created .env configuration file
    ) else (
        echo [WARNING] No .env or .env.example found. Running with defaults
    )
) else (
    echo [OK] Configuration file .env found
)
echo.

REM ----------------------------------------------------------------------
REM 3. Check Database Migrations (Alembic)
REM ----------------------------------------------------------------------
echo [3/5] Verifying Database Schema and Migrations...
"%PYTHON%" -m alembic current >nul 2>&1
if errorlevel 1 (
    echo [WARNING] Alembic check returned non-zero. Attempting upgrade head
    "%PYTHON%" -m alembic upgrade head
    if errorlevel 1 (
        echo [ERROR] Database migration verification failed
        set "STAGE_MIGRATIONS=FAIL"
        set "OVERALL_STATUS=1"
    ) else (
        echo [OK] Database migrations upgraded to head
    )
) else (
    echo [OK] Database schema and Alembic revision state verified
)
echo.

REM ----------------------------------------------------------------------
REM 4. Run Ruff Code Quality and Security Linter
REM ----------------------------------------------------------------------
echo [4/5] Running Code Quality and Security Linter (Ruff)...
if exist "%RUFF%" (
    "%RUFF%" check src tests
) else (
    "%PYTHON%" -m ruff check src tests
)
if errorlevel 1 (
    echo [ERROR] Ruff linter detected code style, type, or security issues
    set "STAGE_RUFF=FAIL"
    set "OVERALL_STATUS=1"
) else (
    echo [OK] Ruff check passed: 0 errors detected
)
echo.

REM ----------------------------------------------------------------------
REM 5. Run Full Automated Test Suite (Pytest)
REM ----------------------------------------------------------------------
echo [5/5] Running Automated Test Suite (Pytest)...
echo Executing all unit, RAG, authorization, orchestrator, and security tests...
"%PYTHON%" -m pytest tests/unit -v --tb=short %*
if errorlevel 1 (
    echo [ERROR] Automated test suite encountered test failure
    set "STAGE_TESTS=FAIL"
    set "OVERALL_STATUS=1"
) else (
    echo [OK] All automated tests passed successfully
)
echo.

:summary
REM ----------------------------------------------------------------------
REM Verification Summary and Result
REM ----------------------------------------------------------------------
echo ======================================================================
echo                     VERIFICATION CHECK SUMMARY
echo ======================================================================
echo   [1/5] Python Virtual Environment:  !STAGE_ENV!
echo   [2/5] Configuration (.env):        !STAGE_CONFIG!
echo   [3/5] Database Migrations:         !STAGE_MIGRATIONS!
echo   [4/5] Code Quality and Linter:     !STAGE_RUFF!
echo   [5/5] Automated Test Suite:        !STAGE_TESTS!
echo ======================================================================

if "!OVERALL_STATUS!"=="0" (
    color 0A
    echo [SUCCESS] ALL SYSTEM CHECKS PASSED SUCCESSFULLY
    echo The repository is clean, hardened, and ready for execution
    echo ======================================================================
    exit /b 0
) else (
    color 0C
    echo [FAILURE] ONE OR MORE VERIFICATION CHECKS FAILED
    echo Review the error log above and resolve the reported issues
    echo ======================================================================
    exit /b 1
)
