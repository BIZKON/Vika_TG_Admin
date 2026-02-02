"""
Фильтры и классификатор приоритетов.
Определяет, нужно ли пересылать сообщение и какой у него приоритет.
"""

import re
from dataclasses import dataclass
from config import FilterConfig


@dataclass
class FilterResult:
    """Результат фильтрации сообщения."""
    should_forward: bool   # Пересылать ли
    priority: str          # 'urgent' | 'normal' | 'info'
    reason: str            # Причина решения (для логов)
    tags: list[str]        # Теги: ['вопрос', 'срочно', ...]


class MessageFilter:
    """Классифицирует и фильтрует входящие сообщения."""

    def __init__(self, config: FilterConfig):
        self.config = config
        # Компилируем паттерны для скорости
        self._urgent_re = re.compile(
            "|".join(re.escape(kw) for kw in config.urgent_keywords),
            re.IGNORECASE
        )
        self._noise_set = {p.lower().strip() for p in config.noise_patterns}
        self._question_re = re.compile(r"\?|как\s|где\s|когда\s|почему\s|зачем\s|можно\s|подскажите|помогите", re.IGNORECASE)

    def analyze(self, text: str, chat_type: str, is_reply_to_bot: bool = False) -> FilterResult:
        """
        Анализирует сообщение и решает, пересылать ли его.

        Args:
            text: Текст сообщения
            chat_type: 'group', 'supergroup', 'dm'
            is_reply_to_bot: Является ли ответом на сообщение бота

        Returns:
            FilterResult с решением
        """
        text_stripped = text.strip()
        text_lower = text_stripped.lower()
        tags = []

        # ─── Проверка на шум ───
        if text_lower in self._noise_set:
            return FilterResult(
                should_forward=False,
                priority="info",
                reason="noise_pattern",
                tags=["шум"]
            )

        # ─── Слишком короткое для группы ───
        if chat_type in ("group", "supergroup"):
            if len(text_stripped) < self.config.min_group_message_length:
                return FilterResult(
                    should_forward=False,
                    priority="info",
                    reason="too_short_for_group",
                    tags=["короткое"]
                )

        # ─── Определяем приоритет ───
        priority = "normal"

        # Срочное?
        if self._urgent_re.search(text):
            priority = "urgent"
            tags.append("🔴 срочно")

        # Вопрос?
        if self._question_re.search(text):
            tags.append("❓ вопрос")
            if priority == "normal":
                priority = "normal"  # Вопросы = нормальный приоритет

        # Благодарность / информационное
        gratitude_words = ["спасибо", "благодарю", "thanks", "thank you", "отлично", "супер"]
        if any(w in text_lower for w in gratitude_words):
            tags.append("💚 благодарность")
            if priority == "normal":
                priority = "info"

        # ─── Решение о пересылке ───

        # ЛС — всегда пересылаем
        if chat_type == "dm":
            return FilterResult(
                should_forward=self.config.forward_all_dm,
                priority=priority,
                reason="dm_message",
                tags=tags or ["💬 личное"]
            )

        # Группы — опционально только вопросы
        if chat_type in ("group", "supergroup"):
            if self.config.groups_questions_only:
                has_question = "❓ вопрос" in tags or "🔴 срочно" in tags
                return FilterResult(
                    should_forward=has_question,
                    priority=priority,
                    reason="group_questions_filter" if has_question else "not_a_question",
                    tags=tags or ["💬 группа"]
                )
            else:
                return FilterResult(
                    should_forward=True,
                    priority=priority,
                    reason="group_all_messages",
                    tags=tags or ["💬 группа"]
                )

        # Fallback
        return FilterResult(
            should_forward=True,
            priority=priority,
            reason="default",
            tags=tags
        )

    def is_noise(self, text: str) -> bool:
        """Быстрая проверка: это шум?"""
        return text.strip().lower() in self._noise_set
