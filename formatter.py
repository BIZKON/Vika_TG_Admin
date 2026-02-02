"""
Форматирование сообщений для хаб-группы.
Создаёт красивые карточки с метаданными.
"""

from datetime import datetime
from core.filters import FilterResult


PRIORITY_EMOJI = {
    "urgent": "🔴",
    "normal": "🟡",
    "info": "🟢",
}

SOURCE_EMOJI = {
    "work": "💼",
    "personal": "👤",
}

CHAT_TYPE_LABEL = {
    "dm": "Личное сообщение",
    "group": "Группа",
    "supergroup": "Группа",
}


def format_hub_message(
    text: str,
    sender_name: str,
    sender_username: str | None,
    chat_name: str,
    chat_type: str,
    source_account: str,
    filter_result: FilterResult,
    timestamp: datetime | None = None,
) -> str:
    """
    Форматирует сообщение для отправки в хаб-группу.

    Returns:
        Отформатированная строка (HTML).
    """
    ts = timestamp or datetime.now()
    time_str = ts.strftime("%H:%M")
    priority = PRIORITY_EMOJI.get(filter_result.priority, "⚪")
    source = SOURCE_EMOJI.get(source_account, "📱")
    chat_type_label = CHAT_TYPE_LABEL.get(chat_type, chat_type)

    # Username
    username_part = f" (@{sender_username})" if sender_username else ""

    # Теги
    tags_str = " ".join(filter_result.tags) if filter_result.tags else ""

    # Формат карточки
    lines = [
        f"━━━━━━━━━━━━━━━━━━",
        f"{priority} <b>{chat_type_label}</b>",
        f"👤 <b>{sender_name}</b>{username_part}",
        f"📍 {chat_name}",
        f"{source} Источник: <b>{source_account}</b> │ ⏰ {time_str}",
    ]

    if tags_str:
        lines.append(f"🏷 {tags_str}")

    lines.append("")
    lines.append(text)
    lines.append("")
    lines.append("↩️ <i>Reply на это сообщение для ответа</i>")
    lines.append(f"━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def format_status_message(unreplied: list, stats: dict) -> str:
    """Форматирует сообщение со статусом."""
    lines = [
        "📊 <b>Статус модерации</b>",
        "",
        f"📬 Неотвеченных: <b>{len(unreplied)}</b>",
    ]

    if unreplied:
        urgent = [m for m in unreplied if m.priority == "urgent"]
        if urgent:
            lines.append(f"🔴 Из них срочных: <b>{len(urgent)}</b>")

        lines.append("")
        lines.append("<b>Последние неотвеченные:</b>")
        for msg in unreplied[:5]:
            p = PRIORITY_EMOJI.get(msg.priority, "⚪")
            lines.append(f"  {p} {msg.sender_name} — {msg.chat_name}")

    lines.append("")
    lines.append(f"📈 <b>Статистика за {stats['period_days']} дней:</b>")
    lines.append(f"  Всего сообщений: {stats['total_messages']}")
    lines.append(f"  Отвечено: {stats['replied']} ({stats['reply_rate']})")
    if stats['avg_reply_minutes']:
        lines.append(f"  Среднее время ответа: {stats['avg_reply_minutes']} мин")

    if stats['top_sources']:
        lines.append("")
        lines.append("<b>Топ источников:</b>")
        for src in stats['top_sources']:
            lines.append(f"  • {src['name']}: {src['count']} сообщ.")

    return "\n".join(lines)


def format_sources_list(watched_chats: dict, muted: list[int]) -> str:
    """Форматирует список отслеживаемых источников."""
    if not watched_chats:
        return "📭 Нет отслеживаемых чатов. Они появятся автоматически при получении первого сообщения."

    lines = ["📡 <b>Отслеживаемые источники:</b>", ""]

    for chat_id, info in watched_chats.items():
        is_muted = int(chat_id) in muted
        status = "🔇" if is_muted else "🔔"
        source = SOURCE_EMOJI.get(info.get("account", ""), "📱")
        lines.append(
            f"  {status} {source} <b>{info.get('name', 'Unknown')}</b> "
            f"[{info.get('type', '?')}] (ID: {chat_id})"
        )

    lines.append("")
    lines.append("Управление: /mute [ID] · /unmute [ID]")
    return "\n".join(lines)
