"""
TG-Hub V2: Главный модуль запуска.

Единый хаб для модератора курсов:
- Telegram Business API (личные сообщения)
- Telegram группы (ученики, кураторы)
- GetCourse webhooks (домашние задания)
- RAG система для генерации ответов

Запуск: python main.py
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import config
from core.storage import Database

# ──────────────────────────────────────────
# Logging
# ──────────────────────────────────────────

def setup_logging():
    """Настройка логирования."""
    Path("data").mkdir(exist_ok=True)

    log_format = "%(asctime)s │ %(levelname)-7s │ %(name)-25s │ %(message)s"
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("data/tg-hub.log", encoding="utf-8"),
        ],
    )
    # Приглушаем логи библиотек
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)


logger = logging.getLogger("tg-hub")


# ──────────────────────────────────────────
# Main
# ──────────────────────────────────────────

async def main():
    """Основной запуск."""
    setup_logging()

    logger.info("=" * 55)
    logger.info("  TG-Hub V2: Запуск системы")
    logger.info("=" * 55)

    # ─── Валидация конфигурации ───
    errors = config.validate()
    if errors:
        for err in errors:
            logger.error(f"❌ {err}")
        logger.error("Проверьте файл .env")
        sys.exit(1)

    # ─── Инициализация компонентов ───

    # 1. База данных
    db = Database(config.db_path)
    logger.info(f"📦 База данных: {config.db_path}")

    # 2. Telegram Bot
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Middleware для передачи db во все хендлеры
    @dp.update.outer_middleware()
    async def db_middleware(handler, event, data):
        data["db"] = db
        return await handler(event, data)

    # 3. Подключаем роутеры
    from bot.handlers import business, groups, commands

    dp.include_router(business.router)
    dp.include_router(groups.router)
    dp.include_router(commands.router)

    logger.info("🤖 Telegram Bot роутеры подключены")

    # 4. Получаем информацию о боте
    bot_info = await bot.get_me()
    logger.info(f"🤖 Бот: @{bot_info.username} (ID: {bot_info.id})")

    # 5. Webhook сервер для GetCourse
    webhook_task = None
    if config.getcourse.enabled:
        from webhooks.server import run_webhook_server, set_hub_callback

        # Callback для отправки GetCourse событий в хаб
        async def hub_callback(incoming):
            from core.formatter import format_getcourse_message
            from core.models import MessageSource, HubMessage
            from datetime import datetime

            hub_text = format_getcourse_message(incoming)
            hub_msg = await bot.send_message(config.hub_chat_id, hub_text)

            # Сохраняем в БД
            hub_record = HubMessage(
                hub_message_id=hub_msg.message_id,
                source=MessageSource.GETCOURSE,
                sender_name=incoming.sender_name,
                sender_username=None,
                chat_name="GetCourse",
                priority=incoming.priority.value,
                created_at=datetime.now().isoformat(),
            )
            db.save_hub_message(hub_record)
            db.increment_stat(MessageSource.GETCOURSE)

            logger.info(f"📚 GetCourse → Hub #{hub_msg.message_id}")

        set_hub_callback(hub_callback)
        webhook_task = asyncio.create_task(run_webhook_server())
        logger.info(
            f"📚 GetCourse webhook: "
            f"http://{config.webhook_server.host}:{config.webhook_server.port}"
        )

    # ─── Приветственное сообщение ───
    groups_info = ", ".join([g.name for g in config.monitored_groups]) or "не настроены"
    gc_status = "🟢 вкл" if config.getcourse.enabled else "🔴 выкл"
    ai_status = "🟢 вкл" if config.ai_enabled else "🔴 выкл"

    await bot.send_message(
        config.hub_chat_id,
        f"🟢 <b>TG-Hub V2 запущен!</b>\n\n"
        f"<b>Источники:</b>\n"
        f"├ 📱 Business API: ожидание подключения\n"
        f"├ 👥 Группы: {groups_info}\n"
        f"└ 📚 GetCourse: {gc_status}\n\n"
        f"<b>AI:</b> {ai_status}\n"
        f"<b>Бот:</b> @{bot_info.username}\n\n"
        f"Отправьте /help для списка команд.",
    )

    logger.info("✅ Система полностью запущена!")
    logger.info("Для остановки: Ctrl+C")

    # ─── Graceful shutdown ───
    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Получен сигнал завершения...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            signal.signal(sig, lambda s, f: handle_signal())

    # ─── Запуск polling ───
    try:
        # Запускаем polling в фоне
        polling_task = asyncio.create_task(
            dp.start_polling(bot, handle_signals=False)
        )

        # Ждём сигнала остановки
        await stop_event.wait()

    finally:
        logger.info("Завершение работы...")

        # Отправляем сообщение об остановке
        try:
            await bot.send_message(
                config.hub_chat_id,
                "🔴 <b>TG-Hub V2 остановлен</b>",
            )
        except:
            pass

        # Останавливаем polling
        await dp.stop_polling()

        # Останавливаем webhook сервер
        if webhook_task:
            webhook_task.cancel()
            try:
                await webhook_task
            except asyncio.CancelledError:
                pass

        # Закрываем сессию бота
        await bot.session.close()

        logger.info("👋 TG-Hub V2 остановлен. До встречи!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
