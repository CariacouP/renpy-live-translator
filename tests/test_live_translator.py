"""Tests unitaires pour le système Live Translator."""

import os
import sys
import unittest
import tempfile
import json
import io
import re
from unittest.mock import patch, MagicMock

# Ajouter server au sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "server"))

from storage import TranslationStorage
from engines import (
    protect_tags,
    restore_tags,
    GoogleEngine,
    DeepLEngine,
    GroqEngine,
    GeminiEngine,
    MistralEngine,
    LibreTranslateEngine,
    OllamaEngine
)
from server import LiveTranslatorHandler, state

class TestStorage(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.storage = TranslationStorage(self.temp_db.name)

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_save_and_get_translation(self):
        self.assertIsNone(self.storage.get_translation("GameA", "Hello", "fr"))
        self.storage.save_translation("GameA", "Hello", "Bonjour", "fr")
        self.assertEqual(self.storage.get_translation("GameA", "Hello", "fr"), "Bonjour")
        # Langue différente
        self.assertIsNone(self.storage.get_translation("GameA", "Hello", "es"))

    def test_stats_and_history(self):
        self.storage.save_translation("Game1", "Hi", "Salut", "fr")
        self.storage.save_translation("Game2", "Yes", "Oui", "fr")
        stats = self.storage.get_stats()
        self.assertEqual(stats["total_translations"], 2)
        self.assertEqual(stats["total_games"], 2)

        history = self.storage.get_history(limit=5)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["source_text"], "Yes")

    def test_register_game(self):
        self.storage.register_game("NewGame123", "/path/to/game")
        games = self.storage.get_games()
        self.assertTrue(any(g["game_id"] == "NewGame123" for g in games))
        stats = self.storage.get_stats()
        self.assertEqual(stats["total_games"], 1)

    def test_export(self):
        self.storage.save_translation("TestGame", "Start", "Commencer", "fr")
        rpy_export = self.storage.export_translations("TestGame", "fr", "rpy")
        self.assertIn("_offline_cache", rpy_export)
        self.assertIn("Commencer", rpy_export)

        json_export = self.storage.export_translations("TestGame", "fr", "json")
        data = json.loads(json_export)
        self.assertEqual(data.get("Start"), "Commencer")

class TestEngines(unittest.TestCase):
    def test_tag_protection_complex(self):
        text = "Hello {b}[player_name]{/b}! How are {color=#ff0000}you{/color}?"
        protected, tags = protect_tags(text)
        self.assertNotIn("[player_name]", protected)
        self.assertNotIn("{b}", protected)
        self.assertIn("__TAG0__", protected)

        restored = restore_tags(protected, tags)
        self.assertEqual(restored, text)

    def test_tag_protection_with_whitespace(self):
        text = "{i}Thinking to myself...{/i}"
        protected, tags = protect_tags(text)
        restored = restore_tags(protected, tags)
        self.assertEqual(restored, text)

    def test_tag_protection_relative_size_and_math(self):
        text = "{size=+10}SMACK{/size} and {size=-5}whisper{/size} {alpha=*0.5}ghost{/alpha}"
        protected, tags = protect_tags(text)
        self.assertNotIn("{size=+10}", protected)
        self.assertNotIn("{size=-5}", protected)
        self.assertNotIn("{alpha=*0.5}", protected)
        restored = restore_tags(protected, tags)
        self.assertEqual(restored, text)

    def test_tag_repair_safety_net(self):
        corrupted = "Bonjour {taille=+10}CLAC{/taille} et {gras}Important{/gras}"
        repaired = restore_tags(corrupted, [])
        self.assertEqual(repaired, "Bonjour {size=+10}CLAC{/size} et {b}Important{/b}")

    @patch('urllib.request.urlopen')
    def test_google_engine_mock(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([[["Bonjour le monde", "Hello world", None, None]]]).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        engine = GoogleEngine()
        result = engine.translate("Hello world", "fr")
        self.assertEqual(result, "Bonjour le monde")

    @patch('urllib.request.urlopen')
    def test_deepl_engine_mock(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "translations": [{"detected_source_language": "EN", "text": "Bonjour __TAG0__"}]
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        engine = DeepLEngine(api_key="mock-key:fx")
        result = engine.translate("Hello [name]", "fr")
        self.assertEqual(result, "Bonjour [name]")

    @patch('urllib.request.urlopen')
    def test_groq_engine_mock(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Bonjour __TAG0__"}}]
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        engine = GroqEngine(api_key="gsk_mock", model="llama-3.3-70b-versatile")
        result = engine.translate("Hello [name]", "fr")
        self.assertEqual(result, "Bonjour [name]")

    @patch('urllib.request.urlopen')
    def test_gemini_engine_mock(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "Bonjour __TAG0__"}]}}]
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        engine = GeminiEngine(api_key="AIzaMock", model="gemini-2.0-flash")
        result = engine.translate("Hello [name]", "fr")
        self.assertEqual(result, "Bonjour [name]")

    @patch('urllib.request.urlopen')
    def test_mistral_engine_mock(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Bonjour __TAG0__"}}]
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        engine = MistralEngine(api_key="mock_mistral", model="mistral-small-latest")
        result = engine.translate("Hello [name]", "fr")
        self.assertEqual(result, "Bonjour [name]")

    @patch('urllib.request.urlopen')
    def test_libretranslate_engine_mock(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "translatedText": "Bonjour __TAG0__"
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        engine = LibreTranslateEngine(url="https://libretranslate.com", api_key="")
        result = engine.translate("Hello [name]", "fr")
        self.assertEqual(result, "Bonjour [name]")

    @patch('urllib.request.urlopen')
    def test_ollama_engine_mock(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"message": {"content": "Bonjour __TAG0__"}}).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        engine = OllamaEngine(model="dolphin3")
        result = engine.translate("Hello [name]", "fr")
        self.assertEqual(result, "Bonjour [name]")

class DummyRequest:
    def __init__(self, raw_input):
        self.raw_input = raw_input

    def makefile(self, *args, **kwargs):
        return io.BytesIO(self.raw_input)

    def sendall(self, data):
        pass

class TestServerHandler(unittest.TestCase):
    def test_api_status_logic(self):
        state.engine_name = "google"
        state.target_lang = "fr"

        handler = LiveTranslatorHandler.__new__(LiveTranslatorHandler)
        handler.path = "/api/status"
        sent_data = []

        def dummy_send(data, status=200):
            sent_data.append((status, data))

        handler._send_json = dummy_send
        handler.do_GET()

        self.assertEqual(len(sent_data), 1)
        status, data = sent_data[0]
        self.assertEqual(status, 200)
        self.assertEqual(data["engine"], "google")
        self.assertEqual(data["target_lang"], "fr")

    def test_api_translate_cache_hit_and_miss(self):
        # Configuration d'un stockage temporaire
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        state.storage = TranslationStorage(temp_db.name)
        state.target_lang = "fr"

        handler = LiveTranslatorHandler.__new__(LiveTranslatorHandler)
        handler.path = "/api/translate"
        handler.headers = {"Content-Length": 100}

        # Mock engine
        mock_engine = MagicMock()
        mock_engine.translate.return_value = "Salut !"
        state.google_engine = mock_engine
        state.engine_name = "google"

        # 1. Premier appel (miss)
        handler.rfile = io.BytesIO(json.dumps({"text": "Hello!", "game_id": "TestGame"}).encode('utf-8'))
        handler.headers["Content-Length"] = len(handler.rfile.getvalue())

        sent_data = []
        handler._send_json = lambda data, status=200: sent_data.append(data)
        handler.do_POST()

        self.assertEqual(len(sent_data), 1)
        self.assertFalse(sent_data[0]["cached"])
        self.assertEqual(sent_data[0]["translated"], "Salut !")

        # 2. Deuxième appel (cache hit immédiat)
        sent_data.clear()
        handler.rfile = io.BytesIO(json.dumps({"text": "Hello!", "game_id": "TestGame"}).encode('utf-8'))
        handler.headers["Content-Length"] = len(handler.rfile.getvalue())
        handler.do_POST()

        self.assertEqual(len(sent_data), 1)
        self.assertTrue(sent_data[0]["cached"])
        self.assertEqual(sent_data[0]["translated"], "Salut !")

        if os.path.exists(temp_db.name):
            os.remove(temp_db.name)

    def test_api_config_multi_engines(self):
        handler = LiveTranslatorHandler.__new__(LiveTranslatorHandler)
        handler.path = "/api/config"
        payload = {
            "engine": "deepl",
            "target_lang": "es",
            "deepl_api_key": "test_deepl:fx",
            "groq_api_key": "test_groq",
            "groq_model": "llama-3.3-70b-versatile",
            "gemini_api_key": "test_gemini",
            "gemini_model": "gemini-2.0-flash",
            "mistral_api_key": "test_mistral",
            "mistral_model": "mistral-small-latest",
            "libretranslate_url": "https://test.libre.com",
            "libretranslate_api_key": "test_libre"
        }
        handler.rfile = io.BytesIO(json.dumps(payload).encode('utf-8'))
        handler.headers = {"Content-Length": len(handler.rfile.getvalue())}

        sent_data = []
        handler._send_json = lambda data, status=200: sent_data.append((status, data))
        handler.do_POST()

        self.assertEqual(len(sent_data), 1)
        status, res = sent_data[0]
        self.assertEqual(status, 200)
        self.assertEqual(state.engine_name, "deepl")
        self.assertEqual(state.target_lang, "es")
        self.assertEqual(state.deepl_api_key, "test_deepl:fx")
        self.assertEqual(state.groq_api_key, "test_groq")
        self.assertEqual(state.gemini_api_key, "test_gemini")
        self.assertEqual(state.mistral_api_key, "test_mistral")
        self.assertEqual(state.libretranslate_url, "https://test.libre.com")

        # Test get_engine return
        eng = state.get_engine()
        self.assertIsInstance(eng, DeepLEngine)
        self.assertEqual(eng.api_key, "test_deepl:fx")

        # Restore state and config.ini so tests do not pollute production config
        state.engine_name = "google"
        state.target_lang = "fr"
        state.deepl_api_key = ""
        state.groq_api_key = ""
        state.gemini_api_key = ""
        state.mistral_api_key = ""
        state.libretranslate_url = ""
        state.libretranslate_api_key = ""
        try:
            import configparser
            from server import CONFIG_INI
            cfg = configparser.ConfigParser()
            cfg.read(CONFIG_INI)
            if not cfg.has_section("Translation"):
                cfg.add_section("Translation")
            cfg.set("Translation", "ENGINE", "google")
            cfg.set("Translation", "TARGET_LANG", "fr")
            for s in ["DeepL", "Groq", "Gemini", "Mistral", "LibreTranslate"]:
                if cfg.has_section(s):
                    for k in cfg.options(s):
                        cfg.set(s, k, "")
            with open(CONFIG_INI, "w", encoding="utf-8") as f:
                cfg.write(f)
        except Exception:
            pass

    def test_api_shutdown(self):
        handler = LiveTranslatorHandler.__new__(LiveTranslatorHandler)
        handler.path = "/api/shutdown"
        handler.headers = {"Content-Length": 0}
        handler.rfile = io.BytesIO(b"")
        mock_server = MagicMock()
        handler.server = mock_server

        sent_data = []
        handler._send_json = lambda data, status=200: sent_data.append((status, data))
        handler.do_POST()

        self.assertEqual(len(sent_data), 1)
        status, data = sent_data[0]
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "shutting_down")

    def test_record_server_location(self):
        from server import record_server_location
        with patch("builtins.open", unittest.mock.mock_open()) as mock_file:
            record_server_location()
            mock_file.assert_called_once()

    def test_plugin_server_discovery_and_lifecycle(self):
        # Extract and compile the python code from 00_translator.rpy
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        # Strip out the 'init ... python:' and config hooks for testing
        py_lines = []
        skip_block = False
        for line in lines:
            if line.strip().startswith("init 999"):
                skip_block = True
                continue
            if skip_block:
                continue
            if line.strip().startswith("init -999") or "config.say_menu_text_filter" in line or "_live_translator_instance = LiveTranslator()" in line:
                continue
            if line.startswith("    "):
                py_lines.append(line[4:])
            else:
                py_lines.append(line)
        
        test_scope = {"config": type("MockConfig", (), {"gamedir": "/mock/game", "name": "TestGame"})()}
        exec("".join(py_lines), test_scope)
        
        LiveTranslatorClass = test_scope["LiveTranslator"]
        
        # Test 1: Resolve server script with explicit SERVER_PATH
        with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
            instance = LiveTranslatorClass()
            instance.game_dir = "/mock/game"
            instance.spawned_server = False
            instance.server_process = None
            instance.opener = MagicMock()
            
            # Explicit file
            server_file = os.path.join(BASE_DIR, "server", "server.py")
            test_scope["SERVER_PATH"] = server_file
            self.assertEqual(instance._resolve_server_script(), server_file)

            # Test 2: If server is already running, spawned_server remains False
            with patch.object(instance, '_is_server_running', return_value=True):
                with patch.object(instance, '_prompt_target_language', return_value="fr"):
                    with patch.object(instance, '_set_server_language') as mock_set_lang:
                        instance._ensure_server()
                        self.assertFalse(instance.spawned_server)
                        mock_set_lang.assert_called_with("fr")

            # Test 3: Cleanup does NOT shutdown server if spawned_server is False
            with patch.object(instance.opener, 'open') as mock_open:
                instance.spawned_server = False
                instance._cleanup()
                mock_open.assert_not_called()

            # Test 4: Cleanup DOES shutdown server if spawned_server is True
            with patch.object(instance.opener, 'open') as mock_open:
                instance.spawned_server = True
                instance._cleanup()
                mock_open.assert_called_once()

            # Test 5: _remember_server_path updates global SERVER_PATH and writes file
            with tempfile.TemporaryDirectory() as temp_dir:
                plugin_mock = os.path.join(temp_dir, "00_translator.rpy")
                with open(plugin_mock, "w", encoding="utf-8") as f:
                    f.write('SERVER_PATH = ""\nAUTO_START_MODE = "ask"\n')
                
                instance.game_dir = temp_dir
                test_scope["SERVER_PATH"] = ""
                instance._remember_server_path(server_file)
                
                self.assertEqual(test_scope["SERVER_PATH"], server_file)
                with open(plugin_mock, "r", encoding="utf-8") as f:
                    written = f.read()
                self.assertTrue("server.py" in written)

            # Test 6: Language choice parser
            self.assertEqual(instance._parse_lang_choice("Français (fr)"), "fr")
            self.assertEqual(instance._parse_lang_choice("English (en)"), "en")
            self.assertEqual(instance._parse_lang_choice("Español (es)"), "es")
            self.assertEqual(instance._parse_lang_choice("Deutsch (de)"), "de")
            self.assertEqual(instance._parse_lang_choice("Italiano (it)"), "it")
            self.assertEqual(instance._parse_lang_choice("Português (pt)"), "pt")
            self.assertEqual(instance._parse_lang_choice("Русский (ru)"), "ru")
            self.assertEqual(instance._parse_lang_choice("日本語 (ja)"), "ja")
            self.assertEqual(instance._parse_lang_choice("中文 (zh)"), "zh")

            # Test 7: Verify _should_skip safety filtering
            with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
                instance = LiveTranslatorClass()
                # Translatable dialogue elements
                self.assertFalse(instance._should_skip("Start Game"))
                self.assertFalse(instance._should_skip("Hello world!"))
                self.assertFalse(instance._should_skip("Bonjour"))

                # Non-translatable technical elements
                self.assertTrue(instance._should_skip(""))
                self.assertTrue(instance._should_skip("   "))
                self.assertTrue(instance._should_skip("12345"))
                self.assertTrue(instance._should_skip("..."))
                self.assertTrue(instance._should_skip("---"))


class TestRegression(unittest.TestCase):
    """Tests de non-régression pour garantir la fluidité (60 FPS), la détection de jeu et la traduction partielle."""

    def test_regression_register_game_endpoint(self):
        """Vérifie que /api/register_game enregistre immédiatement le jeu sans exiger de traduction préalable."""
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        old_storage = state.storage
        state.storage = TranslationStorage(temp_db.name)

        try:
            handler = LiveTranslatorHandler.__new__(LiveTranslatorHandler)
            handler.path = "/api/register_game"
            payload = {"game_id": "SuperGameVN", "game_dir": "/path/to/game", "target_lang": "fr"}
            body = json.dumps(payload).encode('utf-8')
            handler.rfile = io.BytesIO(body)
            handler.headers = {"Content-Length": len(body)}

            sent_data = []
            handler._send_json = lambda data, status=200: sent_data.append((status, data))
            handler.do_POST()

            self.assertEqual(len(sent_data), 1)
            status, res = sent_data[0]
            self.assertEqual(status, 200)
            self.assertEqual(res["status"], "registered")
            self.assertEqual(res["game_id"], "SuperGameVN")

            # Vérifier que le jeu est immédiatement compté et listé
            stats = state.storage.get_stats()
            self.assertEqual(stats["total_games"], 1)
            games = state.storage.get_games()
            self.assertEqual(len(games), 1)
            self.assertEqual(games[0]["game_id"], "SuperGameVN")
        finally:
            state.storage = old_storage
            if os.path.exists(temp_db.name):
                os.remove(temp_db.name)

    def test_regression_translate_respects_target_lang(self):
        """Vérifie que /api/translate prend en compte target_lang dans la requête et synchronise l'état."""
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        old_storage = state.storage
        state.storage = TranslationStorage(temp_db.name)

        try:
            handler = LiveTranslatorHandler.__new__(LiveTranslatorHandler)
            handler.path = "/api/translate"
            payload = {"text": "Good morning", "game_id": "TestGame", "target_lang": "es"}
            body = json.dumps(payload).encode('utf-8')
            handler.rfile = io.BytesIO(body)
            handler.headers = {"Content-Length": len(body)}

            sent_data = []
            handler._send_json = lambda data, status=200: sent_data.append((status, data))

            with patch.object(state, 'get_engine') as mock_engine_fn:
                mock_engine = MagicMock()
                mock_engine.translate.return_value = "Buenos días"
                mock_engine_fn.return_value = mock_engine

                handler.do_POST()

                self.assertEqual(state.target_lang, "es")
                mock_engine.translate.assert_called_with("Good morning", "es")
                self.assertEqual(len(sent_data), 1)
                self.assertEqual(sent_data[0][1]["target_lang"], "es")
        finally:
            state.storage = old_storage
            if os.path.exists(temp_db.name):
                os.remove(temp_db.name)

    def test_regression_is_dialogue_text_filters_ui(self):
        """Vérifie que is_dialogue_text filtre les boutons d'interface (0 lag) et accepte les dialogues."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        py_lines = []
        skip_block = False
        for line in lines:
            if line.strip().startswith("init 999"):
                skip_block = True
                continue
            if skip_block:
                continue
            if line.strip().startswith("init -999") or "config.say_menu_text_filter" in line or "_live_translator_instance = LiveTranslator()" in line:
                continue
            if line.startswith("    "):
                py_lines.append(line[4:])
            else:
                py_lines.append(line)

        test_scope = {"config": type("MockConfig", (), {"gamedir": "/mock/game", "name": "TestGame"})()}
        exec("".join(py_lines), test_scope)

        LiveTranslatorClass = test_scope["LiveTranslator"]
        with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
            instance = LiveTranslatorClass()
            # UI elements must be rejected (0 ms, no HTTP)
            self.assertFalse(instance.is_dialogue_text("Start"))
            self.assertFalse(instance.is_dialogue_text("Load"))
            self.assertFalse(instance.is_dialogue_text("Save"))
            self.assertFalse(instance.is_dialogue_text("Preferences"))
            self.assertFalse(instance.is_dialogue_text("Q.Save"))
            self.assertFalse(instance.is_dialogue_text("v1.0.4"))

            # Real dialogue sentences must be accepted
            self.assertTrue(instance.is_dialogue_text("Hello there, how are you?"))
            self.assertTrue(instance.is_dialogue_text("Wait!"))
            self.assertTrue(instance.is_dialogue_text("What...?"))
            self.assertTrue(instance.is_dialogue_text("I was waiting for you all morning."))

    def test_regression_no_menu_freeze(self):
        """Vérifie que translate_string protège les menus contre le lag en vérifiant is_dialogue_text."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Si translate_string est branché, il DOIT obligatoirement filtrer avec is_dialogue_text
        if "_live_translate_string" in content:
            self.assertIn("is_dialogue_text(s)", content)

    def test_regression_dialogue_filter_present(self):
        """Vérifie que config.say_menu_text_filter est actif dès init -999 et sécurisé dans init 999."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("config.say_menu_text_filter = _say_menu_filter_hook", content)
        self.assertIn("init 999 python:", content)
        self.assertIn("config.say_menu_text_filter = _chained_filter", content)

    def test_regression_memory_cache_instant_deduplication(self):
        """Vérifie que la deuxième consultation d'une phrase est instantanée sans appel HTTP."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        py_lines = []
        skip_block = False
        for line in lines:
            if line.strip().startswith("init 999"):
                skip_block = True
                continue
            if skip_block:
                continue
            if line.strip().startswith("init -999") or "config.say_menu_text_filter" in line or "_live_translator_instance = LiveTranslator()" in line:
                continue
            if line.startswith("    "):
                py_lines.append(line[4:])
            else:
                py_lines.append(line)

        test_scope = {"config": type("MockConfig", (), {"gamedir": "/mock/game", "name": "TestGame"})()}
        exec("".join(py_lines), test_scope)

        LiveTranslatorClass = test_scope["LiveTranslator"]
        with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
            instance = LiveTranslatorClass()
            instance.enabled = True
            instance.memory_cache = {"Bonjour": "Hello"}
            instance.opener = MagicMock()

            # Dès que présent dans le cache, opener n'est jamais sollicité
            result = instance.translate("Bonjour")
            self.assertEqual(result, "Hello")
            instance.opener.open.assert_not_called()

    def test_regression_native_language_activation(self):
        """Vérifie que le plugin active formellement la langue cible native de Ren'Py (default_language & change_language)."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("config.default_language = target_folder", content)
        self.assertIn("renpy.change_language(target_folder)", content)
        self.assertIn("def lang_folder(self):", content)

    def test_regression_robust_game_dir_resolution(self):
        """Vérifie que la résolution du dossier de jeu explore de multiples sources fiables et ne dépend pas aveuglément de getcwd."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("def _get_game_dir(self):", content)
        self.assertIn("os.path.dirname(os.path.abspath(__file__))", content)
        self.assertIn("config.gamedir", content)

    def test_regression_live_in_memory_stl_injection(self):
        """Vérifie que les nouvelles traductions sont injectées directement dans le StringTranslator en mémoire de Ren'Py."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("stl.translations[source_text] = translated_text", content)

    def test_regression_no_hook_cascade(self):
        """Vérifie l'absence de prolifération de hooks qui causait des retraductions en cascade (5 requêtes par réplique)."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Ne doit PAS surcharger Character.__call__, renpy.exports.say ni Text.__init__
        self.assertNotIn("renpy.character.Character.__call__ = ", content)
        self.assertNotIn("renpy.exports.say = ", content)
        self.assertNotIn("_rpy_text.Text.__init__ = ", content)

    def test_regression_timeout_adequate(self):
        """Vérifie que le TIMEOUT est au minimum de 4.0s pour éviter d'abandonner sur des phrases longues."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        m = re.search(r'TIMEOUT\s*=\s*([0-9.]+)', content)
        self.assertIsNotNone(m, "TIMEOUT constant not found")
        timeout_val = float(m.group(1))
        self.assertGreaterEqual(timeout_val, 4.0, "TIMEOUT must be at least 4.0s to avoid false timeouts on Google/LLM")

    def test_regression_init_priority_range(self):
        """Vérifie qu'aucune priorité init ne dépasse les limites strictes de Ren'Py (-999 à 999)."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        matches = re.findall(r'init\s+(-?\d+)', content)
        for val_str in matches:
            val = int(val_str)
            self.assertTrue(-999 <= val <= 999, f"Init priority {val} exceeds Ren'Py bounds (-999 to 999)")


    def test_regression_save_slot_rejection(self):
        """Vérifie que is_dialogue_text rejette formellement les slots de sauvegarde et questions système."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        py_lines = []
        skip_block = False
        for line in lines:
            if line.strip().startswith("init 999"):
                skip_block = True
                continue
            if skip_block:
                continue
            if line.strip().startswith("init -999") or "config.say_menu_text_filter" in line or "_live_translator_instance = LiveTranslator()" in line:
                continue
            if line.startswith("    "):
                py_lines.append(line[4:])
            else:
                py_lines.append(line)

        test_scope = {"config": type("MockConfig", (), {"gamedir": "/mock/game", "name": "TestGame"})()}
        exec("".join(py_lines), test_scope)

        LiveTranslatorClass = test_scope["LiveTranslator"]
        with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
            instance = LiveTranslatorClass()
            # Save slot timestamps must be rejected immediately (0 ms)
            self.assertFalse(instance.is_dialogue_text("{#file_time}{#weekday}Thursday, {#month}September 03 2026, 16:21"))
            self.assertFalse(instance.is_dialogue_text("{#slot_name}Slot 1"))
            # System confirmation prompts must be rejected
            self.assertFalse(instance.is_dialogue_text("Are you sure you want to return to the main menu?"))
            self.assertFalse(instance.is_dialogue_text("Are you sure you want to overwrite your save?"))
            self.assertFalse(instance.is_dialogue_text("Auto-Forward Time"))
            # Normal dialogues with formatting tags must still be accepted
            self.assertTrue(instance.is_dialogue_text("{i}Wait for me!{/i}"))
            self.assertTrue(instance.is_dialogue_text("{color=#ffeebb}Poor Judy. This has to be demoralizing.{/color}"))

    def test_regression_idempotent_choice_cache(self):
        """Vérifie qu'un choix traduit en français est immédiatement reconnu en cache (0ms) sans double requête HTTP."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        py_lines = []
        skip_block = False
        for line in lines:
            if line.strip().startswith("init 999"):
                skip_block = True
                continue
            if skip_block:
                continue
            if line.strip().startswith("init -999") or "config.say_menu_text_filter" in line or "_live_translator_instance = LiveTranslator()" in line:
                continue
            if line.startswith("    "):
                py_lines.append(line[4:])
            else:
                py_lines.append(line)

        test_scope = {"config": type("MockConfig", (), {"gamedir": "/mock/game", "name": "TestGame"})()}
        exec("".join(py_lines), test_scope)

        LiveTranslatorClass = test_scope["LiveTranslator"]
        with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
            instance = LiveTranslatorClass()
            instance.enabled = True
            instance.memory_cache = {}
            instance.persisted_strings = set()
            instance.game_dir = "/tmp"
            instance.game_id = "TestGame"
            instance.target_lang = "fr"

            # Mock _query_server returning translation for the English source
            instance._query_server = MagicMock(return_value={"translated": "Demandez-lui des explications", "lang_name": "french"})
            instance._persist_translation = MagicMock()

            # First call: English choice option
            res1 = instance.translate("Ask him for explanations")
            self.assertEqual(res1, "Demandez-lui des explications")
            self.assertEqual(instance._query_server.call_count, 1)

            # Second call: Ren'Py choice screen renders textbutton with the French caption
            res2 = instance.translate("Demandez-lui des explications")
            self.assertEqual(res2, "Demandez-lui des explications")
            # Must NOT call _query_server again (0ms cache hit)
            self.assertEqual(instance._query_server.call_count, 1)

    def test_regression_negative_cache_on_failure(self):
        """Vérifie que l'échec ou le timeout d'une requête est mis en cache négatif pour éviter les freezes en boucle."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        py_lines = []
        skip_block = False
        for line in lines:
            if line.strip().startswith("init 999"):
                skip_block = True
                continue
            if skip_block:
                continue
            if line.strip().startswith("init -999") or "config.say_menu_text_filter" in line or "_live_translator_instance = LiveTranslator()" in line:
                continue
            if line.startswith("    "):
                py_lines.append(line[4:])
            else:
                py_lines.append(line)

        test_scope = {"config": type("MockConfig", (), {"gamedir": "/mock/game", "name": "TestGame"})()}
        exec("".join(py_lines), test_scope)

        LiveTranslatorClass = test_scope["LiveTranslator"]
        with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
            instance = LiveTranslatorClass()
            instance.enabled = True
            instance.memory_cache = {}
            instance.persisted_strings = set()
            instance.game_dir = "/tmp"
            instance.game_id = "TestGame"
            instance.target_lang = "fr"

            # Mock server failure (e.g. timeout or offline)
            instance._query_server = MagicMock(return_value=None)

            # First attempt: queries server and fails
            res1 = instance.translate("A sentence that times out")
            self.assertEqual(res1, "A sentence that times out")
            self.assertEqual(instance._query_server.call_count, 1)

            # Subsequent UI ticks/redraws: must hit negative cache immediately (0 ms)
            res2 = instance.translate("A sentence that times out")
            self.assertEqual(res2, "A sentence that times out")
            self.assertEqual(instance._query_server.call_count, 1)

    def test_regression_system_screens_bypass(self):
        """Vérifie que le hook translate_string contourne explicitement les écrans de menu système."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("context_nesting_level", content)
        self.assertIn("'save'", content)
        self.assertIn("'load'", content)
        self.assertIn("'preferences'", content)
        self.assertIn("'file_slots'", content)

    def test_regression_translate_resilience_on_persist_error(self):
        """Vérifie que translate() retourne toujours le texte traduit même si _persist_translation lève une exception."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        py_lines = []
        skip_block = False
        for line in lines:
            if line.strip().startswith("init 999"):
                skip_block = True
                continue
            if skip_block:
                continue
            if line.strip().startswith("init -999") or "config.say_menu_text_filter" in line or "_live_translator_instance = LiveTranslator()" in line:
                continue
            if line.startswith("    "):
                py_lines.append(line[4:])
            else:
                py_lines.append(line)

        test_scope = {"config": type("MockConfig", (), {"gamedir": "/mock/game", "name": "TestGame"})()}
        exec("".join(py_lines), test_scope)

        LiveTranslatorClass = test_scope["LiveTranslator"]
        with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
            instance = LiveTranslatorClass()
            instance.enabled = True
            instance.memory_cache = {}
            instance.persisted_strings = set()
            instance.game_dir = "/tmp"
            instance.game_id = "TestGame"
            instance.target_lang = "fr"

            # Mock server returning translation successfully
            instance._query_server = MagicMock(return_value={"translated": "Texte traduit avec succès", "lang_name": "french"})
            # Force _persist_translation to raise an IOError (e.g. read-only disk, permission error)
            instance._persist_translation = MagicMock(side_effect=IOError("Permission denied"))

            res = instance.translate("English dialogue line")
            # Translation must STILL be returned to the player despite persistence error!
            self.assertEqual(res, "Texte traduit avec succès")
            self.assertEqual(instance.memory_cache["English dialogue line"], "Texte traduit avec succès")

    def test_regression_escape_renpy_str_unicode(self):
        """Vérifie que _escape_renpy_str gère sans crash les caractères accentués en Python 2 (str/bytes) et Python 3."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        py_lines = []
        skip_block = False
        for line in lines:
            if line.strip().startswith("init 999"):
                skip_block = True
                continue
            if skip_block:
                continue
            if line.strip().startswith("init -999") or "config.say_menu_text_filter" in line or "_live_translator_instance = LiveTranslator()" in line:
                continue
            if line.startswith("    "):
                py_lines.append(line[4:])
            else:
                py_lines.append(line)

        test_scope = {"config": type("MockConfig", (), {"gamedir": "/mock/game", "name": "TestGame"})()}
        exec("".join(py_lines), test_scope)

        LiveTranslatorClass = test_scope["LiveTranslator"]
        with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
            instance = LiveTranslatorClass()
            # Test string with quotes, newlines and french accents
            test_str = 'Un texte avec "guillemets" et éèàç ù\nNouvelle ligne'
            escaped = instance._escape_renpy_str(test_str)
            self.assertIn('\\"', escaped)
            self.assertIn('\\n', escaped)
            self.assertIn('éèàç', escaped)

    def test_regression_revertable_dict_shadowing(self):
        """Vérifie que translate() fonctionne même si 'dict' dans le store Ren'Py est RevertableDict (shadowing)."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        py_lines = []
        skip_block = False
        for line in lines:
            if line.strip().startswith("init 999"):
                skip_block = True
                continue
            if skip_block:
                continue
            if line.strip().startswith("init -999") or "config.say_menu_text_filter" in line or "_live_translator_instance = LiveTranslator()" in line:
                continue
            if line.startswith("    "):
                py_lines.append(line[4:])
            else:
                py_lines.append(line)

        class RevertableDict(dict):
            pass

        test_scope = {
            "config": type("MockConfig", (), {"gamedir": "/mock/game", "name": "TestGame"})(),
            "dict": RevertableDict  # Ren'Py replaces built-in dict with RevertableDict in store
        }
        exec("".join(py_lines), test_scope)

        LiveTranslatorClass = test_scope["LiveTranslator"]
        with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
            instance = LiveTranslatorClass()
            instance.enabled = True
            instance.memory_cache = {}
            instance.persisted_strings = set()
            instance.game_dir = "/tmp"
            instance.game_id = "TestGame"
            instance.target_lang = "fr"

            # _query_server returns a pure standard Python dict (from json.loads)
            instance._query_server = MagicMock(return_value={"translated": "Texte traduit anti-shadowing", "lang_name": "french"})
            instance._persist_translation = MagicMock()

            res = instance.translate("English shadow dialogue")
            self.assertEqual(res, "Texte traduit anti-shadowing")
            self.assertEqual(instance.memory_cache["English shadow dialogue"], "Texte traduit anti-shadowing")


class TestBatchPreload(unittest.TestCase):
    """Tests pour le mode batch et le preload des traductions."""

    def test_storage_batch_get_existing(self):
        """Vérifie que batch_get_existing retourne les traductions en cache efficacement."""
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        try:
            storage = TranslationStorage(temp_db.name)

            # Aucune traduction au départ
            result = storage.batch_get_existing("Game1", "fr", ["Hello", "World"])
            self.assertEqual(result, {})

            # Ajouter quelques traductions
            storage.save_translation("Game1", "Hello", "Bonjour", "fr")
            storage.save_translation("Game1", "World", "Monde", "fr")

            # Vérifier le batch
            result = storage.batch_get_existing("Game1", "fr", ["Hello", "World", "Missing"])
            self.assertEqual(len(result), 2)
            self.assertEqual(result["Hello"], "Bonjour")
            self.assertEqual(result["World"], "Monde")
            self.assertNotIn("Missing", result)

            # Liste vide
            result = storage.batch_get_existing("Game1", "fr", [])
            self.assertEqual(result, {})

            # Jeu différent
            result = storage.batch_get_existing("Game2", "fr", ["Hello"])
            self.assertEqual(result, {})
        finally:
            if os.path.exists(temp_db.name):
                os.remove(temp_db.name)

    def test_batch_translate_endpoint_cache_and_translate(self):
        """Vérifie le endpoint /api/batch_translate (cache hit + misses simulés)."""
        temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        old_storage = state.storage
        state.storage = TranslationStorage(temp_db.name)
        state.target_lang = "fr"

        try:
            handler = LiveTranslatorHandler.__new__(LiveTranslatorHandler)
            handler.path = "/api/batch_translate"

            # Pré-remplir une traduction dans le cache
            state.storage.save_translation("TestGame", "Hello", "Bonjour", "fr")

            # Mock engine
            mock_engine = MagicMock()
            mock_engine.translate.side_effect = ["Salut !", "Adieu !"]
            state.google_engine = mock_engine
            state.engine_name = "google"

            payload = {
                "texts": ["Hello", "Hi", "Bye"],
                "game_id": "TestGame",
                "target_lang": "fr"
            }
            body = json.dumps(payload).encode('utf-8')
            handler.rfile = io.BytesIO(body)
            handler.headers = {"Content-Length": len(body)}

            sent_data = []
            handler._send_json = lambda data, status=200: sent_data.append(data)
            handler.do_POST()

            self.assertEqual(len(sent_data), 1)
            data = sent_data[0]

            # Vérifier les compteurs
            self.assertEqual(data["total"], 3)
            self.assertEqual(data["already_cached"], 1)  # Hello était déjà en cache
            self.assertEqual(data["translated"], 2)       # Hi et Bye traduits
            self.assertEqual(data["errors"], 0)

            # Vérifier les résultats
            self.assertIn("Hello", data["results"])
            self.assertIn("Hi", data["results"])
            self.assertIn("Bye", data["results"])
            self.assertEqual(data["results"]["Hello"], "Bonjour")  # depuis le cache
            self.assertEqual(data["results"]["Hi"], "Salut !")
            self.assertEqual(data["results"]["Bye"], "Adieu !")

            # Vérifier que les nouvelles traductions sont en cache
            self.assertEqual(state.storage.get_translation("TestGame", "Hi", "fr"), "Salut !")
            self.assertEqual(state.storage.get_translation("TestGame", "Bye", "fr"), "Adieu !")
        finally:
            state.storage = old_storage
            if os.path.exists(temp_db.name):
                os.remove(temp_db.name)

    def test_batch_translate_empty_texts(self):
        """Vérifie que batch_translate avec texts=[] retourne un message informatif."""
        handler = LiveTranslatorHandler.__new__(LiveTranslatorHandler)
        handler.path = "/api/batch_translate"

        payload = {"texts": [], "game_id": "TestGame"}
        body = json.dumps(payload).encode('utf-8')
        handler.rfile = io.BytesIO(body)
        handler.headers = {"Content-Length": len(body)}

        sent_data = []
        handler._send_json = lambda data, status=200: sent_data.append(data)
        handler.do_POST()

        self.assertEqual(len(sent_data), 1)
        data = sent_data[0]
        self.assertEqual(data.get("status"), "no_texts")
        self.assertIn("note", data)

    def test_regression_preload_methods_exist(self):
        """Vérifie que les méthodes _extract_all_dialogue_texts et _preload_translations existent dans le plugin."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("def _extract_all_dialogue_texts(self):", content)
        self.assertIn("def _preload_translations(self):", content)
        self.assertIn("renpy.game.script", content)
        self.assertIn("/api/batch_translate", content)

    def test_regression_preload_trigger_in_init_999(self):
        """Vérifie que le déclencheur de pré-traduction est présent dans le bloc init 999."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("_preload_translations", content)
        self.assertIn("import threading as _preload_thr", content)
        self.assertIn("daemon=True", content)

    def test_extraction_mock_ast_traversal(self):
        """Vérifie la logique d'extraction AST avec des nœuds simulés (test de l'algorithme pur)."""
        # Tester l'algorithme de traversée directement, sans mock renpy
        texts = set()
        visited = set()
        stack = []

        class MockSay:
            def __init__(self, what, next_node=None):
                self.what = what
                self._next = next_node
                self.__class__.__name__ = 'Say'
            @property
            def next(self):
                return self._next

        class MockMenu:
            def __init__(self, items, next_node=None):
                self.items = items
                self._next = next_node
                self.__class__.__name__ = 'Menu'
            @property
            def next(self):
                return self._next

        # Créer une chaîne de nœuds
        node_end = MockSay("Goodbye!", next_node=None)
        node_menu = MockMenu([
            (None, "end_label", "Leave now"),
            (None, "stay_label", "Stay a while")
        ], next_node=node_end)
        node_start = MockSay("Hello there, how are you?", next_node=node_menu)

        stack.append(node_start)
        while stack:
            node = stack.pop()
            if node is None:
                continue
            node_id = id(node)
            if node_id in visited:
                continue
            visited.add(node_id)

            type_name = type(node).__name__

            if type_name == 'Say':
                what = node.what
                if what and len(what) > 2:
                    texts.add(what)

            elif type_name == 'Menu':
                for item in getattr(node, 'items', []):
                    if isinstance(item, (list, tuple)) and len(item) >= 3:
                        choice_text = item[2]
                        if choice_text and len(choice_text) > 2:
                            texts.add(choice_text)

            try:
                next_node = getattr(node, 'next', None)
                if next_node:
                    stack.append(next_node)
            except Exception:
                pass

        # Vérifier les textes extraits
        self.assertIn("Hello there, how are you?", texts)
        self.assertIn("Goodbye!", texts)
        self.assertIn("Leave now", texts)
        self.assertIn("Stay a while", texts)
        self.assertEqual(len(texts), 4)

    def test_regression_no_duplicate_or_identity_persistence(self):
        """Vérifie que _persist_translation ne sauvegarde jamais deux fois la même clé ni d'identités old==new."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("if not source_text or not translated_text or source_text == translated_text:", content)
        self.assertIn("if source_text in self.persisted_strings:", content)
        self.assertIn("if translated != text_str:", content)

    def test_regression_performance_caches_and_fast_paths(self):
        """Vérifie l'existence des fast-paths de performance O(1) et des caches de dialogue."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Vérifier la présence des structures de cache O(1)
        self.assertIn("skipped_cache", content)
        self.assertIn("_dialogue_check_cache", content)

        # Fast-paths dans _live_translate_string
        self.assertIn("if s in _live_translator_instance.memory_cache:", content)
        self.assertIn("if s in _live_translator_instance.skipped_cache:", content)
        self.assertIn("_live_translator_instance.skipped_cache.add(s)", content)

        # Injection native en masse à init 999
        self.assertIn("stl.translations[k] = v", content)

        # Écriture groupée en un seul flux de fichier pour _preload_translations
        self.assertIn("to_persist = []", content)
        self.assertIn("for src, trans in to_persist:", content)

    def test_dialogue_memoization_behavior(self):
        """Vérifie que is_dialogue_text utilise son cache pour les appels répétés."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        py_lines = []
        skip_block = False
        for line in lines:
            if line.strip().startswith("init 999"):
                skip_block = True
                continue
            if skip_block:
                continue
            if line.strip().startswith("init -999") or "config.say_menu_text_filter" in line or "_live_translator_instance = LiveTranslator()" in line:
                continue
            if line.startswith("    "):
                py_lines.append(line[4:])
            else:
                py_lines.append(line)

        test_scope = {"config": type("MockConfig", (), {"gamedir": "/mock/game", "name": "TestGame"})()}
        exec("".join(py_lines), test_scope)

        LiveTranslatorClass = test_scope["LiveTranslator"]
        with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
            instance = LiveTranslatorClass()
            instance._dialogue_check_cache = {}
            instance.skipped_cache = set()

            # Premier appel calcule et met en cache
            res1 = instance.is_dialogue_text("Hello there, how are you?")
            self.assertTrue(res1)
            self.assertIn("Hello there, how are you?", instance._dialogue_check_cache)
            self.assertTrue(instance._dialogue_check_cache["Hello there, how are you?"])

            # Deuxième appel retourne immédiatement le résultat depuis le cache
            instance._dialogue_check_cache["Hello there, how are you?"] = False # modifier artificiellement
            self.assertFalse(instance.is_dialogue_text("Hello there, how are you?"))

    def test_regression_lookahead_prefetcher(self):
        """Vérifie le fonctionnement du préchargeur prédictif (lookahead prefetcher)."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Vérifier que les méthodes du lookahead prefetcher sont définies et câblées
        self.assertIn("def _init_prefetcher(self):", content)
        self.assertIn("def _queue_prefetch_texts(self, texts):", content)
        self.assertIn("def _trigger_lookahead_prefetch(self):", content)
        self.assertIn("_trigger_lookahead_prefetch", content)
        self.assertIn("namemap = getattr(script, 'namemap', None)", content)

    def test_lookahead_queue_deduplication(self):
        """Vérifie que la file de préchargement évite les doublons et les chaînes déjà en cache."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        py_lines = []
        skip_block = False
        for line in lines:
            if line.strip().startswith("init 999"):
                skip_block = True
                continue
            if skip_block:
                continue
            if line.strip().startswith("init -999") or "config.say_menu_text_filter" in line or "_live_translator_instance = LiveTranslator()" in line:
                continue
            if line.startswith("    "):
                py_lines.append(line[4:])
            else:
                py_lines.append(line)

        test_scope = {"config": type("MockConfig", (), {"gamedir": "/mock/game", "name": "TestGame"})()}
        exec("".join(py_lines), test_scope)

        LiveTranslatorClass = test_scope["LiveTranslator"]
        with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
            import threading
            instance = LiveTranslatorClass()
            instance._prefetch_queue = []
            instance._prefetch_lock = threading.Lock()
            instance.memory_cache = {"Already translated": "Déjà traduit"}

            instance._queue_prefetch_texts(["Already translated", "Upcoming line 1", "Upcoming line 2"])
            self.assertNotIn("Already translated", instance._prefetch_queue)
            self.assertIn("Upcoming line 1", instance._prefetch_queue)
            self.assertIn("Upcoming line 2", instance._prefetch_queue)
            self.assertEqual(len(instance._prefetch_queue), 2)

            # Évite d'ajouter à nouveau si déjà dans la file
            instance._queue_prefetch_texts(["Upcoming line 1"])
            self.assertEqual(len(instance._prefetch_queue), 2)

    def test_prediction_nonblocking_and_prefetch(self):
        """Vérifie que la phase de prédiction de Ren'Py ne bloque JAMAIS sur le réseau."""
        rpy_path = os.path.join(BASE_DIR, "plugin", "00_translator.rpy")
        with open(rpy_path, "r", encoding="utf-8") as f:
            plugin_code = f.read()

        py_lines = []
        skip_block = False
        for line in plugin_code.splitlines(True):
            if "init 999 python:" in line:
                skip_block = True
                continue
            if skip_block:
                continue
            if line.strip().startswith("init -999") or "config.say_menu_text_filter" in line or "_live_translator_instance = LiveTranslator()" in line:
                continue
            if line.startswith("    "):
                py_lines.append(line[4:])
            else:
                py_lines.append(line)

        test_scope = {"config": type("MockConfig", (), {"gamedir": "/mock/game", "name": "TestGame"})()}
        exec("".join(py_lines), test_scope)

        LiveTranslatorClass = test_scope["LiveTranslator"]
        with patch.object(LiveTranslatorClass, '__init__', lambda self: None):
            import threading
            instance = LiveTranslatorClass()
            instance.enabled = True
            instance.memory_cache = {"Cached line": "Ligne en cache"}
            instance.persisted_strings = set()
            instance._prefetch_queue = []
            instance._prefetch_lock = threading.Lock()
            instance._query_server = MagicMock(return_value={"translated": "Should not be called"})

            # 1. Quand Ren'Py n'est pas en prédiction, translate appelle le serveur
            with patch.object(instance, '_is_predicting', return_value=False):
                res = instance.translate("Fresh line")
                self.assertEqual(res, "Should not be called")
                self.assertEqual(instance._query_server.call_count, 1)

            instance._query_server.reset_mock()

            # 2. Quand Ren'Py EST en prédiction :
            with patch.object(instance, '_is_predicting', return_value=True):
                # 2a. Si le texte est déjà en cache, retourne la traduction instantanément (0 ms)
                self.assertEqual(instance.translate("Cached line"), "Ligne en cache")
                self.assertEqual(instance._query_server.call_count, 0)

                # 2b. Si le texte n'est PAS en cache, ne bloque JAMAIS sur le serveur :
                # retourne le texte original et l'ajoute à la file de prefetch
                res_predict = instance.translate("Upcoming story dialogue")
                self.assertEqual(res_predict, "Upcoming story dialogue")
                self.assertEqual(instance._query_server.call_count, 0)  # Aucun appel HTTP bloquant
                self.assertIn("Upcoming story dialogue", instance._prefetch_queue)


if __name__ == "__main__":
    unittest.main()

