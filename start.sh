#!/bin/bash

# Déterminer le chemin absolu du dossier du script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_SCRIPT="$SCRIPT_DIR/server/server.py"

echo "=================================================="
echo "  🎮 Starting Ren'Py Live Translator Server"
echo "=================================================="

# Ouvrir le navigateur après un court délai
(
  sleep 1.2
  if command -v open > /dev/null; then
    open "http://127.0.0.1:5005"
  elif command -v xdg-open > /dev/null; then
    xdg-open "http://127.0.0.1:5005"
  fi
) &

# Lancer le serveur Python
python3 "$SERVER_SCRIPT"
