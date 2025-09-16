#!/bin/bash
# Остановка всех процессов бота

echo "Останавливаем все процессы бота..."

# Останавливаем все процессы с main.py
pkill -f "python.*main.py"
pkill -f "python.*run_with_webhook.py"

# Ждем 2 секунды
sleep 2

# Проверяем, что процессы остановлены
echo "Проверяем процессы:"
ps aux | grep -E "(main.py|run_with_webhook.py)" | grep -v grep

echo "Готово!"
