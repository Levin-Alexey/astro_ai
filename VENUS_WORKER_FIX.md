# Исправление ошибки в venus_worker.py

## Проблема
Ошибка при обработке предсказания Венеры:
```
ERROR:__main__:♀️ Error processing Venus prediction: send_venus_analysis_to_user() takes 2 positional arguments but 3 were given
```

Функция вызывалась с 3 аргументами, но была определена только с 2 параметрами.

## Решение

### 1. Обновлена сигнатура функции `send_venus_analysis_to_user`

**Было:**
```python
async def send_venus_analysis_to_user(user_telegram_id: int, analysis_text: str):
```

**Стало:**
```python
async def send_venus_analysis_to_user(user_telegram_id: int, analysis_text: str, profile_id: Optional[int] = None):
```

### 2. Обновлена логика создания кнопок

Заменили импорт и использование `create_planet_analysis_buttons` на встроенную логику создания кнопок (аналогично sun_worker.py):

```python
# Создаем кнопки
buttons = []

if is_all_planets:
    buttons.append([
        {
            "text": "➡️ Следующая планета",
            "callback_data": "next_planet"
        }
    ])
else:
    buttons.append([
        {
            "text": "🔍 Исследовать другие сферы",
            "callback_data": "explore_other_areas"
        }
    ])

buttons.append([
    {
        "text": "🏠 Главное меню",
        "callback_data": "back_to_menu"
    }
])

keyboard = {
    "inline_keyboard": buttons
}
```

### 3. Обновлена функция `_check_if_all_planets_analysis`

**Было:**
```python
async def _check_if_all_planets_analysis(telegram_id: int) -> bool:
```

**Стало:**
```python
async def _check_if_all_planets_analysis(telegram_id: int, profile_id: Optional[int] = None) -> bool:
```

Теперь функция корректно проверяет платежи с учетом конкретного профиля пользователя:

```python
# Фильтруем по profile_id
if profile_id:
    conditions.append(PlanetPayment.profile_id == profile_id)
else:
    conditions.append(PlanetPayment.profile_id.is_(None))
```

### 4. Исправлена ошибка с `dispose_engine()`

**Было:**
```python
dispose_engine()
```

**Стало:**
```python
await dispose_engine()
```

## Результат

✓ Все три вызова функции `send_venus_analysis_to_user` теперь передают правильное количество аргументов:
- Строка 295: `await send_venus_analysis_to_user(user.telegram_id, analysis_content, prediction.profile_id)`
- Строка 321: `await send_venus_analysis_to_user(user.telegram_id, llm_result["content"], prediction.profile_id)`
- Строка 338: `await send_venus_analysis_to_user(user.telegram_id, error_message, prediction.profile_id)`

✓ Сигнатура функции соответствует всем вызовам

✓ Логика проверки платежей для разбора всех планет теперь работает с учетом дополнительных профилей

✓ Синтаксис файла корректен

## Что было исправлено
1. ✅ Добавлен параметр `profile_id` в функцию `send_venus_analysis_to_user`
2. ✅ Обновлена логика создания кнопок
3. ✅ Обновлена функция `_check_if_all_planets_analysis` для работы с профилями
4. ✅ Исправлена ошибка с `await` для `dispose_engine()`

Теперь venus_worker должен работать корректно и отправлять разборы Венеры пользователям без ошибок.

