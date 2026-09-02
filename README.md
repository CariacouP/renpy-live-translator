# 🎮 Ren'Py Live Translator

[![CI](https://github.com/CariacouP/renpy-live-translator/actions/workflows/ci.yml/badge.svg)](https://github.com/CariacouP/renpy-live-translator/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.8+](https://img.shields.io/badge/Python-3.8+-brightgreen.svg)](https://www.python.org/)
[![Ren'Py: 7 & 8+](https://img.shields.io/badge/Ren'Py-7%20%26%208+-orange.svg)](https://www.renpy.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()

> Real-time, on-the-fly translation tool for games and Visual Novels built with **Ren'Py**.  
> Zero decompilation, zero `.rpa` extraction, zero risk of corrupting game files.

---

## ✨ Features & Highlights

* **⚡ 1-Click & Ready to Play:** No need to install the heavy Ren'Py SDK or deal with fragile decompilation tools and scripts.
* **💾 Permanent Auto-Patching:** Every translated line is automatically saved into `game/tl/<language>/live_translations.rpy`. As you progress, the game permanently translates itself into standard Ren'Py translation files.
* **🚀 0 ms Latency & Offline Mode:** All previously encountered lines are stored in a local SQLite cache and loaded directly into memory at game startup for instantaneous display.
* **🔄 Hot-Swappable Translation Engines:**
  * **Google Translate:** Lightning-fast (~100 to 200 ms per line), ideal for smooth, uninterrupted gameplay.
  * **Local AI (Ollama):** For contextual, nuanced, and stylized translations (automatic detection of models such as `qwen`, `llama3`, `dolphin3`, `gemma`, `phi3`).
* **🛡️ Native Ren'Py Syntax Protection:** Style tags (`{b}`, `{i}`, `{color}`) and variable interpolations (`[player_name]`) are safely preserved and shielded from corruption.
* **📊 Real-Time Web Dashboard:** Watch dialogue lines stream live as you play, monitor cache statistics, and switch languages or translation engines on the fly without restarting the game.
* **🌐 Cross-Platform & Backwards Compatible:** Runs on macOS, Linux, and Windows. Fully compatible with both **Ren'Py 7** (Python 2) and **Ren'Py 8+** (Python 3).

---

## 🚀 Quick Start

### 1. Launch the Local Server
* **On macOS / Linux:**
  ```bash
  ./start.sh
  ```
* **On Windows:**
  Double-click `start.bat` (or run `python server\server.py`).

The dashboard will automatically open in your default browser at [http://127.0.0.1:5005](http://127.0.0.1:5005).

---

### 2. Install the Plugin in Your Game
Simply copy the file:  
📁 `plugin/00_translator.rpy`

And paste it into the `game/` folder of your Ren'Py game:
```
Your_Renpy_Game/
└── game/
    ├── 00_translator.rpy   <-- Paste the file here
    ├── script.rpy (or .rpyc / .rpa archives)
    └── ...
```

---

### 3. Play!
Launch your game normally:
* As you advance through dialogue, lines appear translated on screen.
* The web dashboard displays the active dialogue stream and cache status in real time.
* `game/tl/<language>/live_translations.rpy` is continuously populated as you discover new lines.

---

## 🧠 Using Local AI (Ollama)

If you prefer translating with a local LLM:
1. Install and start [Ollama](https://ollama.com).
2. Pull your preferred model (e.g., `ollama pull qwen2.5:7b`, `ollama pull llama3:8b`, or `ollama pull phi3:mini`).
3. On the web dashboard ([http://127.0.0.1:5005](http://127.0.0.1:5005)), switch the engine to **Ollama** and select your model from the dropdown menu.

---

## ⚙️ Configuration

Default settings can be adjusted in `config.ini`:

```ini
[Translation]
# Target language code (e.g., en, fr, es, de, it, ja, ru)
TARGET_LANG = fr

[AI]
# Default local LLM model via Ollama
MODEL = qwen3:latest

[Server]
# Local HTTP server port
PORT = 5005
```

You can also change the target language and engine live at any time through the web dashboard.

---

## 📁 Project Structure

```
renpy-live-translator/
├── .github/
│   └── workflows/
│       └── ci.yml              # Automated multi-OS CI workflow
├── config.ini                  # Default configuration (target language, model, port)
├── LICENSE                     # MIT License
├── start.sh                    # macOS / Linux launcher
├── start.bat                   # Windows launcher
├── plugin/
│   └── 00_translator.rpy       # Ren'Py hook (copy to game/)
├── server/
│   ├── server.py               # Lightweight HTTP API server (zero external dependencies)
│   ├── storage.py              # SQLite storage & standalone export management
│   ├── engines.py              # Google Translate & Ollama translation engines
│   └── web/
│       └── index.html          # Interactive real-time web dashboard
└── tests/
    ├── __init__.py             # Test package marker
    └── test_live_translator.py # Automated test suite (11 unit tests)
```

---

## 🧪 Testing

The test suite relies entirely on Python's standard `unittest` library (no external test dependencies required):

```bash
python3 -m unittest discover -s tests
```

Or run the test suite file directly:
```bash
python3 tests/test_live_translator.py
```

---

## 📜 License

This project is open-source and released under the [MIT License](LICENSE).
