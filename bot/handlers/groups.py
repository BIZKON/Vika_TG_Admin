"""
TG-Hub V2: Обработчик сообщений из Telegram групп.
Мониторит указанные группы и пересылает сообщения в хаб.
"""

import logging
from datetime import datetime

from aiogram import Router, Bot, F
from aiogram.types import Message

from config import config
from core.models import IncomingMessage, MessageSource, MessagePriority
from core.storage import Database
from core.formatter import format_hub_message

logger = logging.getLogger(__name__)

# Роутер для групповых сообщений
router = Router(name="groups")


def get_source_for_chat(chat_id: int) -> MessageSource | None:
    """Определить источник по chat_id."""
    if config.group_students.chat_id == chat_id:
        return MessageSource.GROUP_STUDENTS
    if config.group_curators.chat_id == chat_id:
        return MessageSource.GROUP_CURATORS
    return None


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def on_group_message(message: Message, bot: Bot, db: Database):
    """
    Обработка сообщений из мониторируемых групп.
    """
    try:
        chat_id = message.chat.id

        # Проверяем, мониторим ли эту группу
        source = get_source_for_chat(chat_id)
        if not source:
            # Не мониторируемая группа (может быть хаб)
            if chat_id != config.hub_chat_id:
                logger.debug(f"Message from non-monitored group {chat_id}, skipping")
            return

        # Проверяем mute
        if db.is_muted(chat_id):
            return

        # Игнорируем сообщения от ботов
        if message.from_user and message.from_user.is_bot:
            return

        # Получаем текст
        text = message.text or message.caption or ""

        # Фильтрация: минимальная длина
        if len(text) < config.filters.min_group_message_length:
            return

        # Фильтрация: шумовые паттерны
        text_lower = text.lower().strip()
        for noise in config.filters.noise_patterns:
            if text_lower == noise.lower():
                return

        # Дедупликация
        source_key = source.value
        if db.is_duplicate(source_key, chat_id, message.message_id):
            return
        db.mark_processed(source_key, chat_id, message.message_id)

        # Информация об отправителе
        sender = message.from_user
        sender_name = sender.full_name if sender else "Unknown"
        sender_username = sender.username if sender else None
        sender_id = sender.id if sender else None

        # Название группы
        group_name = config.get_group_name(chat_id)

        # Определяем приоритет
        priority = _analyze_priority(text)

        # Создаём унифицированное сообщение
        incoming = IncomingMessage(
            source=source,
            source_message_id=message.message_id,
            source_chat_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_username=sender_username,
            chat_name=group_name,
            text=text,
            has_media=bool(message.photo or message.document or message.video),
            media_type=_get_media_type(message),
            priority=priority,
            tags=_get_tags(priority, source),
            timestamp=message.date or datetime.now(),
            requires_response=(priority in [MessagePriority.URGENT, MessagePriority.HIGH]),
        )

        # Форматируем и отправляем в хаб
        hub_text = format_hub_message(incoming, group_name=group_name)
        hub_msg = await bot.send_message(
            config.hub_chat_id,
            hub_text,
            parse_mode="html",
        )

        # Пересылаем медиа, если есть
        if incoming.has_media:
            try:
                await message.forward(config.hub_chat_id)
            except Exception as e:
                logger.warning(f"Failed to forward media from group: {e}")

        # Сохраняем в БД
        from core.models import HubMessage
        hub_record = HubMessage(
            hub_message_id=hub_msg.message_id,
            source=source,
            source_message_id=message.message_id,
            source_chat_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_username=sender_username,
            chat_name=group_name,
            priority=priority.value,
            created_at=datetime.now().isoformat(),
        )
        db.save_hub_message(hub_record)
        db.increment_stat(source)

        logger.info(
            f"👥 [{group_name}] {sender_name}: {text[:50]}... → Hub #{hub_msg.message_id}"
        )

        # Возвращаем для AI обработки
        return incoming, hub_msg.message_id

    except Exception as e:
        logger.error(f"Error processing group message: {e}", exc_info=True)


# ─── Helpers ───

def _analyze_priority(text: str) -> MessagePriority:
    """Определить приоритет по тексту."""
    if not text:
        return MessagePriority.LOW

    text_lower = text.lower()

    # Срочное
    for keyword in config.filters.urgent_keywords:
        if keyword in text_lower:
            return MessagePriority.URGENT

    # Вопрос
    for keyword in config.filters.question_keywords:
        if keyword in text_lower:
            return MessagePriority.HIGH

    return MessagePriority.NORMAL


def _get_media_type(message: Message) -> str | None:
    """Определить тип медиа."""
    if message.photo:
        return "photo"
    if message.document:
        return "document"
    if message.video:
        return "video"
    if message.voice:
        return "voice"
    return None


def _get_tags(priority: MessagePriority, source: MessageSource) -> list[str]:
    """Сформировать теги."""
    tags = []

    if source == MessageSource.GROUP_STUDENTS:
        tags.append("👥 Ученики")
    elif source == MessageSource.GROUP_CURATORS:
        tags.append("👔 Кураторы")

    if priority == MessagePriority.URGENT:
        tags.append("🔴 Срочно")
    elif priority == MessagePriority.HIGH:
        tags.append("❓ Вопрос")

    return tags
