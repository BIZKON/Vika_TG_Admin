"""
TG-Sync: Главный модуль запуска.

Синхронизация сообщений из нескольких Telegram-аккаунтов
в единый хаб для модератора.

Запуск: python main.py
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

from telethon import TelegramClient

from config import config
from core.storage import Database
from core.aggregator import Aggregator
from core.router import ReplyRouter
from bot.commands import BotCommands
from ai.assistant import AIAssistant
from ai.knowledge_base import KnowledgeBase


# ──────────────────────────────────────────
# Logging
# ──────────────────────────────────────────

def setup_logging():
    """Настройка логирования."""
    log_format = (
        "%(asctime)s │ %(levelname)-7s │ %(name)-20s │ %(message)s"
    )
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("data/tg-sync.log", encoding="utf-8"),
        ],
    )
    # Приглушаем логи Telethon
    logging.getLogger("telethon").setLevel(logging.WARNING)


logger = logging.getLogger("tg-sync")


# ──────────────────────────────────────────
# Main
# ──────────────────────────────────────────

async def main():
    """Основной запуск."""
    setup_logging()

    logger.info("=" * 50)
    logger.info("  TG-Sync: Запуск системы синхронизации")
    logger.info("=" * 50)

    # ─── Валидация конфигурации ───
    errors = []
    if not config.bot_token:
        errors.append("BOT_TOKEN не указан")
    if not config.hub_chat_id:
        errors.append("HUB_CHAT_ID не указан")
    if not config.moderator_user_id:
        errors.append("MODERATOR_USER_ID не указан")

    has_accounts = False
    for acc in config.accounts:
        if acc.api_id and acc.api_hash:
            has_accounts = True
            break

    if not has_accounts:
        errors.append("Нет ни одного настроенного аккаунта")

    if errors:
        for err in errors:
            logger.error(f"❌ {err}")
        logger.error("Проверьте файл .env и заполните обязательные поля.")
        logger.error("Шаблон: .env.example")
        sys.exit(1)

    # ─── Инициализация компонентов ───

    # 1. База данных
    db = Database(config.db_path)
    logger.info(f"📦 База данных: {config.db_path}")

    # 2. AI: база знаний + ассистент
    kb = KnowledgeBase(config.db_path)
    ai_assistant = AIAssistant(config, kb)
    await ai_assistant.start()

    if config.ai_enabled:
        logger.info(f"🤖 AI-ассистент: включён")
    else:
        logger.info(f"🤖 AI-ассистент: выключен (включить: AI_ENABLED=true в .env)")

    # 3. Бот-клиент (через Bot API token)
    bot = TelegramClient(
        "data/sessions/bot",
        config.account_work.api_id,  # api_id можно любой
        config.account_work.api_hash,
    )
    await bot.start(bot_token=config.bot_token)
    bot_me = await bot.get_me()
    logger.info(f"🤖 Бот подключён: @{bot_me.username}")

    # 4. Агрегатор (слушатели аккаунтов) + AI
    aggregator = Aggregator(config, bot, db, ai_assistant=ai_assistant)
    await aggregator.start()

    # 5. Маршрутизатор ответов + AI
    router = ReplyRouter(config, bot, aggregator, db, ai_assistant=ai_assistant)
    await router.start()

    # 6. Команды бота + AI + KB
    commands = BotCommands(config, bot, db, ai_assistant=ai_assistant, kb=kb)
    await commands.start()

    # ─── Отправляем приветствие в хаб ───
    active_accounts = len(aggregator.listeners)
    ai_status = "🟢 вкл" if config.ai_enabled else "🔴 выкл"
    kb_count = len(kb.get_all_articles())

    await bot.send_message(
        config.hub_chat_id,
        f"🟢 <b>TG-Sync запущен</b>\n\n"
        f"📡 Активных аккаунтов: <b>{active_accounts}</b>\n"
        f"🤖 AI-ассистент: <b>{ai_status}</b>\n"
        f"📚 Статей в базе знаний: <b>{kb_count}</b>\n"
        f"🤖 Бот: @{bot_me.username}\n\n"
        f"Отправьте /help для списка команд.",
        parse_mode="html",
    )

    logger.info("✅ Система полностью запущена!")
    logger.info("Для остановки: Ctrl+C")

    # ─── Держим процесс живым ───
    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Получен сигнал завершения...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # Windows
            signal.signal(sig, lambda s, f: handle_signal())

    await stop_event.wait()

    # ─── Graceful shutdown ───
    logger.info("Завершение работы...")

    await bot.send_message(
        config.hub_chat_id,
        "🔴 <b>TG-Sync остановлен</b>",
        parse_mode="html",
    )

    await aggregator.stop()
    await ai_assistant.stop()
    await bot.disconnect()

    logger.info("👋 TG-Sync остановлен. До встречи!")


if __name__ == "__main__":
    asyncio.run(main())
