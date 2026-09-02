## ==============================================================================
## 00_translator.rpy - Ren'Py Live Translator Hook
## ==============================================================================
## Drop this file into the 'game/' folder of your Ren'Py game.
## It intercepts dialogues and choices on the fly, contacts the local server
## (Live Translator Server on http://127.0.0.1:5005), displays the translation,
## and automatically saves every translation in game/tl/<language>/live_translations.rpy.
## Compatible with Ren'Py 7 (Python 2) and Ren'Py 8+ (Python 3).
## ==============================================================================

init -999 python:
    import sys
    import os
    import json
    import re
    import codecs
    import time
    import subprocess
    import atexit

    ## --------------------------------------------------------------------------
    ## CONFIGURATION
    ## --------------------------------------------------------------------------
    # Optional path to server.py or to the renpy-live-translator root directory.
    # If left empty, the plugin will search for server.py automatically.
    # Examples:
    # Windows : SERVER_PATH = r"C:\Tools\renpy-live-translator\server\server.py"
    # macOS   : SERVER_PATH = "/Users/username/renpy-live-translator/server/server.py"
    SERVER_PATH = ""

    # Behavior when the server is offline at game launch:
    # "ask"      : Prompts the user with a dialog: "Would you like to start the server?"
    # "always"   : Automatically starts the server immediately without asking
    # "disabled" : Never auto-starts the server (manual startup only)
    AUTO_START_MODE = "ask"

    # Automatically stop the server on game exit ONLY IF the game started it itself:
    AUTO_STOP_SERVER = True

    # Python 2 (Ren'Py <= 7) vs Python 3 (Ren'Py 8+) compatibility helpers
    if sys.version_info[0] < 3:
        import urllib2 as _url_req
        import urllib2 as _url_err
        _is_py2 = True
        _str_types = (str, unicode)
    else:
        import urllib.request as _url_req
        import urllib.error as _url_err
        _is_py2 = False
        _str_types = (str,)

    class LiveTranslator(object):
        SERVER_URL = "http://127.0.0.1:5005/api/translate"
        SERVER_STATUS_URL = "http://127.0.0.1:5005/api/status"
        SERVER_SHUTDOWN_URL = "http://127.0.0.1:5005/api/shutdown"
        TIMEOUT = 2.0  # Max timeout per dialogue line to prevent game freezing

        def __init__(self):
            self.memory_cache = {}
            self.persisted_strings = set()
            self.enabled = True
            self.spawned_server = False
            self.server_process = None
            self.game_id = self._get_game_id()
            self.game_dir = getattr(config, 'gamedir', None) or os.getcwd()

            try:
                self.opener = _url_req.build_opener(_url_req.ProxyHandler({}))
            except Exception:
                self.opener = _url_req

            # Clean up the spawned server when the game exits
            atexit.register(self._cleanup)

            # Pre-load translations already saved locally in game/tl/
            self._load_local_translations()

            # Check server status and auto-start if needed
            self._ensure_server()

        def _get_game_id(self):
            """Extract a clean identifier for this game."""
            try:
                name = getattr(config, 'name', None) or getattr(config, 'save_directory', None)
                if name:
                    return str(name)
            except Exception:
                pass
            return "RenpyGame"

        def _remember_server_path(self, server_path):
            """Saves server_path globally and writes it into 00_translator.rpy if SERVER_PATH is empty."""
            if not server_path or not os.path.isfile(server_path):
                return

            # 1. Save globally in ~/.renpy_translator_path
            try:
                hist_path = os.path.expanduser("~/.renpy_translator_path")
                with open(hist_path, "w") as f:
                    f.write(server_path)
            except Exception:
                pass

            # 2. Update SERVER_PATH in 00_translator.rpy directly if currently empty
            global SERVER_PATH
            if not SERVER_PATH:
                SERVER_PATH = server_path
                try:
                    plugin_file = os.path.join(self.game_dir, "00_translator.rpy")
                    if os.path.isfile(plugin_file):
                        with codecs.open(plugin_file, "r", encoding="utf-8") as f:
                            content = f.read()

                        esc_path = server_path.replace('\\', '\\\\')
                        new_line = 'SERVER_PATH = r"{}"'.format(esc_path)
                        updated = re.sub(r'SERVER_PATH\s*=\s*["\'].*?["\']', new_line, content, count=1)
                        if updated != content:
                            with codecs.open(plugin_file, "w", encoding="utf-8") as f:
                                f.write(updated)
                except Exception:
                    pass

        def _is_server_running(self, timeout=0.4):
            """Checks if the Live Translator server is reachable and active."""
            try:
                req = _url_req.Request(self.SERVER_STATUS_URL)
                resp = self.opener.open(req, timeout=timeout)
                if resp.getcode() == 200:
                    raw = resp.read()
                    if not _is_py2 and isinstance(raw, bytes):
                        raw = raw.decode('utf-8', 'ignore')
                    data = json.loads(raw)
                    srv_path = data.get("server_path")
                    if srv_path:
                        self._remember_server_path(srv_path)
                    return data.get("status") == "online"
            except Exception:
                pass
            return False

        def _ask_user_dialog(self):
            """Displays a native confirmation dialog in English asking to start the server."""
            # Windows native MessageBox
            if sys.platform.startswith("win"):
                try:
                    import ctypes
                    # MB_YESNO = 0x04, MB_ICONQUESTION = 0x20, MB_SETFOREGROUND = 0x40000
                    res = ctypes.windll.user32.MessageBoxW(
                        0,
                        u"Live Translator server is not running.\n\nWould you like to start it now in the background?",
                        u"Ren'Py Live Translator",
                        0x04 | 0x20 | 0x40000
                    )
                    return res == 6  # 6 == IDYES
                except Exception:
                    return True

            # macOS AppleScript dialog
            elif sys.platform == "darwin":
                try:
                    script = 'display dialog "Live Translator server is not running.\\n\\nWould you like to start it now in the background?" buttons {"No", "Yes"} default button "Yes" with title "Ren\'Py Live Translator"'
                    p = subprocess.Popen(['osascript', '-e', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    out, _ = p.communicate()
                    out_str = out.decode('utf-8', 'ignore') if not isinstance(out, str) else out
                    return "Yes" in out_str
                except Exception:
                    return True

            # Linux Zenity dialog (fallback to True if not available)
            else:
                try:
                    p = subprocess.Popen([
                        'zenity', '--question',
                        '--title=Ren\'Py Live Translator',
                        '--text=Live Translator server is not running.\n\nWould you like to start it now in the background?'
                    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    p.communicate()
                    return p.returncode == 0
                except Exception:
                    return True

        def _resolve_server_script(self):
            """Finds the absolute path to server.py."""
            candidates = []

            # 1. User-configured SERVER_PATH
            if SERVER_PATH and isinstance(SERVER_PATH, _str_types) and SERVER_PATH.strip():
                exp = os.path.expanduser(SERVER_PATH.strip())
                if os.path.isfile(exp):
                    return exp
                if os.path.isdir(exp):
                    candidates.append(os.path.join(exp, "server.py"))
                    candidates.append(os.path.join(exp, "server", "server.py"))

            # 2. Check cached path in user home directory (~/.renpy_translator_path)
            try:
                hist_path = os.path.expanduser("~/.renpy_translator_path")
                if os.path.isfile(hist_path):
                    with open(hist_path, "r") as f:
                        saved = f.read().strip()
                        if saved and os.path.isfile(saved):
                            return saved
                        if saved and os.path.isdir(saved):
                            candidates.append(os.path.join(saved, "server.py"))
                            candidates.append(os.path.join(saved, "server", "server.py"))
            except Exception:
                pass

            # 3. Relative search from game directory
            gdir = self.game_dir
            candidates.append(os.path.join(gdir, "server", "server.py"))
            candidates.append(os.path.join(gdir, "live_translator", "server", "server.py"))
            parent = os.path.dirname(gdir)
            candidates.append(os.path.join(parent, "server", "server.py"))
            candidates.append(os.path.join(parent, "renpy-live-translator", "server", "server.py"))
            candidates.append(os.path.join(os.path.dirname(parent), "renpy-live-translator", "server", "server.py"))

            for path in candidates:
                if os.path.isfile(path):
                    return os.path.abspath(path)

            return None

        def _find_python3(self):
            """Finds a working Python 3 command."""
            # If current interpreter is Python 3, check if it can be used
            if sys.version_info[0] >= 3 and sys.executable:
                return [sys.executable]

            test_code = "import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)"
            
            if sys.platform.startswith("win"):
                commands_to_try = [["python"], ["py", "-3"], ["python3"]]
            else:
                commands_to_try = [["python3"], ["python"]]

            for cmd in commands_to_try:
                try:
                    p = subprocess.Popen(cmd + ["-c", test_code], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    p.communicate()
                    if p.returncode == 0:
                        return cmd
                except Exception:
                    pass

            return ["python3"] if not sys.platform.startswith("win") else ["python"]

        def _start_server(self):
            """Starts server.py as a detached background process."""
            script_path = self._resolve_server_script()
            if not script_path:
                return False

            py_cmd = self._find_python3()
            cmd = py_cmd + [script_path]
            server_dir = os.path.dirname(script_path)

            try:
                devnull = subprocess.DEVNULL
            except AttributeError:
                devnull = open(os.devnull, 'wb')

            try:
                kwargs = {
                    "cwd": server_dir,
                    "stdin": devnull,
                    "stdout": devnull,
                    "stderr": devnull
                }

                if sys.platform.startswith("win"):
                    # CREATE_NO_WINDOW (0x08000000) | DETACHED_PROCESS (0x00000200)
                    kwargs["creationflags"] = 0x08000000 | 0x00000200
                else:
                    if hasattr(os, "setpgrp"):
                        kwargs["preexec_fn"] = os.setpgrp
                    elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

                self.server_process = subprocess.Popen(cmd, **kwargs)
                self.spawned_server = True

                # Wait up to 2 seconds for server readiness
                for _ in range(10):
                    time.sleep(0.2)
                    if self._is_server_running(timeout=0.3):
                        return True
            except Exception:
                pass
            return False

        def _ensure_server(self):
            """Handles two-way server lifecycle: already running vs auto-starting."""
            if self._is_server_running():
                # Server is already running manually or from another session.
                # Keep it running and do not shut it down on exit.
                self.spawned_server = False
                return

            if AUTO_START_MODE == "disabled":
                return

            should_start = False
            if AUTO_START_MODE == "always":
                should_start = True
            elif AUTO_START_MODE == "ask":
                should_start = self._ask_user_dialog()

            if should_start:
                self._start_server()

        def _cleanup(self):
            """Stops the server on game exit only if this game instance started it."""
            if self.spawned_server and AUTO_STOP_SERVER:
                try:
                    payload = b"{}" if not _is_py2 else "{}"
                    req = _url_req.Request(
                        self.SERVER_SHUTDOWN_URL,
                        data=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    self.opener.open(req, timeout=0.6)
                except Exception:
                    pass

                if self.server_process:
                    try:
                        self.server_process.terminate()
                    except Exception:
                        pass

        def _escape_renpy_str(self, text):
            """Escape quotes and newlines for .rpy format."""
            if not text:
                return ""
            res = re.sub(r'\\(?![n"\'\\])', r'\\\\', text)
            res = res.replace('\\"', '"').replace('"', '\\"')
            res = res.replace('\r\n', '\\n').replace('\n', '\\n')
            return res

        def _unescape_renpy_str(self, text):
            """Unescape quotes and escaped newlines."""
            return text.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')

        def _load_local_translations(self):
            """Read existing game/tl/*/live_translations.rpy files to prefill the memory cache."""
            try:
                tl_root = os.path.join(self.game_dir, "tl")
                if not os.path.isdir(tl_root):
                    return

                for lang in os.listdir(tl_root):
                    file_path = os.path.join(tl_root, lang, "live_translations.rpy")
                    if os.path.isfile(file_path):
                        with codecs.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            pattern = r'old\s+"(.*?(?<!\\))"\s*\n\s*new\s+"(.*?(?<!\\))"'
                            matches = re.findall(pattern, content)
                            for old_str, new_str in matches:
                                orig = self._unescape_renpy_str(old_str)
                                trans = self._unescape_renpy_str(new_str)
                                self.memory_cache[orig] = trans
                                self.persisted_strings.add(orig)
            except Exception:
                pass

        def _persist_translation(self, lang_name, source_text, translated_text):
            """Write translation directly to game/tl/<lang_name>/live_translations.rpy."""
            if source_text in self.persisted_strings:
                return

            try:
                lang_folder = lang_name or "french"
                tl_dir = os.path.join(self.game_dir, "tl", lang_folder)
                if not os.path.exists(tl_dir):
                    os.makedirs(tl_dir)

                file_path = os.path.join(tl_dir, "live_translations.rpy")
                write_header = not os.path.exists(file_path) or os.path.getsize(file_path) == 0

                esc_old = self._escape_renpy_str(source_text)
                esc_new = self._escape_renpy_str(translated_text)

                with codecs.open(file_path, 'a', encoding='utf-8') as f:
                    if write_header:
                        f.write(u"# Translation file automatically generated by Live Translator\n")
                        f.write(u"translate {} strings:\n\n".format(lang_folder))
                    f.write(u'    old "{}"\n'.format(esc_old))
                    f.write(u'    new "{}"\n\n'.format(esc_new))

                self.persisted_strings.add(source_text)
            except Exception:
                pass

        def _should_skip(self, text):
            """Avoid sending empty strings, pure numbers, or punctuation."""
            if not text or not text.strip():
                return True
            stripped = text.strip()
            if not re.search(r'[a-zA-Z\u00C0-\u00FF\u0400-\u04FF\u3040-\u30FF\u4E00-\u9FFF]', stripped):
                return True
            return False

        def translate(self, text):
            """Intercept dialogue/choice text, return translation, and persist to game/tl/."""
            if not self.enabled or self._should_skip(text):
                return text

            # 1. In-memory cache check (Instant: 0 ms)
            if text in self.memory_cache:
                return self.memory_cache[text]

            # 2. Query local Live Translator HTTP server
            try:
                payload = json.dumps({
                    "text": text,
                    "game_id": self.game_id
                })

                if not _is_py2 and isinstance(payload, str):
                    payload = payload.encode('utf-8')

                req = _url_req.Request(
                    self.SERVER_URL,
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )

                response = self.opener.open(req, timeout=self.TIMEOUT)
                data = json.loads(response.read().decode('utf-8'))

                translated = data.get("translated", text)
                lang_name = data.get("lang_name", "french")

                if translated:
                    self.memory_cache[text] = translated
                    self._persist_translation(lang_name, text, translated)
                    return translated

            except Exception:
                # Never crash the game on connection or timeout error
                pass

            return text

    # Global translator instance
    _live_translator_instance = LiveTranslator()

    def _say_menu_filter_hook(text):
        """Official Ren'Py hook for dialogue lines and choice menus."""
        return _live_translator_instance.translate(text)

    # Register dialogue filter in Ren'Py configuration
    config.say_menu_text_filter = _say_menu_filter_hook

