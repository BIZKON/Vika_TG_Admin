"""
TG-Hub V2: Команды бота.
"""

import logging
from datetime import datetime

from aiogram import Router, Bot, F
from aiogram.types import Message
from aiogram.filters import Command, CommandStart

from config import config
from core.storage import Database
from core.formatter import format_stats

logger = logging.getLogger(__name__)

router = Router(name="commands")


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Команда /start."""
    await message.answer(
        "👋 <b>TG-Hub V2</b>\n\n"
        "Единый хаб для управления сообщениями из:\n"
        "• 💬 Telegram Business (личка)\n"
        "• 👥 Группы учеников и кураторов\n"
        "• 📚 GetCourse (домашние задания)\n\n"
        "Используйте /help для списка команд.",
        parse_mode="html",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help."""
    help_text = """📚 <b>Команды TG-Hub V2</b>

<b>Основные:</b>
/status — Статус системы
/stats — Статистика сообщений

<b>Модерация:</b>
/mute &lt;chat_id&gt; — Замьютить чат
/unmute &lt;chat_id&gt; — Размьютить чат
/muted — Список замьюченных

<b>AI и база знаний:</b>
/search &lt;запрос&gt; — Поиск в базе знаний
/draft — Сгенерировать черновик (reply)

<b>GetCourse:</b>
/gc_status — Статус интеграции

<b>Как работать:</b>
1. Сообщения из всех источников приходят сюда
2. Отвечайте reply на сообщение — ответ уйдёт отправителю
3. AI может автоматически генерировать черновики"""

    await message.answer(help_text, parse_mode="html")


@router.message(Command("status"))
async def cmd_status(message: Message, db: Database):
    """Команда /status — статус системы."""
    from bot.handlers.business import active_connections

    # Собираем информацию
    business_count = len(active_connections)
    groups_count = len(config.monitored_groups)
    getcourse_status = "🟢 вкл" if config.getcourse.enabled else "🔴 выкл"
    ai_status = "🟢 вкл" if config.ai_enabled else "🔴 выкл"
    muted_count = len(db.get_muted_chats())

    status_text = f"""📊 <b>Статус TG-Hub V2</b>

<b>Источники:</b>
├ 📱 Business аккаунтов: <b>{business_count}</b>
├ 👥 Мониторируемых групп: <b>{groups_count}</b>
└ 📚 GetCourse: <b>{getcourse_status}</b>

<b>Группы:</b>"""

    for g in config.monitored_groups:
        status_text += f"\n├ {g.name}: <code>{g.chat_id}</code>"

    status_text += f"""

<b>AI:</b> {ai_status}
<b>Замьючено чатов:</b> {muted_count}

🕐 Время сервера: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

    await message.answer(status_text, parse_mode="html")


@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database):
    """Команда /stats — статистика."""
    stats = db.get_today_stats()
    stats_text = format_stats(stats)
    await message.answer(stats_text, parse_mode="html")


@router.message(Command("mute"))
async def cmd_mute(message: Message, db: Database):
    """Команда /mute <chat_id> — замьютить чат."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "❌ Укажите chat_id\n"
            "Пример: <code>/mute -100123456789</code>",
            parse_mode="html",
        )
        return

    try:
        chat_id = int(args[1])
        db.mute_chat(chat_id)
        await message.answer(f"🔇 Чат <code>{chat_id}</code> замьючен", parse_mode="html")
        logger.info(f"Chat {chat_id} muted")
    except ValueError:
        await message.answer("❌ Неверный формат chat_id")


@router.message(Command("unmute"))
async def cmd_unmute(message: Message, db: Database):
    """Команда /unmute <chat_id> — размьютить чат."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "❌ Укажите chat_id\n"
            "Пример: <code>/unmute -100123456789</code>",
            parse_mode="html",
        )
        return

    try:
        chat_id = int(args[1])
        db.unmute_chat(chat_id)
        await message.answer(f"🔊 Чат <code>{chat_id}</code> размьючен", parse_mode="html")
        logger.info(f"Chat {chat_id} unmuted")
    except ValueError:
        await message.answer("❌ Неверный формат chat_id")


@router.message(Command("muted"))
async def cmd_muted(message: Message, db: Database):
    """Команда /muted — список замьюченных чатов."""
    muted = db.get_muted_chats()

    if not muted:
        await message.answer("📭 Нет замьюченных чатов")
        return

    text = "🔇 <b>Замьюченные чаты:</b>\n\n"
    for chat_id in muted:
        text += f"• <code>{chat_id}</code>\n"

    await message.answer(text, parse_mode="html")


@router.message(Command("search"))
async def cmd_search(message: Message):
    """Команда /search <запрос> — поиск в базе знаний."""
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "❌ Укажите поисковый запрос\n"
            "Пример: <code>/search как оплатить курс</code>",
            parse_mode="html",
        )
        return

    query = args[1]

    # TODO: Интеграция с RAG системой
    await message.answer(
        f"🔍 Поиск: <i>{query}</i>\n\n"
        "⏳ Функция в разработке...",
        parse_mode="html",
    )


@router.message(Command("draft"))
async def cmd_draft(message: Message):
    """Команда /draft — сгенерировать черновик (используется как reply)."""
    if not message.reply_to_message:
        await message.answer(
            "❌ Используйте эту команду как ответ на сообщение\n"
            "Reply на сообщение и напишите /draft",
        )
        return

    # TODO: Интеграция с AI
    await message.answer(
        "🤖 Генерация черновика...\n\n"
        "⏳ Функция в разработке...",
    )


@router.message(Command("gc_status"))
async def cmd_gc_status(message: Message):
    """Команда /gc_status — статус GetCourse интеграции."""
    if not config.getcourse.enabled:
        await message.answer(
            "📚 <b>GetCourse интеграция</b>\n\n"
            "Статус: 🔴 <b>Выключена</b>\n\n"
            "Для включения установите GETCOURSE_ENABLED=true в .env",
            parse_mode="html",
        )
        return

    webhook_url = f"{config.webhook_server.public_url}/webhook/getcourse"

    await message.answer(
        f"📚 <b>GetCourse интеграция</b>\n\n"
        f"Статус: 🟢 <b>Включена</b>\n"
        f"Аккаунт: <code>{config.getcourse.account_name}</code>\n\n"
        f"<b>Webhook URL для GetCourse:</b>\n"
        f"<code>{webhook_url}</code>\n\n"
        f"Добавьте этот URL в процесс GetCourse с операцией «Вызвать URL»",
        parse_mode="html",
    )
