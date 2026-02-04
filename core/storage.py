"""
TG-Hub V2: База данных SQLite.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from core.models import HubMessage, MessageSource

logger = logging.getLogger(__name__)


class Database:
    """SQLite хранилище для TG-Hub."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_conn(self):
        """Context manager для соединения."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        """Инициализация схемы БД."""
        with self._get_conn() as conn:
            # Таблица сообщений хаба
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hub_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hub_message_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    source_message_id INTEGER,
                    source_chat_id INTEGER,
                    business_connection_id TEXT,
                    sender_id INTEGER,
                    sender_name TEXT,
                    sender_username TEXT,
                    chat_name TEXT,
                    priority TEXT DEFAULT 'normal',
                    created_at TEXT NOT NULL,
                    replied INTEGER DEFAULT 0,
                    replied_at TEXT
                )
            """)

            # Индексы для быстрого поиска
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_hub_msg_id
                ON hub_messages(hub_message_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_msg
                ON hub_messages(source, source_message_id, source_chat_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_business_conn
                ON hub_messages(business_connection_id)
            """)

            # Таблица замьюченных чатов
            conn.execute("""
                CREATE TABLE IF NOT EXISTS muted_chats (
                    chat_id INTEGER PRIMARY KEY,
                    muted_at TEXT NOT NULL,
                    reason TEXT
                )
            """)

            # Таблица для дедупликации
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_messages (
                    source TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY (source, chat_id, message_id)
                )
            """)

            # Таблица статистики
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY,
                    total_messages INTEGER DEFAULT 0,
                    business_dm INTEGER DEFAULT 0,
                    group_students INTEGER DEFAULT 0,
                    group_curators INTEGER DEFAULT 0,
                    getcourse INTEGER DEFAULT 0,
                    ai_drafts INTEGER DEFAULT 0,
                    responses_sent INTEGER DEFAULT 0
                )
            """)

            logger.info(f"Database initialized: {self.db_path}")

    # ─── Hub Messages ───

    def save_hub_message(self, msg: HubMessage) -> int:
        """Сохранить сообщение хаба."""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                INSERT INTO hub_messages (
                    hub_message_id, source, source_message_id, source_chat_id,
                    business_connection_id, sender_id, sender_name, sender_username,
                    chat_name, priority, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                msg.hub_message_id,
                msg.source.value if isinstance(msg.source, MessageSource) else msg.source,
                msg.source_message_id,
                msg.source_chat_id,
                msg.business_connection_id,
                msg.sender_id,
                msg.sender_name,
                msg.sender_username,
                msg.chat_name,
                msg.priority,
                msg.created_at or datetime.now().isoformat(),
            ))
            return cursor.lastrowid

    def get_hub_message(self, hub_message_id: int) -> Optional[HubMessage]:
        """Получить сообщение по ID в хабе."""
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT * FROM hub_messages WHERE hub_message_id = ?
            """, (hub_message_id,)).fetchone()

            if row:
                return HubMessage(
                    id=row["id"],
                    hub_message_id=row["hub_message_id"],
                    source=MessageSource(row["source"]) if row["source"] else MessageSource.HUB,
                    source_message_id=row["source_message_id"],
                    source_chat_id=row["source_chat_id"],
                    business_connection_id=row["business_connection_id"],
                    sender_id=row["sender_id"],
                    sender_name=row["sender_name"] or "",
                    sender_username=row["sender_username"],
                    chat_name=row["chat_name"],
                    priority=row["priority"] or "normal",
                    created_at=row["created_at"],
                    replied=bool(row["replied"]),
                    replied_at=row["replied_at"],
                )
        return None

    def mark_replied(self, hub_message_id: int):
        """Отметить сообщение как отвеченное."""
        with self._get_conn() as conn:
            conn.execute("""
                UPDATE hub_messages
                SET replied = 1, replied_at = ?
                WHERE hub_message_id = ?
            """, (datetime.now().isoformat(), hub_message_id))

    # ─── Muting ───

    def mute_chat(self, chat_id: int, reason: str = None):
        """Замьютить чат."""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO muted_chats (chat_id, muted_at, reason)
                VALUES (?, ?, ?)
            """, (chat_id, datetime.now().isoformat(), reason))

    def unmute_chat(self, chat_id: int):
        """Размьютить чат."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM muted_chats WHERE chat_id = ?", (chat_id,))

    def is_muted(self, chat_id: int) -> bool:
        """Проверить, замьючен ли чат."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM muted_chats WHERE chat_id = ?", (chat_id,)
            ).fetchone()
            return row is not None

    def get_muted_chats(self) -> list[int]:
        """Получить все замьюченные чаты."""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT chat_id FROM muted_chats").fetchall()
            return [r["chat_id"] for r in rows]

    # ─── Deduplication ───

    def is_duplicate(self, source: str, chat_id: int, message_id: int) -> bool:
        """Проверить, обработано ли сообщение."""
        with self._get_conn() as conn:
            row = conn.execute("""
                SELECT 1 FROM processed_messages
                WHERE source = ? AND chat_id = ? AND message_id = ?
            """, (source, chat_id, message_id)).fetchone()
            return row is not None

    def mark_processed(self, source: str, chat_id: int, message_id: int):
        """Отметить сообщение как обработанное."""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO processed_messages (source, chat_id, message_id, processed_at)
                VALUES (?, ?, ?, ?)
            """, (source, chat_id, message_id, datetime.now().isoformat()))

    # ─── Statistics ───

    def increment_stat(self, source: MessageSource, count: int = 1):
        """Увеличить счётчик статистики."""
        today = datetime.now().strftime("%Y-%m-%d")
        column_map = {
            MessageSource.BUSINESS_DM: "business_dm",
            MessageSource.GROUP_STUDENTS: "group_students",
            MessageSource.GROUP_CURATORS: "group_curators",
            MessageSource.GETCOURSE: "getcourse",
        }
        column = column_map.get(source)
        if not column:
            return

        with self._get_conn() as conn:
            conn.execute(f"""
                INSERT INTO daily_stats (date, total_messages, {column})
                VALUES (?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    total_messages = total_messages + ?,
                    {column} = {column} + ?
            """, (today, count, count, count, count))

    def increment_ai_drafts(self, count: int = 1):
        """Увеличить счётчик AI черновиков."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO daily_stats (date, ai_drafts)
                VALUES (?, ?)
                ON CONFLICT(date) DO UPDATE SET ai_drafts = ai_drafts + ?
            """, (today, count, count))

    def get_today_stats(self) -> dict:
        """Получить статистику за сегодня."""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM daily_stats WHERE date = ?", (today,)
            ).fetchone()

            if row:
                return dict(row)
            return {
                "date": today,
                "total_messages": 0,
                "business_dm": 0,
                "group_students": 0,
                "group_curators": 0,
                "getcourse": 0,
                "ai_drafts": 0,
                "responses_sent": 0,
            }

    def get_stats_range(self, days: int = 7) -> list[dict]:
        """Получить статистику за N дней."""
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT * FROM daily_stats
                ORDER BY date DESC
                LIMIT ?
            """, (days,)).fetchall()
            return [dict(r) for r in rows]
