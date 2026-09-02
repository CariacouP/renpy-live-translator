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
from engines import protect_tags, restore_tags, GoogleEngine, OllamaEngine
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

    def test_plugin_local_tl_persistence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Importer ou instancier la logique du plugin
            # On simule LiveTranslator
            tl_dir = os.path.join(temp_dir, "tl", "french")
            os.makedirs(tl_dir)
            file_path = os.path.join(tl_dir, "live_translations.rpy")

            # Écriture
            with open(file_path, "w", encoding="utf-8") as f:
                f.write('translate french strings:\n\n    old "Welcome"\n    new "Bienvenue"\n\n')

            # Vérifier qu'on peut parser ce format
            pattern = r'old\s+"(.*?(?<!\\))"\s*\n\s*new\s+"(.*?(?<!\\))"'
            with open(file_path, "r", encoding="utf-8") as f:
                matches = re.findall(pattern, f.read())
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0], ("Welcome", "Bienvenue"))

if __name__ == "__main__":
    unittest.main()
