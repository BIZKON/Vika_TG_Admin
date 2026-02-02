"""
Хранилище: SQLite база для маппинга сообщений и статистики.
Каждое пересланное в хаб сообщение связывается с оригиналом,
чтобы маршрутизировать ответы обратно.
"""

import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta


@dataclass
class MessageRecord:
    """Запись о пересланном сообщении."""
    id: int | None
    hub_message_id: int          # ID сообщения в хаб-группе
    original_message_id: int     # ID оригинального сообщения
    original_chat_id: int        # ID оригинального чата
    source_account: str          # 'work' или 'personal'
    sender_id: int               # ID отправителя
    sender_name: str             # Имя отправителя
    sender_username: str | None  # @username
    chat_name: str               # Название чата-источника
    chat_type: str               # 'group', 'supergroup', 'dm'
    priority: str                # 'urgent', 'normal', 'info'
    timestamp: str               # ISO datetime
    replied: bool = False        # Виктория ответила?
    replied_at: str | None = None


class Database:
    """Менеджер SQLite базы данных."""

    def __init__(self, db_path: str = "data/messages.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Создать таблицы при первом запуске."""
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS message_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hub_message_id INTEGER NOT NULL,
                    original_message_id INTEGER NOT NULL,
                    original_chat_id INTEGER NOT NULL,
                    source_account TEXT NOT NULL,
                    sender_id INTEGER NOT NULL,
                    sender_name TEXT NOT NULL,
                    sender_username TEXT,
                    chat_name TEXT NOT NULL,
                    chat_type TEXT NOT NULL,
                    priority TEXT DEFAULT 'normal',
                    timestamp TEXT NOT NULL,
                    replied INTEGER DEFAULT 0,
                    replied_at TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_hub_msg
                    ON message_mapping(hub_message_id);

                CREATE INDEX IF NOT EXISTS idx_original
                    ON message_mapping(original_chat_id, original_message_id);

                CREATE INDEX IF NOT EXISTS idx_replied
                    ON message_mapping(replied);

                CREATE TABLE IF NOT EXISTS muted_chats (
                    chat_id INTEGER PRIMARY KEY,
                    chat_name TEXT,
                    muted_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS watched_chats (
                    chat_id INTEGER PRIMARY KEY,
                    chat_name TEXT NOT NULL,
                    account_name TEXT NOT NULL,
                    chat_type TEXT NOT NULL,
                    added_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS quick_replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger_pattern TEXT NOT NULL,
                    reply_text TEXT NOT NULL,
                    usage_count INTEGER DEFAULT 0
                );
            """)

    # ──────────────────────────────────────────
    # Message Mapping
    # ──────────────────────────────────────────

    def save_message(self, record: MessageRecord) -> int:
        """Сохранить маппинг сообщения. Возвращает ID записи."""
        with self._connection() as conn:
            cursor = conn.execute("""
                INSERT INTO message_mapping
                    (hub_message_id, original_message_id, original_chat_id,
                     source_account, sender_id, sender_name, sender_username,
                     chat_name, chat_type, priority, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.hub_message_id,
                record.original_message_id,
                record.original_chat_id,
                record.source_account,
                record.sender_id,
                record.sender_name,
                record.sender_username,
                record.chat_name,
                record.chat_type,
                record.priority,
                record.timestamp,
            ))
            return cursor.lastrowid

    def find_by_hub_message(self, hub_message_id: int) -> MessageRecord | None:
        """Найти оригинальное сообщение по ID в хабе."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM message_mapping WHERE hub_message_id = ?",
                (hub_message_id,)
            ).fetchone()
            if row:
                return self._row_to_record(row)
        return None

    def mark_replied(self, hub_message_id: int):
        """Отметить сообщение как отвеченное."""
        with self._connection() as conn:
            conn.execute("""
                UPDATE message_mapping
                SET replied = 1, replied_at = datetime('now')
                WHERE hub_message_id = ?
            """, (hub_message_id,))

    def get_unreplied(self, limit: int = 20) -> list[MessageRecord]:
        """Получить неотвеченные сообщения."""
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT * FROM message_mapping
                WHERE replied = 0
                ORDER BY
                    CASE priority
                        WHEN 'urgent' THEN 0
                        WHEN 'normal' THEN 1
                        WHEN 'info' THEN 2
                    END,
                    timestamp ASC
                LIMIT ?
            """, (limit,)).fetchall()
            return [self._row_to_record(r) for r in rows]

    def is_duplicate(self, original_chat_id: int, original_message_id: int) -> bool:
        """Проверить, не пересылали ли уже это сообщение."""
        with self._connection() as conn:
            row = conn.execute("""
                SELECT 1 FROM message_mapping
                WHERE original_chat_id = ? AND original_message_id = ?
            """, (original_chat_id, original_message_id)).fetchone()
            return row is not None

    # ──────────────────────────────────────────
    # Mute / Unmute
    # ──────────────────────────────────────────

    def mute_chat(self, chat_id: int, chat_name: str = ""):
        with self._connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO muted_chats (chat_id, chat_name) VALUES (?, ?)",
                (chat_id, chat_name)
            )

    def unmute_chat(self, chat_id: int):
        with self._connection() as conn:
            conn.execute("DELETE FROM muted_chats WHERE chat_id = ?", (chat_id,))

    def is_muted(self, chat_id: int) -> bool:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM muted_chats WHERE chat_id = ?", (chat_id,)
            ).fetchone()
            return row is not None

    def get_muted_chats(self) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM muted_chats").fetchall()
            return [dict(r) for r in rows]

    # ──────────────────────────────────────────
    # Statistics
    # ──────────────────────────────────────────

    def get_stats(self, days: int = 7) -> dict:
        """Статистика за последние N дней."""
        since = (datetime.now() - timedelta(days=days)).isoformat()
        with self._connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM message_mapping WHERE timestamp >= ?",
                (since,)
            ).fetchone()[0]

            replied = conn.execute(
                "SELECT COUNT(*) FROM message_mapping WHERE replied = 1 AND timestamp >= ?",
                (since,)
            ).fetchone()[0]

            unreplied = conn.execute(
                "SELECT COUNT(*) FROM message_mapping WHERE replied = 0 AND timestamp >= ?",
                (since,)
            ).fetchone()[0]

            urgent = conn.execute(
                "SELECT COUNT(*) FROM message_mapping WHERE priority = 'urgent' AND timestamp >= ?",
                (since,)
            ).fetchone()[0]

            # Среднее время ответа (в минутах)
            avg_reply = conn.execute("""
                SELECT AVG(
                    (julianday(replied_at) - julianday(timestamp)) * 24 * 60
                )
                FROM message_mapping
                WHERE replied = 1 AND replied_at IS NOT NULL AND timestamp >= ?
            """, (since,)).fetchone()[0]

            # Топ источников
            by_source = conn.execute("""
                SELECT chat_name, COUNT(*) as cnt
                FROM message_mapping WHERE timestamp >= ?
                GROUP BY chat_name ORDER BY cnt DESC LIMIT 5
            """, (since,)).fetchall()

            return {
                "period_days": days,
                "total_messages": total,
                "replied": replied,
                "unreplied": unreplied,
                "urgent": urgent,
                "avg_reply_minutes": round(avg_reply, 1) if avg_reply else None,
                "reply_rate": f"{(replied / total * 100):.0f}%" if total > 0 else "—",
                "top_sources": [{"name": r["chat_name"], "count": r["cnt"]} for r in by_source],
            }

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    @staticmethod
    def _row_to_record(row) -> MessageRecord:
        return MessageRecord(
            id=row["id"],
            hub_message_id=row["hub_message_id"],
            original_message_id=row["original_message_id"],
            original_chat_id=row["original_chat_id"],
            source_account=row["source_account"],
            sender_id=row["sender_id"],
            sender_name=row["sender_name"],
            sender_username=row["sender_username"],
            chat_name=row["chat_name"],
            chat_type=row["chat_type"],
            priority=row["priority"],
            timestamp=row["timestamp"],
            replied=bool(row["replied"]),
            replied_at=row["replied_at"],
        )
