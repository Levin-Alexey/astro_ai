# Инструкция по развертыванию проекта NeyroAstro на сервере

## 📋 Содержание
- [Требования](#требования)
- [Установка зависимостей](#установка-зависимостей)
- [Настройка проекта](#настройка-проекта)
- [Запуск сервисов](#запуск-сервисов)
- [Управление процессами](#управление-процессами)
- [Мониторинг и логи](#мониторинг-и-логи)
- [Troubleshooting](#troubleshooting)

---

## 🔧 Требования

### Системные требования
- Ubuntu 20.04 LTS или выше
- Python 3.9+
- PostgreSQL 12+
- RabbitMQ
- Nginx (для webhook)
- Минимум 2GB RAM
- Минимум 10GB свободного места на диске

### Предварительная проверка
```bash
# Проверка версии Python
python3 --version

# Проверка PostgreSQL
psql --version

# Проверка RabbitMQ
systemctl status rabbitmq-server
```

---

## 📦 Установка зависимостей

### 1. Обновление системы
```bash
sudo apt update
sudo apt upgrade -y
```

### 2. Установка Python и необходимых пакетов
```bash
# Установка Python и pip
sudo apt install -y python3 python3-pip python3-venv

# Установка системных зависимостей
sudo apt install -y build-essential libpq-dev git curl
```

### 3. Установка PostgreSQL
```bash
# Установка PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Запуск PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Создание базы данных и пользователя
sudo -u postgres psql << EOF
CREATE DATABASE astro_db;
CREATE USER astro_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE astro_db TO astro_user;
\q
EOF
```

### 4. Установка RabbitMQ
```bash
# Установка RabbitMQ
sudo apt install -y rabbitmq-server

# Запуск RabbitMQ
sudo systemctl start rabbitmq-server
sudo systemctl enable rabbitmq-server

# Создание пользователя RabbitMQ
sudo rabbitmqctl add_user astro_user astro_password_123
sudo rabbitmqctl set_permissions -p / astro_user ".*" ".*" ".*"
sudo rabbitmqctl set_user_tags astro_user administrator

# Включение веб-интерфейса (опционально)
sudo rabbitmq-plugins enable rabbitmq_management
```

---

## ⚙️ Настройка проекта

### 1. Клонирование репозитория (если не сделано)
```bash
cd ~
git clone https://github.com/Levin-Alexey/astro_ai.git
cd astro_ai
```

### 2. Создание виртуального окружения
```bash
# Создание venv
python3 -m venv venv

# Активация venv
source venv/bin/activate

# Обновление pip
pip install --upgrade pip
```

### 3. Установка зависимостей Python
```bash
# Установка всех зависимостей из requirements.txt
pip install -r requirements.txt
```

### 4. Настройка .env файла
```bash
# Создание .env файла
cp .env.example .env  # если есть example файл

# Редактирование .env
nano .env
```

**Пример .env файла:**
```env
# Telegram Bot
BOT_TOKEN=your_telegram_bot_token_here

# Database
DATABASE_URL=postgresql+asyncpg://astro_user:your_secure_password@localhost:5432/astro_db

# RabbitMQ
RABBITMQ_URL=amqp://astro_user:astro_password_123@localhost:5672/

# OpenRouter API (для LLM)
OPENROUTER_API_KEY=your_openrouter_api_key

# YooKassa (платежи)
PAYMENT_SHOP_ID=your_shop_id
PAYMENT_SECRET_KEY=your_secret_key
PAYMENT_TEST_AMOUNT=7700
PAYMENT_CURRENCY=RUB

# AstrologyAPI
ASTROLOGY_API_USER_ID=your_user_id
ASTROLOGY_API_KEY=your_api_key

# Geocoding
GEOCODER_BASE_URL=https://nominatim.openstreetmap.org/search
GEOCODER_USER_AGENT=AstroBot/1.0 (+https://t.me/NeyroAstroBot)

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=%(asctime)s - %(levelname)s - %(message)s
```

### 5. Инициализация базы данных
```bash
# Активируем venv (если не активирован)
source venv/bin/activate

# Инициализация таблиц
python init_db.py
```

---

## 🚀 Запуск сервисов

### Вариант 1: Ручной запуск (для тестирования)

```bash
# Активация виртуального окружения
cd ~/astro_ai
source venv/bin/activate

# 1. Основной бот
python main.py &

# 2. Webhook сервер
python run_with_webhook.py &

# 3. Worker для Луны
python worker.py &

# 4. Workers для планет
python run_sun_worker.py &
python run_mercury_worker.py &
python run_venus_worker.py &
python run_mars_worker.py &
python run_planet_worker.py &

# 5. Workers для рекомендаций
python run_sun_recommendations_worker.py &
python run_mercury_recommendations_worker.py &
python run_venus_recommendations_worker.py &
python run_mars_recommendations_worker.py &

# 6. Worker для вопросов
python question_worker.py &
```

### Вариант 2: Использование astro-manager.sh

```bash
# Делаем скрипт исполняемым
chmod +x astro-manager.sh

# Запуск всех сервисов
./astro-manager.sh start

# Остановка всех сервисов
./astro-manager.sh stop

# Перезапуск всех сервисов
./astro-manager.sh restart

# Проверка статуса
./astro-manager.sh status
```

### Вариант 3: Systemd сервисы (рекомендуется для production)

#### Создание systemd сервиса для основного бота

```bash
sudo nano /etc/systemd/system/astro-bot.service
```

**Содержимое файла:**
```ini
[Unit]
Description=NeyroAstro Telegram Bot
After=network.target postgresql.service rabbitmq-server.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/astro_ai
Environment="PATH=/root/astro_ai/venv/bin"
ExecStart=/root/astro_ai/venv/bin/python /root/astro_ai/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Создание systemd сервиса для webhook

```bash
sudo nano /etc/systemd/system/astro-webhook.service
```

**Содержимое файла:**
```ini
[Unit]
Description=NeyroAstro Webhook Server
After=network.target astro-bot.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/astro_ai
Environment="PATH=/root/astro_ai/venv/bin"
ExecStart=/root/astro_ai/venv/bin/python /root/astro_ai/run_with_webhook.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Создание systemd сервиса для всех workers

```bash
sudo nano /etc/systemd/system/astro-workers.service
```

**Содержимое файла:**
```ini
[Unit]
Description=NeyroAstro Workers (Moon, Planets, Recommendations)
After=network.target postgresql.service rabbitmq-server.service

[Service]
Type=forking
User=root
WorkingDirectory=/root/astro_ai
ExecStart=/root/astro_ai/astro-manager.sh start
ExecStop=/root/astro_ai/astro-manager.sh stop
RemainAfterExit=yes
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

#### Запуск systemd сервисов

```bash
# Перезагрузка конфигурации systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable astro-bot.service
sudo systemctl enable astro-webhook.service
sudo systemctl enable astro-workers.service

# Запуск сервисов
sudo systemctl start astro-bot.service
sudo systemctl start astro-webhook.service
sudo systemctl start astro-workers.service

# Проверка статуса
sudo systemctl status astro-bot.service
sudo systemctl status astro-webhook.service
sudo systemctl status astro-workers.service
```

---

## 🎛️ Управление процессами

### Просмотр запущенных процессов
```bash
# Все процессы Python
ps aux | grep python

# Процессы astro проекта
ps aux | grep astro

# Использование астро-менеджера
./astro-manager.sh status
```

### Остановка процессов
```bash
# Через astro-manager
./astro-manager.sh stop

# Через systemd
sudo systemctl stop astro-bot.service
sudo systemctl stop astro-webhook.service
sudo systemctl stop astro-workers.service

# Вручную (если нужно)
python stop_all_bots.py
```

### Перезапуск при обновлении кода
```bash
# 1. Pull изменений
cd ~/astro_ai
git pull origin main

# 2. Обновление зависимостей (если изменились)
source venv/bin/activate
pip install -r requirements.txt

# 3. Перезапуск сервисов
sudo systemctl restart astro-bot.service
sudo systemctl restart astro-webhook.service
sudo systemctl restart astro-workers.service

# Или через astro-manager
sudo ./astro-manager.sh restart
```

### Перезапуск только workers
```bash
# Перезапуск всех воркеров через astro-manager
cd ~/astro_ai
sudo ./astro-manager.sh restart

# Остановка всех воркеров
sudo ./astro-manager.sh stop

# Запуск всех воркеров
sudo ./astro-manager.sh start

# Проверка статуса воркеров
sudo ./astro-manager.sh status
```

---

## 📊 Мониторинг и логи

### Просмотр логов systemd
```bash
# Логи основного бота
sudo journalctl -u astro-bot.service -f

# Логи webhook
sudo journalctl -u astro-webhook.service -f

# Логи workers
sudo journalctl -u astro-workers.service -f

# Все логи вместе
sudo journalctl -u astro-bot.service -u astro-webhook.service -u astro-workers.service -f

# Последние 100 строк
sudo journalctl -u astro-bot.service -n 100
```

### Мониторинг RabbitMQ
```bash
# Статус очередей
sudo rabbitmqctl list_queues

# Веб-интерфейс (если включен)
# Открыть в браузере: http://your_server_ip:15672
# Логин: astro_user
# Пароль: astro_password_123
```

### Мониторинг PostgreSQL
```bash
# Подключение к БД
psql -U astro_user -d astro_db

# Проверка таблиц
\dt

# Подсчет записей
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM predictions;
SELECT COUNT(*) FROM planet_payments;
```

### Мониторинг дискового пространства
```bash
# Проверка использования диска
df -h

# Размер проекта
du -sh ~/astro_ai

# Размер логов
sudo journalctl --disk-usage
```

---

## 🔥 Troubleshooting

### Проблема: Бот не отвечает

```bash
# 1. Проверить статус сервиса
sudo systemctl status astro-bot.service

# 2. Проверить логи
sudo journalctl -u astro-bot.service -n 50

# 3. Проверить подключение к БД
psql -U astro_user -d astro_db -c "SELECT 1;"

# 4. Проверить RabbitMQ
sudo rabbitmqctl status

# 5. Перезапустить бота
sudo systemctl restart astro-bot.service
```

### Проблема: Workers не обрабатывают задачи

```bash
# 1. Проверить очереди RabbitMQ
sudo rabbitmqctl list_queues

# 2. Проверить логи workers
sudo journalctl -u astro-workers.service -n 100

# 3. Проверить процессы
ps aux | grep worker

# 4. Перезапустить workers
./astro-manager.sh restart
```

### Проблема: Webhook не работает

```bash
# 1. Проверить статус webhook
sudo systemctl status astro-webhook.service

# 2. Проверить логи
sudo journalctl -u astro-webhook.service -n 50

# 3. Проверить порт (обычно 8443)
sudo netstat -tulpn | grep 8443

# 4. Перезапустить webhook
sudo systemctl restart astro-webhook.service
```

### Проблема: Нехватка памяти

```bash
# Проверка использования памяти
free -h

# Топ процессов по памяти
top -o %MEM

# Очистка кэша (осторожно!)
sudo sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'

# Перезапуск сервисов для освобождения памяти
./astro-manager.sh restart
```

### Проблема: База данных не работает

```bash
# 1. Проверить статус PostgreSQL
sudo systemctl status postgresql

# 2. Перезапустить PostgreSQL
sudo systemctl restart postgresql

# 3. Проверить подключение
psql -U astro_user -d astro_db

# 4. Восстановить из бэкапа (если есть)
psql -U astro_user -d astro_db < backup.sql
```

---

## 🔐 Безопасность

### Настройка firewall
```bash
# Установка UFW
sudo apt install -y ufw

# Разрешить SSH
sudo ufw allow ssh

# Разрешить webhook порт (если используется)
sudo ufw allow 8443/tcp

# Включить firewall
sudo ufw enable

# Проверить статус
sudo ufw status
```

### Регулярное обновление
```bash
# Создать cron job для обновления системы
sudo crontab -e

# Добавить строку (обновление каждое воскресенье в 3:00)
0 3 * * 0 apt update && apt upgrade -y
```

---

## 💾 Бэкап

### Бэкап базы данных
```bash
# Создание бэкапа
pg_dump -U astro_user astro_db > ~/backups/astro_db_$(date +%Y%m%d_%H%M%S).sql

# Восстановление из бэкапа
psql -U astro_user -d astro_db < ~/backups/astro_db_20250125_120000.sql
```

### Автоматический бэкап (cron)
```bash
# Создать директорию для бэкапов
mkdir -p ~/backups

# Редактировать crontab
crontab -e

# Добавить строку (бэкап каждый день в 2:00)
0 2 * * * pg_dump -U astro_user astro_db > ~/backups/astro_db_$(date +\%Y\%m\%d_\%H\%M\%S).sql

# Удаление старых бэкапов (старше 7 дней)
0 3 * * * find ~/backups -name "astro_db_*.sql" -mtime +7 -delete
```

---

## � Полезные команды

```bash
# Быстрый перезапуск всего проекта
cd ~/astro_ai && sudo ./astro-manager.sh restart && sudo systemctl restart astro-bot.service astro-webhook.service

# Перезапуск только воркеров
cd ~/astro_ai && sudo ./astro-manager.sh restart

# Просмотр всех логов в реальном времени
sudo journalctl -f

# Проверка использования ресурсов
htop

# Очистка старых логов
sudo journalctl --vacuum-time=7d

# Обновление проекта из git
cd ~/astro_ai && git pull origin main && sudo ./astro-manager.sh restart

# Проверка статуса всех воркеров
cd ~/astro_ai && sudo ./astro-manager.sh status
```

---

## 📝 Полезные ссылки

- [Документация по астро-менеджеру](./ASTRO_MANAGER_README.md)
- [Мониторинг через journalctl](./JOURNALCTL_MONITORING.md)
- [Настройка рекомендаций](./RECOMMENDATIONS_SETUP.md)
- [Защита платежей](./PAYMENT_PROTECTION.md)

---

**Автор:** NeyroAstro Team  
**Последнее обновление:** 25.10.2025
