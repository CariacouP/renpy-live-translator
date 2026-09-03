"""engines.py - Moteurs de traduction multi-fournisseurs (Google, DeepL, Groq, Gemini, Mistral, LibreTranslate, Ollama)."""

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

def get_language_name(lang_code):
    """Retourne le nom complet d'une langue pour les prompts IA."""
    lang_names = {
        "fr": "français",
        "es": "espagnol",
        "de": "allemand",
        "it": "italien",
        "ja": "japonais",
        "ru": "russe",
        "en": "anglais",
        "pt": "portugais",
        "zh": "chinois"
    }
    return lang_names.get(lang_code.lower(), lang_code)

def get_llm_system_prompt(target_lang="fr"):
    """Génère le prompt système strict pour les LLMs traducteurs."""
    lang_label = get_language_name(target_lang)
    return (
        f"Tu es un traducteur de Visual Novel expert. Traduis fidèlement et naturellement le texte suivant en {lang_label}.\n"
        "RÈGLES ABSOLUES :\n"
        "- Ne renvoie STRICTEMENT QUE la traduction directe.\n"
        "- Ne traduis pas et ne modifie JAMAIS les marqueurs comme __TAG0__, __TAG1__, etc. Conserve-les exactement à leur place.\n"
        "- N'ajoute pas de guillemets autour de ta réponse, pas d'introduction, pas de notes ni de bavardage."
    )

def clean_llm_output(raw_translation, tags):
    """Nettoie la sortie des LLMs (guillemets superflus, balises) et restaure les tags."""
    cleaned = raw_translation.strip()
    if cleaned.startswith('"') and cleaned.endswith('"') and len(cleaned) > 1:
        cleaned = cleaned[1:-1].strip()
    elif cleaned.startswith('«') and cleaned.endswith('»') and len(cleaned) > 1:
        cleaned = cleaned[1:-1].strip()
    return restore_tags(cleaned, tags)


class GoogleEngine:
    """Moteur Google Translate ultra-rapide (~100-200ms) avec système multi-fallbacks sans clé."""
    def __init__(self):
        pass

    def _translate_chrome_ex(self, text, target_lang):
        params = {
            "client": "dict-chrome-ex",
            "sl": "auto",
            "tl": target_lang,
            "q": text
        }
        url = f"https://clients5.google.com/translate_a/t?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=3.5) as response:
            data = json.loads(response.read().decode('utf-8'))
            if isinstance(data, list):
                if len(data) > 0 and isinstance(data[0], list):
                    return "".join([part[0] for part in data if isinstance(part, list) and len(part) > 0])
                elif len(data) > 0 and isinstance(data[0], str):
                    return data[0]
        return ""

    def _translate_gtx(self, text, target_lang):
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": target_lang,
            "dt": "t",
            "q": text
        }
        url = f"https://translate.googleapis.com/translate_a/single?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=3.0) as response:
            result = json.loads(response.read().decode('utf-8'))
            translated_parts = []
            if result and isinstance(result, list) and len(result) > 0 and isinstance(result[0], list):
                for part in result[0]:
                    if part and len(part) > 0 and part[0]:
                        translated_parts.append(part[0])
            return "".join(translated_parts).strip()

    def _translate_mobile_scrape(self, text, target_lang):
        params = {
            "sl": "auto",
            "tl": target_lang,
            "q": text
        }
        url = f"https://translate.google.com/m?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)"}
        )
        with urllib.request.urlopen(req, timeout=3.5) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
            match = re.search(r'class="result-container">([^<]+)<', html_content)
            if match:
                import html as html_lib
                return html_lib.unescape(match.group(1)).strip()
        return ""

    def translate(self, text, target_lang="fr"):
        protected_text, tags = protect_tags(text)
        translated_text = ""

        # Tentative 1 : Endpoint Chrome Extension (le plus stable et sans rate-limit 429)
        try:
            translated_text = self._translate_chrome_ex(protected_text, target_lang)
        except Exception:
            translated_text = ""

        # Tentative 2 : Fallback GTX
        if not translated_text:
            try:
                translated_text = self._translate_gtx(protected_text, target_lang)
            except Exception:
                translated_text = ""

        # Tentative 3 : Fallback Web Mobile Scrape
        if not translated_text:
            try:
                translated_text = self._translate_mobile_scrape(protected_text, target_lang)
            except Exception:
                translated_text = ""

        if not translated_text:
            translated_text = text

        return restore_tags(translated_text, tags)



class DeepLEngine:
    """Moteur DeepL API Free et Pro avec qualité littéraire de référence."""
    def __init__(self, api_key=""):
        self.api_key = api_key.strip() if api_key else ""

    def _get_endpoint(self):
        if self.api_key.endswith(":fx"):
            return "https://api-free.deepl.com/v2/translate"
        return "https://api.deepl.com/v2/translate"

    def _normalize_lang(self, target_lang):
        code = target_lang.upper()
        if code == "EN":
            return "EN-US"
        if code == "PT":
            return "PT-PT"
        if code == "ZH":
            return "ZH-HANS"
        return code

    def translate(self, text, target_lang="fr"):
        if not self.api_key:
            return f"[DeepL Error: Clé API manquante dans la configuration] {text}"

        protected_text, tags = protect_tags(text)
        deepl_lang = self._normalize_lang(target_lang)

        payload = {
            "text": [protected_text],
            "target_lang": deepl_lang,
            "preserve_formatting": True
        }

        req = urllib.request.Request(
            self._get_endpoint(),
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "Authorization": f"DeepL-Auth-Key {self.api_key}",
                "Content-Type": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=5.0) as response:
                result = json.loads(response.read().decode('utf-8'))
                translations = result.get("translations", [])
                if translations:
                    raw = translations[0].get("text", "")
                    return restore_tags(raw, tags)
                return text
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode('utf-8'))
                msg = err_body.get("message", str(e))
            except Exception:
                msg = str(e)
            return f"[DeepL HTTP {e.code}: {msg}] {text}"
        except Exception as e:
            return f"[DeepL Error: {str(e)}] {text}"


class GroqEngine:
    """Moteur Groq Cloud ultra-rapide (<200ms) pour LLMs (Llama 3.3, Qwen, Mixtral)."""
    def __init__(self, api_key="", model="llama-3.3-70b-versatile"):
        self.api_key = api_key.strip() if api_key else ""
        self.model = model.strip() if model else "llama-3.3-70b-versatile"
        self.endpoint = "https://api.groq.com/openai/v1/chat/completions"

    def translate(self, text, target_lang="fr"):
        if not self.api_key:
            return f"[Groq Error: Clé API manquante dans la configuration] {text}"

        protected_text, tags = protect_tags(text)
        system_prompt = get_llm_system_prompt(target_lang)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": protected_text}
            ],
            "temperature": 0.2
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=6.0) as response:
                result = json.loads(response.read().decode('utf-8'))
                choices = result.get("choices", [])
                if choices:
                    raw = choices[0].get("message", {}).get("content", "").strip()
                    return clean_llm_output(raw, tags)
                return text
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode('utf-8'))
                msg = err_body.get("error", {}).get("message", str(e))
            except Exception:
                msg = str(e)
            return f"[Groq HTTP {e.code}: {msg}] {text}"
        except Exception as e:
            return f"[Groq Error: {str(e)}] {text}"


class GeminiEngine:
    """Moteur Google Gemini API (Gemini 2.0 Flash / 1.5 Flash)."""
    def __init__(self, api_key="", model="gemini-2.0-flash"):
        self.api_key = api_key.strip() if api_key else ""
        self.model = model.strip() if model else "gemini-2.0-flash"

    def translate(self, text, target_lang="fr"):
        if not self.api_key:
            return f"[Gemini Error: Clé API manquante dans la configuration] {text}"

        protected_text, tags = protect_tags(text)
        system_prompt = get_llm_system_prompt(target_lang)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\nTexte source à traduire :\n{protected_text}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=8.0) as response:
                result = json.loads(response.read().decode('utf-8'))
                candidates = result.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        raw = parts[0].get("text", "").strip()
                        return clean_llm_output(raw, tags)
                return text
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode('utf-8'))
                msg = err_body.get("error", {}).get("message", str(e))
            except Exception:
                msg = str(e)
            return f"[Gemini HTTP {e.code}: {msg}] {text}"
        except Exception as e:
            return f"[Gemini Error: {str(e)}] {text}"


class MistralEngine:
    """Moteur Mistral AI (Mistral Small / Large)."""
    def __init__(self, api_key="", model="mistral-small-latest"):
        self.api_key = api_key.strip() if api_key else ""
        self.model = model.strip() if model else "mistral-small-latest"
        self.endpoint = "https://api.mistral.ai/v1/chat/completions"

    def translate(self, text, target_lang="fr"):
        if not self.api_key:
            return f"[Mistral Error: Clé API manquante dans la configuration] {text}"

        protected_text, tags = protect_tags(text)
        system_prompt = get_llm_system_prompt(target_lang)

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": protected_text}
            ],
            "temperature": 0.2
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=6.0) as response:
                result = json.loads(response.read().decode('utf-8'))
                choices = result.get("choices", [])
                if choices:
                    raw = choices[0].get("message", {}).get("content", "").strip()
                    return clean_llm_output(raw, tags)
                return text
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode('utf-8'))
                msg = err_body.get("message", str(e))
            except Exception:
                msg = str(e)
            return f"[Mistral HTTP {e.code}: {msg}] {text}"
        except Exception as e:
            return f"[Mistral Error: {str(e)}] {text}"


class LibreTranslateEngine:
    """Moteur LibreTranslate (instances publiques gratuites ou auto-hébergées)."""
    def __init__(self, url="https://libretranslate.com", api_key=""):
        self.url = url.strip() if url else "https://libretranslate.com"
        self.api_key = api_key.strip() if api_key else ""

    def translate(self, text, target_lang="fr"):
        protected_text, tags = protect_tags(text)
        endpoint = f"{self.url.rstrip('/')}/translate"

        payload = {
            "q": protected_text,
            "source": "auto",
            "target": target_lang,
            "format": "text"
        }
        if self.api_key:
            payload["api_key"] = self.api_key

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=6.0) as response:
                result = json.loads(response.read().decode('utf-8'))
                translated = result.get("translatedText", "")
                if translated:
                    return restore_tags(translated, tags)
                return text
        except urllib.error.HTTPError as e:
            try:
                err_body = json.loads(e.read().decode('utf-8'))
                msg = err_body.get("error", str(e))
            except Exception:
                msg = str(e)
            return f"[LibreTranslate HTTP {e.code}: {msg}] {text}"
        except Exception as e:
            return f"[LibreTranslate Error: {str(e)}] {text}"


class OllamaEngine:
    """Moteur IA local via Ollama HTTP API."""
    def __init__(self, model="qwen3:latest", host="http://localhost:11434"):
        self.model = model
        self.host = host

    def translate(self, text, target_lang="fr"):
        protected_text, tags = protect_tags(text)
        system_prompt = get_llm_system_prompt(target_lang)

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
            with urllib.request.urlopen(req, timeout=12.0) as response:
                result = json.loads(response.read().decode('utf-8'))
                raw_translation = result.get("message", {}).get("content", "").strip()
                return clean_llm_output(raw_translation, tags)
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

