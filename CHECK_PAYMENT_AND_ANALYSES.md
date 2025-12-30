# Как проверить, были ли отправлены разборы пользователю

## Механизм отправки разборов

После успешного платежа система следует этому процессу:

1. **Webhook получает платеж** (`webhook_server.py`)
   - Статус: `payment.succeeded`
   - Вызывается `handle_payment_success()` из `all_planets_handler.py`

2. **Последовательный запуск анализов** (`all_planets_handler.py`)
   - Солнце → Меркурий → Венера → Марс
   - Для каждой планеты вызывается воркер

3. **Сохранение анализов в БД** (`predictions` таблица)
   - Поля: `sun_analysis`, `mercury_analysis`, `venus_analysis`, `mars_analysis`

---

## SQL Запросы для проверки

### 1️⃣ Найти пользователя и его Telegram ID

```sql
SELECT user_id, telegram_id, username, joined_at, last_seen_at
FROM users
WHERE telegram_id = 518337064;
```

**Ожидаемый результат:**
- `user_id`: внутренний ID (например, 661)
- `telegram_id`: 518337064
- `username`: anjlvo

---

### 2️⃣ Проверить платежи пользователя

```sql
SELECT 
    payment_id,
    payment_type,
    planet,
    status,
    amount_kopecks,
    external_payment_id,
    created_at,
    completed_at
FROM planet_payments
WHERE user_id = 661
ORDER BY created_at DESC;
```

**Ожидаемые результаты:**
- 2 платежа по 22200 копеек (222 RUB)
- `payment_type`: `all_planets`
- `status`: `completed` (если успешно)
- `external_payment_id`: ID из Yookassa (например, `30e5b00d-000f-5000-b000-1d51b4164d91`)

---

### 3️⃣ Проверить, созданы ли предсказания (анализы)

```sql
SELECT 
    prediction_id,
    user_id,
    planet,
    prediction_type,
    CASE 
        WHEN sun_analysis IS NOT NULL THEN '✅ Солнце'
        ELSE '❌ Нет'
    END as sun_analysis,
    CASE 
        WHEN mercury_analysis IS NOT NULL THEN '✅ Меркурий'
        ELSE '❌ Нет'
    END as mercury_analysis,
    CASE 
        WHEN venus_analysis IS NOT NULL THEN '✅ Венера'
        ELSE '❌ Нет'
    END as venus_analysis,
    CASE 
        WHEN mars_analysis IS NOT NULL THEN '✅ Марс'
        ELSE '❌ Нет'
    END as mars_analysis,
    created_at
FROM predictions
WHERE user_id = 661
ORDER BY created_at DESC;
```

**Ожидаемый результат:**
- Несколько строк с `planet` = 'sun', 'mercury', 'venus', 'mars'
- Все `*_analysis` поля должны содержать текст анализов
- `prediction_type`: `paid`

---

### 4️⃣ Детальная проверка конкретного анализа (пример для Солнца)

```sql
SELECT 
    prediction_id,
    created_at,
    LENGTH(sun_analysis) as sun_analysis_length,
    SUBSTRING(sun_analysis, 1, 100) as sun_analysis_preview
FROM predictions
WHERE user_id = 661 
  AND planet = 'sun'
  AND sun_analysis IS NOT NULL
ORDER BY created_at DESC
LIMIT 1;
```

---

### 5️⃣ Комбинированная проверка: платежи + анализы

```sql
-- Все платежи и связанные с ними анализы
SELECT 
    pp.payment_id,
    pp.status,
    pp.created_at as payment_created_at,
    COUNT(p.prediction_id) as predictions_count,
    SUM(CASE WHEN p.sun_analysis IS NOT NULL THEN 1 ELSE 0 END) as has_sun,
    SUM(CASE WHEN p.mercury_analysis IS NOT NULL THEN 1 ELSE 0 END) as has_mercury,
    SUM(CASE WHEN p.venus_analysis IS NOT NULL THEN 1 ELSE 0 END) as has_venus,
    SUM(CASE WHEN p.mars_analysis IS NOT NULL THEN 1 ELSE 0 END) as has_mars
FROM planet_payments pp
LEFT JOIN predictions p ON pp.user_id = p.user_id
WHERE pp.user_id = 661 AND pp.payment_type = 'all_planets'
GROUP BY pp.payment_id, pp.status, pp.created_at
ORDER BY pp.created_at DESC;
```

---

## Проверка логов

### В systemd журнале (уже видно в присланных логах):

```
✅ Платеж создан: 30e5ad44-000f-5001-8000-1e20af16f791
✅ Платеж создан: 30e5b00d-000f-5000-b000-1d51b4164d91
✅ WEBHOOK RECEIVED: payment.succeeded
✅ Обновляем payment status
✅ Начинаем последовательный разбор планет
✅ Payment processed for Telegram ID 518337064
```

### Проверка в коде (см. `all_planets_handler.py`):

Метод `handle_payment_success()` (строка 193):
1. Логирует: `🌌 Начинаем последовательный разбор планет`
2. Вызывает `_start_planet_analysis()` для каждой планеты
3. Каждый анализ сохраняется в `predictions` таблице

---

## Возможные проблемы и решения

| Проблема | Проверка | Решение |
|----------|----------|---------|
| Платежи есть, анализов нет | Проверить `predictions` таблицу | Может быть ошибка в воркерах (sun_worker, mercury_worker и т.д.) |
| Платежи отсутствуют | `planet_payments` пуста | Webhook не получил платеж или он не обработан |
| Платежи есть, но статус `pending` | `status = 'pending'` в `planet_payments` | Webhook обработал платеж, но статус не обновился |
| Анализы неполные | Только некоторые `*_analysis` заполнены | Может быть ошибка в определенном воркере |

---

## Как запустить эти запросы

### Вариант 1: Через PostgreSQL клиент
```bash
psql -h localhost -U your_user -d your_database -c "SELECT * FROM users WHERE telegram_id = 518337064;"
```

### Вариант 2: Из Python скрипта (добавить в проект)
```python
import asyncio
from db import get_session
from models import User, PlanetPayment, Prediction
from sqlalchemy import select

async def check_user_analyses():
    async with get_session() as session:
        # Найти пользователя
        user = await session.execute(
            select(User).where(User.telegram_id == 518337064)
        )
        user_obj = user.scalar_one_or_none()
        
        if not user_obj:
            print("❌ Пользователь не найден")
            return
        
        # Проверить платежи
        payments = await session.execute(
            select(PlanetPayment)
            .where(PlanetPayment.user_id == user_obj.user_id)
            .order_by(PlanetPayment.created_at.desc())
        )
        payments_list = payments.scalars().all()
        
        print(f"📊 Найдено платежей: {len(payments_list)}")
        for p in payments_list:
            print(f"  - {p.payment_type}: {p.status} ({p.amount_kopecks} kopecks)")
        
        # Проверить анализы
        predictions = await session.execute(
            select(Prediction)
            .where(Prediction.user_id == user_obj.user_id)
            .order_by(Prediction.created_at.desc())
        )
        predictions_list = predictions.scalars().all()
        
        print(f"📊 Найдено анализов: {len(predictions_list)}")
        for pred in predictions_list:
            has_analyses = {
                'sun': '✅' if pred.sun_analysis else '❌',
                'mercury': '✅' if pred.mercury_analysis else '❌',
                'venus': '✅' if pred.venus_analysis else '❌',
                'mars': '✅' if pred.mars_analysis else '❌'
            }
            print(f"  - {pred.planet}: {has_analyses}")

# asyncio.run(check_user_analyses())
```

---

## Вывод из анализа ваших логов

На основе присланных логов **система работает правильно**:

1. ✅ **Платежи успешны**: оба платежа статус `succeeded`
2. ✅ **Webhook получен**: видно в логах `WEBHOOK RECEIVED: payment.succeeded`
3. ✅ **Обработка запущена**: `Начинаем последовательный разбор планет`
4. ✅ **Статус обновлён**: `✅ Payment processed for Telegram ID 518337064`

**Остаётся проверить в БД**, что анализы действительно сохранены в таблице `predictions`.
