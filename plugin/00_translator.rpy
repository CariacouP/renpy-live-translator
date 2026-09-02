## ==============================================================================
## 00_translator.rpy - Ren'Py Live Translator Hook
## ==============================================================================
## Déposez simplement ce fichier dans le dossier 'game/' de votre jeu Ren'Py.
## Il intercepte les dialogues et choix à la volée, contacte le serveur local
## (Live Translator Server sur http://127.0.0.1:5005), affiche la traduction,
## et sauvegarde automatiquement chaque traduction dans game/tl/<langue>/live_translations.rpy
## Compatible Ren'Py 7 (Python 2) et Ren'Py 8+ (Python 3).
## ==============================================================================

init -999 python:
    import sys
    import os
    import json
    import re
    import codecs

    # Gestion de la compatibilité Python 2 (Ren'Py <= 7) et Python 3 (Ren'Py 8+)
    if sys.version_info[0] < 3:
        import urllib2 as _url_req
        import urllib2 as _url_err
        _is_py2 = True
    else:
        import urllib.request as _url_req
        import urllib.error as _url_err
        _is_py2 = False

    class LiveTranslator(object):
        SERVER_URL = "http://127.0.0.1:5005/api/translate"
        TIMEOUT = 2.0  # Timeout maximal par réplique pour éviter tout gel du jeu

        def __init__(self):
            self.memory_cache = {}
            self.persisted_strings = set()
            self.enabled = True
            self.game_id = self._get_game_id()
            self.game_dir = getattr(config, 'gamedir', None) or os.getcwd()
            
            try:
                self.opener = _url_req.build_opener(_url_req.ProxyHandler({}))
            except Exception:
                self.opener = _url_req

            # Pré-charger les traductions déjà sauvegardées localement dans game/tl/
            self._load_local_translations()

        def _get_game_id(self):
            """Extrait un identifiant propre pour ce jeu."""
            try:
                name = getattr(config, 'name', None) or getattr(config, 'save_directory', None)
                if name:
                    return str(name)
            except Exception:
                pass
            return "RenpyGame"

        def _escape_renpy_str(self, text):
            """Échappe les guillemets et retours à la ligne pour le format .rpy."""
            if not text:
                return ""
            # Échapper les antislashs isolés
            res = re.sub(r'\\(?![n"\'\\])', r'\\\\', text)
            # Échapper les guillemets doubles
            res = res.replace('\\"', '"').replace('"', '\\"')
            # Normaliser les sauts de ligne
            res = res.replace('\r\n', '\\n').replace('\n', '\\n')
            return res

        def _unescape_renpy_str(self, text):
            """Déchiffre les guillemets et sauts de ligne échappés."""
            return text.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')

        def _load_local_translations(self):
            """Lit les fichiers game/tl/*/live_translations.rpy existants pour pré-remplir le cache."""
            try:
                tl_root = os.path.join(self.game_dir, "tl")
                if not os.path.isdir(tl_root):
                    return

                for lang in os.listdir(tl_root):
                    file_path = os.path.join(tl_root, lang, "live_translations.rpy")
                    if os.path.isfile(file_path):
                        with codecs.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            # Parse les couples old "..." / new "..."
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
            """Écrit la traduction en direct dans game/tl/<lang_name>/live_translations.rpy."""
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
                        f.write(u"# Fichier de traduction généré automatiquement par Live Translator\n")
                        f.write(u"translate {} strings:\n\n".format(lang_folder))
                    f.write(u'    old "{}"\n'.format(esc_old))
                    f.write(u'    new "{}"\n\n'.format(esc_new))

                self.persisted_strings.add(source_text)
            except Exception:
                pass

        def _should_skip(self, text):
            """Évite d'envoyer des chaînes vides, purement numériques ou de ponctuation."""
            if not text or not text.strip():
                return True
            stripped = text.strip()
            if not re.search(r'[a-zA-Z\u00C0-\u00FF\u0400-\u04FF\u3040-\u30FF\u4E00-\u9FFF]', stripped):
                return True
            return False

        def translate(self, text):
            """Intercepte le texte, renvoie sa traduction et la sauvegarde dans game/tl/."""
            if not self.enabled or self._should_skip(text):
                return text

            # 1. Vérification dans le cache mémoire local (Instantané : 0 ms)
            if text in self.memory_cache:
                return self.memory_cache[text]

            # 2. Requête vers le serveur de traduction local
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
                    # Sauvegarde directe dans game/tl/<lang_name>/live_translations.rpy
                    self._persist_translation(lang_name, text, translated)
                    return translated

            except Exception:
                # En cas de timeout, serveur déconnecté ou erreur, continuer avec le texte d'origine
                # pour ne JAMAIS interrompre ni faire crasher le jeu du joueur.
                pass

            return text

    # Instanciation unique du traducteur
    _live_translator_instance = LiveTranslator()

    def _say_menu_filter_hook(text):
        """Hook officiel Ren'Py pour les dialogues et les menus de choix."""
        return _live_translator_instance.translate(text)

    # Enregistrement du filtre de dialogue dans la configuration Ren'Py
    config.say_menu_text_filter = _say_menu_filter_hook
