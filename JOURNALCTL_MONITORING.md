# Проверка всех процессов через journalctl

## 🔍 Основные команды для мониторинга всех процессов

### **1. Просмотр всех активных сервисов:**
```bash
# Все запущенные сервисы
sudo systemctl list-units --type=service --state=running

# Все сервисы (включая остановленные)
sudo systemctl list-units --type=service --all

# Неудачные сервисы
sudo systemctl list-units --type=service --state=failed
```

### **2. Просмотр логов всех сервисов:**
```bash
# Все логи системы в реальном времени
sudo journalctl -f

# Все логи за последний час
sudo journalctl --since "1 hour ago"

# Все логи за сегодня
sudo journalctl --since today

# Логи с приоритетом ошибок
sudo journalctl --priority=err
```

### **3. Поиск конкретных процессов:**
```bash
# Найти все сервисы содержащие слово
sudo systemctl list-units --type=service | grep "python"
sudo systemctl list-units --type=service | grep "bot"
sudo systemctl list-units --type=service | grep "worker"

# Поиск по названию процесса
ps aux | grep python
ps aux | grep bot
ps aux | grep worker
```

### **4. Логи конкретного сервиса (если знаете название):**
```bash
# Замените SERVICE_NAME на название вашего сервиса
sudo journalctl -u SERVICE_NAME -f

# Примеры поиска ваших сервисов:
sudo systemctl list-units --type=service | grep -E "(bot|worker|python|astro)"
```

### **5. Поиск Python процессов:**
```bash
# Все Python процессы
ps aux | grep python

# Python процессы с полным путем
ps -ef | grep python

# Логи всех Python сервисов
sudo journalctl | grep -i python
```

### **6. Поиск ваших конкретных процессов:**
```bash
# Найти все сервисы с ботами
sudo systemctl list-units --type=service | grep -i bot

# Найти все сервисы с воркерами  
sudo systemctl list-units --type=service | grep -i worker

# Найти сервисы содержащие "astro", "mercury", "venus", "sun"
sudo systemctl list-units --type=service | grep -E "(astro|mercury|venus|sun)"

# Посмотреть логи найденного сервиса
sudo journalctl -u НАЙДЕННЫЙ_СЕРВИС -f
```

### **7. Универсальный поиск ваших процессов:**
```bash
# Шаг 1: Найти все ваши сервисы
sudo systemctl list-units --type=service --all | grep -E "(bot|worker|python|astro|mercury|venus|sun)"

# Шаг 2: Проверить запущенные Python процессы
ps aux | grep -E "(python|bot|worker)"

# Шаг 3: Поиск в логах по ключевым словам
sudo journalctl | grep -E "(mercury|venus|sun|астро|bot)" | tail -50
```

### **8. Проверка активности процессов:**
```bash
# Топ процессов по CPU
top -p $(pgrep -d',' python)

# Топ процессов по памяти
ps aux --sort=-%mem | grep python

# Проверка сетевых соединений Python процессов
sudo netstat -tulpn | grep python
```

## 🚨 **Пошаговая диагностика ваших процессов:**

### **Шаг 1: Найти все ваши сервисы**
```bash
# Поиск всех возможных названий ваших сервисов
sudo systemctl list-units --type=service --all | grep -E "(bot|worker|python|astro|mercury|venus|sun|telegram)"

# Показать только активные
sudo systemctl list-units --type=service --state=running | grep -E "(bot|worker|python|astro)"
```

### **Шаг 2: Проверить Python процессы**
```bash
# Все Python процессы с полной информацией
ps -ef | grep python | grep -v grep

# Показать только процессы связанные с ботом
ps aux | grep -E "(bot|astro|mercury|venus|sun)" | grep -v grep
```

### **Шаг 3: Посмотреть логи найденных процессов**
```bash
# После того как найдете названия сервисов, используйте:
sudo journalctl -u ИМЯ_СЕРВИСА -f

# Или поиск в общих логах
sudo journalctl | grep -E "(python|bot|astro)" | tail -100
```

### **Шаг 4: Проверить статус**
```bash
# Статус найденного сервиса
sudo systemctl status ИМЯ_СЕРВИСА

# Перезапустить если нужно
sudo systemctl restart ИМЯ_СЕРВИСА
```

### **6. Мониторинг производительности:**
```bash
# Время ответа OpenRouter
sudo journalctl -u astro-* | grep -i "response time"

# Использование токенов
sudo journalctl -u astro-* | grep -i "usage\|tokens"

# Очереди RabbitMQ
sudo journalctl -u astro-* | grep -i "queue\|rabbitmq"
```

### **7. Полезные комбинации:**
```bash
# Логи в реальном времени с фильтрацией
sudo journalctl -u astro-venus-worker -f | grep -v "INFO"

# Экспорт логов в файл
sudo journalctl -u astro-* --since "1 day ago" > astro_logs.txt

# Логи с JSON форматированием
sudo journalctl -u astro-venus-worker -o json-pretty
```

## 🚨 **Специальные команды для диагностики платежей:**

### **Проверка защиты платежей:**
```bash
# Поиск неудачных анализов
sudo journalctl -u astro-* | grep "mark_analysis_failed"

# Поиск успешных доставок
sudo journalctl -u astro-* | grep "mark_analysis_completed"

# Проверка повторных попыток пользователей
sudo journalctl -u astro-main-bot | grep "retry.*analysis"
```

### **Проверка OpenRouter API:**
```bash
# Ошибки API
sudo journalctl -u astro-* | grep "OpenRouter error"

# Успешные запросы
sudo journalctl -u astro-* | grep "OpenRouter response received"

# Таймауты
sudo journalctl -u astro-* | grep "timeout"
```

## 📊 **Мониторинг ключевых метрик:**

### **1. Количество обработанных платежей:**
```bash
sudo journalctl -u astro-* --since today | grep -c "payment.*created"
```

### **2. Количество успешных доставок:**
```bash
sudo journalctl -u astro-* --since today | grep -c "analysis.*sent"
```

### **3. Количество ошибок:**
```bash
sudo journalctl -u astro-* --since today | grep -c "ERROR"
```

### **4. Rate limiting:**
```bash
sudo journalctl -u astro-* --since today | grep -c "429"
```

## 🔄 **Управление сервисами:**

### **Перезапуск воркеров:**
```bash
sudo systemctl restart astro-venus-worker
sudo systemctl restart astro-sun-worker  
sudo systemctl restart astro-mercury-worker
sudo systemctl restart astro-main-bot
```

### **Остановка/запуск:**
```bash
sudo systemctl stop astro-venus-worker
sudo systemctl start astro-venus-worker
```

### **Автозапуск:**
```bash
sudo systemctl enable astro-venus-worker
sudo systemctl disable astro-venus-worker
```

## 🎯 **Быстрая диагностика проблем:**

```bash
# Проверить что все сервисы работают
sudo systemctl is-active astro-*

# Посмотреть последние ошибки
sudo journalctl -u astro-* --priority=err --since "1 hour ago"

# Проверить подключение к RabbitMQ  
sudo journalctl -u astro-* | grep -i "rabbitmq\|connection"

# Проверить базу данных
sudo journalctl -u astro-* | grep -i "database\|postgres"
```