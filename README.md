# 🏠 TG-Hub V2

**Единый хаб для модератора курсов: все сообщения из Telegram и GetCourse в одном месте.**

---

## Как это работает

```
┌─────────────────────────────────────────────────────────────────┐
│                          ИСТОЧНИКИ                               │
├──────────────────┬───────────────────┬───────────────────────────┤
│  📱 TG Business  │  👥 TG Группы     │  📚 GetCourse             │
│  (Premium)       │  (ученики/кураторы)│  (домашние задания)      │
│                  │                    │                          │
│  Личные чаты     │  Вопросы в группах │  ДЗ, комментарии         │
└────────┬─────────┴─────────┬──────────┴────────────┬─────────────┘
         │                   │                       │
         └───────────────────┴───────────┬───────────┘
                                         │
                                 ┌───────▼───────┐
                                 │   🏠 ХАБ      │
                                 │  (Telegram)   │
                                 │               │
                                 │  Виктория     │
                                 │  читает и     │
                                 │  отвечает     │
                                 └───────────────┘
```

## Возможности

- ✅ **Telegram Business API** — личные сообщения через Premium аккаунт
- ✅ **Мониторинг групп** — сообщения из групп учеников и кураторов
- ✅ **GetCourse интеграция** — домашние задания и комментарии через webhook
- ✅ **RAG система** — AI-черновики ответов на базе LanceDB + Claude
- ✅ **Приоритизация** — срочные вопросы выделяются
- ✅ **Статистика** — сколько сообщений, откуда, сколько отвечено

---

## Требования

- Python 3.11+
- **Telegram Premium** на рабочем аккаунте (для Business API)
- Telegram бот ([@BotFather](https://t.me/BotFather))
- VPS с публичным IP (для GetCourse webhooks)
- GetCourse аккаунт (опционально)

---

## Быстрый старт

### 1. Установка

```bash
git clone <repo>
cd Vika_TG_Admin
pip install -r requirements.txt
cp .env.example .env
nano .env
```

### 2. Настройка .env

```bash
# Обязательно:
BOT_TOKEN=7123456789:AAH...          # От @BotFather
HUB_CHAT_ID=-100...                   # ID хаб-группы
MODERATOR_USER_ID=123456789           # Ваш User ID

# Группы для мониторинга:
GROUP_STUDENTS_ID=-100...             # Группа учеников
GROUP_CURATORS_ID=-100...             # Группа кураторов

# GetCourse (опционально):
GETCOURSE_ENABLED=true
GETCOURSE_WEBHOOK_SECRET=your_secret
WEBHOOK_URL=https://your-server.com

# AI (опционально):
AI_ENABLED=true
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

### 3. Подготовка Telegram

1. **Создайте хаб-группу** и добавьте туда бота
2. **Добавьте бота** в группы учеников и кураторов
3. **Подключите Business API**:
   - Telegram → Настройки → Telegram Business → Чат-боты
   - Выберите вашего бота

### 4. Запуск

```bash
python main.py
```

---

## Команды бота

| Команда | Описание |
|---------|----------|
| `/help` | Список команд |
| `/status` | Статус системы |
| `/stats` | Статистика за день |
| `/mute <chat_id>` | Замьютить чат |
| `/unmute <chat_id>` | Размьютить чат |
| `/gc_status` | Статус GetCourse |
| `/search <запрос>` | Поиск в базе знаний |

---

## GetCourse интеграция

### Настройка в GetCourse

1. **CRM → Процессы → Создать процесс**
2. **Добавить блок "Операция" → "Вызвать URL"**
3. **Настроить:**
   ```
   URL: https://your-server.com/webhook/getcourse
   Метод: POST

   Параметры:
   - user_email: {object.email}
   - user_name: {object.name}
   - course_title: {object.course_title}
   - lesson_title: {object.lesson_title}
   - task_text: {object.task_text}
   - secret: your_webhook_secret
   ```

4. **Настроить триггер** — например, при добавлении комментария к уроку

---

## Структура проекта

```
Vika_TG_Admin/
├── main.py                 # Точка входа
├── config.py               # Конфигурация
├── requirements.txt        # Зависимости
│
├── bot/
│   └── handlers/
│       ├── business.py     # Telegram Business API
│       ├── groups.py       # Сообщения из групп
│       └── commands.py     # Команды бота
│
├── webhooks/
│   └── server.py           # FastAPI для GetCourse
│
├── core/
│   ├── models.py           # Модели данных
│   ├── storage.py          # SQLite база
│   └── formatter.py        # Форматирование сообщений
│
├── ai/                     # RAG система (опционально)
│
└── data/
    ├── messages.db         # База данных
    └── tg-hub.log          # Логи
```

---

## Деплой на VPS

См. подробную инструкцию: [DEPLOY_TIMEWEB.md](DEPLOY_TIMEWEB.md)

Краткий чеклист:
1. Ubuntu 22.04+ VPS
2. Python 3.11+
3. Nginx + SSL (для GetCourse webhooks)
4. Systemd service для автозапуска

---

## Безопасность

⚠️ **Важно:**

- Никогда не коммитьте `.env` в git
- Используйте надёжный `GETCOURSE_WEBHOOK_SECRET`
- Настройте firewall на VPS
- Используйте HTTPS для webhooks

---

## FAQ

**Q: Почему нужен Telegram Premium?**
A: Без Premium нельзя использовать Business API для получения личных сообщений. Это официальный способ, который не приводит к бану аккаунта.

**Q: Можно ли без GetCourse?**
A: Да, установите `GETCOURSE_ENABLED=false`. Система будет работать только с Telegram.

**Q: Сколько стоит?**
A: Telegram Premium ~299₽/мес. GetCourse — зависит от тарифа. OpenAI/Anthropic API — pay-as-you-go.

---

## Лицензия

MIT
