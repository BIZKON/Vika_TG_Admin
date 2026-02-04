#!/usr/bin/env python3
"""
Парсер Q&A из экспорта Telegram чата.
Извлекает пары "вопрос ученика → ответ куратора" для RAG базы знаний.

Использование:
    python parse_chat_qa.py result.json output_qa.jsonl
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════
# НАСТРОЙКИ: Список кураторов
# ═══════════════════════════════════════════

CURATOR_NAMES = [
    "Виктория Сырова",
    "Виктория Лебедева",
    "Марина Корица",
    "Вика @wowsweets.ru",  # Виктория в другом формате
]

# Также считаем куратором сообщения с author="Куратор"
CURATOR_AUTHOR = "Куратор"

# Минимальная длина вопроса (символов)
MIN_QUESTION_LENGTH = 15

# Минимальная длина ответа (символов)
MIN_ANSWER_LENGTH = 20


# ═══════════════════════════════════════════
# ФУНКЦИИ
# ═══════════════════════════════════════════

def is_curator(message: dict) -> bool:
    """Проверить, является ли автор сообщения куратором."""
    # Проверяем по имени
    from_name = message.get("from", "")
    for curator in CURATOR_NAMES:
        if curator.lower() in from_name.lower():
            return True

    # Проверяем по полю author (для сообщений от канала)
    author = message.get("author", "")
    if author == CURATOR_AUTHOR:
        return True

    return False


def extract_text(message: dict) -> str:
    """Извлечь текст из сообщения."""
    text = message.get("text", "")

    # Текст может быть строкой или списком
    if isinstance(text, list):
        parts = []
        for item in text:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", ""))
        return "".join(parts)

    return text


def is_question(text: str) -> bool:
    """Определить, является ли текст вопросом."""
    if not text or len(text) < MIN_QUESTION_LENGTH:
        return False

    # Содержит знак вопроса
    if "?" in text:
        return True

    # Начинается с вопросительных слов
    question_starters = [
        "как ", "где ", "когда ", "почему ", "зачем ", "кто ", "что ",
        "можно ли", "подскажите", "посоветуйте", "помогите",
        "а если", "а как", "а где", "а кто",
        "скажите", "объясните", "расскажите",
    ]
    text_lower = text.lower().strip()
    for starter in question_starters:
        if text_lower.startswith(starter):
            return True

    return False


def clean_text(text: str) -> str:
    """Очистить текст от лишних символов."""
    # Убираем множественные переносы строк
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Убираем лишние пробелы
    text = re.sub(r' {2,}', ' ', text)
    # Убираем пробелы в начале и конце
    text = text.strip()
    return text


def parse_chat(input_file: str) -> list[dict]:
    """
    Парсить чат и извлечь пары Q&A.

    Returns:
        Список словарей с парами вопрос-ответ
    """
    print(f"📂 Загрузка файла: {input_file}")

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    messages = data.get("messages", [])
    print(f"📊 Всего сообщений: {len(messages):,}")

    # Создаём индекс сообщений по ID для быстрого поиска
    msg_by_id = {msg.get("id"): msg for msg in messages if msg.get("type") == "message"}

    # Счётчики
    total_questions = 0
    curator_answers = 0
    qa_pairs = []

    # Находим ответы кураторов
    for msg in messages:
        if msg.get("type") != "message":
            continue

        # Проверяем, является ли это ответом куратора
        if not is_curator(msg):
            continue

        # Получаем ID сообщения, на которое отвечает куратор
        reply_to_id = msg.get("reply_to_message_id")
        if not reply_to_id:
            continue

        # Находим оригинальный вопрос
        original_msg = msg_by_id.get(reply_to_id)
        if not original_msg:
            continue

        # Проверяем, что оригинал — это вопрос (не от куратора)
        if is_curator(original_msg):
            continue

        question_text = extract_text(original_msg)
        answer_text = extract_text(msg)

        # Фильтруем по длине
        if len(question_text) < MIN_QUESTION_LENGTH:
            continue
        if len(answer_text) < MIN_ANSWER_LENGTH:
            continue

        # Проверяем, что это похоже на вопрос
        if not is_question(question_text):
            continue

        # Очищаем тексты
        question_text = clean_text(question_text)
        answer_text = clean_text(answer_text)

        # Получаем метаданные
        question_author = original_msg.get("from", "Ученик")
        answer_author = msg.get("from", msg.get("author", "Куратор"))
        question_date = original_msg.get("date", "")
        answer_date = msg.get("date", "")

        qa_pair = {
            "question": question_text,
            "answer": answer_text,
            "question_author": question_author,
            "answer_author": answer_author,
            "question_date": question_date,
            "answer_date": answer_date,
            "question_id": original_msg.get("id"),
            "answer_id": msg.get("id"),
        }

        qa_pairs.append(qa_pair)
        curator_answers += 1

    print(f"✅ Найдено пар Q&A: {len(qa_pairs):,}")

    return qa_pairs


def save_jsonl(qa_pairs: list[dict], output_file: str):
    """Сохранить в JSONL формате."""
    with open(output_file, 'w', encoding='utf-8') as f:
        for qa in qa_pairs:
            json.dump(qa, f, ensure_ascii=False)
            f.write('\n')

    print(f"💾 Сохранено в: {output_file}")


def save_readable(qa_pairs: list[dict], output_file: str):
    """Сохранить в читаемом формате (для проверки)."""
    with open(output_file, 'w', encoding='utf-8') as f:
        for i, qa in enumerate(qa_pairs, 1):
            f.write(f"{'='*60}\n")
            f.write(f"# {i}\n")
            f.write(f"📅 {qa['question_date']}\n")
            f.write(f"❓ [{qa['question_author']}]:\n{qa['question']}\n\n")
            f.write(f"✅ [{qa['answer_author']}]:\n{qa['answer']}\n\n")

    print(f"📄 Читаемая версия: {output_file}")


def print_stats(qa_pairs: list[dict]):
    """Вывести статистику."""
    print("\n" + "="*50)
    print("📊 СТАТИСТИКА")
    print("="*50)

    # Статистика по кураторам
    curator_counts = {}
    for qa in qa_pairs:
        author = qa['answer_author']
        curator_counts[author] = curator_counts.get(author, 0) + 1

    print("\nОтветы по кураторам:")
    for curator, count in sorted(curator_counts.items(), key=lambda x: -x[1]):
        print(f"  {curator}: {count}")

    # Средняя длина
    avg_q_len = sum(len(qa['question']) for qa in qa_pairs) / len(qa_pairs) if qa_pairs else 0
    avg_a_len = sum(len(qa['answer']) for qa in qa_pairs) / len(qa_pairs) if qa_pairs else 0

    print(f"\nСредняя длина вопроса: {avg_q_len:.0f} символов")
    print(f"Средняя длина ответа: {avg_a_len:.0f} символов")


def main():
    if len(sys.argv) < 2:
        print("Использование: python parse_chat_qa.py <input.json> [output.jsonl]")
        print("\nПример:")
        print("  python parse_chat_qa.py result.json qa_pairs.jsonl")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "qa_pairs.jsonl"

    if not Path(input_file).exists():
        print(f"❌ Файл не найден: {input_file}")
        sys.exit(1)

    # Парсим чат
    qa_pairs = parse_chat(input_file)

    if not qa_pairs:
        print("⚠️ Пары Q&A не найдены. Проверьте настройки кураторов.")
        sys.exit(1)

    # Сохраняем результаты
    save_jsonl(qa_pairs, output_file)

    # Сохраняем читаемую версию
    readable_file = output_file.replace('.jsonl', '_readable.txt')
    save_readable(qa_pairs, readable_file)

    # Выводим статистику
    print_stats(qa_pairs)

    print("\n✅ Готово!")
    print(f"\nФайлы:")
    print(f"  📦 {output_file} — для загрузки в RAG")
    print(f"  📄 {readable_file} — для проверки глазами")


if __name__ == "__main__":
    main()
