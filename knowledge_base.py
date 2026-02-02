"""
База знаний курса.

Хранит FAQ, инструкции, ссылки — всё, что помогает AI генерировать
точные ответы. Виктория может пополнять базу через команды бота.

Источники знаний:
1. SQLite таблица kb_articles — основная база (управляется через бота)
2. YAML файл data/knowledge_base.yml — начальная загрузка
3. Автоматически извлечённые пары "вопрос-ответ" из истории Виктории
"""

import logging
import sqlite3
import yaml
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class KBArticle:
    """Статья базы знаний."""
    id: int | None
    category: str          # "faq", "instruction", "link", "policy"
    title: str             # Заголовок / краткое описание
    content: str           # Полный текст
    keywords: str          # Ключевые слова через запятую
    usage_count: int = 0   # Сколько раз использовалось AI
    created_at: str = ""
    updated_at: str = ""


class KnowledgeBase:
    """Менеджер базы знаний курса."""

    def __init__(self, db_path: str = "data/messages.db"):
        self.db_path = db_path
        self._init_tables()
        self._load_default_kb()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """Создать таблицы базы знаний."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kb_articles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL DEFAULT 'faq',
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    keywords TEXT NOT NULL DEFAULT '',
                    usage_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_kb_keywords
                    ON kb_articles(keywords);

                CREATE INDEX IF NOT EXISTS idx_kb_category
                    ON kb_articles(category);

                -- Таблица для обучения на ответах Виктории
                CREATE TABLE IF NOT EXISTS learned_replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_text TEXT NOT NULL,
                    reply_text TEXT NOT NULL,
                    sender_name TEXT,
                    chat_name TEXT,
                    quality_score REAL DEFAULT 1.0,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_learned_question
                    ON learned_replies(question_text);

                -- AI статистика
                CREATE TABLE IF NOT EXISTS ai_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hub_message_id INTEGER,
                    draft_text TEXT,
                    action TEXT,
                    final_text TEXT,
                    generation_time_ms INTEGER,
                    kb_articles_used TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def _load_default_kb(self):
        """Загрузить начальную базу знаний из YAML, если есть."""
        yaml_path = Path("data/knowledge_base.yml")
        if not yaml_path.exists():
            return

        conn = self._get_conn()
        try:
            # Проверяем, не загружали ли уже
            count = conn.execute("SELECT COUNT(*) FROM kb_articles").fetchone()[0]
            if count > 0:
                return

            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data or "articles" not in data:
                return

            for article in data["articles"]:
                conn.execute("""
                    INSERT INTO kb_articles (category, title, content, keywords)
                    VALUES (?, ?, ?, ?)
                """, (
                    article.get("category", "faq"),
                    article.get("title", ""),
                    article.get("content", ""),
                    article.get("keywords", ""),
                ))

            conn.commit()
            logger.info(f"📚 Загружено {len(data['articles'])} статей из knowledge_base.yml")
        except Exception as e:
            logger.error(f"Ошибка загрузки KB из YAML: {e}")
        finally:
            conn.close()

    # ──────────────────────────────────────────
    # CRUD операции
    # ──────────────────────────────────────────

    def add_article(self, category: str, title: str, content: str, keywords: str = "") -> int:
        """Добавить статью в базу знаний."""
        # Автогенерация ключевых слов из title если не указаны
        if not keywords:
            keywords = ",".join(title.lower().split()[:5])

        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                INSERT INTO kb_articles (category, title, content, keywords)
                VALUES (?, ?, ?, ?)
            """, (category, title, content, keywords))
            conn.commit()
            article_id = cursor.lastrowid
            logger.info(f"📚 KB: добавлена статья #{article_id}: {title}")
            return article_id
        finally:
            conn.close()

    def remove_article(self, article_id: int) -> bool:
        """Удалить статью."""
        conn = self._get_conn()
        try:
            cursor = conn.execute("DELETE FROM kb_articles WHERE id = ?", (article_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_article(self, article_id: int, content: str) -> bool:
        """Обновить текст статьи."""
        conn = self._get_conn()
        try:
            cursor = conn.execute("""
                UPDATE kb_articles
                SET content = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (content, article_id))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_all_articles(self, category: str | None = None) -> list[KBArticle]:
        """Получить все статьи, опционально по категории."""
        conn = self._get_conn()
        try:
            if category:
                rows = conn.execute(
                    "SELECT * FROM kb_articles WHERE category = ? ORDER BY usage_count DESC",
                    (category,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM kb_articles ORDER BY category, usage_count DESC"
                ).fetchall()
            return [self._row_to_article(r) for r in rows]
        finally:
            conn.close()

    # ──────────────────────────────────────────
    # Поиск
    # ──────────────────────────────────────────

    def search(self, query: str, limit: int = 5) -> list[KBArticle]:
        """
        Поиск по базе знаний.
        Ищет по ключевым словам, заголовкам и содержимому.
        """
        conn = self._get_conn()
        try:
            # Разбиваем запрос на слова
            words = [w.strip().lower() for w in query.replace(",", " ").split() if len(w.strip()) > 2]

            if not words:
                return []

            # Строим LIKE условия
            conditions = []
            params = []
            for word in words:
                conditions.append(
                    "(LOWER(keywords) LIKE ? OR LOWER(title) LIKE ? OR LOWER(content) LIKE ?)"
                )
                pattern = f"%{word}%"
                params.extend([pattern, pattern, pattern])

            where_clause = " OR ".join(conditions)

            rows = conn.execute(f"""
                SELECT *,
                    -- Примитивный scoring: сколько слов совпало
                    ({' + '.join(
                        f"(CASE WHEN LOWER(keywords) LIKE ? THEN 3 ELSE 0 END + "
                        f"CASE WHEN LOWER(title) LIKE ? THEN 2 ELSE 0 END + "
                        f"CASE WHEN LOWER(content) LIKE ? THEN 1 ELSE 0 END)"
                        for _ in words
                    )}) as relevance_score
                FROM kb_articles
                WHERE {where_clause}
                ORDER BY relevance_score DESC
                LIMIT ?
            """, params + [f"%{w}%" for w in words for _ in range(3)] + [limit]).fetchall()

            articles = [self._row_to_article(r) for r in rows]

            # Инкрементим usage_count для найденных
            if articles:
                ids = [a.id for a in articles if a.id]
                placeholders = ",".join("?" * len(ids))
                conn.execute(
                    f"UPDATE kb_articles SET usage_count = usage_count + 1 WHERE id IN ({placeholders})",
                    ids
                )
                conn.commit()

            return articles

        except Exception as e:
            logger.error(f"KB search error: {e}")
            return []
        finally:
            conn.close()

    # ──────────────────────────────────────────
    # Обучение на ответах Виктории
    # ──────────────────────────────────────────

    def save_learned_reply(
        self,
        question_text: str,
        reply_text: str,
        sender_name: str = "",
        chat_name: str = "",
    ):
        """Сохранить пару вопрос-ответ из реальной переписки Виктории."""
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO learned_replies (question_text, reply_text, sender_name, chat_name)
                VALUES (?, ?, ?, ?)
            """, (question_text, reply_text, sender_name, chat_name))
            conn.commit()
            logger.debug(f"📝 Learned reply saved: {question_text[:50]}...")
        finally:
            conn.close()

    def find_similar_replies(self, question: str, limit: int = 3) -> list[dict]:
        """Найти похожие прошлые ответы Виктории для стилистического контекста."""
        conn = self._get_conn()
        try:
            words = [w.strip().lower() for w in question.split() if len(w.strip()) > 3]

            if not words:
                # Fallback: вернуть последние ответы как примеры стиля
                rows = conn.execute("""
                    SELECT * FROM learned_replies
                    ORDER BY created_at DESC LIMIT ?
                """, (limit,)).fetchall()
                return [dict(r) for r in rows]

            conditions = []
            params = []
            for word in words:
                conditions.append("LOWER(question_text) LIKE ?")
                params.append(f"%{word}%")

            where_clause = " OR ".join(conditions)

            rows = conn.execute(f"""
                SELECT * FROM learned_replies
                WHERE {where_clause}
                ORDER BY quality_score DESC, created_at DESC
                LIMIT ?
            """, params + [limit]).fetchall()

            if not rows:
                # Fallback
                rows = conn.execute("""
                    SELECT * FROM learned_replies
                    ORDER BY quality_score DESC, created_at DESC LIMIT ?
                """, (limit,)).fetchall()

            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_learned_count(self) -> int:
        """Количество сохранённых пар вопрос-ответ."""
        conn = self._get_conn()
        try:
            return conn.execute("SELECT COUNT(*) FROM learned_replies").fetchone()[0]
        finally:
            conn.close()

    # ──────────────────────────────────────────
    # AI Stats
    # ──────────────────────────────────────────

    def log_ai_action(
        self,
        hub_message_id: int,
        draft_text: str,
        action: str,
        final_text: str = "",
        generation_time_ms: int = 0,
        kb_articles_used: str = "",
    ):
        """Логировать действие AI (для аналитики)."""
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO ai_stats
                    (hub_message_id, draft_text, action, final_text,
                     generation_time_ms, kb_articles_used)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (hub_message_id, draft_text, action, final_text,
                  generation_time_ms, kb_articles_used))
            conn.commit()
        finally:
            conn.close()

    def get_ai_stats(self, days: int = 7) -> dict:
        """Статистика AI за N дней."""
        since = datetime.now().isoformat()[:10]  # Simplified
        conn = self._get_conn()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM ai_stats WHERE created_at >= date('now', ?)",
                (f"-{days} days",)
            ).fetchone()[0]

            accepted = conn.execute(
                "SELECT COUNT(*) FROM ai_stats WHERE action = 'accepted' AND created_at >= date('now', ?)",
                (f"-{days} days",)
            ).fetchone()[0]

            edited = conn.execute(
                "SELECT COUNT(*) FROM ai_stats WHERE action = 'edited' AND created_at >= date('now', ?)",
                (f"-{days} days",)
            ).fetchone()[0]

            rejected = conn.execute(
                "SELECT COUNT(*) FROM ai_stats WHERE action = 'rejected' AND created_at >= date('now', ?)",
                (f"-{days} days",)
            ).fetchone()[0]

            avg_time = conn.execute("""
                SELECT AVG(generation_time_ms) FROM ai_stats
                WHERE created_at >= date('now', ?)
            """, (f"-{days} days",)).fetchone()[0]

            return {
                "total_drafts": total,
                "accepted": accepted,
                "edited": edited,
                "rejected": rejected,
                "acceptance_rate": f"{(accepted / total * 100):.0f}%" if total > 0 else "—",
                "edit_rate": f"{(edited / total * 100):.0f}%" if total > 0 else "—",
                "avg_generation_ms": round(avg_time) if avg_time else 0,
                "kb_articles_count": len(self.get_all_articles()),
                "learned_replies_count": self.get_learned_count(),
            }
        finally:
            conn.close()

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    @staticmethod
    def _row_to_article(row) -> KBArticle:
        return KBArticle(
            id=row["id"],
            category=row["category"],
            title=row["title"],
            content=row["content"],
            keywords=row["keywords"],
            usage_count=row["usage_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
