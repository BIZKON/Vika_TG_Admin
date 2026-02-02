# Деплой Vika TG Admin на VPS

Пошаговая инструкция по запуску бота на сервере.

---

## Шаг 1: Покупка VPS

### Рекомендуемые провайдеры (Россия)

| Провайдер | Мин. тариф | Сайт |
|-----------|------------|------|
| **Timeweb Cloud** | ~300₽/мес | timeweb.cloud |
| **REG.RU** | ~400₽/мес | reg.ru |
| **Selectel** | ~500₽/мес | selectel.ru |

### Рекомендуемые провайдеры (Зарубежные)

| Провайдер | Мин. тариф | Сайт |
|-----------|------------|------|
| **Hetzner** | €4/мес | hetzner.com |
| **DigitalOcean** | $6/мес | digitalocean.com |
| **Vultr** | $6/мес | vultr.com |

### Минимальные требования

```
CPU: 1 ядро
RAM: 1 GB (лучше 2 GB)
Диск: 20 GB SSD
ОС: Ubuntu 22.04 LTS
```

### Что выбрать при заказе

1. Операционная система: **Ubuntu 22.04 LTS**
2. Локация: любая (для РФ лучше Москва/Петербург)
3. При создании вам дадут:
   - IP-адрес (например: `185.123.45.67`)
   - Пароль root или SSH-ключ

---

## Шаг 2: Подключение к серверу

### Windows

1. Скачайте [PuTTY](https://putty.org/) или используйте Windows Terminal
2. Откройте терминал и введите:

```bash
ssh root@ВАШ_IP_АДРЕС
```

3. Введите пароль (он не отображается при вводе — это нормально)

### Mac / Linux

Откройте терминал:

```bash
ssh root@ВАШ_IP_АДРЕС
```

### Первое подключение

При первом подключении спросит "Are you sure you want to continue connecting?" — напишите `yes`.

---

## Шаг 3: Настройка сервера

Выполните команды по очереди (копируйте и вставляйте):

### 3.1 Обновление системы

```bash
apt update && apt upgrade -y
```

### 3.2 Установка Python и зависимостей

```bash
apt install -y python3.11 python3.11-venv python3-pip git
```

### 3.3 Создание пользователя (безопаснее чем root)

```bash
adduser vika --disabled-password --gecos ""
usermod -aG sudo vika
```

### 3.4 Переключение на нового пользователя

```bash
su - vika
```

---

## Шаг 4: Загрузка проекта

### 4.1 Клонирование репозитория

```bash
git clone https://github.com/BIZKON/Vika_TG_Admin.git
cd Vika_TG_Admin
```

### 4.2 Создание виртуального окружения

```bash
python3.11 -m venv venv
source venv/bin/activate
```

### 4.3 Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Шаг 5: Получение API ключей

### 5.1 Telegram API (для аккаунтов)

1. Перейдите на https://my.telegram.org
2. Войдите по номеру телефона
3. Выберите "API development tools"
4. Создайте приложение (название любое)
5. Запишите **API ID** и **API Hash**

> Повторите для второго аккаунта если нужно

### 5.2 Telegram Bot Token

1. Откройте @BotFather в Telegram
2. Отправьте `/newbot`
3. Придумайте имя и username бота
4. Скопируйте токен (выглядит как `123456789:ABCdefGHI...`)

### 5.3 OpenAI API Key (для RAG)

1. Перейдите на https://platform.openai.com/api-keys
2. Создайте новый ключ
3. Скопируйте (начинается с `sk-...`)

### 5.4 Anthropic API Key (для Claude)

1. Перейдите на https://console.anthropic.com/
2. Создайте API ключ
3. Скопируйте (начинается с `sk-ant-...`)

---

## Шаг 6: Настройка конфигурации

### 6.1 Создание .env файла

```bash
nano .env
```

### 6.2 Вставьте и заполните:

```bash
# ═══════════════════════════════════════════
# TELEGRAM АККАУНТЫ
# ═══════════════════════════════════════════

# Рабочий аккаунт (основной)
ACCOUNT_WORK_API_ID=12345678
ACCOUNT_WORK_API_HASH=abcdef1234567890abcdef1234567890
ACCOUNT_WORK_PHONE=+79001234567

# Личный аккаунт (опционально, можно оставить пустым)
ACCOUNT_PERSONAL_API_ID=87654321
ACCOUNT_PERSONAL_API_HASH=fedcba0987654321fedcba0987654321
ACCOUNT_PERSONAL_PHONE=+79007654321

# ═══════════════════════════════════════════
# БОТ И ХАБ
# ═══════════════════════════════════════════

# Токен бота от @BotFather
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# ID хаб-группы (узнаете на шаге 7)
HUB_CHAT_ID=-1001234567890

# Ваш Telegram User ID (узнаете на шаге 7)
MODERATOR_USER_ID=123456789

# ═══════════════════════════════════════════
# AI НАСТРОЙКИ
# ═══════════════════════════════════════════

# Включить AI-черновики
AI_ENABLED=true

# Claude API (для генерации ответов)
ANTHROPIC_API_KEY=sk-ant-api03-xxx

# OpenAI API (для семантического поиска)
OPENAI_API_KEY=sk-xxx

# ═══════════════════════════════════════════
# ДОПОЛНИТЕЛЬНО
# ═══════════════════════════════════════════

# Задержка перед ответом (секунды, антибан)
REPLY_DELAY_SECONDS=1

# Уровень логов (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
```

### 6.3 Сохранение файла

- Нажмите `Ctrl+O` → Enter (сохранить)
- Нажмите `Ctrl+X` (выйти)

---

## Шаг 7: Первый запуск и авторизация

### 7.1 Запуск помощника настройки

```bash
python setup.py
```

Помощник проведёт вас через:
1. Авторизацию Telegram аккаунтов (придут коды)
2. Определение ID хаб-группы
3. Определение вашего User ID

### 7.2 Обновите .env

После setup.py обновите `HUB_CHAT_ID` и `MODERATOR_USER_ID`:

```bash
nano .env
```

### 7.3 Тестовый запуск

```bash
python main.py
```

Если видите:
```
INFO: Бот запущен
INFO: Аккаунт work подключен
INFO: Мониторинг запущен
```

Всё работает! Нажмите `Ctrl+C` чтобы остановить.

---

## Шаг 8: Автозапуск (systemd)

Чтобы бот работал постоянно и запускался после перезагрузки.

### 8.1 Создание сервиса

```bash
sudo nano /etc/systemd/system/vika-bot.service
```

### 8.2 Вставьте:

```ini
[Unit]
Description=Vika TG Admin Bot
After=network.target

[Service]
Type=simple
User=vika
WorkingDirectory=/home/vika/Vika_TG_Admin
Environment=PATH=/home/vika/Vika_TG_Admin/venv/bin
ExecStart=/home/vika/Vika_TG_Admin/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 8.3 Сохраните и активируйте

```bash
sudo systemctl daemon-reload
sudo systemctl enable vika-bot
sudo systemctl start vika-bot
```

### 8.4 Проверка статуса

```bash
sudo systemctl status vika-bot
```

Должно показать `Active: active (running)`.

---

## Шаг 9: Управление ботом

### Команды управления сервисом

```bash
# Посмотреть статус
sudo systemctl status vika-bot

# Перезапустить
sudo systemctl restart vika-bot

# Остановить
sudo systemctl stop vika-bot

# Посмотреть логи (последние 100 строк)
sudo journalctl -u vika-bot -n 100

# Логи в реальном времени
sudo journalctl -u vika-bot -f
```

### Обновление бота

```bash
cd /home/vika/Vika_TG_Admin
git pull
sudo systemctl restart vika-bot
```

---

## Шаг 10: Загрузка документов для RAG

### 10.1 Загрузка через SFTP

Используйте FileZilla или WinSCP:
- Хост: ваш IP
- Пользователь: vika
- Порт: 22

Загрузите PDF/DOCX файлы в:
```
/home/vika/Vika_TG_Admin/data/documents/
```

### 10.2 Или через командную строку

```bash
# С вашего компьютера
scp /путь/к/документу.pdf vika@ВАШ_IP:/home/vika/Vika_TG_Admin/data/documents/
```

### 10.3 Индексация

После загрузки файлов отправьте в хаб-группу:
```
/kb_upload
/kb_index
```

---

## Возможные проблемы

### Ошибка "Permission denied"

```bash
sudo chown -R vika:vika /home/vika/Vika_TG_Admin
```

### Ошибка "Module not found"

```bash
cd /home/vika/Vika_TG_Admin
source venv/bin/activate
pip install -r requirements.txt
```

### Telegram просит код повторно

Сессии сохраняются в `data/sessions/`. Если потеряли — удалите и авторизуйтесь заново:

```bash
rm -rf data/sessions/*
python setup.py
```

### Бот не отвечает

Проверьте логи:
```bash
sudo journalctl -u vika-bot -n 50
```

---

## Альтернатива: Docker

Если предпочитаете Docker:

```bash
# Установка Docker
curl -fsSL https://get.docker.com | sh

# Запуск
cd /home/vika/Vika_TG_Admin
docker-compose up -d

# Логи
docker-compose logs -f

# Перезапуск
docker-compose restart
```

---

## Чеклист готовности

- [ ] VPS куплен и работает
- [ ] Python 3.11 установлен
- [ ] Проект склонирован
- [ ] .env заполнен всеми ключами
- [ ] Telegram аккаунты авторизованы
- [ ] Бот добавлен в хаб-группу как админ
- [ ] Systemd сервис создан и запущен
- [ ] Документы загружены и проиндексированы

---

## Поддержка

Если что-то не работает:
1. Проверьте логи: `sudo journalctl -u vika-bot -n 100`
2. Убедитесь что .env заполнен правильно
3. Перезапустите: `sudo systemctl restart vika-bot`
