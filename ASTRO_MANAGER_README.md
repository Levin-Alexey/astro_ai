# 🚀 Астро-Менеджер - Управление сервисами

## 📥 Установка

### 1. Скопируйте файл на сервер:
```bash
# Загрузите astro-manager.sh в корень сервера
scp astro-manager.sh user@your-server:/root/
```

### 2. Сделайте файл исполняемым:
```bash
chmod +x /root/astro-manager.sh
```

### 3. Создайте символическую ссылку (опционально):
```bash
ln -s /root/astro-manager.sh /usr/local/bin/astro
```

## 🎯 Использование

### Запуск скрипта:
```bash
# Из корня сервера
sudo ./astro-manager.sh

# Или если создали ссылку
sudo astro
```

### Меню скрипта:
```
Выберите действие:
1) Проверить статус всех сервисов
2) Перезапустить все сервисы  
3) Остановить все сервисы
4) Запустить все сервисы
5) Показать логи всех сервисов
6) Перезапустить конкретный сервис
7) Показать статус в реальном времени
0) Выход
```

## 🔧 Функции скрипта

### ✅ Проверка статуса (опция 1)
- Показывает статус всех 9 сервисов
- Сводка: сколько активно из общего числа
- Цветовая индикация (зеленый/красный)

### 🔄 Перезапуск всех (опция 2)
- Перезапускает все сервисы по очереди
- Показывает результат каждого
- Сводная статистика успешных перезапусков

### 🛑 Остановка всех (опция 3)
- Останавливает все сервисы
- Полезно при обновлении кода

### 🟢 Запуск всех (опция 4)
- Запускает все остановленные сервисы
- Используется после остановки или обновления

### 📋 Логи (опция 5)
- Показывает последние 5 строк логов каждого сервиса
- Быстрая диагностика проблем

### 🎯 Конкретный сервис (опция 6)
- Выбор и перезапуск одного сервиса
- Удобно при проблемах с отдельным воркером

### 📊 Реальное время (опция 7)
- Мониторинг статуса каждые 5 секунд
- Ctrl+C для выхода

## 🚨 Быстрые команды

### Только перезапуск всех сервисов:
```bash
# Создайте отдельный файл для быстрого перезапуска
echo '#!/bin/bash
sudo systemctl restart astro-mercury-recommendations-worker.service
sudo systemctl restart astro-mercury-worker.service
sudo systemctl restart astro-question-worker.service
sudo systemctl restart astro-sun-recommendations-worker.service
sudo systemctl restart astro-sun-worker.service
sudo systemctl restart astro-worker.service
sudo systemctl restart rec-worker.service
sudo systemctl restart venus-recommendations-worker.service
sudo systemctl restart venus-worker.service
echo "✅ Все сервисы перезапущены!"' > /root/restart-all.sh

chmod +x /root/restart-all.sh
```

### Проверка статуса одной командой:
```bash
echo '#!/bin/bash
sudo systemctl is-active astro-mercury-recommendations-worker.service astro-mercury-worker.service astro-question-worker.service astro-sun-recommendations-worker.service astro-sun-worker.service astro-worker.service rec-worker.service venus-recommendations-worker.service venus-worker.service' > /root/check-all.sh

chmod +x /root/check-all.sh
```

## 🎨 Особенности скрипта

- 🌈 **Цветной вывод** - легко читать статус
- 📊 **Счетчики** - видно сколько сервисов работает
- 🔄 **Интерактивное меню** - простое управление
- ⚡ **Быстрые операции** - все действия в одном месте
- 🛡️ **Проверка прав** - требует sudo для безопасности

## 📋 Сервисы в скрипте

1. astro-mercury-recommendations-worker.service
2. astro-mercury-worker.service
3. astro-question-worker.service
4. astro-sun-recommendations-worker.service
5. astro-sun-worker.service
6. astro-worker.service
7. rec-worker.service
8. venus-recommendations-worker.service
9. venus-worker.service

## 🔧 Настройка

Если нужно добавить/убрать сервисы, отредактируйте массив в файле:
```bash
SERVICES=(
    "новый-сервис.service"
    # добавьте сюда
)
```

Готово! Теперь у вас есть удобный менеджер для всех астро-сервисов! 🚀