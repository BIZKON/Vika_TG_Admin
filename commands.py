"""
Бот-интерфейс для Виктории.
Команды управления: /status, /mute, /unmute, /sources, /stats, /help
Команды AI: /ai, /ai_on, /ai_off, /ai_stats, /kb_add, /kb_list, /kb_del
"""

import logging

from telethon import TelegramClient, events

from config import Config
from core.storage import Database
from core.formatter import format_status_message, format_sources_list

logger = logging.getLogger(__name__)


class BotCommands:
    """Обработчик команд бота в хаб-группе."""

    def __init__(self, config: Config, bot_client: TelegramClient, db: Database, ai_assistant=None, kb=None):
        self.config = config
        self.bot = bot_client
        self.db = db
        self.ai = ai_assistant
        self.kb = kb

    async def start(self):
        """Зарегистрировать обработчики команд."""
        # Все команды только от модератора в хабе
        base_filter = events.NewMessage(
            chats=[self.config.hub_chat_id],
            from_users=[self.config.moderator_user_id],
        )

        self.bot.add_event_handler(self._cmd_help, events.NewMessage(pattern=r"/help", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_status, events.NewMessage(pattern=r"/status", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_stats, events.NewMessage(pattern=r"/stats", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_sources, events.NewMessage(pattern=r"/sources", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_mute, events.NewMessage(pattern=r"/mute", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_unmute, events.NewMessage(pattern=r"/unmute", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_unreplied, events.NewMessage(pattern=r"/unreplied", chats=[self.config.hub_chat_id]))

        # AI commands
        self.bot.add_event_handler(self._cmd_ai, events.NewMessage(pattern=r"/ai$", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_ai_on, events.NewMessage(pattern=r"/ai_on", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_ai_off, events.NewMessage(pattern=r"/ai_off", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_ai_stats, events.NewMessage(pattern=r"/ai_stats", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_kb_add, events.NewMessage(pattern=r"/kb_add", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_kb_list, events.NewMessage(pattern=r"/kb_list", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_kb_del, events.NewMessage(pattern=r"/kb_del", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_kb_search, events.NewMessage(pattern=r"/kb_search", chats=[self.config.hub_chat_id]))

        # Vector Store commands
        self.bot.add_event_handler(self._cmd_kb_index, events.NewMessage(pattern=r"/kb_index", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_kb_upload, events.NewMessage(pattern=r"/kb_upload", chats=[self.config.hub_chat_id]))
        self.bot.add_event_handler(self._cmd_kb_vstats, events.NewMessage(pattern=r"/kb_vstats", chats=[self.config.hub_chat_id]))

        logger.info("Команды бота зарегистрированы ✓")

    async def _cmd_help(self, event):
        """Справка по командам."""
        ai_status = "🟢 вкл" if (self.ai and self.ai.enabled) else "🔴 выкл"
        help_text = f"""
🤖 <b>Команды модератора</b>

📊 <b>Информация:</b>
  /status — Сводка: неотвеченные + статистика
  /stats — Подробная статистика за 7 дней
  /unreplied — Список неотвеченных сообщений
  /sources — Список отслеживаемых чатов

🔇 <b>Управление:</b>
  /mute [chat_id] — Приостановить пересылку из чата
  /unmute [chat_id] — Возобновить пересылку

🤖 <b>AI-ассистент</b> (сейчас: {ai_status}):
  /ai — Статус AI-ассистента
  /ai_on — Включить AI-черновики
  /ai_off — Выключить AI-черновики
  /ai_stats — Статистика AI (точность, скорость)

📚 <b>База знаний:</b>
  /kb_list — Показать все статьи
  /kb_add [категория] [заголовок] | [текст]
  /kb_del [id] — Удалить статью
  /kb_search [запрос] — Семантический поиск

🗄️ <b>Векторный поиск (RAG):</b>
  /kb_index — Индексировать базу для поиска
  /kb_upload — Загрузить PDF/DOCX из data/documents
  /kb_vstats — Статистика VectorStore

💡 <b>Как отвечать:</b>
  • <b>Reply</b> на сообщение → ответ уходит в оригинальный чат
  • <b>Reply</b> <code>!ok</code> → отправить AI-черновик как есть
  • <b>Reply</b> <code>!no</code> → отклонить AI-черновик
  • <b>Reply</b> с вашим текстом → отправить ваш вариант

  /help — Эта справка
"""
        await event.reply(help_text.strip(), parse_mode="html")

    async def _cmd_status(self, event):
        """Сводка статуса."""
        unreplied = self.db.get_unreplied(limit=10)
        stats = self.db.get_stats(days=7)
        text = format_status_message(unreplied, stats)
        await event.reply(text, parse_mode="html")

    async def _cmd_stats(self, event):
        """Подробная статистика."""
        stats = self.db.get_stats(days=7)

        lines = [
            "📈 <b>Статистика за 7 дней</b>",
            "",
            f"  📩 Всего сообщений: <b>{stats['total_messages']}</b>",
            f"  ✅ Отвечено: <b>{stats['replied']}</b>",
            f"  ⏳ Неотвечено: <b>{stats['unreplied']}</b>",
            f"  🔴 Срочных: <b>{stats['urgent']}</b>",
            f"  📊 Процент ответов: <b>{stats['reply_rate']}</b>",
        ]

        if stats['avg_reply_minutes']:
            lines.append(f"  ⏱ Среднее время ответа: <b>{stats['avg_reply_minutes']} мин</b>")

        if stats['top_sources']:
            lines.append("")
            lines.append("<b>Топ источников:</b>")
            for i, src in enumerate(stats['top_sources'], 1):
                lines.append(f"  {i}. {src['name']} — {src['count']} сообщ.")

        await event.reply("\n".join(lines), parse_mode="html")

    async def _cmd_sources(self, event):
        """Список отслеживаемых источников."""
        muted = [m["chat_id"] for m in self.db.get_muted_chats()]
        text = format_sources_list(self.config.watched_chats, muted)
        await event.reply(text, parse_mode="html")

    async def _cmd_mute(self, event):
        """Замьютить чат."""
        parts = event.text.split()
        if len(parts) < 2:
            await event.reply(
                "⚠️ Укажите ID чата: <code>/mute -1001234567890</code>",
                parse_mode="html"
            )
            return

        try:
            chat_id = int(parts[1])
        except ValueError:
            await event.reply("⚠️ Неверный ID чата. Используйте числовой ID.")
            return

        chat_info = self.config.watched_chats.get(str(chat_id), {})
        chat_name = chat_info.get("name", f"ID {chat_id}")

        self.db.mute_chat(chat_id, chat_name)
        await event.reply(
            f"🔇 Чат <b>{chat_name}</b> замьючен.\n"
            f"Сообщения из него больше не пересылаются.\n"
            f"Снять: <code>/unmute {chat_id}</code>",
            parse_mode="html"
        )
        logger.info(f"Чат замьючен: {chat_name} ({chat_id})")

    async def _cmd_unmute(self, event):
        """Размьютить чат."""
        parts = event.text.split()
        if len(parts) < 2:
            muted = self.db.get_muted_chats()
            if muted:
                lines = ["🔇 <b>Замьюченные чаты:</b>", ""]
                for m in muted:
                    lines.append(f"  • {m['chat_name']} (ID: <code>{m['chat_id']}</code>)")
                lines.append("")
                lines.append("Снять: <code>/unmute [ID]</code>")
                await event.reply("\n".join(lines), parse_mode="html")
            else:
                await event.reply("✅ Нет замьюченных чатов.")
            return

        try:
            chat_id = int(parts[1])
        except ValueError:
            await event.reply("⚠️ Неверный ID чата.")
            return

        self.db.unmute_chat(chat_id)
        await event.reply(f"🔔 Чат <b>{chat_id}</b> размьючен.", parse_mode="html")
        logger.info(f"Чат размьючен: {chat_id}")

    async def _cmd_unreplied(self, event):
        """Список неотвеченных сообщений."""
        unreplied = self.db.get_unreplied(limit=20)

        if not unreplied:
            await event.reply("✅ Все сообщения отвечены! 🎉")
            return

        lines = [f"⏳ <b>Неотвеченных: {len(unreplied)}</b>", ""]

        from core.formatter import PRIORITY_EMOJI
        for msg in unreplied:
            p = PRIORITY_EMOJI.get(msg.priority, "⚪")
            username = f" (@{msg.sender_username})" if msg.sender_username else ""
            lines.append(
                f"{p} <b>{msg.sender_name}</b>{username}\n"
                f"   📍 {msg.chat_name} │ ⏰ {msg.timestamp[:16]}"
            )
            lines.append("")

        await event.reply("\n".join(lines), parse_mode="html")

    # ──────────────────────────────────────────
    # AI Commands
    # ──────────────────────────────────────────

    async def _cmd_ai(self, event):
        """Статус AI-ассистента."""
        if not self.ai:
            await event.reply("🤖 AI-модуль не инициализирован.\nУкажите ANTHROPIC_API_KEY в .env")
            return

        status = "🟢 <b>Включён</b>" if self.ai.enabled else "🔴 <b>Выключен</b>"
        pending = len(self.ai.pending_drafts)

        kb_count = len(self.kb.get_all_articles()) if self.kb else 0
        learned = self.kb.get_learned_count() if self.kb else 0

        lines = [
            "🤖 <b>AI-ассистент</b>",
            "",
            f"  Статус: {status}",
            f"  Ожидают решения: <b>{pending}</b> черновиков",
            f"  📚 Статей в базе знаний: <b>{kb_count}</b>",
            f"  📝 Выученных ответов: <b>{learned}</b>",
            "",
            f"  Автогенерация: {'✅' if self.config.ai_auto_draft else '❌'}",
            f"  Мин. длина сообщения: {self.config.ai_min_message_length} символов",
            f"  Только ЛС: {'✅' if self.config.ai_draft_for_dm_only else '❌'}",
            "",
            "Управление: /ai_on · /ai_off · /ai_stats",
        ]
        await event.reply("\n".join(lines), parse_mode="html")

    async def _cmd_ai_on(self, event):
        """Включить AI."""
        if not self.ai:
            await event.reply("⚠️ AI-модуль не инициализирован. Проверьте ANTHROPIC_API_KEY.")
            return
        if not self.config.anthropic_api_key:
            await event.reply("⚠️ ANTHROPIC_API_KEY не указан в .env")
            return

        self.ai.enabled = True
        self.config.ai_enabled = True
        if not self.ai._http_client:
            await self.ai.start()
        await event.reply("🟢 AI-ассистент <b>включён</b>. Черновики будут генерироваться автоматически.", parse_mode="html")
        logger.info("AI assistant enabled by moderator")

    async def _cmd_ai_off(self, event):
        """Выключить AI."""
        if self.ai:
            self.ai.enabled = False
            self.config.ai_enabled = False
        await event.reply("🔴 AI-ассистент <b>выключен</b>.", parse_mode="html")
        logger.info("AI assistant disabled by moderator")

    async def _cmd_ai_stats(self, event):
        """Статистика AI."""
        if not self.kb:
            await event.reply("⚠️ AI-модуль не инициализирован.")
            return

        stats = self.kb.get_ai_stats(days=7)

        lines = [
            "🤖 <b>Статистика AI за 7 дней</b>",
            "",
            f"  📝 Всего черновиков: <b>{stats['total_drafts']}</b>",
            f"  ✅ Принято без правок: <b>{stats['accepted']}</b> ({stats['acceptance_rate']})",
            f"  ✏️ Отредактировано: <b>{stats['edited']}</b> ({stats['edit_rate']})",
            f"  ❌ Отклонено: <b>{stats['rejected']}</b>",
            "",
            f"  ⚡ Среднее время генерации: <b>{stats['avg_generation_ms']}мс</b>",
            f"  📚 Статей в базе знаний: <b>{stats['kb_articles_count']}</b>",
            f"  📝 Выученных ответов: <b>{stats['learned_replies_count']}</b>",
        ]

        if stats['total_drafts'] > 0:
            useful = stats['accepted'] + stats['edited']
            useful_pct = useful / stats['total_drafts'] * 100
            lines.append("")
            lines.append(f"  🎯 Полезность (принято + отредактировано): <b>{useful_pct:.0f}%</b>")

        await event.reply("\n".join(lines), parse_mode="html")

    # ──────────────────────────────────────────
    # Knowledge Base Commands
    # ──────────────────────────────────────────

    async def _cmd_kb_add(self, event):
        """
        Добавить статью в базу знаний.
        Формат: /kb_add [категория] [заголовок] | [текст]
        Пример: /kb_add faq Где найти ДЗ | Домашние задания находятся в разделе "Материалы" каждого урока
        """
        if not self.kb:
            await event.reply("⚠️ AI-модуль не инициализирован.")
            return

        text = event.text.replace("/kb_add", "", 1).strip()
        if not text or "|" not in text:
            await event.reply(
                "📚 <b>Формат:</b>\n"
                "<code>/kb_add [категория] [заголовок] | [текст]</code>\n\n"
                "<b>Категории:</b> faq, instruction, link, policy\n\n"
                "<b>Примеры:</b>\n"
                "<code>/kb_add faq Где найти ДЗ | Домашние задания в разделе «Материалы» каждого урока</code>\n"
                "<code>/kb_add link Чат поддержки | Ссылка: t.me/support_chat</code>\n"
                "<code>/kb_add instruction Как сдать ДЗ | 1. Откройте урок 2. Нажмите \"Загрузить\" 3. Прикрепите файл</code>",
                parse_mode="html"
            )
            return

        header, content = text.split("|", 1)
        header_parts = header.strip().split(None, 1)

        if len(header_parts) < 2:
            await event.reply("⚠️ Укажите категорию и заголовок перед '|'")
            return

        category = header_parts[0].lower()
        title = header_parts[1].strip()
        content = content.strip()

        valid_categories = {"faq", "instruction", "link", "policy"}
        if category not in valid_categories:
            await event.reply(
                f"⚠️ Неизвестная категория: {category}\n"
                f"Доступные: {', '.join(valid_categories)}"
            )
            return

        article_id = self.kb.add_article(category, title, content)
        await event.reply(
            f"✅ Статья добавлена в базу знаний!\n\n"
            f"  📋 ID: <b>#{article_id}</b>\n"
            f"  📂 Категория: {category}\n"
            f"  📝 Заголовок: {title}\n"
            f"  📄 Текст: {content[:100]}{'...' if len(content) > 100 else ''}",
            parse_mode="html"
        )

    async def _cmd_kb_list(self, event):
        """Показать все статьи базы знаний."""
        if not self.kb:
            await event.reply("⚠️ AI-модуль не инициализирован.")
            return

        articles = self.kb.get_all_articles()

        if not articles:
            await event.reply(
                "📚 База знаний пуста.\n\n"
                "Добавьте статьи командой:\n"
                "<code>/kb_add faq Заголовок | Текст ответа</code>",
                parse_mode="html"
            )
            return

        lines = [f"📚 <b>База знаний ({len(articles)} статей)</b>", ""]

        category_emoji = {"faq": "❓", "instruction": "📋", "link": "🔗", "policy": "📜"}
        current_category = ""

        for article in articles:
            if article.category != current_category:
                current_category = article.category
                emoji = category_emoji.get(current_category, "📄")
                lines.append(f"\n{emoji} <b>{current_category.upper()}</b>")

            used = f" (использовано: {article.usage_count})" if article.usage_count > 0 else ""
            lines.append(
                f"  #{article.id} <b>{article.title}</b>{used}\n"
                f"      {article.content[:80]}{'...' if len(article.content) > 80 else ''}"
            )

        lines.append("")
        lines.append("Удалить: <code>/kb_del [id]</code> · Поиск: <code>/kb_search [запрос]</code>")
        await event.reply("\n".join(lines), parse_mode="html")

    async def _cmd_kb_del(self, event):
        """Удалить статью из базы знаний."""
        if not self.kb:
            await event.reply("⚠️ AI-модуль не инициализирован.")
            return

        parts = event.text.split()
        if len(parts) < 2:
            await event.reply("⚠️ Укажите ID статьи: <code>/kb_del 5</code>", parse_mode="html")
            return

        try:
            article_id = int(parts[1].replace("#", ""))
        except ValueError:
            await event.reply("⚠️ Неверный ID.")
            return

        if self.kb.remove_article(article_id):
            await event.reply(f"✅ Статья #{article_id} удалена.")
        else:
            await event.reply(f"⚠️ Статья #{article_id} не найдена.")

    async def _cmd_kb_search(self, event):
        """Поиск по базе знаний."""
        if not self.kb:
            await event.reply("⚠️ AI-модуль не инициализирован.")
            return

        query = event.text.replace("/kb_search", "", 1).strip()
        if not query:
            await event.reply("⚠️ Укажите запрос: <code>/kb_search домашнее задание</code>", parse_mode="html")
            return

        articles = self.kb.search(query, limit=5)

        if not articles:
            await event.reply(f"🔍 По запросу «{query}» ничего не найдено.")
            return

        lines = [f"🔍 <b>Результаты поиска: «{query}»</b>", ""]

        for article in articles:
            lines.append(
                f"  #{article.id} [{article.category}] <b>{article.title}</b>\n"
                f"      {article.content[:120]}{'...' if len(article.content) > 120 else ''}"
            )
            lines.append("")

        await event.reply("\n".join(lines), parse_mode="html")

    # ──────────────────────────────────────────
    # Vector Store Commands
    # ──────────────────────────────────────────

    async def _cmd_kb_index(self, event):
        """
        Синхронизировать базу знаний с VectorStore.
        Создаёт embeddings для семантического поиска.
        """
        if not self.kb:
            await event.reply("⚠️ AI-модуль не инициализирован.")
            return

        if not self.config.openai_api_key:
            await event.reply(
                "⚠️ <b>OPENAI_API_KEY не настроен</b>\n\n"
                "Для семантического поиска нужен OpenAI API.\n"
                "Добавьте в .env:\n"
                "<code>OPENAI_API_KEY=sk-...</code>",
                parse_mode="html"
            )
            return

        await event.reply("🔄 Индексирую базу знаний... Это может занять некоторое время.")

        try:
            result = self.kb.sync_to_vector_store()

            if "error" in result:
                await event.reply(f"❌ Ошибка: {result['error']}")
            else:
                await event.reply(
                    f"✅ <b>Индексация завершена!</b>\n\n"
                    f"  📚 Проиндексировано: <b>{result['synced']}</b> статей\n"
                    f"  🔍 Теперь поиск работает семантически!",
                    parse_mode="html"
                )
                logger.info(f"KB indexed: {result['synced']} articles")
        except Exception as e:
            logger.error(f"KB index error: {e}")
            await event.reply(f"❌ Ошибка индексации: {e}")

    async def _cmd_kb_upload(self, event):
        """
        Загрузить документы из папки data/documents в базу знаний.
        Поддерживает PDF, DOCX, TXT, MD файлы.
        """
        if not self.kb:
            await event.reply("⚠️ AI-модуль не инициализирован.")
            return

        if not self.config.openai_api_key:
            await event.reply(
                "⚠️ <b>OPENAI_API_KEY не настроен</b>\n\n"
                "Для загрузки документов нужен OpenAI API.\n"
                "Добавьте в .env:\n"
                "<code>OPENAI_API_KEY=sk-...</code>",
                parse_mode="html"
            )
            return

        await event.reply(
            "🔄 Загружаю документы из <code>data/documents/</code>...\n"
            "Поддерживаемые форматы: PDF, DOCX, TXT, MD",
            parse_mode="html"
        )

        try:
            result = self.kb.load_documents_to_vector_store()

            if "error" in result:
                await event.reply(f"❌ Ошибка: {result['error']}")
            elif result.get("loaded", 0) == 0:
                await event.reply(
                    "📁 Документы не найдены.\n\n"
                    "Положите файлы (PDF, DOCX, TXT) в папку:\n"
                    "<code>data/documents/</code>\n\n"
                    "Затем выполните <code>/kb_upload</code> снова.",
                    parse_mode="html"
                )
            else:
                await event.reply(
                    f"✅ <b>Документы загружены!</b>\n\n"
                    f"  📄 Загружено: <b>{result['loaded']}</b> чанков\n"
                    f"  🔍 Контент доступен для поиска",
                    parse_mode="html"
                )
                logger.info(f"Documents loaded: {result['loaded']} chunks")
        except Exception as e:
            logger.error(f"KB upload error: {e}")
            await event.reply(f"❌ Ошибка загрузки: {e}")

    async def _cmd_kb_vstats(self, event):
        """Статистика VectorStore."""
        if not self.kb:
            await event.reply("⚠️ AI-модуль не инициализирован.")
            return

        stats = self.kb.get_vector_stats()

        if "error" in stats:
            await event.reply(
                f"⚠️ VectorStore недоступен: {stats['error']}\n\n"
                "Настройте OPENAI_API_KEY и выполните /kb_index",
                parse_mode="html"
            )
            return

        lines = [
            "🗄️ <b>Статистика VectorStore</b>",
            "",
            f"  📚 Всего документов: <b>{stats['total_documents']}</b>",
            f"  🤖 Модель embeddings: <b>{stats['embedding_model']}</b>",
            f"  📁 Путь к БД: <code>{stats['db_path']}</code>",
        ]

        if stats.get("by_category"):
            lines.append("")
            lines.append("  <b>По категориям:</b>")
            for cat, count in stats["by_category"].items():
                lines.append(f"    • {cat}: {count}")

        if stats.get("by_source"):
            lines.append("")
            lines.append("  <b>По источникам:</b>")
            for src, count in stats["by_source"].items():
                lines.append(f"    • {src}: {count}")

        await event.reply("\n".join(lines), parse_mode="html")
