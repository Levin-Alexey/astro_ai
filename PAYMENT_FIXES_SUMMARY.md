# 🔧 Исправления ошибок обработки платежей

## Проблема
Платежи принимались и сохранялись в БД, но:
1. ❌ **Статус платежей оставался `pending`** вместо `completed`
2. ❌ **Анализы планет не создавались** (несмотря на то, что функции вызывались)

## Причины

### 1️⃣ Недостаточное логирование ошибок
**Файл**: `webhook_server.py` (функция `update_payment_status`)
- Ошибки скрывались в `except Exception as e: logger.error(...)`
- Не было полного стек-трейса
- Не было информации о коммите

**Исправление**:
```python
try:
    await session.commit()
    logger.info(f"✅ Session committed for payment {payment_record.payment_id}")
except Exception as commit_error:
    logger.error(f"❌ Error committing payment status update: {commit_error}", exc_info=True)
    await session.rollback()
    raise
```

### 2️⃣ Отсутствие трейса в `all_planets_handler.py`
**Файл**: `all_planets_handler.py` (функция `handle_payment_success`)
- Ошибка ловилась, но без деталей
- Не было логирования шагов выполнения

**Исправление**:
```python
except Exception as e:
    import traceback
    logger.error(f"❌ Ошибка при обработке успешной оплаты: {e}", exc_info=True)
    logger.error(f"Traceback: {traceback.format_exc()}")
```

### 3️⃣ Отсутствие промежуточного логирования
**Файл**: `all_planets_handler.py` (функция `_start_planet_analysis`)
- Не было логирования между вызовами функций
- Невозможно определить, где именно произойдет ошибка

**Исправление**:
```python
logger.info(f"🚀 Calling start_{planet}_analysis for user {user_id}")

if planet == "sun":
    astrology_data = await start_sun_analysis(user_id, None)
elif ...

logger.info(f"🚀 Analysis function returned for {planet}, data: {astrology_data is not None}")
```

### 4️⃣ Отсутствие ошибок в `_update_payment_status`
**Файл**: `all_planets_handler.py` (функция `_update_payment_status`)
- Функция была без try-except
- Могла упасть без логирования

**Исправление**:
```python
async def _update_payment_status(self, user_id: int) -> None:
    try:
        # ... код ...
    except Exception as e:
        import traceback
        logger.error(f"❌ Error in _update_payment_status: {e}", exc_info=True)
        logger.error(f"Traceback: {traceback.format_exc()}")
```

## Список изменений

### webhook_server.py
- ✅ Добавлено логирование перед коммитом
- ✅ Добавлена обработка ошибок коммита с rollback
- ✅ Добавлен полный стек-трейс в except блоке

### all_planets_handler.py
- ✅ Добавлено логирование шагов в `handle_payment_success()`
- ✅ Добавлено логирование шагов в `_start_planet_analysis()`
- ✅ Обернула `bot.send_message()` в try-except
- ✅ Добавлено логирование возврата функции анализа
- ✅ Добавлено логирование в `_update_payment_status()`
- ✅ Обернула всю функцию в try-except

## Как тестировать

1. **Запусти боты**:
   ```bash
   # Терминал 1 - webhook
   python run_with_webhook.py
   ```

2. **Запусти диагностику**:
   ```bash
   python diagnose_payment_issue.py
   ```

3. **Если есть старые платежи, очисти их**:
   ```bash
   python cleanup_payments.py
   ```

4. **Запусти новый платеж вручную** (через telegram бота) или вебхук

5. **Проверь логи**:
   ```bash
   journalctl -u yookassa-webhook.service -f
   ```

6. **Проверь БД после платежа**:
   ```bash
   python diagnose_payment_issue.py
   ```

## Ожидаемые логи после исправления

```
✅ Webhook received payment.succeeded
✅ Updating payment status
✅ Payment record found
🔄 Updating payment X status from pending to completed
✅ Session committed for payment X
🌌 Calling _update_payment_status for user Y
🔄 Looking for pending payment for user Y
✅ Found pending payment: X
✅ Статус платежа обновлен для пользователя Y
✅ Payment status updated for user Y
🌌 Calling _start_planet_analysis for user Y
🚀 Запуск анализа sun для пользователя Y
🚀 Calling start_sun_analysis for user Y
🚀 Analysis function returned for sun, data: True
✅ Анализ sun запущен для пользователя Y
```

## Что дальше

Если после исправлений анализы все еще не создаются:
1. Проверь логи астрологических воркеров (sun_worker, mercury_worker и т.д.)
2. Проверь логи очереди сообщений (RabbitMQ)
3. Проверь, что воркеры запущены и слушают очередь
4. Проверь, что функции `start_sun_analysis()`, `start_mercury_analysis()` и т.д. работают
