"""
Конфигурация проекта.
Загружает переменные из .env и предоставляет типизированные настройки.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AccountConfig:
    """Настройки одного Telegram-аккаунта."""
    name: str
    api_id: int
    api_hash: str
    phone: str
    session_path: str = ""

    def __post_init__(self):
        if not self.session_path:
            self.session_path = f"data/sessions/{self.name}"


@dataclass
class FilterConfig:
    """Настройки фильтрации сообщений."""
    # Ключевые слова для определения срочности
    urgent_keywords: list[str] = field(default_factory=lambda: [
        "срочно", "помогите", "не работает", "ошибка", "проблема",
        "не могу", "сломалось", "баг", "urgent", "help"
    ])
    # Паттерны, которые НЕ пересылаем (шум)
    noise_patterns: list[str] = field(default_factory=lambda: [
        "👍", "👎", "❤️", "🔥", "+1", "ок", "спс", "спасибо",
        "благодарю", "ясно", "понял", "понятно"
    ])
    # Пересылать только сообщения с вопросами из групп?
    groups_questions_only: bool = False
    # Минимальная длина сообщения для пересылки из групп
    min_group_message_length: int = 3
    # Пересылать ВСЕ ЛС (без фильтра)
    forward_all_dm: bool = True


@dataclass
class Config:
    """Главная конфигурация."""

    # Аккаунты
    account_work: AccountConfig = field(default_factory=lambda: AccountConfig(
        name="work",
        api_id=int(os.getenv("ACCOUNT_WORK_API_ID", "0")),
        api_hash=os.getenv("ACCOUNT_WORK_API_HASH", ""),
        phone=os.getenv("ACCOUNT_WORK_PHONE", ""),
    ))
    account_personal: AccountConfig = field(default_factory=lambda: AccountConfig(
        name="personal",
        api_id=int(os.getenv("ACCOUNT_PERSONAL_API_ID", "0")),
        api_hash=os.getenv("ACCOUNT_PERSONAL_API_HASH", ""),
        phone=os.getenv("ACCOUNT_PERSONAL_PHONE", ""),
    ))

    # Бот
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    hub_chat_id: int = field(default_factory=lambda: int(os.getenv("HUB_CHAT_ID", "0")))
    moderator_user_id: int = field(default_factory=lambda: int(os.getenv("MODERATOR_USER_ID", "0")))

    # AI
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    ai_enabled: bool = field(default_factory=lambda: os.getenv("AI_ENABLED", "false").lower() == "true")
    ai_auto_draft: bool = field(
        default_factory=lambda: os.getenv("AI_AUTO_DRAFT", "true").lower() == "true"
    )
    ai_min_message_length: int = field(
        default_factory=lambda: int(os.getenv("AI_MIN_MESSAGE_LENGTH", "10"))
    )
    ai_draft_for_dm_only: bool = field(
        default_factory=lambda: os.getenv("AI_DRAFT_FOR_DM_ONLY", "false").lower() == "true"
    )

    # Vector Store (RAG)
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    )
    vector_db_path: str = field(default_factory=lambda: os.getenv("VECTOR_DB_PATH", "data/vector_db"))
    vector_search_limit: int = field(
        default_factory=lambda: int(os.getenv("VECTOR_SEARCH_LIMIT", "5"))
    )
    # Минимальный score для релевантных результатов (0.0 - 1.0)
    vector_min_score: float = field(
        default_factory=lambda: float(os.getenv("VECTOR_MIN_SCORE", "0.7"))
    )

    # Пути
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "data/messages.db"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # Автоответ
    auto_reply_enabled: bool = field(
        default_factory=lambda: os.getenv("AUTO_REPLY_ENABLED", "false").lower() == "true"
    )
    auto_reply_timeout_minutes: int = field(
        default_factory=lambda: int(os.getenv("AUTO_REPLY_TIMEOUT_MINUTES", "30"))
    )
    auto_reply_text: str = field(
        default_factory=lambda: os.getenv(
            "AUTO_REPLY_TEXT",
            "Виктория ответит в ближайшее время. Спасибо за ожидание!"
        )
    )

    # Задержки (антибан)
    reply_delay_seconds: float = field(
        default_factory=lambda: float(os.getenv("REPLY_DELAY_SECONDS", "1"))
    )

    # Фильтры
    filters: FilterConfig = field(default_factory=FilterConfig)

    # Отслеживаемые чаты (заполняется при первом запуске)
    # Формат: {chat_id: {"name": "...", "account": "work|personal", "type": "group|dm"}}
    watched_chats: dict = field(default_factory=dict)

    def ensure_dirs(self):
        """Создать необходимые директории."""
        Path("data/sessions").mkdir(parents=True, exist_ok=True)
        Path("data").mkdir(parents=True, exist_ok=True)
        Path("data/vector_db").mkdir(parents=True, exist_ok=True)
        Path("data/documents").mkdir(parents=True, exist_ok=True)

    @property
    def accounts(self) -> list[AccountConfig]:
        return [self.account_work, self.account_personal]


# Глобальный singleton
config = Config()
config.ensure_dirs()
