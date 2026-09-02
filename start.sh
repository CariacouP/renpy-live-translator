#!/bin/bash

# Determine script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_SCRIPT="$SCRIPT_DIR/server/server.py"

echo "=================================================="
echo "  🎮 Starting Ren'Py Live Translator Server"
echo "=================================================="
echo ""

# Find a valid Python 3 (version >= 3.8)
PYTHON_CMD=""
for cmd in "python3" "python" "py"; do
  if command -v "$cmd" > /dev/null 2>&1; then
    if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" > /dev/null 2>&1; then
      PYTHON_CMD="$cmd"
      break
    fi
  fi
done

if [ -z "$PYTHON_CMD" ]; then
  echo "❌ Error: Python 3.8 or newer was not found on your system!"
  echo ""
  echo "Ren'Py Live Translator requires Python 3.8+ to run."
  echo "Please download and install Python from:"
  echo "👉 https://www.python.org/downloads/"
  echo ""
  if command -v open > /dev/null 2>&1; then
    open "https://www.python.org/downloads/"
  elif command -v xdg-open > /dev/null 2>&1; then
    xdg-open "https://www.python.org/downloads/"
  fi
  read -p "Press Enter to exit..."
  exit 1
fi

# Open browser dashboard after a short delay
(
  sleep 1.2
  if command -v open > /dev/null 2>&1; then
    open "http://127.0.0.1:5005"
  elif command -v xdg-open > /dev/null 2>&1; then
    xdg-open "http://127.0.0.1:5005"
  fi
) &

# Run Python server
"$PYTHON_CMD" "$SERVER_SCRIPT"
