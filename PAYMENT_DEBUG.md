# Диагностика проблем с ЮKassa

## Найденные проблемы и решения

### 1. **Неправильная настройка return_url**
**Проблема**: Был указан placeholder `https://t.me/your_bot_username`
**Решение**: Изменен на `https://pay.neyroastro.ru/webhook/success`

### 2. **Неправильный заголовок для webhook**
**Проблема**: Искали только `X-YooMoney-Signature`
**Решение**: Добавлена проверка нескольких заголовков:
- `HTTP_AUTHORIZATION`
- `Authorization` 
- `X-YooMoney-Signature`

### 3. **Отсутствие страницы успешной оплаты**
**Решение**: Добавлен эндпоинт `/webhook/success`

## Пошаговая диагностика

### Шаг 1: Проверка конфигурации
```bash
python test_yookassa.py
```

### Шаг 2: Проверка создания платежа
Запустите бота и попробуйте создать платеж. Проверьте логи:
```bash
# В логах должно быть:
# INFO - Создание платежа с ID: ...
# INFO - Данные платежа: ...
# INFO - Платеж создан успешно: ...
```

### Шаг 3: Проверка webhook сервера
```bash
# Проверьте что сервер запущен
curl https://pay.neyroastro.ru/webhook/health

# Проверьте страницу успеха
curl https://pay.neyroastro.ru/webhook/success
```

### Шаг 4: Тест webhook
```bash
curl -X POST https://pay.neyroastro.ru/webhook/payment \
  -H "Content-Type: application/json" \
  -H "Authorization: test_signature" \
  -d '{
    "event": "payment.succeeded",
    "object": {
      "metadata": {
        "user_id": "12345",
        "planet": "sun"
      }
    }
  }'
```

## Возможные проблемы

### 1. Ошибка аутентификации
**Симптом**: `401 Unauthorized` при создании платежа
**Решение**: Проверьте правильность `PAYMENT_SHOP_ID` и `PAYMENT_SECRET_KEY`

### 2. Неверный формат данных
**Симптом**: `400 Bad Request` при создании платежа
**Решение**: Проверьте формат данных в `create_payment_data()`

### 3. Webhook не приходят
**Симптом**: Платеж проходит, но webhook не обрабатывается
**Решение**: 
- Проверьте URL webhook в личном кабинете ЮKassa
- Убедитесь что сервер доступен извне
- Проверьте логи webhook сервера

### 4. Неверная подпись webhook
**Симптом**: `Invalid signature` в логах
**Решение**: Проверьте правильность secret_key и алгоритм подписи

## Настройка в ЮKassa

1. Войдите в личный кабинет ЮKassa
2. Перейдите в "Настройки" → "Уведомления"
3. Укажите URL: `https://pay.neyroastro.ru/webhook/payment`
4. Выберите события: `payment.succeeded`, `payment.canceled`
5. Сохраните настройки

## Логирование

### Включение детального логирования
В `main.py` измените уровень логирования:
```python
logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)
```

### Важные логи для мониторинга
- Создание платежа: `payment_handler.py:55-69`
- Обработка webhook: `webhook_server.py:28-68`
- Предоставление доступа: `payment_handler.py:114-129`

## Тестирование

### 1. Локальное тестирование
```bash
python test_yookassa.py
```

### 2. Тестирование на сервере
```bash
# Запустите webhook сервер
python run_with_webhook.py

# В другом терминале запустите тест
python test_yookassa.py
```

### 3. Тестирование через ngrok
```bash
# Установите ngrok
npm install -g ngrok

# Запустите туннель
ngrok http 8080

# Используйте URL от ngrok в настройках ЮKassa
```

## Контрольный список

- [ ] Правильные credentials в `.env`
- [ ] Webhook URL настроен в ЮKassa
- [ ] Сервер доступен по HTTPS
- [ ] Порт 8080 открыт
- [ ] SSL сертификат действителен
- [ ] Логирование включено
- [ ] Тестовый платеж создается
- [ ] Webhook обрабатывается
- [ ] Пользователь получает уведомление
