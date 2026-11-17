@echo off
setlocal

:: ======================================================================
:: ServerGen AI — Master Runner Script
:: 
:: Commands:
::   run.bat          -> Run all system verification checks, linter & tests
::   run.bat check    -> Run all system verification checks (run_checks.bat)
::   run.bat start    -> Launch Ollama and start FastAPI backend server (start.bat)
::   run.bat serve    -> Launch Ollama and start FastAPI backend server (start.bat)
:: ======================================================================

cd /d "%~dp0"

if /i "%~1"=="start" (
    shift
    call "%~dp0start.bat" %*
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="serve" (
    shift
    call "%~dp0start.bat" %*
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="server" (
    shift
    call "%~dp0start.bat" %*
    exit /b %ERRORLEVEL%
)

if /i "%~1"=="check" (
    shift
)

call "%~dp0run_checks.bat" %*
exit /b %ERRORLEVEL%
