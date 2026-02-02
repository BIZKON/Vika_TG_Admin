"""
Маршрутизатор ответов.
Когда Виктория отвечает на сообщение в хабе —
ответ отправляется в оригинальный чат от нужного аккаунта.

Также обрабатывает AI-действия: !ok, !no, и редактирование черновиков.
"""

import asyncio
import logging
from datetime import datetime

from telethon import TelegramClient, events

from config import Config
from core.storage import Database
from core.aggregator import Aggregator

logger = logging.getLogger(__name__)


class ReplyRouter:
    """
    Перехватывает reply от модератора в хаб-группе
    и маршрутизирует ответы в оригинальные чаты.
    Обрабатывает AI-действия.
    """

    def __init__(
        self,
        config: Config,
        bot_client: TelegramClient,
        aggregator: Aggregator,
        db: Database,
        ai_assistant=None,
    ):
        self.config = config
        self.bot = bot_client
        self.aggregator = aggregator
        self.db = db
        self.ai_assistant = ai_assistant

    async def start(self):
        """Зарегистрировать обработчик ответов в хабе."""
        self.bot.add_event_handler(
            self._on_hub_reply,
            events.NewMessage(
                chats=[self.config.hub_chat_id],
                from_users=[self.config.moderator_user_id],
            )
        )
        logger.info("Маршрутизатор ответов запущен ✓")

    async def _on_hub_reply(self, event: events.NewMessage.Event):
        """Обработка ответа Виктории в хабе."""
        message = event.message

        # Это reply на другое сообщение?
        if not message.reply_to:
            return

        reply_to_id = message.reply_to.reply_to_msg_id
        reply_text = message.text or ""

        if not reply_text:
            return

        # ─── Проверяем: это ответ на AI-черновик? ───
        if self.ai_assistant and reply_to_id in getattr(self.ai_assistant, '_draft_hub_ids', {}):
            await self._handle_ai_reply(event, reply_to_id, reply_text)
            return

        # Проверяем: это AI-команда на ответ к оригинальному сообщению через черновик?
        if self.ai_assistant and reply_text.strip().lower() in ("!ok", "!no"):
            # Ищем, есть ли pending draft для этого reply_to_id
            if reply_to_id in self.ai_assistant.pending_drafts:
                await self._handle_ai_action_on_original(event, reply_to_id, reply_text.strip().lower())
                return

        # ─── Обычный ответ (без AI) — маршрутизация в оригинальный чат ───

        # Если reply_text == "!ok" и есть pending draft для reply_to_id → AI accept
        # Проверяем ещё раз для случая когда reply на оригинальное hub-сообщение
        if self.ai_assistant and reply_text.strip().lower() == "!ok":
            draft_text = self.ai_assistant.pending_drafts.get(reply_to_id)
            if draft_text:
                # Виктория принимает AI-черновик
                reply_text = draft_text
                await self._send_reply_to_original(event, reply_to_id, reply_text, ai_action="accepted")
                return

        if self.ai_assistant and reply_text.strip().lower() == "!no":
            if reply_to_id in self.ai_assistant.pending_drafts:
                # Виктория отклоняет AI-черновик
                record = self.db.find_by_hub_message(reply_to_id)
                original_question = ""
                if record:
                    original_question = ""  # мы не хранили текст, но у нас есть record
                await self.ai_assistant.handle_action(
                    hub_message_id=reply_to_id,
                    action="rejected",
                )
                await event.reply("❌ Черновик отклонён.", parse_mode="html")
                return

        # Стандартная маршрутизация
        await self._send_reply_to_original(event, reply_to_id, reply_text)

    async def _send_reply_to_original(
        self,
        event,
        reply_to_id: int,
        reply_text: str,
        ai_action: str | None = None,
    ):
        """Отправить ответ в оригинальный чат."""
        # Ищем оригинальное сообщение в БД
        record = self.db.find_by_hub_message(reply_to_id)
        if not record:
            logger.warning(f"Не найден маппинг для hub message #{reply_to_id}")
            await event.reply("⚠️ Не удалось найти оригинальное сообщение.")
            return

        # Получаем нужный Telethon-клиент
        client = self.aggregator.get_client_for_account(record.source_account)
        if not client:
            logger.error(f"Клиент для аккаунта '{record.source_account}' не найден")
            await event.reply(f"⚠️ Аккаунт '{record.source_account}' не подключён.")
            return

        try:
            await asyncio.sleep(self.config.reply_delay_seconds)

            # Отправляем ответ в оригинальный чат
            await client.send_message(
                entity=record.original_chat_id,
                message=reply_text,
                reply_to=record.original_message_id,
            )

            # Отмечаем как отвеченное
            self.db.mark_replied(reply_to_id)

            # AI-обучение
            if ai_action and self.ai_assistant:
                await self.ai_assistant.handle_action(
                    hub_message_id=reply_to_id,
                    action=ai_action,
                    final_text=reply_text,
                    sender_name=record.sender_name,
                    chat_name=record.chat_name,
                )

            # Если это ответ не через AI — всё равно обучаемся на реальном ответе
            elif self.ai_assistant and self.ai_assistant.enabled:
                # Был ли черновик для этого сообщения?
                draft = self.ai_assistant.pending_drafts.pop(reply_to_id, None)
                if draft:
                    action = "edited"  # Виктория написала свой текст вместо черновика
                    await self.ai_assistant.handle_action(
                        hub_message_id=reply_to_id,
                        action=action,
                        final_text=reply_text,
                        sender_name=record.sender_name,
                        chat_name=record.chat_name,
                    )
                else:
                    # Обычный ответ без AI — тоже сохраняем для обучения
                    from ai.knowledge_base import KnowledgeBase
                    if hasattr(self.ai_assistant, 'kb'):
                        self.ai_assistant.kb.save_learned_reply(
                            question_text="",  # мы не хранили текст вопроса
                            reply_text=reply_text,
                            sender_name=record.sender_name,
                            chat_name=record.chat_name,
                        )

            # Подтверждение
            ai_badge = " 🤖" if ai_action else ""
            await event.reply(
                f"✅{ai_badge} Ответ отправлен → <b>{record.chat_name}</b> "
                f"({record.source_account})",
                parse_mode="html"
            )

            logger.info(
                f"📤 Ответ отправлен: {record.chat_name} "
                f"(account: {record.source_account}, ai: {ai_action or 'manual'})"
            )

        except Exception as e:
            logger.error(f"Ошибка отправки ответа: {e}", exc_info=True)
            await event.reply(
                f"❌ Ошибка отправки: {e}\n"
                f"Чат: {record.chat_name} ({record.original_chat_id})"
            )

    async def _handle_ai_action_on_original(self, event, hub_message_id: int, command: str):
        """Обработка AI-команды (!ok / !no) на оригинальное сообщение в хабе."""
        if command == "!ok":
            draft_text = self.ai_assistant.pending_drafts.get(hub_message_id)
            if draft_text:
                await self._send_reply_to_original(event, hub_message_id, draft_text, ai_action="accepted")
            else:
                await event.reply("⚠️ Черновик не найден.")
        elif command == "!no":
            self.ai_assistant.pending_drafts.pop(hub_message_id, None)
            await self.ai_assistant.handle_action(
                hub_message_id=hub_message_id,
                action="rejected",
            )
            await event.reply("❌ Черновик отклонён.")

    async def _handle_ai_reply(self, event, draft_message_id: int, reply_text: str):
        """Обработка ответа на AI-черновик."""
        # Этот метод вызывается если reply был именно на сообщение с черновиком
        # (а не на оригинальное переслённое сообщение)
        pass  # Для MVP основная логика в _on_hub_reply
