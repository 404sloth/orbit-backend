#!/bin/bash
# Orbit Backend - Run Script for macOS/Linux

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Starting Orbit Backend Server..."
echo "================================="

cd "$PROJECT_ROOT"

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "Warning: Virtual environment not found. Please run setup.sh first."
    exit 1
fi

cd app

# Run the backend server
echo "Backend running on: http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Run the backend server with a persistence loop
while true; do
    python main.py
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "Server stopped normally."
        break
    else
        echo "Server crashed with exit code $EXIT_CODE. Restarting in 3 seconds..."
        sleep 3
    fi
done
