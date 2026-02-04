"""
TG-Hub V2: Обработчик Telegram Business API.
Получает сообщения из личных чатов через Business Connection.
"""

import logging
from datetime import datetime

from aiogram import Router, Bot, F
from aiogram.types import Message, BusinessConnection, BusinessMessagesDeleted

from config import config
from core.models import IncomingMessage, MessageSource, MessagePriority
from core.storage import Database
from core.formatter import format_hub_message

logger = logging.getLogger(__name__)

# Роутер для Business API событий
router = Router(name="business")

# Хранилище активных Business connections
active_connections: dict[str, BusinessConnection] = {}


@router.business_connection()
async def on_business_connection(event: BusinessConnection, bot: Bot):
    """
    Обработка подключения/отключения Business аккаунта.

    Срабатывает когда пользователь:
    - Подключает бота в Telegram Business настройках
    - Отключает бота
    """
    user = event.user
    connection_id = event.id

    if event.is_enabled:
        # Сохраняем активное соединение
        active_connections[connection_id] = event

        logger.info(
            f"📱 Business connected: {user.full_name} (ID: {user.id}), "
            f"connection_id: {connection_id}"
        )

        # Уведомляем в хаб
        await bot.send_message(
            config.hub_chat_id,
            f"📱 <b>Business аккаунт подключён!</b>\n\n"
            f"👤 {user.full_name}\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"🔗 Connection: <code>{connection_id[:20]}...</code>\n\n"
            f"Теперь личные сообщения этого аккаунта будут приходить сюда.",
            parse_mode="html",
        )
    else:
        # Удаляем соединение
        if connection_id in active_connections:
            del active_connections[connection_id]

        logger.info(f"📱 Business disconnected: {user.full_name} (ID: {user.id})")

        await bot.send_message(
            config.hub_chat_id,
            f"📱 <b>Business аккаунт отключён</b>\n\n"
            f"👤 {user.full_name}\n"
            f"Сообщения больше не будут пересылаться.",
            parse_mode="html",
        )


@router.business_message()
async def on_business_message(message: Message, bot: Bot, db: Database):
    """
    Обработка входящего сообщения через Business API.

    Это сообщения, которые приходят в личку аккаунта с Premium
    и подключённым Business ботом.
    """
    try:
        # Игнорируем исходящие сообщения (от владельца аккаунта)
        if message.from_user and message.from_user.id == message.business_connection_id:
            return

        # Проверяем mute
        chat_id = message.chat.id
        if db.is_muted(chat_id):
            logger.debug(f"Business message from muted chat {chat_id}, skipping")
            return

        # Дедупликация
        if db.is_duplicate("business_dm", chat_id, message.message_id):
            return
        db.mark_processed("business_dm", chat_id, message.message_id)

        # Получаем информацию об отправителе
        sender = message.from_user
        sender_name = sender.full_name if sender else "Unknown"
        sender_username = sender.username if sender else None
        sender_id = sender.id if sender else None

        # Определяем приоритет
        text = message.text or message.caption or ""
        priority = _analyze_priority(text)

        # Создаём унифицированное сообщение
        incoming = IncomingMessage(
            source=MessageSource.BUSINESS_DM,
            source_message_id=message.message_id,
            source_chat_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_username=sender_username,
            chat_name=sender_name,  # В ЛС название = имя собеседника
            text=text,
            has_media=bool(message.photo or message.document or message.video),
            media_type=_get_media_type(message),
            priority=priority,
            tags=_get_tags(priority, "dm"),
            timestamp=message.date or datetime.now(),
            requires_response=True,  # ЛС всегда требует ответа
            business_connection_id=message.business_connection_id,
        )

        # Форматируем и отправляем в хаб
        hub_text = format_hub_message(incoming)
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
                logger.warning(f"Failed to forward media: {e}")

        # Сохраняем в БД
        from core.models import HubMessage
        hub_record = HubMessage(
            hub_message_id=hub_msg.message_id,
            source=MessageSource.BUSINESS_DM,
            source_message_id=message.message_id,
            source_chat_id=chat_id,
            business_connection_id=message.business_connection_id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_username=sender_username,
            chat_name=sender_name,
            priority=priority.value,
            created_at=datetime.now().isoformat(),
        )
        db.save_hub_message(hub_record)
        db.increment_stat(MessageSource.BUSINESS_DM)

        logger.info(
            f"💬 Business DM: {sender_name} → Hub #{hub_msg.message_id}: "
            f"{text[:50]}..."
        )

        # Возвращаем incoming для AI обработки
        return incoming, hub_msg.message_id

    except Exception as e:
        logger.error(f"Error processing business message: {e}", exc_info=True)


@router.deleted_business_messages()
async def on_business_messages_deleted(event: BusinessMessagesDeleted, bot: Bot):
    """Обработка удаления сообщений (опционально)."""
    logger.debug(f"Business messages deleted: {event.message_ids}")


# ─── Helpers ───

def _analyze_priority(text: str) -> MessagePriority:
    """Определить приоритет по тексту."""
    if not text:
        return MessagePriority.NORMAL

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
    if message.video_note:
        return "video_note"
    if message.sticker:
        return "sticker"
    return None


def _get_tags(priority: MessagePriority, chat_type: str) -> list[str]:
    """Сформировать теги."""
    tags = []

    if chat_type == "dm":
        tags.append("📱 Premium Business")

    if priority == MessagePriority.URGENT:
        tags.append("🔴 Срочно")
    elif priority == MessagePriority.HIGH:
        tags.append("❓ Вопрос")

    return tags
