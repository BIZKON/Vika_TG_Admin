"""
AI-ассистент: генерация черновиков ответов.

Использует Claude API для анализа сообщений учеников
и предложения черновиков ответов куратору Виктории.

Поток:
1. Сообщение → классификация (нужен ли ответ?)
2. Поиск по базе знаний (релевантный контекст)
3. Поиск похожих ответов Виктории (стиль)
4. Генерация черновика через Claude API
5. Отправка черновика в хаб с кнопками действий
6. Виктория: ✅ принять / ✏️ редактировать / ❌ отклонить
7. Обучение на результате
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from config import Config
from ai.knowledge_base import KnowledgeBase
from ai.prompts import (
    SYSTEM_PROMPT,
    DRAFT_REQUEST_TEMPLATE,
    SHOULD_RESPOND_PROMPT,
    CHAT_TYPE_LABELS,
    PRIORITY_LABELS,
)

logger = logging.getLogger(__name__)


@dataclass
class DraftResult:
    """Результат генерации черновика."""
    draft_text: str
    should_respond: bool
    generation_time_ms: int
    kb_articles_used: list[str]
    confidence: str  # "high", "medium", "low"


class AIAssistant:
    """
    AI-ассистент куратора.
    Генерирует черновики ответов на вопросы учеников.
    """

    def __init__(self, config: Config, kb: KnowledgeBase):
        self.config = config
        self.kb = kb
        self.api_key = config.anthropic_api_key
        self.enabled = config.ai_enabled
        self._http_client: httpx.AsyncClient | None = None

        # Трекинг: hub_message_id → draft_text (для обработки действий)
        self.pending_drafts: dict[int, str] = {}

    async def start(self):
        """Инициализация HTTP-клиента."""
        if not self.enabled:
            logger.info("🤖 AI-ассистент выключен (AI_ENABLED=false)")
            return

        if not self.api_key:
            logger.warning("⚠️  AI_ENABLED=true, но ANTHROPIC_API_KEY не указан")
            self.enabled = False
            return

        self._http_client = httpx.AsyncClient(
            base_url="https://api.anthropic.com",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=30.0,
        )
        logger.info("🤖 AI-ассистент запущен ✓")

    async def stop(self):
        """Закрыть HTTP-клиент."""
        if self._http_client:
            await self._http_client.aclose()

    # ──────────────────────────────────────────
    # Генерация черновика
    # ──────────────────────────────────────────

    async def generate_draft(
        self,
        message_text: str,
        sender_name: str,
        sender_username: str | None,
        chat_name: str,
        chat_type: str,
        priority: str,
    ) -> DraftResult | None:
        """
        Сгенерировать черновик ответа на сообщение ученика.

        Returns:
            DraftResult или None если AI выключен / не нужен ответ.
        """
        if not self.enabled or not self._http_client:
            return None

        start_time = time.monotonic()

        try:
            # ─── Шаг 1: Нужен ли ответ? ───
            should_respond = await self._classify_message(message_text, chat_type)
            if not should_respond:
                logger.debug(f"🤖 AI: ответ не требуется — {message_text[:50]}...")
                return DraftResult(
                    draft_text="",
                    should_respond=False,
                    generation_time_ms=0,
                    kb_articles_used=[],
                    confidence="high",
                )

            # ─── Шаг 2: Поиск в базе знаний ───
            kb_articles = self.kb.search(message_text, limit=3)
            kb_context = self._format_kb_context(kb_articles)
            kb_titles = [a.title for a in kb_articles]

            # ─── Шаг 3: Похожие ответы Виктории ───
            similar_replies = self.kb.find_similar_replies(message_text, limit=3)
            style_examples = self._format_style_examples(similar_replies)

            # ─── Шаг 4: Генерация черновика ───
            username_part = f" (@{sender_username})" if sender_username else ""
            chat_type_label = CHAT_TYPE_LABELS.get(chat_type, chat_type)
            priority_label = PRIORITY_LABELS.get(priority, priority)

            user_prompt = DRAFT_REQUEST_TEMPLATE.format(
                sender_name=sender_name,
                username_part=username_part,
                chat_name=chat_name,
                chat_type_label=chat_type_label,
                priority=priority_label,
                message_text=message_text,
                knowledge_context=kb_context,
                style_examples=style_examples,
            )

            draft_text = await self._call_claude(
                system_prompt=SYSTEM_PROMPT,
                user_message=user_prompt,
                max_tokens=500,
            )

            if not draft_text:
                return None

            # Определяем уверенность
            confidence = "high" if kb_articles else ("medium" if similar_replies else "low")

            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            return DraftResult(
                draft_text=draft_text.strip(),
                should_respond=True,
                generation_time_ms=elapsed_ms,
                kb_articles_used=kb_titles,
                confidence=confidence,
            )

        except Exception as e:
            logger.error(f"🤖 AI generation error: {e}", exc_info=True)
            return None

    # ──────────────────────────────────────────
    # Обработка действий Виктории
    # ──────────────────────────────────────────

    async def handle_action(
        self,
        hub_message_id: int,
        action: str,
        final_text: str = "",
        original_question: str = "",
        sender_name: str = "",
        chat_name: str = "",
    ):
        """
        Обработать действие Виктории над черновиком.

        Args:
            action: "accepted" | "edited" | "rejected"
        """
        draft_text = self.pending_drafts.pop(hub_message_id, "")

        # Логируем для аналитики
        self.kb.log_ai_action(
            hub_message_id=hub_message_id,
            draft_text=draft_text,
            action=action,
            final_text=final_text,
        )

        # Обучение: сохраняем пару вопрос-ответ
        if action in ("accepted", "edited") and original_question and final_text:
            self.kb.save_learned_reply(
                question_text=original_question,
                reply_text=final_text,
                sender_name=sender_name,
                chat_name=chat_name,
            )
            logger.info(f"🤖 AI: learned from {'accepted' if action == 'accepted' else 'edited'} reply")

    # ──────────────────────────────────────────
    # Claude API
    # ──────────────────────────────────────────

    async def _call_claude(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 500,
    ) -> str | None:
        """Вызвать Claude API и вернуть текст ответа."""
        if not self._http_client:
            return None

        try:
            response = await self._http_client.post(
                "/v1/messages",
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": user_message}
                    ],
                },
            )

            if response.status_code != 200:
                logger.error(f"Claude API error {response.status_code}: {response.text[:200]}")
                return None

            data = response.json()
            text_blocks = [
                block["text"]
                for block in data.get("content", [])
                if block.get("type") == "text"
            ]
            return "\n".join(text_blocks) if text_blocks else None

        except httpx.TimeoutException:
            logger.warning("Claude API timeout")
            return None
        except Exception as e:
            logger.error(f"Claude API call failed: {e}")
            return None

    async def _classify_message(self, message_text: str, chat_type: str) -> bool:
        """Определить, нужен ли ответ на это сообщение."""
        # Быстрые эвристики (без API)
        text_lower = message_text.strip().lower()

        # Очевидно не нужен ответ
        no_reply_patterns = [
            "спасибо", "благодарю", "ок", "хорошо", "понял",
            "понятно", "отлично", "супер", "класс", "ура",
        ]
        if text_lower in no_reply_patterns or len(text_lower) < 3:
            return False

        # Очевидно нужен ответ
        if "?" in message_text:
            return True
        question_words = ["как", "где", "когда", "почему", "можно", "подскажите", "помогите", "скажите"]
        if any(text_lower.startswith(w) for w in question_words):
            return True

        # Для ЛС — всегда генерируем
        if chat_type == "dm":
            return True

        # Для групп — используем AI для неочевидных случаев
        result = await self._call_claude(
            system_prompt="You classify messages. Respond ONLY 'YES' or 'NO'.",
            user_message=SHOULD_RESPOND_PROMPT.format(
                message_text=message_text,
                chat_type=chat_type,
            ),
            max_tokens=5,
        )

        return result is not None and "YES" in result.upper()

    # ──────────────────────────────────────────
    # Форматирование контекста
    # ──────────────────────────────────────────

    @staticmethod
    def _format_kb_context(articles: list) -> str:
        """Форматировать статьи базы знаний для промпта."""
        if not articles:
            return "(База знаний пуста или совпадений не найдено)"

        lines = []
        for i, article in enumerate(articles, 1):
            lines.append(f"### {i}. {article.title} [{article.category}]")
            lines.append(article.content)
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _format_style_examples(replies: list[dict]) -> str:
        """Форматировать примеры ответов Виктории для промпта."""
        if not replies:
            return "(Примеров пока нет — отвечай в дружелюбном профессиональном тоне)"

        lines = []
        for i, r in enumerate(replies, 1):
            q = r.get("question_text", "")[:100]
            a = r.get("reply_text", "")[:200]
            lines.append(f"**Вопрос {i}:** {q}")
            lines.append(f"**Ответ Виктории:** {a}")
            lines.append("")
        return "\n".join(lines)


# ──────────────────────────────────────────
# Форматирование черновика для хаб-группы
# ──────────────────────────────────────────

CONFIDENCE_EMOJI = {
    "high": "🟢",
    "medium": "🟡",
    "low": "🔴",
}

CONFIDENCE_LABEL = {
    "high": "высокая (есть в базе знаний)",
    "medium": "средняя (есть похожие ответы)",
    "low": "низкая (генерация с нуля)",
}


def format_ai_draft_message(draft: DraftResult, hub_message_id: int) -> str:
    """Форматировать черновик AI для отправки в хаб."""
    confidence_emoji = CONFIDENCE_EMOJI.get(draft.confidence, "⚪")
    confidence_label = CONFIDENCE_LABEL.get(draft.confidence, "")

    kb_info = ""
    if draft.kb_articles_used:
        kb_info = "\n📚 Источники: " + ", ".join(draft.kb_articles_used[:3])

    return (
        f"🤖 <b>AI-черновик</b> ({draft.generation_time_ms}мс)\n"
        f"{confidence_emoji} Уверенность: {confidence_label}\n"
        f"{kb_info}\n"
        f"\n"
        f"<blockquote>{draft.draft_text}</blockquote>\n"
        f"\n"
        f"<b>Действия:</b>\n"
        f"  ✅ Reply <code>!ok</code> — отправить как есть\n"
        f"  ✏️ Reply с вашим текстом — отправить ваш вариант\n"
        f"  ❌ Reply <code>!no</code> — отклонить черновик"
    )
