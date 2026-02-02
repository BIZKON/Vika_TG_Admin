"""
Векторное хранилище на базе LanceDB + OpenAI Embeddings.

Обеспечивает семантический поиск по базе знаний курса.
Заменяет keyword-based поиск на поиск по смыслу.

Использование:
    store = VectorStore()

    # Добавить документ
    store.add_document("Как сдать ДЗ", "Откройте урок, нажмите загрузить...", category="faq")

    # Поиск
    results = store.search("где загрузить домашку")
"""

import logging
import hashlib
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

import lancedb
from openai import OpenAI

from config import config

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Результат поиска."""
    id: str
    title: str
    content: str
    category: str
    score: float
    metadata: dict


class VectorStore:
    """
    Векторное хранилище для семантического поиска.

    Использует:
    - LanceDB для хранения и поиска векторов
    - OpenAI text-embedding-3-small для создания embeddings
    """

    TABLE_NAME = "knowledge_base"
    EMBEDDING_DIMENSION = 1536  # для text-embedding-3-small

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.vector_db_path
        self._ensure_db_dir()

        # OpenAI клиент для embeddings
        self.openai_client = None
        if config.openai_api_key:
            self.openai_client = OpenAI(api_key=config.openai_api_key)

        # LanceDB подключение
        self.db = lancedb.connect(self.db_path)
        self._ensure_table()

        logger.info(f"VectorStore инициализирован: {self.db_path}")

    def _ensure_db_dir(self):
        """Создать директорию для БД если не существует."""
        Path(self.db_path).mkdir(parents=True, exist_ok=True)

    def _ensure_table(self):
        """Создать таблицу если не существует."""
        if self.TABLE_NAME not in self.db.table_names():
            # Создаём пустую таблицу со схемой
            import pyarrow as pa
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("title", pa.string()),
                pa.field("content", pa.string()),
                pa.field("category", pa.string()),
                pa.field("source", pa.string()),
                pa.field("created_at", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), self.EMBEDDING_DIMENSION)),
            ])
            self.db.create_table(self.TABLE_NAME, schema=schema)
            logger.info(f"Создана таблица {self.TABLE_NAME}")

    def _get_table(self):
        """Получить таблицу."""
        return self.db.open_table(self.TABLE_NAME)

    def _generate_id(self, title: str, content: str) -> str:
        """Генерация уникального ID на основе контента."""
        text = f"{title}:{content}"
        return hashlib.md5(text.encode()).hexdigest()[:16]

    def _get_embedding(self, text: str) -> list[float]:
        """
        Получить embedding для текста через OpenAI API.

        Args:
            text: Текст для векторизации

        Returns:
            Вектор размерности 1536
        """
        if not self.openai_client:
            raise ValueError("OpenAI API key не настроен. Установите OPENAI_API_KEY в .env")

        # Ограничиваем длину текста (max ~8000 токенов для embedding модели)
        text = text[:30000]

        response = self.openai_client.embeddings.create(
            model=config.embedding_model,
            input=text,
        )

        return response.data[0].embedding

    def _get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Получить embeddings для списка текстов (батч)."""
        if not self.openai_client:
            raise ValueError("OpenAI API key не настроен")

        # Ограничиваем длину каждого текста
        texts = [t[:30000] for t in texts]

        response = self.openai_client.embeddings.create(
            model=config.embedding_model,
            input=texts,
        )

        return [item.embedding for item in response.data]

    # ──────────────────────────────────────────
    # CRUD операции
    # ──────────────────────────────────────────

    def add_document(
        self,
        title: str,
        content: str,
        category: str = "faq",
        source: str = "manual",
        doc_id: str | None = None,
    ) -> str:
        """
        Добавить документ в хранилище.

        Args:
            title: Заголовок документа
            content: Содержимое
            category: Категория (faq, instruction, link, policy, learned)
            source: Источник (manual, yaml, document, telegram)
            doc_id: Опциональный ID (если не указан - генерируется)

        Returns:
            ID добавленного документа
        """
        doc_id = doc_id or self._generate_id(title, content)

        # Создаём текст для embedding (заголовок + содержимое)
        text_for_embedding = f"{title}\n\n{content}"
        vector = self._get_embedding(text_for_embedding)

        table = self._get_table()

        # Проверяем, нет ли уже такого документа
        existing = table.search().where(f"id = '{doc_id}'").limit(1).to_list()
        if existing:
            logger.debug(f"Документ {doc_id} уже существует, обновляю...")
            self.delete_document(doc_id)

        table.add([{
            "id": doc_id,
            "title": title,
            "content": content,
            "category": category,
            "source": source,
            "created_at": datetime.now().isoformat(),
            "vector": vector,
        }])

        logger.info(f"Добавлен документ: {title[:50]}... (id={doc_id})")
        return doc_id

    def add_documents_batch(
        self,
        documents: list[dict],
    ) -> list[str]:
        """
        Добавить несколько документов за один раз (эффективнее).

        Args:
            documents: Список словарей с ключами: title, content, category, source

        Returns:
            Список ID добавленных документов
        """
        if not documents:
            return []

        # Подготавливаем тексты для embedding
        texts = [f"{d['title']}\n\n{d['content']}" for d in documents]
        vectors = self._get_embeddings_batch(texts)

        # Формируем записи
        records = []
        ids = []
        now = datetime.now().isoformat()

        for doc, vector in zip(documents, vectors):
            doc_id = doc.get("id") or self._generate_id(doc["title"], doc["content"])
            ids.append(doc_id)
            records.append({
                "id": doc_id,
                "title": doc["title"],
                "content": doc["content"],
                "category": doc.get("category", "faq"),
                "source": doc.get("source", "batch"),
                "created_at": now,
                "vector": vector,
            })

        table = self._get_table()
        table.add(records)

        logger.info(f"Добавлено {len(records)} документов батчем")
        return ids

    def delete_document(self, doc_id: str) -> bool:
        """Удалить документ по ID."""
        table = self._get_table()
        table.delete(f"id = '{doc_id}'")
        logger.info(f"Удалён документ: {doc_id}")
        return True

    def get_document(self, doc_id: str) -> dict | None:
        """Получить документ по ID."""
        table = self._get_table()
        results = table.search().where(f"id = '{doc_id}'").limit(1).to_list()
        if results:
            return results[0]
        return None

    def get_all_documents(self, category: str | None = None) -> list[dict]:
        """Получить все документы, опционально по категории."""
        table = self._get_table()

        if category:
            results = table.search().where(f"category = '{category}'").limit(10000).to_list()
        else:
            results = table.to_pandas().to_dict('records')

        return results

    def count_documents(self) -> int:
        """Количество документов в хранилище."""
        table = self._get_table()
        return table.count_rows()

    # ──────────────────────────────────────────
    # Поиск
    # ──────────────────────────────────────────

    def search(
        self,
        query: str,
        limit: int | None = None,
        category: str | None = None,
        min_score: float | None = None,
    ) -> list[SearchResult]:
        """
        Семантический поиск по базе знаний.

        Args:
            query: Поисковый запрос на естественном языке
            limit: Максимальное количество результатов
            category: Фильтр по категории
            min_score: Минимальный score релевантности (0-1)

        Returns:
            Список результатов, отсортированных по релевантности
        """
        limit = limit or config.vector_search_limit
        min_score = min_score or config.vector_min_score

        # Получаем embedding запроса
        query_vector = self._get_embedding(query)

        table = self._get_table()

        # Строим поиск
        search_builder = table.search(query_vector).limit(limit * 2)  # берём больше для фильтрации

        if category:
            search_builder = search_builder.where(f"category = '{category}'")

        results = search_builder.to_list()

        # Преобразуем в SearchResult и фильтруем по score
        search_results = []
        for r in results:
            # LanceDB возвращает _distance (L2 distance), конвертируем в similarity score
            # Меньше distance = выше similarity
            distance = r.get("_distance", 0)
            # Примерное преобразование: score = 1 / (1 + distance)
            score = 1 / (1 + distance)

            if score >= min_score:
                search_results.append(SearchResult(
                    id=r["id"],
                    title=r["title"],
                    content=r["content"],
                    category=r["category"],
                    score=round(score, 3),
                    metadata={
                        "source": r.get("source", ""),
                        "created_at": r.get("created_at", ""),
                    }
                ))

        # Ограничиваем количество
        search_results = search_results[:limit]

        logger.debug(f"Поиск '{query[:50]}...': найдено {len(search_results)} результатов")
        return search_results

    def search_similar(
        self,
        doc_id: str,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Найти похожие документы на указанный."""
        doc = self.get_document(doc_id)
        if not doc:
            return []

        # Ищем по вектору документа
        table = self._get_table()
        results = table.search(doc["vector"]).limit(limit + 1).to_list()

        # Исключаем сам документ из результатов
        search_results = []
        for r in results:
            if r["id"] != doc_id:
                distance = r.get("_distance", 0)
                score = 1 / (1 + distance)
                search_results.append(SearchResult(
                    id=r["id"],
                    title=r["title"],
                    content=r["content"],
                    category=r["category"],
                    score=round(score, 3),
                    metadata={"source": r.get("source", "")}
                ))

        return search_results[:limit]

    # ──────────────────────────────────────────
    # Утилиты
    # ──────────────────────────────────────────

    def reindex_all(self):
        """Переиндексировать все документы (пересчитать embeddings)."""
        docs = self.get_all_documents()

        # Удаляем таблицу и создаём заново
        if self.TABLE_NAME in self.db.table_names():
            self.db.drop_table(self.TABLE_NAME)
        self._ensure_table()

        # Добавляем все документы заново
        if docs:
            # Убираем vector из документов (будет пересчитан)
            clean_docs = [{
                "title": d["title"],
                "content": d["content"],
                "category": d["category"],
                "source": d.get("source", "reindex"),
                "id": d["id"],
            } for d in docs]

            self.add_documents_batch(clean_docs)

        logger.info(f"Переиндексировано {len(docs)} документов")

    def get_stats(self) -> dict:
        """Статистика хранилища."""
        docs = self.get_all_documents()

        categories = {}
        sources = {}

        for d in docs:
            cat = d.get("category", "unknown")
            src = d.get("source", "unknown")
            categories[cat] = categories.get(cat, 0) + 1
            sources[src] = sources.get(src, 0) + 1

        return {
            "total_documents": len(docs),
            "by_category": categories,
            "by_source": sources,
            "embedding_model": config.embedding_model,
            "db_path": self.db_path,
        }

    def clear(self):
        """Очистить всё хранилище."""
        if self.TABLE_NAME in self.db.table_names():
            self.db.drop_table(self.TABLE_NAME)
        self._ensure_table()
        logger.warning("Векторное хранилище очищено")


# Глобальный singleton (инициализируется лениво)
_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """Получить инстанс VectorStore."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
