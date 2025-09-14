# Настройка Astro Bot

## Переменные окружения

Создайте файл `.env` в корне проекта со следующими переменными:

```env
# Telegram Bot
BOT_TOKEN=your_telegram_bot_token_here

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/astro_db

# AstrologyAPI
ASTROLOGY_API_USER_ID=645005
ASTROLOGY_API_KEY=f6c596e32bb8e29feebbae1c460aaf0913208c7c

# OpenRouter
OPENROUTER_API_KEY=your_openrouter_api_key_here

# RabbitMQ - ЗАМЕНИТЕ НА ПРАВИЛЬНЫЕ ДАННЫЕ
RABBITMQ_URL=amqp://username:password@31.128.40.111:5672/

# Logging
LOG_LEVEL=INFO
```

## Установка зависимостей

```bash
pip install -r requirements.txt
```

## Настройка RabbitMQ

1. Установите RabbitMQ:
   - Ubuntu/Debian: `sudo apt install rabbitmq-server`
   - macOS: `brew install rabbitmq`
   - Windows: Скачайте с https://www.rabbitmq.com/

2. Запустите RabbitMQ:
   ```bash
   sudo systemctl start rabbitmq-server  # Linux
   brew services start rabbitmq          # macOS
   ```

3. Создайте пользователя (опционально):
   ```bash
   sudo rabbitmqctl add_user astro_user password
   sudo rabbitmqctl set_permissions -p / astro_user ".*" ".*" ".*"
   ```

## Запуск

1. **Запустите воркера** (в отдельном терминале):
   ```bash
   python worker.py
   ```

2. **Запустите бота**:
   ```bash
   python main.py
   ```

## Архитектура

```
Пользователь → Telegram Bot → AstrologyAPI → База данных
                                    ↓
                              RabbitMQ Queue
                                    ↓
                              Worker → OpenRouter → Обновление БД
```

## Очереди

- `moon_predictions` - очередь для обработки предсказаний Луны

## Модели LLM

- `deepseek/deepseek-chat-v3.1:free` - бесплатная модель для анализа Луны
