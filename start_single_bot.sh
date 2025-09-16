#!/bin/bash
# Запуск одного экземпляра бота

echo "Останавливаем все процессы бота..."
pkill -f "python.*main.py"
pkill -f "python.*run_with_webhook.py"

# Ждем 3 секунды
sleep 3

echo "Запускаем бота с webhook..."
cd /root/astro_ai
source venv/bin/activate
python run_with_webhook.py &

echo "Бот запущен!"
echo "PID: $!"
