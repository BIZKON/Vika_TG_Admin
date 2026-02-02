"""
Агрегатор: ядро системы.
Подключается к Telegram-аккаунтам через Telethon,
слушает входящие сообщения и пересылает их в хаб.
"""

import asyncio
import logging
from datetime import datetime

from telethon import TelegramClient, events
from telethon.tl.types import (
    User, Chat, Channel,
    PeerUser, PeerChat, PeerChannel,
    MessageMediaPhoto, MessageMediaDocument,
)

from config import Config, AccountConfig
from core.storage import Database, MessageRecord
from core.filters import MessageFilter
from core.formatter import format_hub_message

logger = logging.getLogger(__name__)


class AccountListener:
    """
    Слушатель одного Telegram-аккаунта.
    Перехватывает входящие сообщения и пересылает в хаб.
    """

    def __init__(
        self,
        account_config: AccountConfig,
        bot_client: TelegramClient,
        config: Config,
        db: Database,
        msg_filter: MessageFilter,
        ai_assistant=None,
    ):
        self.account = account_config
        self.bot = bot_client
        self.config = config
        self.db = db
        self.filter = msg_filter
        self.ai_assistant = ai_assistant

        # Создаём Telethon-клиент для этого аккаунта
        self.client = TelegramClient(
            account_config.session_path,
            account_config.api_id,
            account_config.api_hash,
        )
        # Флаг: слушатель активен
        self._running = False

    async def start(self):
        """Подключиться и начать слушать."""
        logger.info(f"[{self.account.name}] Подключение...")
        await self.client.start(phone=self.account.phone)

        me = await self.client.get_me()
        logger.info(f"[{self.account.name}] Авторизован как: {me.first_name} (ID: {me.id})")

        # Регистрируем обработчик входящих
        self.client.add_event_handler(
            self._on_new_message,
            events.NewMessage(incoming=True)
        )

        self._running = True
        logger.info(f"[{self.account.name}] Слушатель запущен ✓")

    async def stop(self):
        """Остановить слушатель."""
        self._running = False
        await self.client.disconnect()
        logger.info(f"[{self.account.name}] Отключён")

    async def _on_new_message(self, event: events.NewMessage.Event):
        """Обработчик нового входящего сообщения."""
        try:
            message = event.message

            # Игнорируем свои же сообщения
            me = await self.client.get_me()
            if message.sender_id == me.id:
                return

            # Игнорируем сообщения без текста (пока)
            text = message.text or message.message or ""
            if not text and not message.media:
                return

            # Определяем тип чата
            chat = await event.get_chat()
            chat_type = self._get_chat_type(chat)
            chat_name = self._get_chat_name(chat)
            chat_id = event.chat_id

            # Проверяем, не замьючен ли чат
            if self.db.is_muted(chat_id):
                return

            # Дедупликация
            if self.db.is_duplicate(chat_id, message.id):
                logger.debug(f"[{self.account.name}] Дубль: {chat_name} #{message.id}")
                return

            # Фильтрация
            if text:
                filter_result = self.filter.analyze(text, chat_type)
                if not filter_result.should_forward:
                    logger.debug(
                        f"[{self.account.name}] Отфильтровано ({filter_result.reason}): "
                        f"{text[:50]}..."
                    )
                    return
            else:
                # Медиа без текста — пересылаем как обычное
                from core.filters import FilterResult
                filter_result = FilterResult(
                    should_forward=True,
                    priority="normal",
                    reason="media_message",
                    tags=["📎 медиа"]
                )

            # Получаем информацию об отправителе
            sender = await event.get_sender()
            sender_name = self._get_sender_name(sender)
            sender_username = getattr(sender, "username", None)
            sender_id = sender.id if sender else 0

            # Форматируем сообщение
            display_text = text if text else "[Медиа-сообщение]"
            hub_text = format_hub_message(
                text=display_text,
                sender_name=sender_name,
                sender_username=sender_username,
                chat_name=chat_name,
                chat_type=chat_type,
                source_account=self.account.name,
                filter_result=filter_result,
                timestamp=message.date,
            )

            # Отправляем в хаб через бота
            hub_msg = await self.bot.send_message(
                self.config.hub_chat_id,
                hub_text,
                parse_mode="html",
            )

            # Если есть медиа — пересылаем отдельно
            if message.media:
                try:
                    await self.client.forward_messages(
                        entity=self.config.hub_chat_id,
                        messages=message,
                        from_peer=chat,
                    )
                except Exception as e:
                    # Если пересылка не работает (приватный чат) — скачиваем и отправляем
                    logger.warning(f"Forward failed, downloading media: {e}")
                    media_file = await self.client.download_media(message, file=bytes)
                    if media_file and isinstance(message.media, MessageMediaPhoto):
                        await self.bot.send_file(
                            self.config.hub_chat_id,
                            media_file,
                            caption="📎 Вложение к сообщению выше",
                        )

            # Сохраняем маппинг в БД
            record = MessageRecord(
                id=None,
                hub_message_id=hub_msg.id,
                original_message_id=message.id,
                original_chat_id=chat_id,
                source_account=self.account.name,
                sender_id=sender_id,
                sender_name=sender_name,
                sender_username=sender_username,
                chat_name=chat_name,
                chat_type=chat_type,
                priority=filter_result.priority,
                timestamp=message.date.isoformat(),
            )
            self.db.save_message(record)

            logger.info(
                f"[{self.account.name}] ✉️ {sender_name} ({chat_name}): "
                f"{text[:60]}... → Hub #{hub_msg.id}"
            )

            # ─── AI: генерация черновика ответа ───
            if self.ai_assistant and self.ai_assistant.enabled and text:
                # Проверяем минимальную длину
                if len(text) >= self.config.ai_min_message_length:
                    # Проверяем фильтр "только ЛС"
                    if not self.config.ai_draft_for_dm_only or chat_type == "dm":
                        asyncio.create_task(
                            self._generate_ai_draft(
                                hub_msg_id=hub_msg.id,
                                message_text=text,
                                sender_name=sender_name,
                                sender_username=sender_username,
                                chat_name=chat_name,
                                chat_type=chat_type,
                                priority=filter_result.priority,
                            )
                        )

            # Обновляем watched_chats
            self.config.watched_chats[str(chat_id)] = {
                "name": chat_name,
                "account": self.account.name,
                "type": chat_type,
            }

        except Exception as e:
            logger.error(f"[{self.account.name}] Ошибка обработки: {e}", exc_info=True)

    # ─── Helpers ───

    async def _generate_ai_draft(
        self,
        hub_msg_id: int,
        message_text: str,
        sender_name: str,
        sender_username: str | None,
        chat_name: str,
        chat_type: str,
        priority: str,
    ):
        """Асинхронная генерация AI-черновика (запускается как task)."""
        try:
            from ai.assistant import format_ai_draft_message

            draft = await self.ai_assistant.generate_draft(
                message_text=message_text,
                sender_name=sender_name,
                sender_username=sender_username,
                chat_name=chat_name,
                chat_type=chat_type,
                priority=priority,
            )

            if draft and draft.should_respond and draft.draft_text:
                # Сохраняем черновик для обработки действий
                self.ai_assistant.pending_drafts[hub_msg_id] = draft.draft_text

                # Отправляем как reply на исходное сообщение в хабе
                draft_text = format_ai_draft_message(draft, hub_msg_id)
                await self.bot.send_message(
                    self.config.hub_chat_id,
                    draft_text,
                    reply_to=hub_msg_id,
                    parse_mode="html",
                )
                logger.info(f"🤖 AI draft sent for hub #{hub_msg_id}")

        except Exception as e:
            logger.error(f"🤖 AI draft generation failed: {e}", exc_info=True)

    # ─── Chat Type Helpers ───

    @staticmethod
    def _get_chat_type(chat) -> str:
        if isinstance(chat, User):
            return "dm"
        elif isinstance(chat, Chat):
            return "group"
        elif isinstance(chat, Channel):
            return "supergroup" if chat.megagroup else "channel"
        return "unknown"

    @staticmethod
    def _get_chat_name(chat) -> str:
        if isinstance(chat, User):
            parts = [chat.first_name or "", chat.last_name or ""]
            return " ".join(p for p in parts if p) or "Unknown"
        return getattr(chat, "title", "Unknown")

    @staticmethod
    def _get_sender_name(sender) -> str:
        if sender is None:
            return "Unknown"
        if isinstance(sender, User):
            parts = [sender.first_name or "", sender.last_name or ""]
            return " ".join(p for p in parts if p) or "Unknown"
        return getattr(sender, "title", "Unknown")


class Aggregator:
    """
    Главный агрегатор: управляет всеми слушателями.
    """

    def __init__(self, config: Config, bot_client: TelegramClient, db: Database, ai_assistant=None):
        self.config = config
        self.bot = bot_client
        self.db = db
        self.filter = MessageFilter(config.filters)
        self.ai_assistant = ai_assistant
        self.listeners: list[AccountListener] = []

    async def start(self):
        """Запустить все слушатели."""
        for acc in self.config.accounts:
            if not acc.api_id or not acc.api_hash:
                logger.warning(f"Пропуск аккаунта '{acc.name}': нет API credentials")
                continue

            listener = AccountListener(
                account_config=acc,
                bot_client=self.bot,
                config=self.config,
                db=self.db,
                msg_filter=self.filter,
                ai_assistant=self.ai_assistant,
            )
            await listener.start()
            self.listeners.append(listener)

        logger.info(f"Агрегатор запущен: {len(self.listeners)} аккаунт(ов) активно")

    async def stop(self):
        """Остановить все слушатели."""
        for listener in self.listeners:
            await listener.stop()
        logger.info("Агрегатор остановлен")

    def get_client_for_account(self, account_name: str) -> TelegramClient | None:
        """Получить Telethon-клиент по имени аккаунта."""
        for listener in self.listeners:
            if listener.account.name == account_name:
                return listener.client
        return None
