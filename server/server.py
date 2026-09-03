"""server.py - Lightweight HTTP server & API for Ren'Py Live Translator."""

import os
import sys

# Validate Python version immediately
if sys.version_info < (3, 8):
    print("=" * 60)
    print("❌ ERROR: Python 3.8 or newer is required to run the server.")
    print("   Current version: Python {}.{}.{}".format(
        sys.version_info.major, sys.version_info.minor, sys.version_info.micro
    ))
    print("   Please install/update Python from https://www.python.org/downloads/")
    print("=" * 60)
    sys.exit(1)

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
from engines import (
    GoogleEngine,
    DeepLEngine,
    GroqEngine,
    GeminiEngine,
    MistralEngine,
    LibreTranslateEngine,
    OllamaEngine,
    get_ollama_models
)

ROOT_DIR = os.path.dirname(BASE_DIR)
CONFIG_INI = os.path.join(ROOT_DIR, "config.ini")

# Initialisation de la configuration par défaut
config = configparser.ConfigParser()
config.read(CONFIG_INI)

DEFAULT_LANG = config.get("Translation", "TARGET_LANG", fallback=config.get("Translation", "LANG_CODE", fallback="en"))
DEFAULT_ENGINE = config.get("Translation", "ENGINE", fallback="google")
DEFAULT_PORT = config.getint("Server", "PORT", fallback=5005)

DEFAULT_OLLAMA_MODEL = config.get("AI", "MODEL", fallback="qwen3:latest")
DEFAULT_DEEPL_KEY = config.get("DeepL", "api_key", fallback="")
DEFAULT_GROQ_KEY = config.get("Groq", "api_key", fallback="")
DEFAULT_GROQ_MODEL = config.get("Groq", "model", fallback="llama-3.3-70b-versatile")
DEFAULT_GEMINI_KEY = config.get("Gemini", "api_key", fallback="")
DEFAULT_GEMINI_MODEL = config.get("Gemini", "model", fallback="gemini-2.0-flash")
DEFAULT_MISTRAL_KEY = config.get("Mistral", "api_key", fallback="")
DEFAULT_MISTRAL_MODEL = config.get("Mistral", "model", fallback="mistral-small-latest")
DEFAULT_LIBRE_URL = config.get("LibreTranslate", "url", fallback="https://libretranslate.com")
DEFAULT_LIBRE_KEY = config.get("LibreTranslate", "api_key", fallback="")

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

# Global server state
class ServerState:
    def __init__(self):
        self.storage = TranslationStorage()
        self.engine_name = DEFAULT_ENGINE
        self.target_lang = DEFAULT_LANG
        
        self.ollama_model = DEFAULT_OLLAMA_MODEL
        self.deepl_api_key = DEFAULT_DEEPL_KEY
        self.groq_api_key = DEFAULT_GROQ_KEY
        self.groq_model = DEFAULT_GROQ_MODEL
        self.gemini_api_key = DEFAULT_GEMINI_KEY
        self.gemini_model = DEFAULT_GEMINI_MODEL
        self.mistral_api_key = DEFAULT_MISTRAL_KEY
        self.mistral_model = DEFAULT_MISTRAL_MODEL
        self.libretranslate_url = DEFAULT_LIBRE_URL
        self.libretranslate_api_key = DEFAULT_LIBRE_KEY

        self.google_engine = GoogleEngine()
        self.deepl_engine = DeepLEngine(api_key=self.deepl_api_key)
        self.groq_engine = GroqEngine(api_key=self.groq_api_key, model=self.groq_model)
        self.gemini_engine = GeminiEngine(api_key=self.gemini_api_key, model=self.gemini_model)
        self.mistral_engine = MistralEngine(api_key=self.mistral_api_key, model=self.mistral_model)
        self.libretranslate_engine = LibreTranslateEngine(url=self.libretranslate_url, api_key=self.libretranslate_api_key)
        self.ollama_engine = OllamaEngine(model=self.ollama_model)

    def get_engine(self):
        eng = (self.engine_name or "google").lower()
        if eng == "deepl":
            self.deepl_engine.api_key = self.deepl_api_key
            return self.deepl_engine
        elif eng == "groq":
            self.groq_engine.api_key = self.groq_api_key
            self.groq_engine.model = self.groq_model
            return self.groq_engine
        elif eng == "gemini":
            self.gemini_engine.api_key = self.gemini_api_key
            self.gemini_engine.model = self.gemini_model
            return self.gemini_engine
        elif eng == "mistral":
            self.mistral_engine.api_key = self.mistral_api_key
            self.mistral_engine.model = self.mistral_model
            return self.mistral_engine
        elif eng == "libretranslate":
            self.libretranslate_engine.url = self.libretranslate_url
            self.libretranslate_engine.api_key = self.libretranslate_api_key
            return self.libretranslate_engine
        elif eng == "ollama":
            self.ollama_engine.model = self.ollama_model
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
                self.send_error(404, "Dashboard not found")
            return

        elif path == "/api/status":
            ollama_models = get_ollama_models()
            self._send_json({
                "status": "online",
                "server_path": os.path.abspath(__file__),
                "engine": state.engine_name,
                "target_lang": state.target_lang,
                "model": state.ollama_model,
                "available_models": ollama_models if ollama_models else [state.ollama_model],
                "deepl_api_key": state.deepl_api_key,
                "groq_api_key": state.groq_api_key,
                "groq_model": state.groq_model,
                "gemini_api_key": state.gemini_api_key,
                "gemini_model": state.gemini_model,
                "mistral_api_key": state.mistral_api_key,
                "mistral_model": state.mistral_model,
                "libretranslate_url": state.libretranslate_url,
                "libretranslate_api_key": state.libretranslate_api_key
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

        self.send_error(404, "Endpoint not found")

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

            # 3. Sauvegarder dans le cache SQLite (si pas un message d'erreur interne)
            if translated and not translated.startswith("[") and translated != text:
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
                state.engine_name = str(data["engine"])
            if "target_lang" in data:
                state.target_lang = str(data["target_lang"])
            if "model" in data:
                state.ollama_model = str(data["model"])
            if "deepl_api_key" in data:
                state.deepl_api_key = str(data["deepl_api_key"]).strip()
            if "groq_api_key" in data:
                state.groq_api_key = str(data["groq_api_key"]).strip()
            if "groq_model" in data:
                state.groq_model = str(data["groq_model"]).strip()
            if "gemini_api_key" in data:
                state.gemini_api_key = str(data["gemini_api_key"]).strip()
            if "gemini_model" in data:
                state.gemini_model = str(data["gemini_model"]).strip()
            if "mistral_api_key" in data:
                state.mistral_api_key = str(data["mistral_api_key"]).strip()
            if "mistral_model" in data:
                state.mistral_model = str(data["mistral_model"]).strip()
            if "libretranslate_url" in data:
                state.libretranslate_url = str(data["libretranslate_url"]).strip()
            if "libretranslate_api_key" in data:
                state.libretranslate_api_key = str(data["libretranslate_api_key"]).strip()

            # Persist changes to config.ini
            try:
                for sec in ["Translation", "AI", "DeepL", "Groq", "Gemini", "Mistral", "LibreTranslate"]:
                    if not config.has_section(sec):
                        config.add_section(sec)
                config.set("Translation", "TARGET_LANG", state.target_lang)
                config.set("Translation", "ENGINE", state.engine_name)
                config.set("AI", "MODEL", state.ollama_model)
                config.set("DeepL", "api_key", state.deepl_api_key)
                config.set("Groq", "api_key", state.groq_api_key)
                config.set("Groq", "model", state.groq_model)
                config.set("Gemini", "api_key", state.gemini_api_key)
                config.set("Gemini", "model", state.gemini_model)
                config.set("Mistral", "api_key", state.mistral_api_key)
                config.set("Mistral", "model", state.mistral_model)
                config.set("LibreTranslate", "url", state.libretranslate_url)
                config.set("LibreTranslate", "api_key", state.libretranslate_api_key)
                with open(CONFIG_INI, "w", encoding="utf-8") as f:
                    config.write(f)
            except Exception:
                pass

            self._send_json({"status": "updated", "config": {
                "engine": state.engine_name,
                "target_lang": state.target_lang,
                "model": state.ollama_model,
                "deepl_api_key": state.deepl_api_key,
                "groq_api_key": state.groq_api_key,
                "groq_model": state.groq_model,
                "gemini_api_key": state.gemini_api_key,
                "gemini_model": state.gemini_model,
                "mistral_api_key": state.mistral_api_key,
                "mistral_model": state.mistral_model,
                "libretranslate_url": state.libretranslate_url,
                "libretranslate_api_key": state.libretranslate_api_key
            }})
            return

        elif path == "/api/shutdown":
            self._send_json({"status": "shutting_down", "message": "Server stopped successfully."})
            def _delayed_shutdown(srv):
                time.sleep(0.2)
                if srv and hasattr(srv, 'shutdown'):
                    srv.shutdown()
            threading.Thread(target=_delayed_shutdown, args=(getattr(self, 'server', None),), daemon=True).start()
            return

        self.send_error(404, "Endpoint not found")

    def log_message(self, format, *args):
        return

def record_server_location():
    """Saves the absolute path of server.py to ~/.renpy_translator_path for automatic plugin discovery."""
    try:
        path_file = os.path.expanduser("~/.renpy_translator_path")
        with open(path_file, "w", encoding="utf-8") as f:
            f.write(os.path.abspath(__file__))
    except Exception:
        pass

def run_server(port=5005):
    record_server_location()
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, LiveTranslatorHandler)
    print(f"==================================================")
    print(f"  🎮 Ren'Py Live Translator Server active on:")
    print(f"  👉 http://127.0.0.1:{port}")
    print(f"==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown requested (Ctrl+C).")
    finally:
        httpd.server_close()
        print("Server stopped cleanly.")

if __name__ == "__main__":
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
