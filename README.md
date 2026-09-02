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

### 1. First-Time Setup (One-Time Only)

1. **Install the plugin:**  
   Copy 📁 `plugin/00_translator.rpy` into your game's `game/` folder:
   ```
   Your_Renpy_Game/
   └── game/
       ├── 00_translator.rpy   <-- Paste here
       └── ...
   ```

2. **Start the server once:**
   * **macOS / Linux:** `./start.sh`
   * **Windows:** Double-click `start.bat`
   
   The web dashboard will automatically open in your browser at [http://127.0.0.1:5005](http://127.0.0.1:5005).

3. **Choose your settings in the Web Dashboard:**
   * **Target Language:** Select your desired language (French, Spanish, German, Japanese, etc.).
   * **Translation Engine:** Choose **Google Translate** (instant) or **Local AI (Ollama)**.
   * *All settings changed in the dashboard are permanently saved into `config.ini`!*

4. **Launch your game once:**
   * The plugin connects to the server and **automatically registers its path** into `game/00_translator.rpy` and system cache (`~/.renpy_translator_path`).
   * No manual path editing required!

---

### 2. Subsequent Plays: 100% Automatic!

From now on, **you don't even need to open a terminal or start the server manually**:

1. **Just open your Ren'Py game!**
2. If the server is offline:
   * A dialog will ask if you want to start it in the background (`AUTO_START_MODE = "ask"`).
   * Or set `AUTO_START_MODE = "always"` in `00_translator.rpy` to start it instantly without any prompt.
3. Dialogue is translated live as you play.
4. When you quit the game, the background server is cleanly shut down automatically.

*(Note: You can still start the server manually with `./start.sh` or `start.bat` anytime you want to access the live web dashboard).*

The web dashboard is always accessible at [http://127.0.0.1:5005](http://127.0.0.1:5005).

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
