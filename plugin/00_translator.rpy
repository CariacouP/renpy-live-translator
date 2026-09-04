## ==============================================================================
## 00_translator.rpy - Ren'Py Live Translator Hook (Ultra-Fast Edition)
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
    import threading
    import atexit

    ## --------------------------------------------------------------------------
    ## CONFIGURATION
    ## --------------------------------------------------------------------------
    # Optional path to server.py or to the renpy-live-translator root directory.
    # If left empty, the plugin will search for server.py automatically.
    SERVER_PATH = ""

    # Behavior when the server is offline at game launch:
    # "ask"      : Prompts the user with a dialog: "Would you like to start the server?"
    # "always"   : Automatically starts the server immediately without asking
    # "disabled" : Never auto-starts the server (manual startup only)
    AUTO_START_MODE = "ask"

    # Prompt to choose target language on game launch:
    # "always"   : Shows a native language selection popup at each game launch
    # "ask"      : Shows language selection if server was started by the game
    # "disabled" : Uses the language currently set in dashboard / config.ini
    PROMPT_LANGUAGE_ON_START = "always"

    # Automatically stop the server on game exit ONLY IF the game started it itself:
    AUTO_STOP_SERVER = True

    # Python 2 (Ren'Py <= 7) vs Python 3 (Ren'Py 8+) compatibility helpers
    if sys.version_info[0] < 3:
        import __builtin__ as _builtins
        import urllib2 as _url_req
        import urllib2 as _url_err
        import httplib as _http_client
        _is_py2 = True
        _str_types = (_builtins.str, _builtins.unicode)
    else:
        import builtins as _builtins
        import urllib.request as _url_req
        import urllib.error as _url_err
        import http.client as _http_client
        _is_py2 = False
        _str_types = (_builtins.str,)

    _dict_types = (_builtins.dict, dict)

    class LiveTranslator(object):
        SERVER_URL = "http://127.0.0.1:5005/api/translate"
        SERVER_STATUS_URL = "http://127.0.0.1:5005/api/status"
        SERVER_CONFIG_URL = "http://127.0.0.1:5005/api/config"
        SERVER_SHUTDOWN_URL = "http://127.0.0.1:5005/api/shutdown"
        TIMEOUT = 4.5  # Reliable timeout per dialogue line ensuring full translation returns

        def __init__(self):
            self.memory_cache = {}
            self.persisted_strings = set()
            self.enabled = True
            self.spawned_server = False
            self.server_process = None
            self.target_lang = "fr"
            self.game_id = self._get_game_id()
            self.game_dir = self._get_game_dir()

            try:
                self.opener = _url_req.build_opener(_url_req.ProxyHandler({}))
            except Exception:
                self.opener = _url_req

            # Clean up the spawned server when the game exits
            atexit.register(self._cleanup)

            # Pre-load translations already saved locally in game/tl/
            self._load_local_translations()

            # Check server status, auto-start and prompt language if configured
            self._ensure_server()

            # Immediately register game with server
            self._register_game()

        def _register_game(self):
            """Registers this game with the server immediately on launch."""
            try:
                payload = json.dumps({
                    "game_id": self.game_id,
                    "game_dir": self.game_dir,
                    "target_lang": self.target_lang
                })
                if not _is_py2 and isinstance(payload, str):
                    payload = payload.encode('utf-8')
                req = _url_req.Request(
                    "http://127.0.0.1:5005/api/register_game",
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )
                self.opener.open(req, timeout=1.5)
            except Exception:
                pass

        def _get_game_id(self):
            """Extract a clean identifier for this game."""
            try:
                name = getattr(config, 'name', None) or getattr(config, 'save_directory', None)
                if name:
                    return str(name)
            except Exception:
                pass
            return "RenpyGame"

        @property
        def lang_folder(self):
            """Map target language code to Ren'Py standard tl folder name."""
            lang_map = {
                "fr": "french",
                "en": "None",
                "es": "spanish",
                "de": "german",
                "it": "italian",
                "pt": "portuguese",
                "ru": "russian",
                "ja": "japanese",
                "zh": "chinese"
            }
            return lang_map.get(getattr(self, 'target_lang', 'fr'), "french")

        def _get_game_dir(self):
            """Reliably determines the game/ directory across all platforms and execution environments."""
            # 1. Ren'Py loader for this script file (100% infallible inside Ren'Py)
            try:
                import renpy
                if hasattr(renpy, 'loader') and hasattr(renpy.loader, 'transfn'):
                    p = renpy.loader.transfn("00_translator.rpy")
                    if p and os.path.isfile(p):
                        d = os.path.abspath(os.path.dirname(p))
                        if os.path.isdir(d):
                            return d
            except Exception:
                pass

            # 2. renpy.config.gamedir
            try:
                import renpy
                if hasattr(renpy, 'config') and getattr(renpy.config, 'gamedir', None):
                    gd = renpy.config.gamedir
                    if gd and os.path.isdir(gd):
                        return os.path.abspath(gd)
            except Exception:
                pass

            # 3. renpy.config.basedir / game
            try:
                import renpy
                if hasattr(renpy, 'config') and getattr(renpy.config, 'basedir', None):
                    bd_game = os.path.join(renpy.config.basedir, 'game')
                    if os.path.isdir(bd_game):
                        return os.path.abspath(bd_game)
            except Exception:
                pass

            candidates = []
            try:
                candidates.append(os.path.dirname(os.path.abspath(__file__)))
            except Exception:
                pass
            try:
                if hasattr(config, 'gamedir') and config.gamedir:
                    candidates.append(config.gamedir)
            except Exception:
                pass
            try:
                if hasattr(config, 'basedir') and config.basedir:
                    candidates.append(os.path.join(config.basedir, 'game'))
            except Exception:
                pass
            candidates.append(os.path.join(os.getcwd(), 'game'))
            candidates.append(os.getcwd())

            for d in candidates:
                if d and os.path.isdir(d):
                    if os.path.isdir(os.path.join(d, 'tl')) or os.path.isfile(os.path.join(d, '00_translator.rpy')):
                        return os.path.abspath(d)
            for d in candidates:
                if d and os.path.isdir(d):
                    return os.path.abspath(d)
            return os.getcwd()

        def _remember_server_path(self, server_path):
            """Saves server_path globally and writes it into 00_translator.rpy if SERVER_PATH is empty."""
            if not server_path or not os.path.isfile(server_path):
                return

            try:
                hist_path = os.path.expanduser("~/.renpy_translator_path")
                with open(hist_path, "w") as f:
                    f.write(server_path)
            except Exception:
                pass

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

        def _is_server_running(self, timeout=0.3):
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
            """Displays a native confirmation dialog asking to start the server."""
            if sys.platform.startswith("win"):
                try:
                    import ctypes
                    res = ctypes.windll.user32.MessageBoxW(
                        0,
                        u"Le serveur Live Translator n'est pas lancé.\n\nSouhaitez-vous le démarrer en arrière-plan ?",
                        u"Ren'Py Live Translator",
                        0x04 | 0x20 | 0x40000
                    )
                    return res == 6
                except Exception:
                    return True

            elif sys.platform == "darwin":
                try:
                    script = 'display dialog "Le serveur Live Translator n\'est pas lancé.\\n\\nSouhaitez-vous le démarrer en arrière-plan ?" buttons {"Non", "Oui"} default button "Oui" with title "Ren\'Py Live Translator"'
                    p = subprocess.Popen(['osascript', '-e', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    out, _ = p.communicate()
                    out_str = out.decode('utf-8', 'ignore') if not isinstance(out, str) else out
                    return "Oui" in out_str or "Yes" in out_str
                except Exception:
                    return True

            else:
                try:
                    p = subprocess.Popen([
                        'zenity', '--question',
                        '--title=Ren\'Py Live Translator',
                        '--text=Le serveur Live Translator n\'est pas lancé.\n\nSouhaitez-vous le démarrer en arrière-plan ?'
                    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    p.communicate()
                    return p.returncode == 0
                except Exception:
                    return True

        def _prompt_target_language(self):
            """Displays a native dialog allowing the user to select the target language."""
            if sys.platform == "darwin":
                try:
                    script = (
                        'set langList to {"Français (fr)", "English (en)", "Español (es)", "Deutsch (de)", "Italiano (it)", "Português (pt)", "Русский (ru)", "日本語 (ja)", "中文 (zh)"}\n'
                        'set chosen to choose from list langList with title "🎮 Ren\'Py Live Translator" with prompt "Choisissez la langue de traduction pour ce jeu :" default items {"Français (fr)"} OK button name "Valider" cancel button name "Garder actuelle"\n'
                        'if chosen is false then\n'
                        '    return "CURRENT"\n'
                        'else\n'
                        '    return item 1 of chosen\n'
                        'end if'
                    )
                    p = subprocess.Popen(['osascript', '-e', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    out, _ = p.communicate()
                    out_str = out.decode('utf-8', 'ignore') if not isinstance(out, str) else out
                    return self._parse_lang_choice(out_str)
                except Exception:
                    pass

            elif sys.platform.startswith("win"):
                try:
                    ps_cmd = (
                        "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');"
                        "$f=New-Object Windows.Forms.Form;$f.Text='🎮 Ren''Py Live Translator';$f.Size=New-Object Drawing.Size(340,180);"
                        "$f.StartPosition='CenterScreen';$f.TopMost=$true;$f.FormBorderStyle='FixedDialog';$f.MaximizeBox=$false;"
                        "$l=New-Object Windows.Forms.Label;$l.Location=New-Object Drawing.Point(20,15);$l.Size=New-Object Drawing.Size(290,25);"
                        "$l.Text='Choisissez la langue cible de traduction :';"
                        "$c=New-Object Windows.Forms.ComboBox;$c.Location=New-Object Drawing.Point(20,45);$c.Size=New-Object Drawing.Size(280,25);"
                        "$c.DropDownStyle='DropDownList';"
                        "[void]$c.Items.AddRange(@('Français (fr)','English (en)','Español (es)','Deutsch (de)','Italiano (it)','Português (pt)','Русский (ru)','日本語 (ja)','中文 (zh)'));"
                        "$c.SelectedIndex=0;"
                        "$b=New-Object Windows.Forms.Button;$b.Location=New-Object Drawing.Point(100,85);$b.Size=New-Object Drawing.Size(120,32);"
                        "$b.Text='Valider';$b.DialogResult=[Windows.Forms.DialogResult]::OK;"
                        "$f.Controls.Add($l);$f.Controls.Add($c);$f.Controls.Add($b);$f.AcceptButton=$b;"
                        "if($f.ShowDialog() -eq [Windows.Forms.DialogResult]::OK){Write-Output $c.SelectedItem}else{Write-Output 'CURRENT'}"
                    )
                    p = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    out, _ = p.communicate()
                    out_str = out.decode('utf-8', 'ignore') if not isinstance(out, str) else out
                    return self._parse_lang_choice(out_str)
                except Exception:
                    pass

            else:
                try:
                    p = subprocess.Popen([
                        'zenity', '--list',
                        '--title=Ren\'Py Live Translator',
                        '--text=Choisissez la langue cible de traduction :',
                        '--column=Code', '--column=Langue',
                        'fr', 'Français',
                        'en', 'English',
                        'es', 'Español',
                        'de', 'Deutsch',
                        'it', 'Italiano',
                        'pt', 'Português',
                        'ru', 'Русский',
                        'ja', '日本語',
                        'zh', '中文'
                    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    out, _ = p.communicate()
                    out_str = out.decode('utf-8', 'ignore') if not isinstance(out, str) else out
                    choice = out_str.strip().lower()
                    if choice in ('fr', 'en', 'es', 'de', 'it', 'pt', 'ru', 'ja', 'zh'):
                        return choice
                except Exception:
                    pass

            return None

        def _parse_lang_choice(self, text):
            """Extract standard 2-letter language code from string."""
            if not text:
                return None
            m = re.search(r'\(([a-z]{2})\)', text.lower())
            if m:
                return m.group(1)
            t = text.lower()
            if 'fr' in t or 'fran' in t: return 'fr'
            if 'es' in t or 'span' in t or 'esp' in t: return 'es'
            if 'de' in t or 'deut' in t or 'ger' in t: return 'de'
            if 'it' in t or 'ital' in t: return 'it'
            if 'pt' in t or 'port' in t: return 'pt'
            if 'ru' in t or 'russ' in t: return 'ru'
            if 'ja' in t or 'jap' in t: return 'ja'
            if 'zh' in t or 'chin' in t: return 'zh'
            if 'en' in t or 'angl' in t: return 'en'
            return None

        def _set_server_language(self, lang_code):
            """Sends selected target language to the Live Translator server."""
            if not lang_code:
                return
            self.target_lang = lang_code
            try:
                payload = json.dumps({"target_lang": lang_code})
                if not _is_py2 and isinstance(payload, str):
                    payload = payload.encode('utf-8')
                req = _url_req.Request(
                    self.SERVER_CONFIG_URL,
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )
                self.opener.open(req, timeout=1.5)
            except Exception:
                pass

        def _resolve_server_script(self):
            """Finds the absolute path to server.py."""
            candidates = []

            if SERVER_PATH and isinstance(SERVER_PATH, _str_types) and SERVER_PATH.strip():
                exp = os.path.expanduser(SERVER_PATH.strip())
                if os.path.isfile(exp):
                    return exp
                if os.path.isdir(exp):
                    candidates.append(os.path.join(exp, "server.py"))
                    candidates.append(os.path.join(exp, "server", "server.py"))

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
                    kwargs["creationflags"] = 0x08000000 | 0x00000200
                else:
                    if hasattr(os, "setpgrp"):
                        kwargs["preexec_fn"] = os.setpgrp
                    elif hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
                        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

                self.server_process = subprocess.Popen(cmd, **kwargs)
                self.spawned_server = True

                for _ in range(10):
                    time.sleep(0.2)
                    if self._is_server_running(timeout=0.3):
                        return True
            except Exception:
                pass
            return False

        def _ensure_server(self):
            """Handles server lifecycle and language selection prompt."""
            server_was_running = self._is_server_running()

            if not server_was_running:
                if AUTO_START_MODE == "disabled":
                    return

                should_start = False
                if AUTO_START_MODE == "always":
                    should_start = True
                elif AUTO_START_MODE == "ask":
                    should_start = self._ask_user_dialog()

                if should_start:
                    self._start_server()

            if PROMPT_LANGUAGE_ON_START in ("always", "ask"):
                chosen_lang = self._prompt_target_language()
                if chosen_lang and chosen_lang != "CURRENT":
                    self.target_lang = chosen_lang
                    self._set_server_language(chosen_lang)

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
            """Escape quotes and newlines for .rpy format safely in Python 2 and Python 3."""
            if not text:
                return u""
            if _is_py2 and isinstance(text, str):
                text = text.decode('utf-8', 'ignore')
            elif not isinstance(text, _str_types):
                text = unicode(text) if _is_py2 else str(text)

            res = re.sub(r'\\(?![n"\'\\])', r'\\\\', text)
            res = res.replace(u'\\"', u'"').replace(u'"', u'\\"')
            res = res.replace(u'\r\n', u'\\n').replace(u'\n', u'\\n')
            return res

        def _unescape_renpy_str(self, text):
            """Unescape quotes and escaped newlines."""
            if not text:
                return u""
            if _is_py2 and isinstance(text, str):
                text = text.decode('utf-8', 'ignore')
            return text.replace(u'\\"', u'"').replace(u'\\n', u'\n').replace(u'\\\\', u'\\')

        def _load_local_translations(self):
            """Read existing game/tl/*/live_translations.rpy files to prefill the memory cache."""
            try:
                game_dir = self.game_dir or self._get_game_dir()
                self.game_dir = game_dir
                tl_root = os.path.join(game_dir, "tl")
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
                                if orig != trans:
                                    self.memory_cache[orig] = trans
                                    self.memory_cache[trans] = trans
                                self.persisted_strings.add(orig)
            except Exception:
                pass

        def _persist_translation(self, lang_name, source_text, translated_text):
            """Write translation directly to game/tl/<lang_name>/live_translations.rpy."""
            if source_text in self.persisted_strings:
                return

            try:
                lang_folder = lang_name or self.lang_folder or "french"
                game_dir = self.game_dir or self._get_game_dir()
                self.game_dir = game_dir
                tl_dir = os.path.join(game_dir, "tl", lang_folder)
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

                # Immediately register in Ren'Py active in-memory translator
                try:
                    import renpy
                    active_lang = getattr(renpy.game.preferences, 'language', None) or lang_folder
                    stl = renpy.game.script.translator.strings.get(active_lang)
                    if stl and hasattr(stl, 'translations'):
                        stl.translations[source_text] = translated_text
                except Exception:
                    pass
            except Exception:
                pass
            except Exception:
                pass

        def _extract_all_dialogue_texts(self):
            """Walk the in-memory Ren'Py script AST to collect every reachable dialogue and choice text."""
            texts = set()
            visited = set()
            stack = []

            try:
                import renpy
                script = renpy.game.script
                start_node = getattr(script, 'nod', None)
                if start_node is None:
                    return []
                stack.append(start_node)
            except Exception:
                return []

            def _safe_str(obj):
                try:
                    return _builtins.str(obj) if not _is_py2 else unicode(obj)
                except Exception:
                    return u""

            while stack:
                node = stack.pop()
                if node is None:
                    continue
                node_id = id(node)
                if node_id in visited:
                    continue
                visited.add(node_id)

                type_name = type(node).__name__

                # Say nodes — the main dialogue text
                if type_name == 'Say':
                    try:
                        what = _safe_str(getattr(node, 'what', ''))
                        if what and self.is_dialogue_text(what):
                            texts.add(what)
                    except Exception:
                        pass

                # Menu nodes — choice text
                elif type_name == 'Menu':
                    try:
                        items = getattr(node, 'items', []) or []
                        for item in items:
                            if isinstance(item, (list, tuple)) and len(item) >= 1:
                                choice_text = item[0]
                                if choice_text and isinstance(choice_text, _str_types) and not self._should_skip(choice_text):
                                    texts.add(_safe_str(choice_text))
                                # Follow the choice's block
                                if len(item) >= 3 and item[2]:
                                    sub_block = item[2]
                                    if isinstance(sub_block, list):
                                        stack.extend(sub_block)
                                    else:
                                        stack.append(sub_block)
                    except Exception:
                        pass

                # If nodes — follow all branches
                elif type_name == 'If':
                    try:
                        entries = getattr(node, 'entries', []) or []
                        for entry in entries:
                            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                                block = entry[1]
                                if block:
                                    stack.append(block)
                    except Exception:
                        pass

                # While nodes
                elif type_name == 'While':
                    try:
                        block = getattr(node, 'block', None)
                        if block:
                            stack.append(block)
                    except Exception:
                        pass

                # Call nodes
                elif type_name == 'Call':
                    try:
                        label = getattr(node, 'label', None)
                        if label:
                            target = renpy.game.script.lookup(label)
                            if target:
                                stack.append(target)
                    except Exception:
                        pass

                # Always follow the next node in the chain
                try:
                    next_node = getattr(node, 'next', None)
                    if next_node:
                        stack.append(next_node)
                except Exception:
                    pass

            return list(texts)

        def _preload_translations(self):
            """Extract all dialogue texts from the script AST and batch-translate them."""
            try:
                texts = self._extract_all_dialogue_texts()
                if not texts:
                    return

                # Deduplicate against already-cached / already-persisted texts
                new_texts = [t for t in texts if t not in self.memory_cache and t not in self.persisted_strings]
                if not new_texts:
                    return

                # Send batch to server
                try:
                    payload = json.dumps({
                        "texts": new_texts,
                        "game_id": self.game_id,
                        "target_lang": self.target_lang
                    })
                    if not _is_py2 and isinstance(payload, str):
                        payload = payload.encode('utf-8')

                    req = _url_req.Request(
                        "http://127.0.0.1:5005/api/batch_translate",
                        data=payload,
                        headers={"Content-Type": "application/json"}
                    )
                    response = self.opener.open(req, timeout=120.0)
                    raw = response.read()
                    if not _is_py2 and isinstance(raw, bytes):
                        raw = raw.decode('utf-8', 'ignore')
                    data = json.loads(raw)
                except Exception:
                    return  # Server offline or timeout — will be done next session

                if not data or not isinstance(data, _dict_types):
                    return

                results = data.get("results", {})
                lang_name = data.get("lang_name", "french")

                if not results:
                    return

                # Inject into memory and persist to disk
                for source, translation in results.items():
                    if translation and translation != source:
                        self.memory_cache[source] = translation
                        self.memory_cache[translation] = translation
                        try:
                            self._persist_translation(lang_name, source, translation)
                        except Exception:
                            pass
            except Exception:
                pass

        SKIP_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.ogg', '.mp3', '.wav', '.opus', '.rpy', '.rpyc', '.ttf', '.otf', '.woff', '.json', '.xml', '.csv')
        SKIP_PREFIXES = ('gui/', 'images/', 'audio/', 'music/', 'sound/', 'voice/', 'fonts/', 'tl/', 'cache/', '#', '{#', '@', 'http://', 'https://')
        SKIP_UI_WORDS = (
            'start', 'start game', 'load', 'load game', 'save', 'save game',
            'preferences', 'options', 'settings', 'about', 'help', 'quit',
            'exit', 'return', 'main menu', 'back', 'skip', 'auto', 'history',
            'quick save', 'quick load', 'q.save', 'q.load', 'dialogue', 'fullscreen',
            'window', 'music', 'sound', 'voice', 'display', 'rollback', 'empty slot',
            'auto-forward time', 'text speed', 'music volume', 'sound volume', 'voice volume',
            'rollback side', 'unseen text', 'after choices', 'transitions'
        )

        def is_translatable_ui_string(self, text):
            """Strict filter to safely identify human-readable texts without touching code or assets."""
            if not text or not isinstance(text, _str_types):
                return False

            s = text.strip()
            if len(s) < 2:
                return False

            s_lower = s.lower()
            if s_lower in self.SKIP_UI_WORDS:
                return False

            if s.startswith('#') and len(s) in (4, 5, 7, 9):
                return False

            for ext in self.SKIP_EXTENSIONS:
                if s_lower.endswith(ext):
                    return False
            for pfx in self.SKIP_PREFIXES:
                if s_lower.startswith(pfx):
                    return False

            if re.match(r'^[vV]?\d+(\.\d+)+[a-zA-Z0-9._-]*$', s):
                return False

            if not re.search(r'[a-zA-Z\u00C0-\u00FF\u0400-\u04FF\u3040-\u30FF\u4E00-\u9FFF]', s):
                return False
            if re.match(r'^[\d\s.,:;+-\/%=#$€£¥°*()\[\]{}]+$', s):
                return False

            if ' ' not in s:
                if s.startswith('_') or '__' in s or (re.match(r'^[a-zA-Z0-9_]+$', s) and '_' in s):
                    return False

            return True

        def is_dialogue_text(self, text):
            """Identifies human-readable story dialogue lines while ignoring short UI buttons, save slots, and menus."""
            if not text or not isinstance(text, _str_types):
                return False
            s = text.strip()
            if len(s) < 3:
                return False

            # Immediate exclusion of Ren'Py text tags, file/save slot timestamps, and system UI
            if s.startswith('{#'):
                return False
            if '{#file_time}' in s or '{#weekday}' in s or '{#slot' in s:
                return False
            if '[config.' in s or '[renpy.' in s or '{a=' in s:
                return False

            s_lower = s.lower()
            if s_lower in self.SKIP_UI_WORDS:
                return False

            # Exclude common system dialogue confirmation questions
            if any(confirm in s_lower for confirm in (
                'are you sure you want to return',
                'are you sure you want to quit',
                'are you sure you want to overwrite',
                'this will lose unsaved progress'
            )):
                return False

            for pfx in self.SKIP_PREFIXES:
                if s.startswith(pfx) or s_lower.startswith(pfx):
                    return False
            for ext in self.SKIP_EXTENSIONS:
                if s_lower.endswith(ext):
                    return False

            # Strip Ren'Py style/formatting tags ({color...}, {size...}, etc.) before evaluating words
            clean_s = re.sub(r'\{[^{}]*\}', '', s).strip()
            if len(clean_s) < 2:
                return False

            clean_lower = clean_s.lower().strip('!?. \t\r\n')
            if clean_lower in self.SKIP_UI_WORDS:
                return False

            words = clean_s.split()
            if len(words) >= 3:
                return True
            if len(words) >= 1 and any(p in clean_s for p in ('!', '?', '...', '—', '“', '”', '"')):
                return True
            return False

        def _should_skip(self, text):
            """Avoid sending empty strings, pure numbers, or punctuation."""
            if not text:
                return True
            try:
                s = text.strip() if isinstance(text, _str_types) else str(text).strip()
            except Exception:
                return True
            if not s:
                return True
            if re.match(r'^[\d\s.,:;!?+\-\/%=#$€£¥°*()\[\]{}"\'`~^|<>&]+$', s):
                return True
            return False

        def _query_server(self, text):
            """Queries the local Live Translator HTTP server with reliable urllib."""
            try:
                payload = json.dumps({
                    "text": text,
                    "game_id": self.game_id,
                    "target_lang": self.target_lang
                })
                if not _is_py2 and isinstance(payload, str):
                    payload = payload.encode('utf-8')
                elif _is_py2 and isinstance(payload, unicode):
                    payload = payload.encode('utf-8')

                req = _url_req.Request(
                    self.SERVER_URL,
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )

                response = self.opener.open(req, timeout=self.TIMEOUT)
                raw = response.read()
                if not _is_py2 and isinstance(raw, bytes):
                    raw = raw.decode('utf-8', 'ignore')
                return json.loads(raw)
            except Exception:
                return None

        def translate(self, text):
            """Intercept dialogue/choice/screen text, return translation (0ms if cached), and persist to game/tl/."""
            if not self.enabled or self._should_skip(text):
                return text

            text_str = unicode(text) if _is_py2 and not isinstance(text, unicode) else str(text)

            # 1. In-memory cache check (Instant: 0 ms)
            if text_str in self.memory_cache:
                return self.memory_cache[text_str]

            # 2. Query local server
            translated = None
            lang_name = "french"
            try:
                data = self._query_server(text_str)
                if data and (isinstance(data, _dict_types) or hasattr(data, "get")):
                    translated = data.get("translated")
                    lang_name = data.get("lang_name", "french")
            except Exception:
                pass

            if translated and translated.strip():
                # Store both source -> translated and translated -> translated to prevent double-translation of choices
                self.memory_cache[text_str] = translated
                self.memory_cache[translated] = translated
                try:
                    self._persist_translation(lang_name, text_str, translated)
                except Exception:
                    pass
                return translated

            # 3. Negative cache: remember original text for session to prevent freeze loops on every UI frame
            self.memory_cache[text_str] = text_str
            return text

    # Global translator instance
    _live_translator_instance = LiveTranslator()

    def _say_menu_filter_hook(text):
        """Official Ren'Py hook for all dialogue lines and choice menus."""
        return _live_translator_instance.translate(text)

    # 1. Register dialogue and choice menu filter
    config.say_menu_text_filter = _say_menu_filter_hook


init 999 python:
    ## --------------------------------------------------------------------------
    ## LATE HOOK REINFORCEMENT & NATIVE LANGUAGE ACTIVATION
    ## --------------------------------------------------------------------------
    # 1. Activate target language natively in Ren'Py
    try:
        target_folder = _live_translator_instance.lang_folder or "french"
        config.default_language = target_folder
        if getattr(renpy.game.preferences, 'language', None) != target_folder:
            renpy.change_language(target_folder)
    except Exception:
        pass

    # 2. Ensures dialogue & choice filter remains active
    if getattr(config, 'say_menu_text_filter', None) != _say_menu_filter_hook:
        _prev_filter = getattr(config, 'say_menu_text_filter', None)
        def _chained_filter(text):
            if _prev_filter and callable(_prev_filter):
                try:
                    text = _prev_filter(text)
                except Exception:
                    pass
            return _live_translator_instance.translate(text)
        config.say_menu_text_filter = _chained_filter

    # 3. Universal Ren'Py translate_string hook (with zero-lag dialogue & menu protection)
    try:
        import renpy.translation as _rpy_trans
        if hasattr(_rpy_trans, 'translate_string'):
            if not getattr(_rpy_trans.translate_string, '_live_trans_hooked', False):
                _orig_trans_string = _rpy_trans.translate_string
                def _live_translate_string(s, *args, **kwargs):
                    try:
                        res = _orig_trans_string(s, *args, **kwargs)
                        if res != s:
                            return res
                        # Fast-path: Never query network during system menu screens or sub-contexts
                        if hasattr(renpy, 'context_nesting_level') and renpy.context_nesting_level() > 0:
                            return res
                        for _sname in ('save', 'load', 'file_slots', 'preferences', 'help', 'history', 'main_menu'):
                            if hasattr(renpy, 'get_screen') and renpy.get_screen(_sname):
                                return res
                        if isinstance(s, _str_types) and _live_translator_instance.is_dialogue_text(s):
                            return _live_translator_instance.translate(s)
                    except Exception:
                        pass
                    return _orig_trans_string(s, *args, **kwargs)
                _live_translate_string._live_trans_hooked = True
                _rpy_trans.translate_string = _live_translate_string
    except Exception:
        pass

    # 4. Background preload of all dialogue (non-blocking)
    try:
        import threading as _preload_thr
        def _do_preload():
            try:
                _live_translator_instance._preload_translations()
            except Exception:
                pass
        _preload_thr.Thread(target=_do_preload, daemon=True).start()
    except Exception:
        pass




