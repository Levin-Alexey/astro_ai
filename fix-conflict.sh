#!/bin/bash

# Быстрое решение конфликта ботов
# Останавливает все процессы и перезапускает

echo "🚨 РЕШЕНИЕ КОНФЛИКТА БОТОВ!"
echo "=========================="

# Останавливаем все сервисы
echo "1️⃣ Останавливаю все сервисы..."
sudo systemctl stop astro-mercury-recommendations-worker.service
sudo systemctl stop astro-mercury-worker.service
sudo systemctl stop astro-question-worker.service
sudo systemctl stop astro-sun-recommendations-worker.service
sudo systemctl stop astro-sun-worker.service
sudo systemctl stop astro-worker.service
sudo systemctl stop rec-worker.service
sudo systemctl stop venus-recommendations-worker.service
sudo systemctl stop venus-worker.service

# Убиваем все python процессы
echo "2️⃣ Убиваю все Python процессы..."
sudo pkill -f "python.*astro"
sudo pkill -f "python.*bot"
sudo pkill -f "python.*worker"
sudo pkill -f "python.*main.py"

# Ждем
echo "3️⃣ Жду 3 секунды..."
sleep 3

# Запускаем обратно
echo "4️⃣ Запускаю все сервисы..."
sudo systemctl start astro-mercury-recommendations-worker.service
sudo systemctl start astro-mercury-worker.service
sudo systemctl start astro-question-worker.service
sudo systemctl start astro-sun-recommendations-worker.service
sudo systemctl start astro-sun-worker.service
sudo systemctl start astro-worker.service
sudo systemctl start rec-worker.service
sudo systemctl start venus-recommendations-worker.service
sudo systemctl start venus-worker.service

echo "✅ ГОТОВО! Конфликт должен быть решен."
echo ""
echo "Проверьте статус:"
sudo systemctl is-active astro-mercury-recommendations-worker.service astro-mercury-worker.service astro-question-worker.service astro-sun-recommendations-worker.service astro-sun-worker.service astro-worker.service rec-worker.service venus-recommendations-worker.service venus-worker.service