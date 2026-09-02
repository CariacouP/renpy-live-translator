#!/bin/bash

# Change working directory to script location
cd "$(dirname "$0")"
SCRIPT_DIR="$(pwd)"
SERVER_SCRIPT="$SCRIPT_DIR/server/server.py"

echo "=================================================="
echo "  🎮 Starting Ren'Py Live Translator Server"
echo "=================================================="

# Open browser dashboard after a short delay
(
  sleep 1.2
  if command -v open > /dev/null; then
    open "http://127.0.0.1:5005"
  elif command -v xdg-open > /dev/null; then
    xdg-open "http://127.0.0.1:5005"
  fi
) &

# Find python3 executable
if command -v python3 > /dev/null 2>&1; then
  python3 "$SERVER_SCRIPT"
elif command -v python > /dev/null 2>&1; then
  python "$SERVER_SCRIPT"
else
  echo "Error: Python 3 could not be found. Please install Python 3."
  read -p "Press Enter to exit..."
fi
