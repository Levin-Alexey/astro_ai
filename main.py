import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from db import (
    init_engine,
    dispose_engine,
    ensure_gender_enum,
    ensure_birth_date_nullable,
    ensure_zodiac_enum_ru,
)
from models import create_all
from sqlalchemy.ext.asyncio import AsyncEngine
from db import get_session
from models import User, Gender, ZodiacSignRu
from sqlalchemy import select
from datetime import datetime, timezone, date
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN, LOG_LEVEL, LOG_FORMAT
from geocoding import geocode_city_ru, GeocodingError
from timezone_utils import resolve_timezone, format_utc_offset

# Настройка логирования
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)

# Проверка токена перед созданием бота
if BOT_TOKEN in ["YOUR_BOT_TOKEN_HERE", "ваш_токен_здесь"]:
    print("❌ Ошибка: Не установлен токен бота!")
    print("Замените токен в .env файле на реальный токен от @BotFather")
    print("Токен должен выглядеть как: 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz")
    exit(1)

# Создание объектов бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    # Созраняем/обновляем пользователя в БД при первом запуске
    tg_user = message.from_user
    lang = (tg_user.language_code or "ru") if hasattr(tg_user, "language_code") else "ru"
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == tg_user.id))
        user = res.scalar_one_or_none()
        if user is None:
            user = User(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                lang=lang,
                joined_at=now,
                last_seen_at=now,
            )
            session.add(user)
        else:
            # Обновим базовые поля, если изменились, и отметим активность
            user.username = tg_user.username
            user.first_name = tg_user.first_name
            user.last_name = tg_user.last_name
            user.lang = lang or user.lang
            user.last_seen_at = now
    # Кнопка "Далее"
    next_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Далее", callback_data="next")]]
    )

    await message.answer(
        """Привет! Меня зовут Лилит 🐈‍⬛
Я умный бот-астролог на основе искусственного интеллекта 🤖🔮 


🫂 Стану твоим личным астро-помощником, которому можно задать любой вопрос в любое время 

🪐 С моей помощью тебе не нужно проверять точность построения твоей натальной карты – я уже позаботилась о достоверности

🧠 Я не копирую информацию из открытых источников – мои разборы основаны на опыте профессионального астролога и его работе с людьми

😎 Дам личные рекомендации по всем важным сферам: финансы, отношения, уверенность в себе и не только"""
        , reply_markup=next_kb
    )
    logger.info(f"Пользователь {message.from_user.id} запустил бота")


@dp.callback_query(F.data == "next")
async def on_next(callback: CallbackQuery):
    """Обработчик кнопки "Далее" — отправляет следующий текст и кнопку "Окей 👌🏼"""
    text = (
        "Теперь мне нужно узнать тебя получше, чтобы наши разговоры приносили тебе максимум пользы 🤗  \n\n"
        "\n✍🏼 Заполнишь небольшую анкету?\n\n"
        "*нажимая на кнопку, ты соглашаешься с Политикой конфиденциальности (https://disk.yandex.ru/i/DwatWs4N5h5HFA) — все твои данные будут надежно защищены 🔐🫱🏻‍🫲🏼\n"
    )

    ok_kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Окей 👌🏼", callback_data="ok")]]
    )

    await callback.message.answer(text, reply_markup=ok_kb, disable_web_page_preview=True)
    await callback.answer()


@dp.callback_query(F.data == "ok")
async def on_ok(callback: CallbackQuery):
    """После нажатия на "Окей" — старт анкеты, спрашиваем пол"""
    await callback.answer()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👩🏻 Женский", callback_data="gender:female")],
            [InlineKeyboardButton(text="👨🏼 Мужской", callback_data="gender:male")],
        ]
    )
    await callback.message.answer("Для начала укажи свой пол 👇🏼", reply_markup=kb)

class ProfileForm(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_birth_date = State()
    waiting_for_birth_city = State()
    waiting_for_birth_time_accuracy = State()
    waiting_for_birth_time_local = State()


def zodiac_sign_ru_for_date(d: date) -> ZodiacSignRu:
    """Определяет знак зодиака (на русском) по дате рождения.

    Диапазоны (включительно) по западной традиции:
    Козерог 22.12–19.01, Водолей 20.01–18.02, Рыбы 19.02–20.03,
    Овен 21.03–19.04, Телец 20.04–20.05, Близнецы 21.05–20.06,
    Рак 21.06–22.07, Лев 23.07–22.08, Дева 23.08–22.09,
    Весы 23.09–22.10, Скорпион 23.10–21.11, Стрелец 22.11–21.12.
    """
    m, day = d.month, d.day

    if   (m == 12 and day >= 22) or (m == 1 and day <= 19):
        return ZodiacSignRu.kozerog
    elif (m == 1 and day >= 20) or (m == 2 and day <= 18):
        return ZodiacSignRu.vodolei
    elif (m == 2 and day >= 19) or (m == 3 and day <= 20):
        return ZodiacSignRu.ryby
    elif (m == 3 and day >= 21) or (m == 4 and day <= 19):
        return ZodiacSignRu.oven
    elif (m == 4 and day >= 20) or (m == 5 and day <= 20):
        return ZodiacSignRu.telec
    elif (m == 5 and day >= 21) or (m == 6 and day <= 20):
        return ZodiacSignRu.bliznecy
    elif (m == 6 and day >= 21) or (m == 7 and day <= 22):
        return ZodiacSignRu.rak
    elif (m == 7 and day >= 23) or (m == 8 and day <= 22):
        return ZodiacSignRu.lev
    elif (m == 8 and day >= 23) or (m == 9 and day <= 22):
        return ZodiacSignRu.deva
    elif (m == 9 and day >= 23) or (m == 10 and day <= 22):
        return ZodiacSignRu.vesy
    elif (m == 10 and day >= 23) or (m == 11 and day <= 21):
        return ZodiacSignRu.skorpion
    else:  # (m == 11 and day >= 22) or (m == 12 and day <= 21)
        return ZodiacSignRu.strelec


# ======== Вопрос: Ваш пол ========
@dp.message(Command("gender"))
async def ask_gender(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Мужской", callback_data="gender:male")],
            [InlineKeyboardButton(text="Женский", callback_data="gender:female")],
        ]
    )
    await message.answer("Выберите ваш пол:", reply_markup=kb)


@dp.callback_query(F.data.startswith("gender:"))
async def set_gender(callback: CallbackQuery, state: FSMContext):
    _, value = callback.data.split(":", 1)
    if value not in {"male", "female"}:
        await callback.answer("Некорректное значение", show_alert=True)
        return

    tg_id = callback.from_user.id

    # Создаём/обновляем пользователя
    async with get_session() as session:
        from sqlalchemy import select
        res = await session.execute(select(User).where(User.telegram_id == tg_id))
        user = res.scalar_one_or_none()

        if user is None:
            await callback.answer("Сначала заполните анкету (дата рождения и т.д.)", show_alert=True)
            return

        user.gender = Gender(value)

    await callback.answer("Сохранено", show_alert=False)
    await callback.message.edit_reply_markup(reply_markup=None)
    # Следующий шаг анкеты — спросить имя
    await callback.message.answer("Как тебя зовут? 💫")
    # Переводим пользователя в состояние ожидания имени
    await state.set_state(ProfileForm.waiting_for_first_name)


@dp.message(ProfileForm.waiting_for_first_name)
async def receive_first_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("Пожалуйста, напиши своё имя текстом ✍️")
        return

    # Сохраняем в БД
    async with get_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if user is None:
            await message.answer("Похоже, анкета ещё не начата. Нажми /start 💫")
            await state.clear()
            return
        user.first_name = name

    # Переходим к вопросу о дате рождения
    await state.set_state(ProfileForm.waiting_for_birth_date)
    await message.answer(
        f"Очень приятно, {name}🙌🏼\n\n"
        "📆 Теперь напиши свою дату рождения в формате ДД.ММ.ГГГГ\n\n"
        "пример: 23.04.1987"
    )


@dp.message(ProfileForm.waiting_for_birth_date)
async def receive_birth_date(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    try:
        dt = datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(
            "Не получилось распознать дату. Пожалуйста, пришли в формате ДД.ММ.ГГГГ\n"
            "например: 23.04.1987"
        )
        return

    # Сохраняем дату рождения и знак зодиака
    async with get_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if user is None:
            await message.answer("Похоже, анкета ещё не начата. Нажми /start 💫")
            await state.clear()
            return
        user.birth_date = dt
        sign_enum = zodiac_sign_ru_for_date(dt)
        # Сохраняем именно enum-значение; тип колонки настроен хранить русские метки
        user.zodiac_sign = sign_enum

    # Спрашиваем место рождения, показывая знак
    sign = sign_enum.value
    await state.set_state(ProfileForm.waiting_for_birth_city)
    await message.answer(
        f"Понятно, значит ты у нас {sign} 🤭 интересно, что еще зашифровано в твоей карте \n\n\n"
        "📍 Далее напиши место своего рождения\n\n"
        "можно указать конкретный населенный пункт или же ближайший крупный город \n"
        "пример: г. Краснодар"
    )


@dp.message(ProfileForm.waiting_for_birth_city)
async def receive_birth_city(message: Message, state: FSMContext):
    city = (message.text or "").strip()
    if not city:
        await message.answer("Пожалуйста, укажи населённый пункт текстом ✍️")
        return

    # Пробуем геокодировать город (на русском) и сохранить координаты
    try:
        geo = await geocode_city_ru(city)
    except GeocodingError as e:
        logger.warning(f"Geocoding failed for '{city}': {e}")
        geo = None

    async with get_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if user is None:
            await message.answer("Похоже, анкета ещё не начата. Нажми /start 💫")
            await state.clear()
            return

        # Всегда сохраняем сырое пользовательское значение
        user.birth_city_input = city

        # Если геокодирование удалось — записываем нормализованное имя, страну и координаты
        if geo:
            user.birth_place_name = geo.get("place_name")
            user.birth_country_code = geo.get("country_code")
            user.birth_lat = geo.get("lat")
            user.birth_lon = geo.get("lon")
        else:
            # Сбрасываем на случай предыдущих значений
            user.birth_place_name = None
            user.birth_country_code = None
            user.birth_lat = None
            user.birth_lon = None

    if geo:
        place = geo["place_name"]
        lat = geo["lat"]
        lon = geo["lon"]
        await message.answer(
            f"Принято! Нашла: {place}\n"
            f"Координаты: {lat:.5f}, {lon:.5f} ✅"
        )
    else:
        await message.answer(
            "Принято! Но не удалось найти город по базе. "
            "Можешь попробовать указать иначе (например: 'Россия, Краснодар') или выбрать ближайший крупный город."
        )

    # Следующий шаг — спросить про время рождения
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👍🏼 Знаю точное время", callback_data="timeacc:exact")],
            [InlineKeyboardButton(text="🤏🏼 Знаю примерное время", callback_data="timeacc:approx")],
            [InlineKeyboardButton(text="👎🏼 Не знаю время вообще", callback_data="timeacc:unknown")],
        ]
    )
    await message.answer(
        "Для полной информации мне не хватает только времени рождения 🪄  \n\n\n"
        "🕰 Подскажи, знаешь ли ты время своего рождения?",
        reply_markup=kb,
    )
    await state.set_state(ProfileForm.waiting_for_birth_time_accuracy)


@dp.callback_query(F.data.startswith("timeacc:"))
async def set_birth_time_accuracy(callback: CallbackQuery, state: FSMContext):
    _, value = callback.data.split(":", 1)
    if value not in {"exact", "approx", "unknown"}:
        await callback.answer("Некорректный выбор", show_alert=True)
        return

    # Для сценария "unknown" ничего не пишем в БД — только отправляем сообщение
    if value != "unknown":
        async with get_session() as session:
            res = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
            user = res.scalar_one_or_none()
            if user is None:
                await callback.answer("Похоже, анкета ещё не начата. Нажми /start 💫", show_alert=True)
                await state.clear()
                return
            user.birth_time_accuracy = value

    # Убираем клавиатуру под сообщением
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Дальнейшие шаги в зависимости от выбора
    if value == "exact":
        # Просим ввести точное время рождения в формате ЧЧ:ММ
        await callback.message.answer(
            "Супер! 🤌🏼  \n\n"
            "тогда напиши время своего рождения по бирке/справке в формате ЧЧ:ММ\n\n"
            "пример: 10:38"
        )
        await state.set_state(ProfileForm.waiting_for_birth_time_local)
    elif value == "approx":
        await callback.message.answer(
            "Принято! ✌🏼  \n\n"
            "🕰 Напиши примерное время своего рождения в формате ЧЧ:ММ\n\n"
            "пример: 11:00"
        )
        await state.set_state(ProfileForm.waiting_for_birth_time_local)
    else:  # unknown
        await callback.message.answer(
            "Принято! 🔮  \n\n"
            "Ничего страшного, если ты не знаешь время своего рождения 👌🏼 \n"
            "Информация будет чуть менее детальной, но все равно абсолютно точной! 💯🚀"
        )
        await state.clear()

    await callback.answer()


@dp.message(ProfileForm.waiting_for_birth_time_local)
async def receive_birth_time_local(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    from datetime import datetime as dt_mod
    try:
        # Принимаем формат ЧЧ:ММ
        t = dt_mod.strptime(text, "%H:%M").time()
    except ValueError:
        await message.answer(
            "Не получилось распознать время. Пожалуйста, пришли в формате ЧЧ:ММ\n"
            "например: 10:38"
        )
        return

    async with get_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if user is None:
            await message.answer("Похоже, анкета ещё не начата. Нажми /start 💫")
            await state.clear()
            return
        user.birth_time_local = t
        # Не меняем birth_time_accuracy — оно уже сохранено выбором пользователя

        # Пытаемся определить часовой пояс и UTC-смещение, если есть координаты и дата
        try:
            if user.birth_date and user.birth_lat is not None and user.birth_lon is not None:
                tzres = resolve_timezone(user.birth_lat, user.birth_lon, user.birth_date, t)
                if tzres:
                    user.tzid = tzres.tzid
                    user.tz_offset_minutes = tzres.offset_minutes
                    user.birth_datetime_utc = tzres.birth_datetime_utc
                    tz_label = f"{tzres.tzid} ({format_utc_offset(tzres.offset_minutes)})"
                    await message.answer(
                        "Отлично, сохранила твоё время рождения ⏱✅\n"
                        f"Часовой пояс: {tz_label}"
                    )
                else:
                    await message.answer(
                        "Отлично, сохранила твоё время рождения ⏱✅\n"
                        "Не удалось автоматически определить часовой пояс по координатам."
                    )
            else:
                await message.answer(
                    "Отлично, сохранила твоё время рождения ⏱✅\n"
                    "Для определения часового пояса нужны дата и координаты места рождения."
                )
        except Exception as e:
            logger.warning(f"Timezone resolve failed: {e}")
            await message.answer(
                "Отлично, сохранила твоё время рождения ⏱✅\n"
                "Но не удалось определить часовой пояс автоматически."
            )
    await state.clear()

@dp.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = """
🔮 Я бот астролог

Доступные команды:
/start - Запустить бота
/help - Показать это сообщение

Я помогу вам с астрологическими вопросами!
    """
    await message.answer(help_text)

@dp.message()
async def echo_message(message: Message):
    """Обработчик всех остальных сообщений"""
    # Обновляем последнюю активность пользователя
    from sqlalchemy import select
    from datetime import datetime, timezone
    async with get_session() as session:
        res = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = res.scalar_one_or_none()
        if user is not None:
            user.last_seen_at = datetime.now(timezone.utc)

    await message.answer("Привет! Я бот астролог. Используйте /help для списка команд.")

async def main():
    """Основная функция запуска бота"""
    logger.info("Запуск бота...")
    # Инициализируем подключение к БД и создаём таблицы при необходимости
    init_engine()
    from db import engine as _engine
    db_engine: AsyncEngine = _engine  # type: ignore[assignment]

    # Автоинициализация схемы (однократно/идемпотентно):
    try:
        await ensure_gender_enum(db_engine)
        await ensure_birth_date_nullable(db_engine)
        await ensure_zodiac_enum_ru(db_engine)
        # create_all безопасен: создаст отсутствующие таблицы, существующие не тронет
        await create_all(db_engine)
    except Exception as e:
        logger.error(f"Не удалось инициализировать схему БД: {e}")

    try:
        # Запуск бота
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()
        await dispose_engine()

if __name__ == "__main__":
    # Запуск бота
    asyncio.run(main())
