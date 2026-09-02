"""engines.py - Moteurs de traduction (Google Translate rapide et IA locale Ollama)."""

import re
import json
import urllib.request
import urllib.error
import urllib.parse
import time

def protect_tags(text):
    """
    Protège les balises de style Ren'Py {tag} et les interpolations [variable]
    en les remplaçant par des balises neutres avant traduction.
    """
    tags = []
    def replacer(match):
        idx = len(tags)
        tags.append(match.group(0))
        return f"__TAG{idx}__"

    # Capture toutes les balises Ren'Py {...} et interpolations [...]
    # en évitant les séquences d'échappement {{ et [[
    pattern = r'((?<!\{)\{(?!\{)[^{}]+\}(?!\})|(?<!\[)\[(?!\[)[^\[\]]+\](?!\]))'
    protected_text = re.sub(pattern, replacer, text)
    return protected_text, tags

TAG_REPAIRS = [
    (re.compile(r'\{taille(?=[=\s\}])', re.IGNORECASE), '{size'),
    (re.compile(r'\{/taille\}', re.IGNORECASE), '{/size}'),
    (re.compile(r'\{couleur(?=[=\s\}])', re.IGNORECASE), '{color'),
    (re.compile(r'\{/couleur\}', re.IGNORECASE), '{/color}'),
    (re.compile(r'\{police(?=[=\s\}])', re.IGNORECASE), '{font'),
    (re.compile(r'\{/police\}', re.IGNORECASE), '{/font}'),
    (re.compile(r'\{gras\}', re.IGNORECASE), '{b}'),
    (re.compile(r'\{/gras\}', re.IGNORECASE), '{/b}'),
    (re.compile(r'\{italique\}', re.IGNORECASE), '{i}'),
    (re.compile(r'\{/italique\}', re.IGNORECASE), '{/i}'),
]

def restore_tags(text, tags):
    """Restaure les balises Ren'Py protégées."""
    restored = text
    for i, tag in enumerate(tags):
        # Cherche le token exact ou avec des espaces introduits par un traducteur
        pattern = rf'__\s*TAG\s*{i}\s*__'
        restored = re.sub(pattern, lambda m: tag, restored, flags=re.IGNORECASE)
    # Filet de sécurité : réparer d'éventuelles balises Ren'Py traduites par erreur
    for pattern, replacement in TAG_REPAIRS:
        restored = pattern.sub(replacement, restored)
    return restored

class GoogleEngine:
    """Moteur Google Translate ultra-rapide (~100-200ms) sans dépendance lourde."""
    def __init__(self):
        self.endpoint = "https://translate.googleapis.com/translate_a/single"

    def translate(self, text, target_lang="fr"):
        protected_text, tags = protect_tags(text)

        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target_lang,
            "dt": "t",
            "q": protected_text
        }
        url = f"{self.endpoint}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )

        try:
            with urllib.request.urlopen(req, timeout=3.0) as response:
                result = json.loads(response.read().decode('utf-8'))
                translated_parts = []
                if result and isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
                    for part in result[0]:
                        if part and len(part) > 0 and part[0]:
                            translated_parts.append(part[0])
                translated_text = "".join(translated_parts).strip()
                if not translated_text:
                    translated_text = text

                return restore_tags(translated_text, tags)
        except Exception:
            return text

class OllamaEngine:
    """Moteur IA local via Ollama HTTP API."""
    def __init__(self, model="qwen3:latest", host="http://localhost:11434"):
        self.model = model
        self.host = host

    def translate(self, text, target_lang="fr"):
        protected_text, tags = protect_tags(text)

        lang_names = {
            "fr": "français",
            "es": "espagnol",
            "de": "allemand",
            "it": "italien",
            "ja": "japonais",
            "ru": "russe",
            "en": "anglais"
        }
        lang_label = lang_names.get(target_lang.lower(), target_lang)

        system_prompt = (
            f"Tu es un traducteur de Visual Novel expert. Traduis fidèlement le texte suivant en {lang_label}.\n"
            "RÈGLES ABSOLUES :\n"
            "- Ne renvoie QUE la traduction directe.\n"
            "- Ne traduis pas et ne modifie JAMAIS les marqueurs comme __TAG0__, __TAG1__, etc.\n"
            "- N'ajoute pas de guillemets autour de ta réponse, pas de notes ni de bavardage."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": protected_text}
            ],
            "stream": False,
            "options": {
                "temperature": 0.3
            }
        }

        url = f"{self.host}/api/chat"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=8.0) as response:
                result = json.loads(response.read().decode('utf-8'))
                raw_translation = result.get("message", {}).get("content", "").strip()
                if raw_translation.startswith('"') and raw_translation.endswith('"') and len(raw_translation) > 1:
                    raw_translation = raw_translation[1:-1].strip()
                return restore_tags(raw_translation, tags)
        except Exception:
            return text

def get_ollama_models(host="http://localhost:11434"):
    """Récupère la liste des modèles installés dans Ollama."""
    url = f"{host}/api/tags"
    req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1.5) as response:
            data = json.loads(response.read().decode('utf-8'))
            models = [m.get("name") for m in data.get("models", [])]
            return models
    except Exception:
        return []
