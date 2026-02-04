"""
TG-Hub V2: Форматирование сообщений для хаба.
"""

from datetime import datetime
from typing import Optional

from core.models import IncomingMessage, MessageSource, MessagePriority, GetCourseEventType


def get_source_emoji(source: MessageSource) -> str:
    """Эмодзи для источника."""
    return {
        MessageSource.BUSINESS_DM: "💬",
        MessageSource.GROUP_STUDENTS: "👥",
        MessageSource.GROUP_CURATORS: "👔",
        MessageSource.GETCOURSE: "📚",
        MessageSource.HUB: "🏠",
    }.get(source, "📨")


def get_source_label(source: MessageSource) -> str:
    """Название источника."""
    return {
        MessageSource.BUSINESS_DM: "ЛИЧНОЕ СООБЩЕНИЕ",
        MessageSource.GROUP_STUDENTS: "ГРУППА: Ученики",
        MessageSource.GROUP_CURATORS: "ГРУППА: Кураторы",
        MessageSource.GETCOURSE: "GETCOURSE",
        MessageSource.HUB: "ХАБ",
    }.get(source, "СООБЩЕНИЕ")


def get_priority_indicator(priority: MessagePriority) -> str:
    """Индикатор приоритета."""
    return {
        MessagePriority.URGENT: "🔴 Срочно",
        MessagePriority.HIGH: "🟡 Вопрос",
        MessagePriority.NORMAL: "🟢 Обычное",
        MessagePriority.LOW: "⚪ Инфо",
    }.get(priority, "")


def format_hub_message(msg: IncomingMessage, group_name: Optional[str] = None) -> str:
    """
    Форматировать сообщение для отправки в хаб.

    Args:
        msg: Унифицированное входящее сообщение
        group_name: Переопределение названия группы

    Returns:
        Отформатированный HTML текст
    """
    emoji = get_source_emoji(msg.source)
    source_label = get_source_label(msg.source)

    # Для групп добавляем название
    if msg.source in [MessageSource.GROUP_STUDENTS, MessageSource.GROUP_CURATORS]:
        if group_name or msg.chat_name:
            source_label = f"ГРУППА: {group_name or msg.chat_name}"

    # Заголовок
    lines = [f"┌─ {emoji} <b>{source_label}</b> ─"]

    # Отправитель
    sender_line = f"│ От: <b>{_escape_html(msg.sender_name)}</b>"
    if msg.sender_username:
        sender_line += f" (@{msg.sender_username})"
    lines.append(sender_line)

    # Для GetCourse — дополнительная информация
    if msg.source == MessageSource.GETCOURSE:
        if msg.sender_email:
            lines.append(f"│ Email: {_escape_html(msg.sender_email)}")
        if msg.course_name:
            lines.append(f"│ Курс: {_escape_html(msg.course_name)}")
        if msg.lesson_name:
            lines.append(f"│ Урок: {_escape_html(msg.lesson_name)}")

    # Разделитель
    lines.append("├" + "─" * 40)

    # Текст сообщения
    text = msg.text or "[Нет текста]"
    # Ограничиваем длину
    if len(text) > 1000:
        text = text[:1000] + "..."
    lines.append(f"│ {_escape_html(text)}")

    # Медиа
    if msg.has_media:
        lines.append(f"│ 📎 <i>Вложение: {msg.media_type or 'файл'}</i>")

    # Разделитель
    lines.append("├" + "─" * 40)

    # Время и приоритет
    time_str = msg.timestamp.strftime("%H:%M") if msg.timestamp else datetime.now().strftime("%H:%M")
    priority_str = get_priority_indicator(msg.priority)

    footer_parts = [f"│ 🕐 {time_str}"]
    if priority_str:
        footer_parts.append(priority_str)
    if msg.requires_response:
        footer_parts.append("📝 Требует ответа")

    lines.append(" │ ".join(footer_parts))

    # Теги
    if msg.tags:
        valid_tags = [t for t in msg.tags if t]
        if valid_tags:
            lines.append(f"│ {' '.join(valid_tags)}")

    # GetCourse ссылка
    if msg.getcourse_url:
        lines.append(f"│ <a href='{msg.getcourse_url}'>Открыть в GetCourse</a>")

    # Закрывающая линия
    lines.append("└" + "─" * 40)

    return "\n".join(lines)


def format_getcourse_message(msg: IncomingMessage) -> str:
    """
    Специальное форматирование для GetCourse событий.
    """
    event_type = msg.getcourse_event_type

    # Определяем тип события
    if event_type == GetCourseEventType.HOMEWORK:
        header = "📝 ДОМАШНЕЕ ЗАДАНИЕ"
        icon = "📝"
    elif event_type == GetCourseEventType.COMMENT:
        header = "💬 КОММЕНТАРИЙ К УРОКУ"
        icon = "💬"
    elif event_type == GetCourseEventType.MESSAGE:
        header = "✉️ СООБЩЕНИЕ ОТ УЧЕНИКА"
        icon = "✉️"
    else:
        header = "📌 СОБЫТИЕ GETCOURSE"
        icon = "📌"

    lines = [
        f"┌─ 📚 <b>GETCOURSE: {header}</b> ─",
        f"│ {icon} Ученик: <b>{_escape_html(msg.sender_name)}</b>",
    ]

    if msg.sender_email:
        lines.append(f"│ 📧 Email: {_escape_html(msg.sender_email)}")

    if msg.course_name:
        lines.append(f"│ 📖 Курс: {_escape_html(msg.course_name)}")

    if msg.lesson_name:
        lines.append(f"│ 📄 Урок: {_escape_html(msg.lesson_name)}")

    lines.append("├" + "─" * 40)

    # Текст
    text = msg.text or "[Нет текста]"
    if len(text) > 800:
        text = text[:800] + "..."
    lines.append(f"│ {_escape_html(text)}")

    lines.append("├" + "─" * 40)

    # Футер
    time_str = msg.timestamp.strftime("%H:%M") if msg.timestamp else datetime.now().strftime("%H:%M")
    status = "📝 Требует проверки" if msg.requires_response else "ℹ️ Информация"

    lines.append(f"│ 🕐 {time_str} │ {status}")

    if msg.getcourse_url:
        lines.append(f"│ 🔗 <a href='{msg.getcourse_url}'>Открыть в GetCourse</a>")

    lines.append("└" + "─" * 40)

    return "\n".join(lines)


def format_ai_draft(draft_text: str, hub_msg_id: int, confidence: float = 0.0) -> str:
    """
    Форматировать AI черновик ответа.
    """
    confidence_indicator = ""
    if confidence >= 0.8:
        confidence_indicator = "🟢 Высокая уверенность"
    elif confidence >= 0.5:
        confidence_indicator = "🟡 Средняя уверенность"
    else:
        confidence_indicator = "🔴 Низкая уверенность"

    return f"""┌─ 🤖 <b>AI ЧЕРНОВИК</b> ─────────────────
│ {confidence_indicator}
├────────────────────────────────────────
│ {_escape_html(draft_text)}
├────────────────────────────────────────
│ <i>Нажмите кнопку для отправки или отредактируйте</i>
└────────────────────────────────────────"""


def format_stats(stats: dict) -> str:
    """Форматировать статистику."""
    return f"""📊 <b>Статистика за {stats.get('date', 'сегодня')}</b>

📨 Всего сообщений: <b>{stats.get('total_messages', 0)}</b>

По источникам:
├ 💬 Личные (Business): {stats.get('business_dm', 0)}
├ 👥 Группа учеников: {stats.get('group_students', 0)}
├ 👔 Группа кураторов: {stats.get('group_curators', 0)}
└ 📚 GetCourse: {stats.get('getcourse', 0)}

🤖 AI черновиков: {stats.get('ai_drafts', 0)}
✅ Отправлено ответов: {stats.get('responses_sent', 0)}"""


def _escape_html(text: str) -> str:
    """Экранировать HTML символы."""
    if not text:
        return ""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
