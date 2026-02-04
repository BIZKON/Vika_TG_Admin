"""
Модели данных для TG-Hub V2.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class MessageSource(str, Enum):
    """Источник сообщения."""
    BUSINESS_DM = "business_dm"      # Telegram Business API (личка)
    GROUP_STUDENTS = "group_students" # Группа учеников
    GROUP_CURATORS = "group_curators" # Группа кураторов
    GETCOURSE = "getcourse"           # GetCourse webhook
    HUB = "hub"                       # Из хаба (команды)


class MessagePriority(str, Enum):
    """Приоритет сообщения."""
    URGENT = "urgent"       # Срочное
    HIGH = "high"           # Высокий (вопрос)
    NORMAL = "normal"       # Обычный
    LOW = "low"             # Низкий (информационное)


class GetCourseEventType(str, Enum):
    """Тип события от GetCourse."""
    HOMEWORK = "homework"         # Домашнее задание
    COMMENT = "comment"           # Комментарий к уроку
    MESSAGE = "message"           # Сообщение от ученика
    ORDER = "order"               # Новый заказ
    UNKNOWN = "unknown"


@dataclass
class IncomingMessage:
    """
    Унифицированное входящее сообщение из любого источника.
    """
    # Идентификация
    source: MessageSource
    source_message_id: Optional[int] = None  # ID в источнике (если есть)
    source_chat_id: Optional[int] = None     # Chat ID в источнике

    # Отправитель
    sender_id: Optional[int] = None
    sender_name: str = "Unknown"
    sender_username: Optional[str] = None
    sender_email: Optional[str] = None       # Для GetCourse
    sender_phone: Optional[str] = None       # Для GetCourse

    # Контекст
    chat_name: Optional[str] = None          # Название группы/чата
    course_name: Optional[str] = None        # Название курса (GetCourse)
    lesson_name: Optional[str] = None        # Название урока (GetCourse)

    # Содержимое
    text: str = ""
    has_media: bool = False
    media_type: Optional[str] = None         # photo, document, video, etc.

    # Метаданные
    priority: MessagePriority = MessagePriority.NORMAL
    tags: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    # GetCourse специфичное
    getcourse_event_type: Optional[GetCourseEventType] = None
    getcourse_url: Optional[str] = None      # Ссылка на объект в GetCourse

    # Бизнес-логика
    requires_response: bool = False
    business_connection_id: Optional[str] = None  # Для ответа через Business API


@dataclass
class HubMessage:
    """
    Сообщение, отправленное в хаб.
    """
    id: Optional[int] = None                 # ID в БД
    hub_message_id: int = 0                  # ID сообщения в хабе

    # Связь с оригиналом
    source: MessageSource = MessageSource.HUB
    source_message_id: Optional[int] = None
    source_chat_id: Optional[int] = None
    business_connection_id: Optional[str] = None

    # Отправитель
    sender_id: Optional[int] = None
    sender_name: str = ""
    sender_username: Optional[str] = None

    # Контекст
    chat_name: Optional[str] = None
    priority: str = "normal"

    # Время
    created_at: str = ""

    # Статус
    replied: bool = False
    replied_at: Optional[str] = None


@dataclass
class GetCourseEvent:
    """
    Событие от GetCourse webhook.
    """
    event_type: GetCourseEventType

    # Пользователь
    user_email: str = ""
    user_name: str = ""
    user_phone: str = ""
    user_id: Optional[int] = None

    # Контекст
    course_title: str = ""
    lesson_title: str = ""

    # Данные
    task_text: str = ""
    comment_text: str = ""
    file_url: Optional[str] = None

    # Метаданные
    timestamp: datetime = field(default_factory=datetime.now)
    raw_data: dict = field(default_factory=dict)

    def to_incoming_message(self) -> IncomingMessage:
        """Преобразовать в унифицированное сообщение."""
        text_parts = []

        if self.event_type == GetCourseEventType.HOMEWORK:
            text_parts.append(f"📝 Домашнее задание")
            if self.task_text:
                text_parts.append(f"\n{self.task_text}")
        elif self.event_type == GetCourseEventType.COMMENT:
            text_parts.append(f"💬 Комментарий к уроку")
            if self.comment_text:
                text_parts.append(f"\n{self.comment_text}")
        elif self.event_type == GetCourseEventType.MESSAGE:
            text_parts.append(f"✉️ Сообщение")
            if self.comment_text or self.task_text:
                text_parts.append(f"\n{self.comment_text or self.task_text}")
        else:
            text_parts.append(f"📌 Событие: {self.event_type.value}")

        return IncomingMessage(
            source=MessageSource.GETCOURSE,
            sender_name=self.user_name or self.user_email,
            sender_email=self.user_email,
            sender_phone=self.user_phone,
            course_name=self.course_title,
            lesson_name=self.lesson_title,
            text="\n".join(text_parts),
            priority=MessagePriority.HIGH,
            tags=["📚 GetCourse", f"📖 {self.course_title}" if self.course_title else ""],
            timestamp=self.timestamp,
            getcourse_event_type=self.event_type,
            requires_response=self.event_type in [GetCourseEventType.HOMEWORK, GetCourseEventType.COMMENT],
        )
