@echo off
setlocal enabledelayedexpansion

title ServerGen AI -- Local Runtime Launcher
color 0B

echo ======================================================================
echo                     SERVERGEN AI -- LOCAL RUNTIME
echo            Secure Enterprise AI Automation with Local LLM
echo ======================================================================
echo.

:: Ensure we are in the script's root directory
cd /d "%~dp0"

:: 1. Check Python Virtual Environment
echo [1/4] Checking Python Virtual Environment...
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\Scripts\python.exe!
    echo Please create the virtual environment first:
    echo   python -m venv .venv
    echo   .venv\Scripts\pip install -e .
    echo.
    pause
    exit /b 1
)
echo [OK] Python virtual environment detected.
echo.

:: 2. Check Configuration File (.env)
echo [2/4] Checking Environment Configuration...
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] .env not found. Creating from .env.example...
        copy /y ".env.example" ".env" >nul
        echo [OK] Created .env configuration file.
    ) else (
        echo [WARNING] No .env or .env.example found. Running with defaults.
    )
) else (
    echo [OK] Configuration file .env found.
)
echo.

:: 3. Check / Start Ollama Local LLM Service
echo [3/4] Checking Ollama Local LLM Runtime...
curl.exe -s http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [INFO] Ollama service is not running on port 11434.
    echo [INFO] Attempting to start Ollama in background...
    start "Ollama Server" /min ollama serve
    
    :: Wait up to 10 seconds for Ollama to become responsive
    set OLLAMA_READY=0
    for /L %%i in (1,1,10) do (
        timeout /t 1 /nobreak >nul
        curl.exe -s http://127.0.0.1:11434/api/tags >nul 2>&1
        if !errorlevel! equ 0 (
            set OLLAMA_READY=1
            goto :ollama_started
        )
    )
    :ollama_started
    if "!OLLAMA_READY!"=="1" (
        echo [OK] Ollama service started successfully.
    ) else (
        echo [WARNING] Ollama did not respond within 10s. Start it manually with 'ollama serve'.
    )
) else (
    echo [OK] Ollama service is already active on port 11434.
)

:: Check if llama3.2:3b model is available
curl.exe -s http://127.0.0.1:11434/api/tags | findstr /i "llama3.2:3b" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Model 'llama3.2:3b' not detected in Ollama. Pulling now...
    ollama pull llama3.2:3b
    if errorlevel 1 (
        echo [WARNING] Could not pull 'llama3.2:3b'. Ensure internet connection or pull manually.
    ) else (
        echo [OK] Model 'llama3.2:3b' downloaded and ready.
    )
) else (
    echo [OK] Local model 'llama3.2:3b' is installed and ready.
)
echo.

:: 4. Start FastAPI Backend & Open Dashboard
echo [4/4] Launching ServerGen AI Backend Server...
echo.
echo ======================================================================
echo   Endpoints:
echo     - Test Dashboard:  http://localhost:8000/test
echo     - OpenAPI Docs:    http://localhost:8000/docs
echo     - Telemetry Probe: http://localhost:8000/api/v1/health
echo.
echo   Press CTRL+C in this console to stop the server.
echo ======================================================================
echo.

:: Open browser test interface after brief delay in background
start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000/test"

:: Run FastAPI server using Python venv
.venv\Scripts\python.exe -m uvicorn src.app:app --host 127.0.0.1 --port 8000 --reload
