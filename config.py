"""
TG-Hub V2: Конфигурация проекта.
Поддержка: Telegram Business API, Groups, GetCourse Webhooks.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TelegramGroupConfig:
    """Настройки одной Telegram-группы для мониторинга."""
    chat_id: int
    name: str
    enabled: bool = True


@dataclass
class GetCourseConfig:
    """Настройки интеграции с GetCourse."""
    enabled: bool = False
    account_name: str = ""
    secret_key: str = ""
    webhook_secret: str = ""  # Для верификации входящих запросов


@dataclass
class WebhookServerConfig:
    """Настройки веб-сервера для webhooks."""
    host: str = "0.0.0.0"
    port: int = 8080
    public_url: str = ""  # https://your-domain.com


@dataclass
class FilterConfig:
    """Настройки фильтрации сообщений."""
    # Ключевые слова для определения срочности
    urgent_keywords: list[str] = field(default_factory=lambda: [
        "срочно", "помогите", "не работает", "ошибка", "проблема",
        "не могу", "сломалось", "баг", "urgent", "help", "asap"
    ])
    # Ключевые слова для вопросов
    question_keywords: list[str] = field(default_factory=lambda: [
        "как", "почему", "зачем", "когда", "где", "кто", "что",
        "можно ли", "подскажите", "объясните", "?",
    ])
    # Паттерны, которые НЕ пересылаем (шум)
    noise_patterns: list[str] = field(default_factory=lambda: [
        "👍", "👎", "❤️", "🔥", "+1", "ок", "спс", "спасибо",
        "благодарю", "ясно", "понял", "понятно", "хорошо", "ага"
    ])
    # Минимальная длина сообщения для пересылки из групп
    min_group_message_length: int = 5
    # Пересылать ВСЕ личные сообщения (Business API)
    forward_all_business_dm: bool = True


@dataclass
class Config:
    """Главная конфигурация TG-Hub V2."""

    # ═══════════════════════════════════════════
    # TELEGRAM BOT
    # ═══════════════════════════════════════════
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    hub_chat_id: int = field(default_factory=lambda: int(os.getenv("HUB_CHAT_ID", "0")))
    moderator_user_id: int = field(default_factory=lambda: int(os.getenv("MODERATOR_USER_ID", "0")))

    # ═══════════════════════════════════════════
    # TELEGRAM GROUPS (мониторинг)
    # ═══════════════════════════════════════════
    group_students: TelegramGroupConfig = field(default_factory=lambda: TelegramGroupConfig(
        chat_id=int(os.getenv("GROUP_STUDENTS_ID", "0")),
        name=os.getenv("GROUP_STUDENTS_NAME", "Ученики"),
        enabled=os.getenv("GROUP_STUDENTS_ENABLED", "true").lower() == "true",
    ))
    group_curators: TelegramGroupConfig = field(default_factory=lambda: TelegramGroupConfig(
        chat_id=int(os.getenv("GROUP_CURATORS_ID", "0")),
        name=os.getenv("GROUP_CURATORS_NAME", "Кураторы"),
        enabled=os.getenv("GROUP_CURATORS_ENABLED", "true").lower() == "true",
    ))

    # ═══════════════════════════════════════════
    # GETCOURSE INTEGRATION
    # ═══════════════════════════════════════════
    getcourse: GetCourseConfig = field(default_factory=lambda: GetCourseConfig(
        enabled=os.getenv("GETCOURSE_ENABLED", "false").lower() == "true",
        account_name=os.getenv("GETCOURSE_ACCOUNT_NAME", ""),
        secret_key=os.getenv("GETCOURSE_SECRET_KEY", ""),
        webhook_secret=os.getenv("GETCOURSE_WEBHOOK_SECRET", ""),
    ))

    # ═══════════════════════════════════════════
    # WEBHOOK SERVER
    # ═══════════════════════════════════════════
    webhook_server: WebhookServerConfig = field(default_factory=lambda: WebhookServerConfig(
        host=os.getenv("WEBHOOK_HOST", "0.0.0.0"),
        port=int(os.getenv("WEBHOOK_PORT", "8080")),
        public_url=os.getenv("WEBHOOK_URL", ""),
    ))

    # ═══════════════════════════════════════════
    # AI SETTINGS
    # ═══════════════════════════════════════════
    ai_enabled: bool = field(default_factory=lambda: os.getenv("AI_ENABLED", "false").lower() == "true")
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    # AI поведение
    ai_auto_draft: bool = field(
        default_factory=lambda: os.getenv("AI_AUTO_DRAFT", "true").lower() == "true"
    )
    ai_min_message_length: int = field(
        default_factory=lambda: int(os.getenv("AI_MIN_MESSAGE_LENGTH", "10"))
    )

    # ═══════════════════════════════════════════
    # VECTOR STORE (RAG)
    # ═══════════════════════════════════════════
    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    )
    vector_db_path: str = field(default_factory=lambda: os.getenv("VECTOR_DB_PATH", "data/vector_db"))
    vector_search_limit: int = field(
        default_factory=lambda: int(os.getenv("VECTOR_SEARCH_LIMIT", "5"))
    )
    vector_min_score: float = field(
        default_factory=lambda: float(os.getenv("VECTOR_MIN_SCORE", "0.7"))
    )

    # ═══════════════════════════════════════════
    # PATHS & LOGGING
    # ═══════════════════════════════════════════
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "data/messages.db"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # ═══════════════════════════════════════════
    # FILTERS
    # ═══════════════════════════════════════════
    filters: FilterConfig = field(default_factory=FilterConfig)

    def ensure_dirs(self):
        """Создать необходимые директории."""
        Path("data").mkdir(parents=True, exist_ok=True)
        Path("data/vector_db").mkdir(parents=True, exist_ok=True)
        Path("data/documents").mkdir(parents=True, exist_ok=True)

    @property
    def monitored_groups(self) -> list[TelegramGroupConfig]:
        """Список всех мониторируемых групп."""
        groups = []
        if self.group_students.enabled and self.group_students.chat_id:
            groups.append(self.group_students)
        if self.group_curators.enabled and self.group_curators.chat_id:
            groups.append(self.group_curators)
        return groups

    @property
    def monitored_chat_ids(self) -> list[int]:
        """ID всех мониторируемых чатов (группы + хаб)."""
        ids = [g.chat_id for g in self.monitored_groups]
        if self.hub_chat_id:
            ids.append(self.hub_chat_id)
        return ids

    def get_group_name(self, chat_id: int) -> str:
        """Получить название группы по ID."""
        for g in self.monitored_groups:
            if g.chat_id == chat_id:
                return g.name
        return "Неизвестная группа"

    def validate(self) -> list[str]:
        """Проверить конфигурацию, вернуть список ошибок."""
        errors = []

        if not self.bot_token:
            errors.append("BOT_TOKEN не указан")
        if not self.hub_chat_id:
            errors.append("HUB_CHAT_ID не указан")
        if not self.moderator_user_id:
            errors.append("MODERATOR_USER_ID не указан")

        # Проверка AI
        if self.ai_enabled:
            if not self.anthropic_api_key:
                errors.append("AI включён, но ANTHROPIC_API_KEY не указан")
            if not self.openai_api_key:
                errors.append("AI включён, но OPENAI_API_KEY не указан (нужен для embeddings)")

        # Проверка GetCourse
        if self.getcourse.enabled:
            if not self.getcourse.webhook_secret:
                errors.append("GetCourse включён, но GETCOURSE_WEBHOOK_SECRET не указан")
            if not self.webhook_server.public_url:
                errors.append("GetCourse включён, но WEBHOOK_URL не указан")

        return errors


# Глобальный singleton
config = Config()
config.ensure_dirs()
