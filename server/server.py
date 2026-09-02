"""server.py - Serveur HTTP léger et API pour le traducteur Ren'Py à la volée."""

import os
import sys
import json
import time
import threading
import configparser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from storage import TranslationStorage
from engines import GoogleEngine, OllamaEngine, get_ollama_models

ROOT_DIR = os.path.dirname(BASE_DIR)
CONFIG_INI = os.path.join(ROOT_DIR, "config.ini")

# Initialisation de la configuration par défaut
config = configparser.ConfigParser()
config.read(CONFIG_INI)

DEFAULT_LANG = config.get("Translation", "TARGET_LANG", fallback=config.get("Translation", "LANG_CODE", fallback="fr"))
DEFAULT_MODEL = config.get("AI", "MODEL", fallback="qwen3:latest")
DEFAULT_PORT = config.getint("Server", "PORT", fallback=5005)

LANG_NAMES = {
    "fr": "french",
    "es": "spanish",
    "de": "german",
    "it": "italian",
    "ja": "japanese",
    "ru": "russian",
    "en": "english",
    "pt": "portuguese",
    "zh": "chinese"
}

# État global du serveur
class ServerState:
    def __init__(self):
        self.storage = TranslationStorage()
        self.google_engine = GoogleEngine()
        self.ollama_engine = OllamaEngine(model=DEFAULT_MODEL)
        self.engine_name = "google" # "google" ou "ollama"
        self.target_lang = DEFAULT_LANG
        self.model_name = DEFAULT_MODEL

    def get_engine(self):
        if self.engine_name == "ollama":
            self.ollama_engine.model = self.model_name
            return self.ollama_engine
        return self.google_engine

state = ServerState()

class LiveTranslatorHandler(BaseHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_json(self, data, status=200):
        try:
            body = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            html_path = os.path.join(BASE_DIR, "web", "index.html")
            if os.path.exists(html_path):
                with open(html_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Dashboard introuvable")
            return

        elif path == "/api/status":
            models = get_ollama_models()
            self._send_json({
                "status": "online",
                "engine": state.engine_name,
                "target_lang": state.target_lang,
                "model": state.model_name,
                "available_models": models if models else [state.model_name]
            })
            return

        elif path == "/api/stats":
            stats = state.storage.get_stats()
            games = state.storage.get_games()
            stats["games"] = games
            self._send_json(stats)
            return

        elif path == "/api/history":
            history = state.storage.get_history(limit=50)
            self._send_json(history)
            return

        elif path == "/api/export":
            params = parse_qs(parsed.query)
            export_format = params.get("format", ["rpy"])[0]
            game_id = params.get("game_id", [None])[0]

            if not game_id:
                games = state.storage.get_games()
                game_id = games[0]["game_id"] if games else "RenpyGame"

            content = state.storage.export_translations(game_id, state.target_lang, export_format)

            content_bytes = content.encode('utf-8')
            self.send_response(200)
            filename = f"translations_{game_id}_{state.target_lang}.{export_format}"
            self.send_header("Content-Disposition", f"attachment; filename=\"{filename}\"")
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(content_bytes)))
            self.end_headers()
            self.wfile.write(content_bytes)
            return

        self.send_error(404, "Endpoint non trouvé")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode('utf-8')
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        if path == "/api/translate":
            text = data.get("text", "")
            game_id = data.get("game_id", "RenpyGame")

            if not text:
                self._send_json({"translated": "", "cached": False})
                return

            lang_folder = LANG_NAMES.get(state.target_lang, state.target_lang)

            # 1. Vérifier le cache SQLite
            cached = state.storage.get_translation(game_id, text, state.target_lang)
            if cached:
                self._send_json({
                    "translated": cached,
                    "cached": True,
                    "target_lang": state.target_lang,
                    "lang_name": lang_folder
                })
                return

            # 2. Traduction via le moteur actif
            engine = state.get_engine()
            translated = engine.translate(text, state.target_lang)

            # 3. Sauvegarder dans le cache SQLite
            if translated and translated != text:
                state.storage.save_translation(game_id, text, translated, state.target_lang)

            self._send_json({
                "translated": translated,
                "cached": False,
                "target_lang": state.target_lang,
                "lang_name": lang_folder
            })
            return

        elif path == "/api/config":
            if "engine" in data:
                state.engine_name = data["engine"]
            if "target_lang" in data:
                state.target_lang = data["target_lang"]
            if "model" in data:
                state.model_name = data["model"]
            self._send_json({"status": "updated", "config": {
                "engine": state.engine_name,
                "target_lang": state.target_lang,
                "model": state.model_name
            }})
            return

        elif path == "/api/shutdown":
            self._send_json({"status": "shutting_down", "message": "Serveur arrêté avec succès."})
            def _delayed_shutdown(srv):
                time.sleep(0.2)
                if srv and hasattr(srv, 'shutdown'):
                    srv.shutdown()
            threading.Thread(target=_delayed_shutdown, args=(getattr(self, 'server', None),), daemon=True).start()
            return

        self.send_error(404, "Endpoint non trouvé")

    def log_message(self, format, *args):
        return

def run_server(port=5005):
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, LiveTranslatorHandler)
    print(f"==================================================")
    print(f"  🎮 Ren'Py Live Translator Server actif sur :")
    print(f"  👉 http://127.0.0.1:{port}")
    print(f"==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt demandé par l'utilisateur (Ctrl+C).")
    finally:
        httpd.server_close()
        print("Serveur arrêté proprement.")

if __name__ == "__main__":
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
