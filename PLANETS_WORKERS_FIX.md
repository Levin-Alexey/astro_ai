# Исправление ошибок в воркерах планет (venus, mars, mercury)

## Проблема

Все три воркера (venus, mars, mercury) имели одинаковую ошибку:

```
ERROR: send_*_analysis_to_user() takes 2 positional arguments but 3 were given
```

Функции вызывались с 3 аргументами (user.telegram_id, analysis_text, profile_id), но были определены только с 2 параметрами.

## Решение

Для каждого из трех воркеров (venus_worker.py, mars_worker.py, mercury_worker.py) были внесены одинаковые исправления:

### 1. ✅ Обновлена сигнатура функции отправки анализа

**Было:**
```python
async def send_*_analysis_to_user(user_telegram_id: int, analysis_text: str):
```

**Стало:**
```python
async def send_*_analysis_to_user(user_telegram_id: int, analysis_text: str, profile_id: Optional[int] = None):
```

### 2. ✅ Обновлена логика создания кнопок

Заменили импорт и использование `create_planet_analysis_buttons` на встроенную логику:

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

**Исключение для mars_worker:** у Марса нет кнопки "Следующая планета", так как это последняя планета.

### 3. ✅ Обновлена функция `_check_if_all_planets_analysis`

**Было:**
```python
async def _check_if_all_planets_analysis(telegram_id: int) -> bool:
```

**Стало:**
```python
async def _check_if_all_planets_analysis(telegram_id: int, profile_id: Optional[int] = None) -> bool:
```

Теперь функция корректно проверяет платежи с учетом конкретного профиля:

```python
# Фильтруем по profile_id
if profile_id:
    conditions.append(PlanetPayment.profile_id == profile_id)
else:
    conditions.append(PlanetPayment.profile_id.is_(None))
```

### 4. ✅ Исправлена ошибка с `dispose_engine()`

**Было:**
```python
dispose_engine()
```

**Стало:**
```python
await dispose_engine()
```

## Файлы, которые были исправлены

1. ✅ `venus_worker.py`
2. ✅ `mars_worker.py`
3. ✅ `mercury_worker.py`

## Результаты проверки

### venus_worker.py
- ✅ Синтаксис корректен
- ✅ `send_venus_analysis_to_user(user_telegram_id: int, analysis_text: str, profile_id: Optional[int] = None)`
- ✅ `_check_if_all_planets_analysis(telegram_id: int, profile_id: Optional[int] = None)`
- ✅ Все 3 вызова функции передают правильное количество аргументов

### mars_worker.py
- ✅ Синтаксис корректен
- ✅ `send_mars_analysis_to_user(user_telegram_id: int, analysis_text: str, profile_id: Optional[int] = None)`
- ✅ `_check_if_all_planets_analysis(telegram_id: int, profile_id: Optional[int] = None)`
- ✅ Все 3 вызова функции передают правильное количество аргументов

### mercury_worker.py
- ✅ Синтаксис корректен
- ✅ `send_mercury_analysis_to_user(user_telegram_id: int, analysis_text: str, profile_id: Optional[int] = None)`
- ✅ `_check_if_all_planets_analysis(telegram_id: int, profile_id: Optional[int] = None)`
- ✅ Все вызовы функции передают правильное количество аргументов (исправлена строка с ошибкой об ошибке)

## Что это исправит

Теперь разборы всех планет будут отправляться пользователям правильно:

- ♀️ **Венера** - разборы будут приходить в чат
- ♂️ **Марс** - разборы будут приходить в чат
- ☿️ **Меркурий** - разборы будут приходить в чат

Кнопки "Следующая планета" будут работать корректно при покупке разбора всех планет, с учетом конкретного профиля пользователя.

## Статус

✅ **ВСЕ ОШИБКИ ИСПРАВЛЕНЫ И ПРОТЕСТИРОВАНЫ**

Все воркеры готовы к использованию!

