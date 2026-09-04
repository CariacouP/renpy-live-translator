"""storage.py - Gestionnaire de stockage persistant SQLite pour les traductions."""

import sqlite3
import os
import json
from contextlib import contextmanager
from datetime import datetime, timezone

class TranslationStorage:
    def __init__(self, db_path=None):
        if db_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, "translations.db")
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS translations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(game_id, source_text, target_lang)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    game_id TEXT PRIMARY KEY,
                    game_dir TEXT,
                    last_seen TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_translations_lookup 
                ON translations(game_id, target_lang, source_text)
            """)
            conn.commit()

    def register_game(self, game_id, game_dir=""):
        """Enregistre un jeu dès sa détection ou son lancement."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO games (game_id, game_dir, last_seen)
                VALUES (?, ?, ?)
                ON CONFLICT(game_id) DO UPDATE SET game_dir = excluded.game_dir, last_seen = excluded.last_seen
                """,
                (game_id, game_dir or "", now_str)
            )
            conn.commit()

    def get_translation(self, game_id, source_text, target_lang):
        """Récupère une traduction depuis le cache SQLite."""
        with self._connection() as conn:
            cursor = conn.execute(
                """
                SELECT translated_text FROM translations 
                WHERE game_id = ? AND source_text = ? AND target_lang = ?
                """,
                (game_id, source_text, target_lang)
            )
            row = cursor.fetchone()
            if row:
                return row["translated_text"]
            return None

    def save_translation(self, game_id, source_text, translated_text, target_lang):
        """Enregistre ou met à jour une traduction."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self.register_game(game_id)
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO translations (game_id, source_text, translated_text, target_lang, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(game_id, source_text, target_lang) 
                DO UPDATE SET translated_text = excluded.translated_text, created_at = excluded.created_at
                """,
                (game_id, source_text, translated_text, target_lang, now_str)
            )
            conn.commit()

    def get_stats(self, game_id=None):
        """Retourne les statistiques de la base."""
        with self._connection() as conn:
            if game_id:
                total = conn.execute(
                    "SELECT COUNT(*) as count FROM translations WHERE game_id = ?",
                    (game_id,)
                ).fetchone()["count"]
            else:
                total = conn.execute("SELECT COUNT(*) as count FROM translations").fetchone()["count"]

            games_count = conn.execute(
                "SELECT COUNT(DISTINCT game_id) as count FROM (SELECT game_id FROM translations UNION SELECT game_id FROM games)"
            ).fetchone()["count"]
            return {
                "total_translations": total,
                "total_games": games_count
            }

    def get_history(self, limit=50):
        """Récupère l'historique récent des traductions."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, game_id, source_text, translated_text, target_lang, created_at
                FROM translations
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_games(self):
        """Retourne la liste des jeux répertoriés."""
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT g.game_id, COUNT(t.id) as count, MAX(g.last_seen) as last_seen
                FROM (
                    SELECT game_id, last_seen FROM games
                    UNION
                    SELECT DISTINCT game_id, created_at as last_seen FROM translations
                ) g
                LEFT JOIN translations t ON g.game_id = t.game_id
                GROUP BY g.game_id
                ORDER BY count DESC, last_seen DESC
            """).fetchall()
            return [{"game_id": row["game_id"], "count": row["count"]} for row in rows]

    def export_translations(self, game_id, target_lang, export_format="json"):
        """Exporte les traductions pour rendre le jeu autonome hors-ligne."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT source_text, translated_text
                FROM translations
                WHERE game_id = ? AND target_lang = ?
                """,
                (game_id, target_lang)
            ).fetchall()

            dict_data = {row["source_text"]: row["translated_text"] for row in rows}

            if export_format == "json":
                return json.dumps(dict_data, ensure_ascii=False, indent=2)
            elif export_format == "rpy":
                lines = [
                    f"# Dictionnaire de traduction hors-ligne pour {game_id} ({target_lang})",
                    "init 999 python:",
                    "    _offline_cache = " + json.dumps(dict_data, ensure_ascii=False, indent=8),
                    "    def _offline_filter(text):",
                    "        return _offline_cache.get(text, text)",
                    "    config.say_menu_text_filter = _offline_filter",
                    ""
                ]
                return "\n".join(lines)
            return ""
