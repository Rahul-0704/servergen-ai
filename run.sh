#!/usr/bin/env bash
# =============================================================================
# ServerGen AI — Master Runner for Linux & macOS
# =============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Virtual environment python binary
if [ -d "$DIR/.venv" ]; then
    PYTHON="$DIR/.venv/bin/python"
    UVICORN="$DIR/.venv/bin/uvicorn"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
    UVICORN="uvicorn"
else
    echo "[ERROR] Python 3 not found. Please install Python 3.11+."
    exit 1
fi

# Ensure .env exists
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "[INFO] Initializing .env configuration from .env.example..."
    cp .env.example .env
    echo "[OK] Created .env configuration file."
fi

# Parse subcommands
case "$1" in
    check)
        echo "======================================================================"
        echo "         SERVERGEN AI -- SYSTEM VERIFICATION & CHECKS"
        echo "======================================================================"
        "$DIR/.venv/bin/ruff" check src tests scripts
        "$PYTHON" scripts/verify_all_5_tests.py
        exit 0
        ;;
    lint)
        "$DIR/.venv/bin/ruff" check src tests scripts
        exit 0
        ;;
    test)
        "$DIR/.venv/bin/pytest" tests/unit/
        exit 0
        ;;
esac

echo "======================================================================"
echo "                    SERVERGEN AI -- LOCAL RUNTIME"
echo "           Secure Enterprise AI Automation with Local LLM"
echo "======================================================================"
echo ""

# Check Ollama
echo "[1/2] Checking Local Ollama Runtime..."
if curl -s http://127.0.0.1:11434/api/tags &>/dev/null; then
    echo "[OK] Ollama is active on http://127.0.0.1:11434"
else
    echo "[INFO] Ollama service not detected on port 11434."
    if command -v ollama &>/dev/null; then
        echo "[INFO] Starting Ollama in background..."
        ollama serve &>/dev/null &
        sleep 2
    else
        echo "[WARNING] Ollama is not installed or not in PATH."
        echo "          Install from https://ollama.com and run 'ollama pull llama3.2:3b'."
        echo "          Non-LLM backend features (Auth, RAG storage, Approvals) will still work."
    fi
fi
echo ""

# Start FastAPI
echo "[2/2] Launching ServerGen AI FastAPI Backend..."
echo ""
echo " * Test & Demo Dashboard : http://127.0.0.1:8000/test"
echo " * Interactive API Docs  : http://127.0.0.1:8000/docs"
echo " * Health Status Check   : http://127.0.0.1:8000/api/v1/health"
echo ""

exec "$UVICORN" src.app:app --host 127.0.0.1 --port 8000 --reload
