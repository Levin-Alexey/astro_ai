import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    User as TgUser,
)
from aiogram.fsm.context import FSMContext
from typing import cast, Optional
from db import (
    init_engine,
    dispose_engine,
    ensure_gender_enum,
    ensure_birth_date_nullable,
    ensure_zodiac_enum_ru,
    ensure_planet_enum,
    ensure_prediction_type_enum,
    ensure_payment_type_enum,
    ensure_payment_status_enum,
)
from models import create_all
from sqlalchemy.ext.asyncio import AsyncEngine
from db import get_session
from models import (
    User as DbUser,
    Gender,
    ZodiacSignRu,
    Prediction,
    Planet,
    PredictionType,
)
from sqlalchemy import select
from datetime import datetime, timezone, date
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN, LOG_LEVEL, LOG_FORMAT
from geocoding import geocode_city_ru, GeocodingError
from timezone_utils import resolve_timezone, format_utc_offset
from astrology_handlers import (
    start_moon_analysis,
    check_existing_moon_prediction
)
from handlers.recommendations_handler import handle_get_recommendations
from handlers.sun_recommendations_handler import handle_get_sun_recommendations
from handlers.mercury_recommendations_handler import (
    handle_get_mercury_recommendations
)
from handlers.venus_recommendations_handler import (
    handle_get_venus_recommendations
)
from handlers.mars_recommendations_handler import (
    handle_get_mars_recommendations
)
from handlers.ask_question_handler import handle_ask_question
from handlers.support_handler import SupportForm
from handlers.additional_profile_handler import (
    AdditionalProfileForm,
    start_additional_profile_creation,
    handle_additional_name,
    handle_additional_birth_date,
    handle_additional_birth_city,
    handle_additional_birth_time_accuracy_callback,
    handle_additional_birth_time_local,
    handle_additional_gender_callback,
    handle_additional_birth_date_callback,
    handle_additional_birth_city_callback,
    handle_additional_birth_time_callback,
    handle_additional_profile_cancel,
    handle_additional_time_unknown_callback,
)
from payment_handler import init_payment_handler
from all_planets_handler import init_all_planets_handler

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

# Глобальная переменная для payment_handler
payment_handler = None


@dp.message(Command("lk"))
async def cmd_lk(message: Message, state: FSMContext):
    """Обработчик команды /lk - личный кабинет"""
    # Сбрасываем состояние FSM при переходе в личный кабинет
    await state.clear()
    await show_personal_cabinet(message)


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    # Сбрасываем состояние FSM при перезапуске
    await state.clear()
    
    # Созраняем/обновляем пользователя в БД при первом запуске
    tg_user = cast(TgUser, message.from_user)
    lang = tg_user.language_code or "ru"
    now = datetime.now(timezone.utc)
    async with get_session() as session:
        res = await session.execute(
            select(DbUser).where(DbUser.telegram_id == tg_user.id)
        )
        user = res.scalar_one_or_none()
        if user is None:
            user = DbUser(
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

    # Проверяем, есть ли у пользователя уже бесплатный разбор Луны
    has_moon_analysis = await check_existing_moon_prediction(tg_user.id)

    if has_moon_analysis:
        # Если разбор есть, показываем главное меню
        await show_main_menu(message)
        logger.info(
            f"Пользователь {tg_user.id} с существующим разбором "
            "показано главное меню"
        )
    else:
        # Если разбора нет, запускаем стандартный опросник
        # Первое сообщение
        await message.answer(
            (
                "Привет! Меня зовут Лилит 🐈‍⬛\n"
                "Я умный бот-астролог на основе искусственного интеллекта "
                "🤖🔮\n\n"
                "🫂 Стану твоим личным астро-помощником, которому можно задать "
                "любой вопрос в любое время\n\n"
                "🪐 С моей помощью тебе не нужно проверять точность "
                "построения твоей натальной карты – я уже позаботилась о "
                "достоверности\n\n"
                "🧠 Я не копирую информацию из открытых источников – мои "
                "разборы основаны на опыте профессионального астролога и его "
                "работе с людьми\n\n"
                "😎 Дам личные рекомендации по всем важным сферам: финансы, "
                "отношения, уверенность в себе и не только"
            )
        )

        # Второе сообщение с кнопками
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Политика конфиденциальности",
                        url="https://disk.yandex.ru/i/DwatWs4N5h5HFA"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Окей 👌🏼",
                        callback_data="ok",
                    )
                ]
            ]
        )

        await message.answer(
            (
                "Теперь мне нужно узнать тебя получше, чтобы наши разговоры "
                "приносили тебе максимум пользы 🤗\n\n"
                "✍🏼 Заполнишь небольшую анкету?\n\n"
                "нажимая на кнопку, ты соглашаешься с "
                "Политикой конфиденциальности "
                "— все твои данные будут надежно защищены 🔐🫱🏻‍🫲🏼"
            ),
            reply_markup=kb,
        )
        logger.info(f"Пользователь {tg_user.id} без разбора запустил анкету")


@dp.callback_query(F.data == "ok")
async def on_ok(callback: CallbackQuery):
    """После нажатия на "Окей" — старт анкеты, спрашиваем пол"""
    await callback.answer()
    kb = build_gender_kb(selected=None)
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        "Для начала укажи свой пол 👇🏼",
        reply_markup=kb,
    )


@dp.callback_query(F.data == "start_new_analysis")
async def on_start_new_analysis(callback: CallbackQuery):
    """Обработчик кнопки 'Да, начать анкету' для нового разбора"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        "🆕 Начинаем новый разбор!\n\n"
        "Для начала укажи свой пол 👇🏼",
        reply_markup=build_gender_kb(selected=None)
    )


class ProfileForm(StatesGroup):
    waiting_for_first_name = State()
    waiting_for_birth_date = State()
    waiting_for_birth_city = State()
    waiting_for_birth_city_confirm = State()
    waiting_for_birth_time_accuracy = State()
    waiting_for_birth_time_local = State()
    waiting_for_birth_time_confirm = State()
    waiting_for_birth_time_approx_confirm = State()
    waiting_for_birth_time_unknown_confirm = State()


class QuestionForm(StatesGroup):
    waiting_for_question = State()


def build_gender_kb(selected: str | None) -> InlineKeyboardMarkup:
    """
    Строит клавиатуру выбора пола. Если selected задан — добавляет чек и
    кнопку 'Подтвердить'.
    """
    female_text = ("✅ " if selected == "female" else "") + "👩🏻 Женский"
    male_text = ("✅ " if selected == "male" else "") + "👨🏼 Мужской"

    rows = [
        [
            InlineKeyboardButton(
                text=female_text, callback_data="gender:female"
            )
        ],
        [
            InlineKeyboardButton(
                text=male_text, callback_data="gender:male"
            )
        ],
    ]
    if selected in {"male", "female"}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Подтвердить", callback_data="gender_confirm"
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_personal_cabinet(message_or_callback):
    """Показывает личный кабинет пользователя"""
    # Определяем тип объекта (Message или CallbackQuery)
    if hasattr(message_or_callback, 'from_user'):
        # Это CallbackQuery
        user_id = message_or_callback.from_user.id if message_or_callback.from_user else 0
        cb_msg = cast(Message, message_or_callback.message)
        answer_method = cb_msg.answer
    else:
        # Это Message
        user_id = message_or_callback.from_user.id if message_or_callback.from_user else 0
        answer_method = message_or_callback.answer
    
    try:
        # Получаем информацию о пользователе из БД
        from db import get_session
        from models import User, Prediction
        from sqlalchemy import select, func
        
        async with get_session() as session:
            # Находим пользователя
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                await answer_method(
                    "❌ Пользователь не найден в базе данных.\n"
                    "Попробуйте перезапустить бота командой /start"
                )
                return
            
            # Получаем статистику разборов
            predictions_result = await session.execute(
                select(
                    Prediction.planet,
                    Prediction.prediction_type,
                    func.count(Prediction.prediction_id).label('count')
                )
                .where(
                    Prediction.user_id == user.user_id,
                    Prediction.is_deleted.is_(False)
                )
                .group_by(Prediction.planet, Prediction.prediction_type)
            )
            predictions_stats = predictions_result.fetchall()
            
            # Формируем информацию о пользователе
            profile_info = []
            if user.full_name:
                profile_info.append(f"📝 Имя: {user.full_name}")
            if user.gender and user.gender != "unknown":
                gender_emoji = {"male": "👨", "female": "👩", "other": "🧑"}.get(user.gender.value, "❓")
                gender_text = {"male": "Мужской", "female": "Женский", "other": "Другой"}.get(user.gender.value, "Не указан")
                profile_info.append(f"{gender_emoji} Пол: {gender_text}")
            if user.birth_date:
                profile_info.append(f"🎂 Дата рождения: {user.birth_date.strftime('%d.%m.%Y')}")
            if user.birth_place_name:
                profile_info.append(f"📍 Место рождения: {user.birth_place_name}")
            if user.zodiac_sign:
                profile_info.append(f"♈ Знак зодиака: {user.zodiac_sign.value}")
            
            # Формируем статистику разборов
            analysis_stats = []
            planet_emojis = {
                "moon": "🌙", "sun": "☀️", "mercury": "☿️", 
                "venus": "♀️", "mars": "♂️"
            }
            
            total_analyses = 0
            for stat in predictions_stats:
                planet = stat.planet.value
                prediction_type = stat.prediction_type.value
                count = stat.count
                total_analyses += count
                
                emoji = planet_emojis.get(planet, "🪐")
                type_text = "Бесплатный" if prediction_type == "free" else "Платный"
                analysis_stats.append(f"{emoji} {planet.title()}: {count} ({type_text})")
            
            # Формируем текст сообщения
            text_parts = ["👤 **Личный кабинет**\n"]
            
            if profile_info:
                text_parts.append("**📋 Профиль:**")
                text_parts.extend(profile_info)
                text_parts.append("")
            
            text_parts.append(f"**📊 Статистика разборов:**")
            text_parts.append(f"Всего разборов: {total_analyses}")
            
            if analysis_stats:
                text_parts.append("")
                for stat in analysis_stats:
                    text_parts.append(f"• {stat}")
            else:
                text_parts.append("• Разборов пока нет")
            
            text_parts.append("")
            text_parts.append("**💡 Доступные действия:**")
            text_parts.append("• Задать вопрос астрологу")
            text_parts.append("• Купить новые разборы")
            text_parts.append("• Начать разбор по новой дате")
            
            # Создаем клавиатуру с действиями
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="❓ Задать вопрос",
                            callback_data="ask_question"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="💳 Купить разбор",
                            callback_data="buy_analysis"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🆕 Новый разбор",
                            callback_data="new_analysis"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data="back_to_menu"
                        )
                    ]
                ]
            )
            
            await answer_method(
                "\n".join(text_parts),
                reply_markup=kb,
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"Ошибка в личном кабинете для пользователя {user_id}: {e}")
        await answer_method(
            "❌ Произошла ошибка при загрузке личного кабинета.\n"
            "Попробуйте позже или обратитесь в службу заботы."
        )


async def show_main_menu(message_or_callback):
    """Показывает главное меню с кнопками для пользователей с существующим
    разбором"""
    text = (
        "🔮 Добро пожаловать в главное меню!\n\n"
        "Выбери, что тебя интересует:"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👤 Личный кабинет",
                    callback_data="personal_cabinet"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❓ Задать вопрос",
                    callback_data="ask_question"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💳 Купить разбор", callback_data="buy_analysis"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🆕 Начать разбор по новой дате",
                    callback_data="new_analysis"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❓ FAQ", callback_data="faq"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🆘 Служба заботы", callback_data="support"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑️ Удалить разборы", 
                    callback_data="delete_predictions"
                )
            ]
        ]
    )

    if hasattr(message_or_callback, 'message'):
        # Это callback
        cb_msg = cast(Message, message_or_callback.message)
        await cb_msg.answer(text, reply_markup=kb)
    else:
        # Это message
        await message_or_callback.answer(text, reply_markup=kb)


async def show_profile_completion_message(message_or_callback):
    """Показывает финальное сообщение после завершения анкеты"""
    text = (
        "Смотри, я предлагаю начать нашу работу с тебя, а именно с разбора "
        "твоей Луны 🌙\n\n"
        "Объясню почему👇🏼\n\n"
        "🌒 Луна включается еще в утробе матери и работает всю жизнь, от неё "
        "зависят твои эмоции, характер, то, как ты воспринимаешь мир и даже "
        "отношения в семье\n\n"
        "🌓 Эта планета является фундаментом твоего внутреннего мира: если он "
        "не прочен, остальные планеты работать просто не будут и нет смысла "
        "разбирать всеми любимых Венеру и Асцендент ;)\n\n"
        "🌔 Пока все бегут, спешат и забывают про себя, ты сможешь не бояться "
        "выгорания на работе, что очень важно с нашей тенденцией к "
        "достигаторству, согласись?\n\n"
        "🌕 Никаких больше эмоциональных качелей — только спокойное и "
        "уверенное движение по жизни"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Начнем", callback_data="start_moon_analysis"
                )
            ]
        ]
    )

    if hasattr(message_or_callback, 'answer'):
        # Это callback
        cb_msg = cast(Message, message_or_callback.message)
        await cb_msg.answer(text, reply_markup=kb)
    else:
        # Это message
        await message_or_callback.answer(text, reply_markup=kb)


def zodiac_sign_ru_for_date(d: date) -> ZodiacSignRu:
    """Определяет знак зодиака (на русском) по дате рождения.

    Диапазоны (включительно) по западной традиции:
    Козерог 22.12–19.01, Водолей 20.01–18.02, Рыбы 19.02–20.03,
    Овен 21.03–19.04, Телец 20.04–20.05, Близнецы 21.05–20.06,
    Рак 21.06–22.07, Лев 23.07–22.08, Дева 23.08–22.09,
    Весы 23.09–22.10, Скорпион 23.10–21.11, Стрелец 22.11–21.12.
    """
    m, day = d.month, d.day

    if (m == 12 and day >= 22) or (m == 1 and day <= 19):
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
            [
                InlineKeyboardButton(
                    text="Мужской", callback_data="gender:male"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Женский", callback_data="gender:female"
                )
            ],
        ]
    )
    await message.answer("Выберите ваш пол:", reply_markup=kb)


@dp.callback_query(F.data.startswith("gender:"))
async def set_gender(callback: CallbackQuery, state: FSMContext):
    cb_data = cast(str, callback.data)
    _, value = cb_data.split(":", 1)
    if value not in {"male", "female"}:
        await callback.answer("Некорректное значение", show_alert=True)
        return

    # Запоминаем выбор пола во временном состоянии, не сохраняем в БД сразу
    await state.update_data(pending_gender=value)

    # Оставляем кнопки пола и помечаем выбранный чек‑маркой + добавляем
    # кнопку "Подтвердить"
    kb = build_gender_kb(selected=value)
    try:
        cb_msg = cast(Message, callback.message)
        await cb_msg.edit_reply_markup(reply_markup=kb)
    except Exception:
        cb_msg = cast(Message, callback.message)
        await cb_msg.answer("Подтверди выбор пола", reply_markup=kb)
    await callback.answer()


# Callback обработчики для дополнительного профиля
@dp.callback_query(F.data.startswith("additional_gender:"))
async def handle_additional_gender_callback_wrapper(callback: CallbackQuery, state: FSMContext):
    """Обертка для обработчика выбора пола дополнительного профиля"""
    await handle_additional_gender_callback(callback, state)


@dp.callback_query(F.data.startswith("additional_birth_date:"))
async def handle_additional_birth_date_callback_wrapper(callback: CallbackQuery, state: FSMContext):
    """Обертка для обработчика подтверждения даты рождения дополнительного профиля"""
    await handle_additional_birth_date_callback(callback, state)


@dp.callback_query(F.data.startswith("additional_city:"))
async def handle_additional_birth_city_callback_wrapper(callback: CallbackQuery, state: FSMContext):
    """Обертка для обработчика подтверждения города дополнительного профиля"""
    await handle_additional_birth_city_callback(callback, state)


@dp.callback_query(F.data.startswith("additional_birth_time:"))
async def handle_additional_birth_time_callback_wrapper(callback: CallbackQuery, state: FSMContext):
    """Обертка для обработчика подтверждения времени рождения дополнительного профиля"""
    await handle_additional_birth_time_callback(callback, state)


@dp.callback_query(F.data.startswith("additional_time_unknown:"))
async def handle_additional_time_unknown_callback_wrapper(callback: CallbackQuery, state: FSMContext):
    """Обертка для обработчика неизвестного времени дополнительного профиля"""
    await handle_additional_time_unknown_callback(callback, state)


@dp.callback_query(F.data == "additional_profile:cancel")
async def handle_additional_profile_cancel_wrapper(callback: CallbackQuery, state: FSMContext):
    """Обертка для обработчика отмены создания дополнительного профиля"""
    await handle_additional_profile_cancel(callback, state)


@dp.callback_query(F.data.startswith("additional_timeacc:"))
async def handle_additional_birth_time_accuracy_callback_wrapper(callback: CallbackQuery, state: FSMContext):
    """Обертка для обработчика выбора точности времени рождения дополнительного профиля"""
    await handle_additional_birth_time_accuracy_callback(callback, state)


@dp.callback_query(F.data == "gender_confirm")
async def confirm_gender(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    value = data.get("pending_gender")
    if value not in {"male", "female"}:
        await callback.answer("Сначала выбери пол", show_alert=True)
        return
    cb_user = cast(TgUser, callback.from_user)
    tg_id = cb_user.id

    # Сохраняем выбор в БД
    async with get_session() as session:
        res = await session.execute(
            select(DbUser).where(DbUser.telegram_id == tg_id)
        )
        user = res.scalar_one_or_none()
        if user is None:
            await callback.answer(
                "Сначала запусти анкету: /start", show_alert=True
            )
            await state.clear()
            return
        user.gender = Gender(value)

    # Очищаем временные данные о поле
    await state.update_data(pending_gender=None)

    # Убираем клавиатуру подтверждения
    try:
        cb_msg = cast(Message, callback.message)
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Следующий шаг анкеты — спросить имя
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer("Как тебя зовут? 💫")
    await state.set_state(ProfileForm.waiting_for_first_name)
    await callback.answer("Сохранено")


@dp.message(ProfileForm.waiting_for_first_name)
async def receive_first_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("Пожалуйста, напиши своё имя текстом ✍️")
        return

    # Сохраняем в БД
    async with get_session() as session:
        uid = cast(TgUser, message.from_user).id
        res = await session.execute(
            select(DbUser).where(DbUser.telegram_id == uid)
        )
        user = res.scalar_one_or_none()
        if user is None:
            await message.answer(
                "Похоже, анкета ещё не начата. Нажми /start 💫"
            )
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
            "Не получилось распознать дату. Пожалуйста, пришли в формате "
            "ДД.ММ.ГГГГ\nнапример: 23.04.1987"
        )
        return
    # Сохраняем дату временно и предлагаем подтвердить
    await state.update_data(pending_birth_date=dt.isoformat())

    date_str = dt.strftime("%d.%m.%Y")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Верно", callback_data="bdate:confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Ввести заново", callback_data="bdate:redo"
                )
            ],
        ]
    )
    await message.answer(
        f"Дата рождения: {date_str} -\n" "Верно? Нажми кнопку 👇🏼",
        reply_markup=kb,
    )
    # Остаёмся в состоянии ожидания даты до подтверждения/переввода
    await state.set_state(ProfileForm.waiting_for_birth_date)


@dp.callback_query(F.data == "bdate:confirm")
async def on_birth_date_confirm(
    callback: CallbackQuery, state: FSMContext
):
    # Подтверждение: записать дату, определить знак и перейти к городу
    data = await state.get_data()
    iso = data.get("pending_birth_date")
    if not iso:
        await callback.answer(
            "Не нашла дату. Пожалуйста, введите снова.",
            show_alert=True,
        )
        return

    from datetime import date as _date
    try:
        dt = _date.fromisoformat(iso)
    except Exception:
        await callback.answer(
            "Формат даты потерялся, введите дату ещё раз.",
            show_alert=True,
        )
        return

    cb_user = cast(TgUser, callback.from_user)
    async with get_session() as session:
        res = await session.execute(
            select(DbUser).where(DbUser.telegram_id == cb_user.id)
        )
        user = res.scalar_one_or_none()
        if user is None:
            await callback.answer(
                "Похоже, анкета ещё не начата. Нажми /start 💫",
                show_alert=True,
            )
            await state.clear()
            return
        user.birth_date = dt
        sign_enum = zodiac_sign_ru_for_date(dt)
        user.zodiac_sign = sign_enum

    await state.update_data(pending_birth_date=None)
    await state.set_state(ProfileForm.waiting_for_birth_city)

    cb_msg = cast(Message, callback.message)
    sign = sign_enum.value
    await cb_msg.answer(
        f"Понятно, значит ты у нас {sign} 🤭 интересно, что еще "
        "зашифровано в твоей карте \n\n\n"
        "📍 Далее напиши место своего рождения\n\n"
        "можно указать конкретный населенный пункт или же ближайший "
        "крупный город \n"
        "пример: г. Краснодар"
    )
    try:
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()


@dp.callback_query(F.data == "bdate:redo")
async def on_birth_date_redo(callback: CallbackQuery, state: FSMContext):
    # Просим ввести дату снова
    await state.update_data(pending_birth_date=None)
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        "Окей! Пришли дату рождения в формате ДД.ММ.ГГГГ\n"
        "например: 23.04.1987"
    )
    try:
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.set_state(ProfileForm.waiting_for_birth_date)
    await callback.answer()


@dp.message(ProfileForm.waiting_for_birth_city)
async def receive_birth_city(message: Message, state: FSMContext):
    city = (message.text or "").strip()
    if not city:
        await message.answer("Пожалуйста, укажи населённый пункт текстом ✍️")
        return

    # Пробуем геокодировать город (на русском)
    try:
        geo = await geocode_city_ru(city)
    except GeocodingError as e:
        logger.warning(f"Geocoding failed for '{city}': {e}")
        geo = None

    # Сохраняем данные временно для подтверждения
    city_data = {
        "city_input": city,
        "geo": geo
    }
    await state.update_data(pending_birth_city=city_data)

    # Показываем что нашли и просим подтвердить
    if geo:
        place = geo["place_name"]
        display_text = f"Место рождения: {place}\nВерно? Нажми кнопку 👇🏼"
    else:
        display_text = f"Место рождения: {city}\nВерно? Нажми кнопку 👇🏼"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Верно", callback_data="bcity:confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Ввести заново", callback_data="bcity:redo"
                )
            ],
        ]
    )
    await message.answer(display_text, reply_markup=kb)
    await state.set_state(ProfileForm.waiting_for_birth_city_confirm)


@dp.callback_query(F.data == "bcity:confirm")
async def on_birth_city_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение места рождения: сохраняем данные и переходим к времени"""
    data = await state.get_data()
    city_data = data.get("pending_birth_city")
    if not city_data:
        await callback.answer(
            "Не нашла данные о городе. Пожалуйста, введите снова.",
            show_alert=True,
        )
        return

    city_input = city_data["city_input"]
    geo = city_data["geo"]

    cb_user = cast(TgUser, callback.from_user)
    async with get_session() as session:
        res = await session.execute(
            select(DbUser).where(DbUser.telegram_id == cb_user.id)
        )
        user = res.scalar_one_or_none()
        if user is None:
            await callback.answer(
                "Похоже, анкета ещё не начата. Нажми /start 💫",
                show_alert=True,
            )
            await state.clear()
            return

        # Сохраняем данные в БД
        user.birth_city_input = city_input

        # Если геокодирование удалось — записываем нормализованное имя,
        # страну и координаты
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

    # Очищаем временные данные
    await state.update_data(pending_birth_city=None)

    # Убираем клавиатуру
    try:
        cb_msg = cast(Message, callback.message)
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Показываем результат и переходим к следующему шагу
    if geo:
        place = geo["place_name"]
        lat = geo["lat"]
        lon = geo["lon"]
        cb_msg = cast(Message, callback.message)
        await cb_msg.answer(
            f"Принято! Нашла: {place}\n"
            f"Координаты: {lat:.5f}, {lon:.5f} ✅"
        )
    else:
        cb_msg = cast(Message, callback.message)
        await cb_msg.answer(
            "Принято! Но не удалось найти город по базе. "
            "Можешь попробовать указать иначе (например: 'Россия, Краснодар') "
            "или выбрать ближайший крупный город."
        )

    # Следующий шаг — спросить про время рождения
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👍🏼 Знаю точное время",
                    callback_data="timeacc:exact",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤏🏼 Знаю примерное время",
                    callback_data="timeacc:approx",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👎🏼 Не знаю время вообще",
                    callback_data="timeacc:unknown",
                )
            ],
        ]
    )
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        "Для полной информации мне не хватает только времени рождения "
        "🪄  \n\n\n"
        "🕰 Подскажи, знаешь ли ты время своего рождения?",
        reply_markup=kb,
    )
    await state.set_state(ProfileForm.waiting_for_birth_time_accuracy)
    await callback.answer()


@dp.callback_query(F.data == "bcity:redo")
async def on_birth_city_redo(callback: CallbackQuery, state: FSMContext):
    """Просим ввести место рождения заново"""
    await state.update_data(pending_birth_city=None)
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        "Окей! Пришли место своего рождения\n"
        "можно указать конкретный населенный пункт или же ближайший "
        "крупный город\n"
        "пример: г. Краснодар"
    )
    try:
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.set_state(ProfileForm.waiting_for_birth_city)
    await callback.answer()


@dp.callback_query(F.data.startswith("timeacc:"))
async def set_birth_time_accuracy(callback: CallbackQuery, state: FSMContext):
    cb_data = cast(str, callback.data)
    _, value = cb_data.split(":", 1)
    if value not in {"exact", "approx", "unknown"}:
        await callback.answer("Некорректный выбор", show_alert=True)
        return

    # Для сценария "unknown" ничего не пишем в БД — только отправляем сообщение
    if value != "unknown":
        async with get_session() as session:
            cb_user = cast(TgUser, callback.from_user)
            res = await session.execute(
                select(DbUser).where(
                    DbUser.telegram_id == cb_user.id
                )
            )
            user = res.scalar_one_or_none()
            if user is None:
                await callback.answer(
                    "Похоже, анкета ещё не начата. Нажми /start 💫",
                    show_alert=True,
                )
                await state.clear()
                return
            user.birth_time_accuracy = value

    # Убираем клавиатуру под сообщением
    try:
        cb_msg = cast(Message, callback.message)
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Дальнейшие шаги в зависимости от выбора
    if value == "exact":
        # Просим ввести точное время рождения в формате ЧЧ:ММ
        await state.update_data(time_accuracy_type="exact")
        cb_msg = cast(Message, callback.message)
        await cb_msg.answer(
            "Супер! 🤌🏼  \n\n"
            + "тогда напиши время своего рождения по бирке/справке "
            + "в формате ЧЧ:ММ\n\n"
            + "пример: 10:38"
        )
        await state.set_state(ProfileForm.waiting_for_birth_time_local)
    elif value == "approx":
        await state.update_data(time_accuracy_type="approx")
        cb_msg = cast(Message, callback.message)
        await cb_msg.answer(
            "Принято! ✌🏼  \n\n"
            "🕰 Напиши примерное время своего рождения в формате ЧЧ:ММ\n\n"
            "пример: 11:00"
        )
        await state.set_state(ProfileForm.waiting_for_birth_time_local)
    else:  # unknown
        # Показываем подтверждение для работы без времени
        display_text = "Работаем без времени рождения\nВерно? Нажми кнопку 👇🏼"

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Верно", callback_data="btime_unknown:confirm"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 Указать время",
                        callback_data="btime_unknown:specify"
                    )
                ],
            ]
        )

        cb_msg = cast(Message, callback.message)
        await cb_msg.answer(display_text, reply_markup=kb)
        await state.set_state(
            ProfileForm.waiting_for_birth_time_unknown_confirm
        )

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
            "Не получилось распознать время. Пожалуйста, пришли в формате "
            "ЧЧ:ММ\n"
            "например: 10:38"
        )
        return

    # Получаем тип точности времени
    data = await state.get_data()
    time_accuracy_type = data.get("time_accuracy_type", "exact")

    # Сохраняем время временно для подтверждения
    await state.update_data(pending_birth_time=t.isoformat())

    # Показываем подтверждение в зависимости от типа
    time_str = t.strftime("%H:%M")
    if time_accuracy_type == "exact":
        display_text = (
            f"Точное время рождения: {time_str}\nВерно? Нажми кнопку 👇🏼"
        )
        next_state = ProfileForm.waiting_for_birth_time_confirm
        callback_data = "btime:confirm"
        redo_callback_data = "btime:redo"
    else:  # approx
        display_text = (
            f"Примерное время рождения: {time_str}\nВерно? Нажми кнопку 👇🏼"
        )
        next_state = ProfileForm.waiting_for_birth_time_approx_confirm
        callback_data = "btime_approx:confirm"
        redo_callback_data = "btime_approx:redo"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Верно", callback_data=callback_data
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Ввести заново", callback_data=redo_callback_data
                )
            ],
        ]
    )
    await message.answer(display_text, reply_markup=kb)
    await state.set_state(next_state)


@dp.callback_query(F.data == "btime:confirm")
async def on_birth_time_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение времени рождения: сохраняем данные и завершаем анкету"""
    data = await state.get_data()
    time_iso = data.get("pending_birth_time")
    if not time_iso:
        await callback.answer(
            "Не нашла время. Пожалуйста, введите снова.",
            show_alert=True,
        )
        return

    from datetime import time as _time
    try:
        t = _time.fromisoformat(time_iso)
    except Exception:
        await callback.answer(
            "Формат времени потерялся, введите время ещё раз.",
            show_alert=True,
        )
        return

    cb_user = cast(TgUser, callback.from_user)
    async with get_session() as session:
        res = await session.execute(
            select(DbUser).where(DbUser.telegram_id == cb_user.id)
        )
        user = res.scalar_one_or_none()
        if user is None:
            await callback.answer(
                "Похоже, анкета ещё не начата. Нажми /start 💫",
                show_alert=True,
            )
            await state.clear()
            return

        # Сохраняем время в БД
        user.birth_time_local = t

        # Пытаемся определить часовой пояс и UTC-смещение, если есть
        # координаты и дата
        try:
            if (
                user.birth_date
                and user.birth_lat is not None
                and user.birth_lon is not None
            ):
                tzres = resolve_timezone(
                    user.birth_lat, user.birth_lon, user.birth_date, t
                )
                if tzres:
                    user.tzid = tzres.tzid
                    user.tz_offset_minutes = tzres.offset_minutes
                    user.birth_datetime_utc = tzres.birth_datetime_utc
                    tz_label = (
                        f"{tzres.tzid} "
                        f"({format_utc_offset(tzres.offset_minutes)})"
                    )
                    cb_msg = cast(Message, callback.message)
                    await cb_msg.answer(
                        "Отлично, сохранила твоё время рождения ⏱✅\n"
                        f"Часовой пояс: {tz_label}"
                    )
                else:
                    cb_msg = cast(Message, callback.message)
                    await cb_msg.answer(
                        "Отлично, сохранила твоё время рождения ⏱✅\n"
                        "Не удалось автоматически определить часовой пояс "
                        "по координатам."
                    )
            else:
                cb_msg = cast(Message, callback.message)
                await cb_msg.answer(
                    "Отлично, сохранила твоё время рождения ⏱✅\n"
                    "Для определения часового пояса нужны дата и координаты "
                    "места рождения."
                )
        except Exception as e:
            logger.warning(f"Timezone resolve failed: {e}")
            cb_msg = cast(Message, callback.message)
            await cb_msg.answer(
                "Отлично, сохранила твоё время рождения ⏱✅\n"
                "Но не удалось определить часовой пояс автоматически."
            )

    # Очищаем временные данные
    await state.update_data(pending_birth_time=None)

    # Убираем клавиатуру
    try:
        cb_msg = cast(Message, callback.message)
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await state.clear()
    await show_profile_completion_message(callback)
    await callback.answer()


@dp.callback_query(F.data == "btime:redo")
async def on_birth_time_redo(callback: CallbackQuery, state: FSMContext):
    """Просим ввести время рождения заново"""
    await state.update_data(pending_birth_time=None)
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        "Окей! Пришли время своего рождения в формате ЧЧ:ММ\n"
        "например: 10:38"
    )
    try:
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.set_state(ProfileForm.waiting_for_birth_time_local)
    await callback.answer()


@dp.callback_query(F.data == "btime_approx:confirm")
async def on_birth_time_approx_confirm(
    callback: CallbackQuery, state: FSMContext
):
    """Подтверждение примерного времени рождения:
    сохраняем данные и завершаем анкету"""
    data = await state.get_data()
    time_iso = data.get("pending_birth_time")
    if not time_iso:
        await callback.answer(
            "Не нашла время. Пожалуйста, введите снова.",
            show_alert=True,
        )
        return

    from datetime import time as _time
    try:
        t = _time.fromisoformat(time_iso)
    except Exception:
        await callback.answer(
            "Формат времени потерялся, введите время ещё раз.",
            show_alert=True,
        )
        return

    cb_user = cast(TgUser, callback.from_user)
    async with get_session() as session:
        res = await session.execute(
            select(DbUser).where(DbUser.telegram_id == cb_user.id)
        )
        user = res.scalar_one_or_none()
        if user is None:
            await callback.answer(
                "Похоже, анкета ещё не начата. Нажми /start 💫",
                show_alert=True,
            )
            await state.clear()
            return

        # Сохраняем время в БД
        user.birth_time_local = t

        # Пытаемся определить часовой пояс и UTC-смещение, если есть
        # координаты и дата
        try:
            if (
                user.birth_date
                and user.birth_lat is not None
                and user.birth_lon is not None
            ):
                tzres = resolve_timezone(
                    user.birth_lat, user.birth_lon, user.birth_date, t
                )
                if tzres:
                    user.tzid = tzres.tzid
                    user.tz_offset_minutes = tzres.offset_minutes
                    user.birth_datetime_utc = tzres.birth_datetime_utc
                    tz_label = (
                        f"{tzres.tzid} "
                        f"({format_utc_offset(tzres.offset_minutes)})"
                    )
                    cb_msg = cast(Message, callback.message)
                    await cb_msg.answer(
                        "Отлично, сохранила твоё примерное время рождения ⏱✅\n"
                        f"Часовой пояс: {tz_label}"
                    )
                else:
                    cb_msg = cast(Message, callback.message)
                    await cb_msg.answer(
                        "Отлично, сохранила твоё примерное время рождения ⏱✅\n"
                        "Не удалось автоматически определить часовой пояс "
                        "по координатам."
                    )
            else:
                cb_msg = cast(Message, callback.message)
                await cb_msg.answer(
                    "Отлично, сохранила твоё примерное время рождения ⏱✅\n"
                    "Для определения часового пояса нужны дата и координаты "
                    "места рождения."
                )
        except Exception as e:
            logger.warning(f"Timezone resolve failed: {e}")
            cb_msg = cast(Message, callback.message)
            await cb_msg.answer(
                "Отлично, сохранила твоё примерное время рождения ⏱✅\n"
                "Но не удалось определить часовой пояс автоматически."
            )

    # Очищаем временные данные
    await state.update_data(pending_birth_time=None)

    # Убираем клавиатуру
    try:
        cb_msg = cast(Message, callback.message)
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await state.clear()
    await show_profile_completion_message(callback)
    await callback.answer()


@dp.callback_query(F.data == "btime_approx:redo")
async def on_birth_time_approx_redo(
    callback: CallbackQuery, state: FSMContext
):
    """Просим ввести примерное время рождения заново"""
    await state.update_data(pending_birth_time=None)
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        "Окей! Пришли примерное время своего рождения в формате ЧЧ:ММ\n"
        "например: 11:00"
    )
    try:
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.set_state(ProfileForm.waiting_for_birth_time_local)
    await callback.answer()


@dp.callback_query(F.data == "btime_unknown:confirm")
async def on_birth_time_unknown_confirm(
    callback: CallbackQuery, state: FSMContext
):
    """Подтверждение работы без времени рождения: завершаем анкету"""
    # Убираем клавиатуру
    try:
        cb_msg = cast(Message, callback.message)
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Показываем сообщение о завершении
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        "Принято! 🔮  \n\n"
        "Ничего страшного, если ты не знаешь время своего рождения 👌🏼 \n"
        "Информация будет чуть менее детальной, но все равно "
        "абсолютно точной! 💯🚀"
    )

    await state.clear()
    await show_profile_completion_message(callback)
    await callback.answer()


@dp.callback_query(F.data == "btime_unknown:specify")
async def on_birth_time_unknown_specify(
    callback: CallbackQuery, state: FSMContext
):
    """Переход к указанию времени рождения"""
    # Убираем клавиатуру
    try:
        cb_msg = cast(Message, callback.message)
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Показываем клавиатуру выбора точности времени
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👍🏼 Знаю точное время",
                    callback_data="timeacc:exact",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤏🏼 Знаю примерное время",
                    callback_data="timeacc:approx",
                )
            ],
        ]
    )

    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        "Отлично! Тогда давай укажем время рождения 🕰\n\n"
        "Подскажи, знаешь ли ты время своего рождения?",
        reply_markup=kb,
    )
    await state.set_state(ProfileForm.waiting_for_birth_time_accuracy)
    await callback.answer()


@dp.callback_query(F.data == "start_moon_analysis")
async def on_start_moon_analysis(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Начнем' - запуск анализа Луны"""
    await start_moon_analysis(callback, state)


@dp.callback_query(F.data == "personal_cabinet")
async def on_personal_cabinet(callback: CallbackQuery):
    """Обработчик кнопки 'Личный кабинет'"""
    await callback.answer()
    await show_personal_cabinet(callback)


@dp.callback_query(F.data == "buy_analysis")
async def on_buy_analysis(callback: CallbackQuery):
    """Обработчик кнопки 'Купить разбор'"""
    await callback.answer()
    
    # Импортируем функцию из обработчика покупки разборов
    from handlers.buy_analysis_handler import show_buy_analysis_menu
    
    cb_msg = cast(Message, callback.message)
    await show_buy_analysis_menu(cb_msg)


@dp.callback_query(F.data == "buy_analysis_self")
async def on_buy_analysis_self(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Купить разбор для себя'"""
    await callback.answer()
    
    from handlers.buy_analysis_handler import handle_buy_analysis_self
    
    await handle_buy_analysis_self(callback, state)


@dp.callback_query(F.data == "add_new_date")
async def on_add_new_date(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Добавить новую дату'"""
    await callback.answer()
    
    await start_additional_profile_creation(callback, state)


@dp.callback_query(F.data == "new_analysis")
async def on_new_analysis(callback: CallbackQuery):
    """Обработчик кнопки 'Начать разбор по новой дате'"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    
    try:
        # Получаем ID пользователя
        user_id = callback.from_user.id if callback.from_user else 0
        
        # Получаем информацию о пользователе
        from db import get_session
        from models import User, Prediction
        from sqlalchemy import select, func
        
        async with get_session() as session:
            # Находим пользователя
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                await cb_msg.answer(
                    "❌ Пользователь не найден в базе данных.\n"
                    "Попробуйте перезапустить бота командой /start"
                )
                return
            
            # Получаем количество существующих разборов
            predictions_count = await session.execute(
                select(func.count(Prediction.prediction_id))
                .where(
                    Prediction.user_id == user.user_id,
                    Prediction.is_deleted.is_(False)
                )
            )
            existing_count = predictions_count.scalar()
            
            # Формируем текст с информацией о текущих данных
            text_parts = [
                "🆕 **Начать разбор по новой дате**\n",
                "Ты можешь создать новый разбор с обновленными данными рождения.\n"
            ]
            
            if user.full_name:
                text_parts.append(f"📝 **Текущее имя:** {user.full_name}")
            if user.birth_date:
                text_parts.append(f"🎂 **Текущая дата рождения:** {user.birth_date.strftime('%d.%m.%Y')}")
            if user.birth_place_name:
                text_parts.append(f"📍 **Текущее место рождения:** {user.birth_place_name}")
            
            text_parts.extend([
                "",
                f"📊 **Текущие разборы:** {existing_count}",
                "",
                "⚠️ **Важно:**",
                "• Новый разбор заменит существующие данные",
                "• Все предыдущие разборы останутся доступными",
                "• Заполнение анкеты займет 3-5 минут",
                "",
                "Хочешь начать заполнение новой анкеты?"
            ])
            
            # Создаем клавиатуру
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Да, начать анкету",
                            callback_data="start_new_analysis"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="👤 Посмотреть профиль",
                            callback_data="personal_cabinet"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="❌ Отмена",
                            callback_data="back_to_menu"
                        )
                    ]
                ]
            )
            
            await cb_msg.answer(
                "\n".join(text_parts),
                reply_markup=kb,
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"Ошибка в новом разборе для пользователя {user_id}: {e}")
        await cb_msg.answer(
            "❌ Произошла ошибка при загрузке формы нового разбора.\n"
            "Попробуйте позже или обратитесь в службу заботы."
        )


@dp.callback_query(F.data == "faq")
async def on_faq(callback: CallbackQuery):
    """Обработчик кнопки 'FAQ'"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    
    # Создаем клавиатуру с кнопкой возврата в меню
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="back_to_menu"
                )
            ]
        ]
    )
    
    faq_text = (
        "⁉️ FAQ\n\n"
        "❔ Откуда берётся информация? Это не копия из интернета?\n"
        "😼: Нет, я не копирую тексты из интернета. Мои разборы основаны на знаниях и практике профессионального астролога, которые встроены в работу ИИ.\n"
        "Бесплатные сайты дают только шаблонные описания — одни и те же для всех (и то неправильные).\n"
        "У меня же разбор индивидуальный: я учитываю не только знак планеты, но и её дом, аспекты, сочетания с другими элементами карты — в итоге даю цельный анализ именно твоей натальной карты, а не общие заготовки.\n\n"
        "❔ Что делать, если я не знаю время рождения / знаю неточно?\n"
        "😼: Если ты не знаешь время рождения — не переживай, всё равно получится сделать ценный разбор! При заполнении анкеты можно указать:\n"
        "▪️ точное время (лучший вариант),\n"
        "▪️ или примерное время (например: «утро» → 07:00, «около 12» → 12:00),\n"
        "▪️ или совсем без времени.\n"
        "Что даёт время? Оно влияет на положение планет в домах. С ним разбор получается более полный и детальный. Без него ты всё равно получишь точный анализ планет, просто без домов.\n"
        "Совет от меня: если сомневаешься, пиши хотя бы примерное время — это всегда лучше, чем ничего!\n\n"
        "❔ Как ввести или изменить дату/время/место рождения?\n"
        "😼: В твоем Личном кабинете (введи в боте /lk) есть раздел «Мои даты» — там можно добавить новые данные.\n\n"
        "❔ Можно ли добавить несколько дат (для друзей/детей/партнёра)?\n"
        "😼: Да, можно. Более того, в ближайшее время будет обновление: добавим детские разборы и совместимость, не пропусти!\n\n"
        "❔ Луна бесплатна всегда или только первый раз?\n"
        "😼: Разбор Луны всегда бесплатный.\n\n"
        "❔ Какую планету лучше выбрать первой?\n"
        "😼: Я советую взять сразу полный разбор всех планет — так ты увидишь полную картину по всем сферам + у тебя будет возможность задавать неограниченное количество вопросов по любой планете.\n\n"
        "❔ Почему такие низкие цены?\n"
        "😼: Цены низкие, так как бот находится на тестировании + дополняется функционал. Когда бот начнет работать в «боевом режиме», цена увеличится.\n\n"
        "❔ Как происходит оплата?\n"
        "😼: У нас официальная оплата через платежный сервис «ЮKassa».\n\n"
        "❔ Я оплатил, но ничего не пришло, что делать?\n"
        "😼: По любому вопросу пиши в /help, там быстро помогут.\n\n"
        "❔ Сколько раз я могу читать свой разбор — он сохраняется?\n"
        "😼: Да, разборы сохраняются. В твоем Личном кабинете (введи в боте /lk) есть раздел «Мои даты» — там можно выбрать дату и прочитать любой разбор еще раз.\n\n"
        "❔ Как посмотреть совместимость и прогноз на год?\n"
        "😼: Разбор совместимости, прогнозы на день/месяц/год, разбор детских карт и не только — это все мы добавим в ближайшее время! Следи за новостями!"
    )
    
    await cb_msg.answer(
        faq_text,
        reply_markup=kb
    )


@dp.callback_query(F.data == "support")
async def on_support(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Служба заботы'"""
    await callback.answer()
    
    # Импортируем функцию из обработчика поддержки
    from handlers.support_handler import start_support_conversation
    
    cb_msg = cast(Message, callback.message)
    await start_support_conversation(cb_msg, state)


@dp.callback_query(F.data == "cancel_support")
async def on_cancel_support(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки отмены отправки в поддержку"""
    await callback.answer()
    
    from handlers.support_handler import cancel_support
    
    cb_msg = cast(Message, callback.message)
    await cancel_support(cb_msg, state)


@dp.message(SupportForm.waiting_for_message)
async def handle_support_message(message: Message, state: FSMContext):
    """Обработчик сообщений для службы поддержки"""
    from handlers.support_handler import handle_support_message as support_handler
    await support_handler(message, state)


@dp.callback_query(F.data == "delete_predictions")
async def on_delete_predictions(callback: CallbackQuery):
    """Обработчик кнопки 'Удалить разборы'"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    
    # Показываем подтверждение
    await cb_msg.answer(
        "🗑️ Удаление разборов\n\n"
        "⚠️ ВНИМАНИЕ! Это действие необратимо!\n\n"
        "Будут удалены ВСЕ твои разборы:\n"
        "• Разбор Луны\n"
        "• Разборы других планет\n"
        "• Рекомендации\n"
        "• Ответы на вопросы\n\n"
        "Ты уверен, что хочешь продолжить?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Да, удалить все",
                        callback_data="confirm_delete_predictions"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="back_to_menu"
                    )
                ]
            ]
        )
    )


@dp.callback_query(F.data == "back_to_menu")
async def on_back_to_menu(callback: CallbackQuery):
    """Обработчик кнопки 'Назад в меню'"""
    await callback.answer()
    await show_main_menu(callback)


@dp.callback_query(F.data == "confirm_delete_predictions")
async def on_confirm_delete_predictions(callback: CallbackQuery):
    """Обработчик подтверждения удаления разборов"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    
    try:
        # Получаем ID пользователя
        user_id = callback.from_user.id if callback.from_user else 0
        
        # Удаляем все разборы пользователя
        from db import get_session
        from models import Prediction
        from sqlalchemy import delete
        
        async with get_session() as session:
            # Находим пользователя
            from models import User
            from sqlalchemy import select
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                await cb_msg.answer(
                    "❌ Пользователь не найден. Попробуйте /start"
                )
                return
            
            # Удаляем все разборы пользователя
            delete_result = await session.execute(
                delete(Prediction).where(Prediction.user_id == user.user_id)
            )
            
            await session.commit()
            
            deleted_count = delete_result.rowcount
            
            await cb_msg.answer(
                f"✅ Разборы успешно удалены!\n\n"
                f"Удалено записей: {deleted_count}\n\n"
                f"Все твои данные очищены. Можешь начать заново! 🔄",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🏠 Главное меню",
                                callback_data="back_to_menu"
                            )
                        ]
                    ]
                )
            )
            
            logger.info(
                f"Deleted {deleted_count} predictions for user {user_id}"
            )
            
    except Exception as e:
        logger.error(f"Error deleting predictions: {e}")
        await cb_msg.answer(
            "❌ Произошла ошибка при удалении разборов.\n\n"
            "Попробуйте позже или обратитесь в поддержку.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data="back_to_menu"
                        )
                    ]
                ]
            )
        )


# Старый обработчик удален - теперь используется on_pay_sun


# Обработчики для кнопок после разбора Луны
@dp.callback_query(F.data == "get_recommendations")
async def on_get_recommendations(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Получить рекомендации'"""
    await handle_get_recommendations(callback, state)


# Обработчики для кнопок после разбора Солнца
@dp.callback_query(F.data == "get_sun_recommendations")
async def on_get_sun_recommendations(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Получить рекомендации' для Солнца"""
    await handle_get_sun_recommendations(callback, state)


@dp.callback_query(F.data == "ask_question")
async def on_ask_question(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Задать вопрос'"""
    await handle_ask_question(callback, state)




@dp.callback_query(F.data == "get_mars_recommendations")
async def on_get_mars_recommendations(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Получить рекомендации' для Марса"""
    await handle_get_mars_recommendations(callback, state)


@dp.callback_query(F.data == "get_mercury_recommendations")
async def on_get_mercury_recommendations(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Получить рекомендации' для Меркурия"""
    await handle_get_mercury_recommendations(callback, state)


@dp.callback_query(F.data == "get_venus_recommendations")
async def on_get_venus_recommendations(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Получить рекомендации' для Венеры"""
    await handle_get_venus_recommendations(callback, state)












# Обработчики сообщений для дополнительного профиля
@dp.message(AdditionalProfileForm.waiting_for_additional_name)
async def process_additional_name(message: Message, state: FSMContext):
    """Обработчик ввода имени для дополнительного профиля"""
    await handle_additional_name(message, state)


@dp.message(AdditionalProfileForm.waiting_for_additional_birth_date)
async def process_additional_birth_date(message: Message, state: FSMContext):
    """Обработчик ввода даты рождения для дополнительного профиля"""
    await handle_additional_birth_date(message, state)


@dp.message(AdditionalProfileForm.waiting_for_additional_birth_city)
async def process_additional_birth_city(message: Message, state: FSMContext):
    """Обработчик ввода места рождения для дополнительного профиля"""
    await handle_additional_birth_city(message, state)


# Удалено: теперь используется callback обработчик для выбора времени с кнопками
# @dp.message(AdditionalProfileForm.waiting_for_additional_birth_time_accuracy)
# async def process_additional_birth_time_accuracy(message: Message, state: FSMContext):
#     """Обработчик выбора точности времени для дополнительного профиля"""
#     await handle_additional_birth_time_accuracy(message, state)


@dp.message(AdditionalProfileForm.waiting_for_additional_birth_time_local)
async def process_additional_birth_time_local(message: Message, state: FSMContext):
    """Обработчик ввода времени рождения для дополнительного профиля"""
    await handle_additional_birth_time_local(message, state)


@dp.message(QuestionForm.waiting_for_question)
async def process_user_question(message: Message, state: FSMContext):
    """Обработчик текстового вопроса пользователя"""
    question = message.text.strip() if message.text else ""
    
    if not question:
        await message.answer(
            "❌ Пожалуйста, напиши свой вопрос текстом."
        )
        return
    
    # Проверяем лимит вопросов еще раз
    from handlers.ask_question_handler import (
        get_user_question_count, 
        MAX_QUESTIONS_PER_USER
    )
    
    user_id = message.from_user.id if message.from_user else 0
    question_count = await get_user_question_count(user_id)
    
    if question_count >= MAX_QUESTIONS_PER_USER:
        await message.answer(
            f"❌ Лимит вопросов исчерпан\n\n"
            f"Ты уже задал {question_count} вопросов. "
            f"Максимальное количество: {MAX_QUESTIONS_PER_USER}\n\n"
            "Но ты можешь получить рекомендации или исследовать другие сферы:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💡 Получить рекомендации",
                            callback_data="get_recommendations"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔍 Исследовать другие сферы",
                            callback_data="explore_other_areas"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data="back_to_menu"
                        )
                    ]
                ]
            )
        )
        await state.clear()
        return
    
    # Показываем сообщение о начале обработки
    await message.answer(
        "💭 Обрабатываю твой вопрос...\n\n"
        "⏳ Это займет несколько секунд"
    )
    
    try:
        # Отправляем вопрос в очередь для обработки
        from queue_sender import send_question_to_queue
        user_telegram_id = message.from_user.id if message.from_user else 0
        
        logger.info(
            f"Attempting to send question to queue: user={user_telegram_id}, "
            f"question='{question[:50]}...'"
        )
        
        success = await send_question_to_queue(
            user_telegram_id=user_telegram_id,
            question=question
        )
        
        if success:
            logger.info(
                f"Question successfully sent to queue for user {user_telegram_id}"
            )
            # Сбрасываем состояние
            await state.clear()
        else:
            logger.error(
                f"Failed to send question to queue for user {user_telegram_id}"
            )
            await message.answer(
                "❌ Произошла ошибка при обработке вопроса.\n\n"
                "Попробуйте позже или обратитесь в поддержку."
            )
            
    except Exception as e:
        logger.error(f"Error processing question: {e}")
        await message.answer(
            "❌ Произошла ошибка при обработке вопроса.\n\n"
            "Попробуйте позже или обратитесь в поддержку."
        )




async def get_last_moon_prediction_profile_id(user_id: int) -> Optional[int]:
    """
    Получает profile_id из последнего разбора Луны пользователя
    
    Args:
        user_id: Telegram ID пользователя
        
    Returns:
        profile_id если это дополнительный профиль, None если основной
    """
    async with get_session() as session:
        # Находим пользователя
        user_result = await session.execute(
            select(DbUser).where(DbUser.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            return None
        
        # Находим последний разбор Луны (может быть несколько для разных профилей)
        prediction_result = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.user_id,
                Prediction.planet == Planet.moon,
                Prediction.prediction_type == PredictionType.free,
                Prediction.is_active.is_(True),
                Prediction.is_deleted.is_(False)
            ).order_by(Prediction.created_at.desc())
        )
        prediction = prediction_result.scalars().first()  # Берем первый (последний созданный)
        
        if not prediction:
            return None
        
        return prediction.profile_id


@dp.callback_query(F.data == "explore_other_areas")
async def on_explore_other_areas(callback: CallbackQuery):
    """Обработчик кнопки 'Исследовать другие сферы'"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    
    # Определяем тип профиля (основной или дополнительный)
    profile_id = await get_last_moon_prediction_profile_id(callback.from_user.id)
    
    # Создаем callback_data с profile_id если это дополнительный профиль
    def create_callback_data(base_data: str) -> str:
        if profile_id:
            return f"{base_data}:{profile_id}"
        return base_data
    
    await cb_msg.answer(
        "Давай выберем планету, с которой начнем прямо сейчас 🌟\n\n"
        "☀️ Солнце\n"
        "результат: прилив энергии, уверенность, высокая самооценка, "
        "непоколебимая опора, горящие глаза, осознание своей уникальности "
        "и жизненной задачи\n\n"
        "🧠 Меркурий\n"
        "результат: развитие речи и мышления, умение убеждать и "
        "договариваться, лёгкое обучение и ясная подача идей\n\n"
        "💰💍 Венера\n"
        "результат: разбор блоков в отношениях и финансах, женственность "
        "и притягательность, построение гармоничных для себя отношений, "
        "наслаждение от жизни, расширение финансовой ёмкости — одним словом, "
        "изобилие\n\n"
        "🔥 Марс\n"
        "результат: рост мотивации и силы воли, решительность, спортивный "
        "дух, умение разрешать конфликты и уверенно начинать новое\n\n"
        "🔓 Пока бот на тесте, ты получаешь консультацию астролога почти "
        "даром:\n\n"
        "💸 Одна планета — 10₽ (вместо 999₽)\n"
        "🌌 Все планеты сразу — 5₽ (тестовая цена) + 🎁: неограниченное "
        "количество вопросов по своим разборам\n\n"
        "Выбери разбор по кнопке ниже 😼👇🏼",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🌌 Все планеты",
                        callback_data=create_callback_data("explore_all_planets")
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="☀️ Солнце",
                        callback_data=create_callback_data("explore_sun")
                    ),
                    InlineKeyboardButton(
                        text="☿️ Меркурий",
                        callback_data=create_callback_data("explore_mercury")
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="♀️ Венера",
                        callback_data=create_callback_data("explore_venus")
                    ),
                    InlineKeyboardButton(
                        text="♂️ Марс",
                        callback_data=create_callback_data("explore_mars")
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🏠 Главное меню",
                        callback_data="back_to_menu"
                    )
                ]
            ]
        )
    )


# Обработчики для исследования планет
@dp.callback_query(F.data.startswith("explore_all_planets"))
async def on_explore_all_planets(callback: CallbackQuery):
    """Обработчик кнопки 'Все планеты'"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    user_id = callback.from_user.id
    
    # Извлекаем profile_id из callback_data если есть
    profile_id = None
    if ":" in callback.data:
        try:
            profile_id = int(callback.data.split(":")[1])
        except (ValueError, IndexError):
            profile_id = None
    
    # Проверяем, есть ли у пользователя оплаченный доступ ко всем планетам
    has_access = await check_user_payment_access(user_id, "all_planets")
    
    if has_access:
        # Если доступ есть, запускаем последовательный разбор планет
        from all_planets_handler import get_all_planets_handler
        
        handler = get_all_planets_handler()
        if handler:
            await handler.handle_payment_success(user_id, profile_id)
        else:
            await cb_msg.answer(
                "❌ Ошибка: обработчик всех планет не инициализирован",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🔙 Назад",
                                callback_data="explore_other_areas"
                            )
                        ]
                    ]
                )
            )
        logger.info(
            f"Пользователь {user_id} запросил разборы всех планет (доступ есть)"
        )
    else:
        # Если доступа нет, предлагаем оплату
        pay_callback = f"pay_all_planets:{profile_id}" if profile_id else "pay_all_planets"
        back_callback = f"explore_other_areas:{profile_id}" if profile_id else "explore_other_areas"
        
        await cb_msg.answer(
            "🌌 Все планеты\n\n"
            "💰 Для получения персональных астрологических разборов "
            "по всем планетам необходимо произвести оплату.\n\n"
            "💸 Стоимость: 5₽ (тестовая цена)\n\n"
            "🎁 Бонус: неограниченное количество вопросов по своим разборам\n\n"
            "📋 Что вы получите:\n"
            "☀️ Солнце - энергия, уверенность, самооценка\n"
            "☿️ Меркурий - речь, мышление, обучение\n"
            "♀️ Венера - отношения, финансы, изобилие\n"
            "♂️ Марс - мотивация, сила воли, решительность",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 5₽",
                            callback_data=pay_callback
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data=back_callback
                        )
                    ]
                ]
            )
        )
        logger.info(
            f"Пользователь {user_id} запросил разборы всех планет (доступа нет), profile_id={profile_id}"
        )


@dp.callback_query(F.data.startswith("explore_sun"))
async def on_explore_sun(callback: CallbackQuery):
    """Обработчик кнопки 'Солнце'"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    user_id = callback.from_user.id
    
    # Извлекаем profile_id из callback_data если есть
    profile_id = None
    if ":" in callback.data:
        try:
            profile_id = int(callback.data.split(":")[1])
        except (ValueError, IndexError):
            profile_id = None
    
    # Проверяем, есть ли у пользователя оплаченный доступ к Солнцу
    has_access = await check_user_payment_access(user_id, "sun")
    
    if has_access:
        # Если доступ есть, получаем и отправляем разбор
        await cb_msg.answer(
            "☀️ Солнце\n\n"
            "🔮 Получаю ваш персональный астрологический разбор...\n\n"
            "⏳ Пожалуйста, подождите несколько секунд.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_other_areas"
                        )
                    ]
                ]
            )
        )
        
        # Получаем разбор из БД
        await send_existing_analysis(user_id, "sun", cb_msg, profile_id)
        
        logger.info(
            f"Пользователь {user_id} запросил разбор Солнца (доступ есть)"
        )
    else:
        # Если доступа нет, предлагаем оплату
        await cb_msg.answer(
            "☀️ Солнце\n\n"
            "💰 Для получения персонального астрологического разбора "
            "по Солнцу необходимо произвести оплату.\n\n"
            "💸 Стоимость: 10₽ (вместо 999₽)\n\n"
            "🎯 Что вы получите:\n"
            "• Прилив энергии и уверенности\n"
            "• Высокая самооценка\n"
            "• Осознание своей уникальности\n"
            "• Понимание жизненной задачи",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 10₽",
                            callback_data=f"pay_sun:{profile_id}" if profile_id else "pay_sun"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data=f"explore_other_areas:{profile_id}" if profile_id else "explore_other_areas"
                        )
                    ]
                ]
            )
        )
        logger.info(
            f"Пользователь {user_id} запросил разбор Солнца (доступа нет)"
        )


@dp.callback_query(F.data.startswith("explore_mercury"))
async def on_explore_mercury(callback: CallbackQuery):
    """Обработчик кнопки 'Меркурий'"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    user_id = callback.from_user.id
    
    # Извлекаем profile_id из callback_data если есть
    profile_id = None
    if ":" in callback.data:
        try:
            profile_id = int(callback.data.split(":")[1])
        except (ValueError, IndexError):
            profile_id = None
    
    # Проверяем, есть ли у пользователя оплаченный доступ к Меркурию
    has_access = await check_user_payment_access(user_id, "mercury")
    
    if has_access:
        # Если доступ есть, получаем и отправляем разбор
        await cb_msg.answer(
            "☿️ Меркурий\n\n"
            "🔮 Получаю ваш персональный астрологический разбор...\n\n"
            "⏳ Пожалуйста, подождите несколько секунд.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_other_areas"
                        )
                    ]
                ]
            )
        )
        
        # Получаем разбор из БД
        await send_existing_analysis(user_id, "mercury", cb_msg, profile_id)
        
        logger.info(
            f"Пользователь {user_id} запросил разбор Меркурия (доступ есть)"
        )
    else:
        # Если доступа нет, предлагаем оплату
        await cb_msg.answer(
            "☿️ Меркурий\n\n"
            "💰 Для получения персонального астрологического разбора "
            "по Меркурию необходимо произвести оплату.\n\n"
            "💸 Стоимость: 10₽ (вместо 999₽)\n\n"
            "🎯 Что вы получите:\n"
            "• Развитие речи и мышления\n"
            "• Умение убеждать и договариваться\n"
            "• Лёгкое обучение и ясная подача идей\n"
            "• Улучшение коммуникативных навыков",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 10₽",
                            callback_data="pay_mercury"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_other_areas"
                        )
                    ]
                ]
            )
        )
        logger.info(
            f"Пользователь {user_id} запросил разбор Меркурия (доступа нет)"
        )


@dp.callback_query(F.data.startswith("explore_venus"))
async def on_explore_venus(callback: CallbackQuery):
    """Обработчик кнопки 'Венера'"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    user_id = callback.from_user.id
    
    # Извлекаем profile_id из callback_data если есть
    profile_id = None
    if ":" in callback.data:
        try:
            profile_id = int(callback.data.split(":")[1])
        except (ValueError, IndexError):
            profile_id = None
    
    # Проверяем, есть ли у пользователя оплаченный доступ к Венере
    has_access = await check_user_payment_access(user_id, "venus")
    
    if has_access:
        # Если доступ есть, получаем и отправляем разбор
        await cb_msg.answer(
            "♀️ Венера\n\n"
            "🔮 Получаю ваш персональный астрологический разбор...\n\n"
            "⏳ Пожалуйста, подождите несколько секунд.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_other_areas"
                        )
                    ]
                ]
            )
        )
        
        # Получаем разбор из БД
        await send_existing_analysis(user_id, "venus", cb_msg, profile_id)
        
        logger.info(
            f"Пользователь {user_id} запросил разбор Венеры (доступ есть)"
        )
    else:
        # Если доступа нет, предлагаем оплату
        await cb_msg.answer(
            "♀️ Венера\n\n"
            "💰 Для получения персонального астрологического разбора "
            "по Венере необходимо произвести оплату.\n\n"
            "💸 Стоимость: 10₽ (вместо 999₽)\n\n"
            "🎯 Что вы получите:\n"
            "• Разбор блоков в отношениях и финансах\n"
            "• Женственность и притягательность\n"
            "• Построение гармоничных отношений\n"
            "• Расширение финансовой ёмкости",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 10₽",
                            callback_data="pay_venus"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_other_areas"
                        )
                    ]
                ]
            )
        )
        logger.info(
            f"Пользователь {user_id} запросил разбор Венеры (доступа нет)"
        )


@dp.callback_query(F.data.startswith("explore_mars"))
async def on_explore_mars(callback: CallbackQuery):
    """Обработчик кнопки 'Марс'"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    user_id = callback.from_user.id
    
    # Извлекаем profile_id из callback_data если есть
    profile_id = None
    if ":" in callback.data:
        try:
            profile_id = int(callback.data.split(":")[1])
        except (ValueError, IndexError):
            profile_id = None
    
    # Проверяем, есть ли у пользователя оплаченный доступ к Марсу
    has_access = await check_user_payment_access(user_id, "mars")
    
    if has_access:
        # Если доступ есть, получаем и отправляем разбор
        await cb_msg.answer(
            "♂️ Марс\n\n"
            "🔮 Получаю ваш персональный астрологический разбор...\n\n"
            "⏳ Пожалуйста, подождите несколько секунд.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_other_areas"
                        )
                    ]
                ]
            )
        )
        
        # Получаем разбор из БД
        await send_existing_analysis(user_id, "mars", cb_msg, profile_id)
        
        logger.info(
            f"Пользователь {user_id} запросил разбор Марса (доступ есть)"
        )
    else:
        # Если доступа нет, предлагаем оплату
        await cb_msg.answer(
            "♂️ Марс\n\n"
            "💰 Для получения персонального астрологического разбора "
            "по Марсу необходимо произвести оплату.\n\n"
            "💸 Стоимость: 10₽ (вместо 999₽)\n\n"
            "🎯 Что вы получите:\n"
            "• Рост мотивации и силы воли\n"
            "• Решительность в действиях\n"
            "• Спортивный дух и выносливость\n"
            "• Умение разрешать конфликты\n"
            "• Уверенность в начинании нового",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 10₽",
                            callback_data="pay_mars"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_other_areas"
                        )
                    ]
                ]
            )
        )
        logger.info(
            f"Пользователь {user_id} запросил разбор Марса (доступа нет)"
        )


# Старые обработчики тематических рекомендаций удалены
# Теперь используется единый обработчик handle_get_recommendations


# Обработчики для тематических вопросов по Солнцу
@dp.callback_query(F.data.startswith("sun_question_"))
async def on_sun_question_topic(callback: CallbackQuery, state: FSMContext):
    """Обработчик тематических вопросов по Солнцу"""
    topic = (callback.data or "").replace("sun_question_", "")

    topic_names = {
        "relationships": "💕 Отношения",
        "career": "💼 Карьера",
        "family": "🏠 Семья",
        "health": "💪 Здоровье",
        "finances": "💰 Финансы",
        "goals": "🎯 Цели и мечты"
    }

    topic_name = topic_names.get(topic, topic)

    await callback.answer()
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        f"{topic_name}\n\n"
        "Отлично! Теперь напиши свой конкретный вопрос по этой теме.\n\n"
        "Например:\n"
        "• Как улучшить отношения с партнером?\n"
        "• В какой сфере лучше развиваться?\n"
        "• Как наладить отношения в семье?\n"
        "• Что делать для поддержания здоровья?\n"
        "• Как правильно распоряжаться финансами?\n"
        "• Какие цели ставить перед собой?\n\n"
        "Я дам персональный ответ на основе твоей астрологической карты! 🔮"
    )
    
    # Устанавливаем состояние ожидания вопроса
    await state.set_state(QuestionForm.waiting_for_question)


# Обработчики для тематических вопросов
@dp.callback_query(F.data.startswith("question_"))
async def on_question_topic(callback: CallbackQuery):
    """Обработчик тематических вопросов"""
    topic = (callback.data or "").replace("question_", "")

    topic_names = {
        "relationships": "💕 Отношения",
        "career": "💼 Карьера",
        "family": "🏠 Семья",
        "health": "💪 Здоровье"
    }

    topic_name = topic_names.get(topic, topic)

    await callback.answer()
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        f"{topic_name}\n\n"
        "Отлично! Теперь напиши свой конкретный вопрос по этой теме.\n\n"
        "Например:\n"
        "• Как улучшить отношения с партнером?\n"
        "• В какой сфере лучше развиваться?\n"
        "• Как наладить отношения в семье?\n"
        "• Что делать для поддержания здоровья?\n\n"
        "Я дам персональный ответ на основе твоей натальной карты! ✨"
    )


@dp.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    """Обработчик команды /help"""
    # Сбрасываем состояние FSM при запросе помощи
    await state.clear()
    
    help_text = """
🔮 Я бот астролог

Доступные команды:
/start - Запустить бота
/help - Показать это сообщение

Я помогу вам с астрологическими вопросами!
    """
    await message.answer(help_text)


@dp.message()
async def echo_message(message: Message, state: FSMContext):
    """Обработчик всех остальных сообщений"""
    # Проверяем, находится ли пользователь в состоянии анкеты
    current_state = await state.get_state()
    if current_state in [
        ProfileForm.waiting_for_first_name,
        ProfileForm.waiting_for_birth_date,
        ProfileForm.waiting_for_birth_city,
        ProfileForm.waiting_for_birth_city_confirm,
        ProfileForm.waiting_for_birth_time_accuracy,
        ProfileForm.waiting_for_birth_time_local,
        ProfileForm.waiting_for_birth_time_confirm,
        ProfileForm.waiting_for_birth_time_approx_confirm,
        ProfileForm.waiting_for_birth_time_unknown_confirm
    ]:
        # Если пользователь в состоянии анкеты, не обрабатываем сообщение здесь
        # Пусть его обработает соответствующий обработчик состояния
        return
    
    # Проверяем, находится ли пользователь в состоянии создания дополнительного профиля
    if current_state in [
        AdditionalProfileForm.waiting_for_additional_name,
        AdditionalProfileForm.waiting_for_additional_birth_date,
        AdditionalProfileForm.waiting_for_additional_birth_city,
        AdditionalProfileForm.waiting_for_additional_birth_city_confirm,
        AdditionalProfileForm.waiting_for_additional_birth_time_accuracy,
        AdditionalProfileForm.waiting_for_additional_birth_time_local,
        AdditionalProfileForm.waiting_for_additional_birth_time_confirm,
        AdditionalProfileForm.waiting_for_additional_birth_time_approx_confirm,
        AdditionalProfileForm.waiting_for_additional_birth_time_unknown_confirm
    ]:
        # Если пользователь в состоянии создания дополнительного профиля, не обрабатываем сообщение здесь
        # Пусть его обработает соответствующий обработчик состояния
        return
    
    # Проверяем, находится ли пользователь в состоянии ожидания вопроса
    if current_state == QuestionForm.waiting_for_question:
        # Если пользователь в состоянии ожидания вопроса, не обрабатываем сообщение здесь
        # Пусть его обработает соответствующий обработчик состояния
        return
    
    # Обновляем последнюю активность пользователя
    async with get_session() as session:
        uid = cast(TgUser, message.from_user).id
        res = await session.execute(
            select(DbUser).where(DbUser.telegram_id == uid)
        )
        user = res.scalar_one_or_none()
        if user is not None:
            user.last_seen_at = datetime.now(timezone.utc)

    await message.answer(
        "Привет! Я бот астролог. Используйте /help для списка команд."
    )


async def send_existing_analysis(user_id: int, planet: str, message_obj, profile_id: Optional[int] = None):
    """Отправляет существующий разбор пользователю"""
    try:
        from models import User, Prediction, PredictionType, Planet
        from sqlalchemy import select
        
        async with get_session() as session:
            # Получаем пользователя
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                await message_obj.answer("❌ Пользователь не найден в базе данных")
                return
            
            # Получаем разбор планеты (основной профиль или дополнительный)
            planet_enum = Planet(planet)
            query_conditions = [
                Prediction.user_id == user.user_id,
                Prediction.planet == planet_enum,
                Prediction.prediction_type == PredictionType.paid
            ]
            
            # Добавляем условие для profile_id если указан
            if profile_id:
                query_conditions.append(Prediction.profile_id == profile_id)
            else:
                query_conditions.append(Prediction.profile_id.is_(None))
            
            prediction_result = await session.execute(
                select(Prediction).where(*query_conditions).order_by(Prediction.created_at.desc())
            )
            
            prediction = prediction_result.scalar_one_or_none()
            
            if prediction:
                # Получаем текст разбора
                analysis_text = getattr(prediction, f"{planet}_analysis", None)
                
                if analysis_text:
                    # Отправляем разбор
                    planet_emojis = {
                        "sun": "☀️",
                        "mercury": "☿️", 
                        "venus": "♀️",
                        "mars": "♂️"
                    }
                    
                    emoji = planet_emojis.get(planet, "🔮")
                    
                    # Определяем заголовок в зависимости от типа профиля
                    if profile_id:
                        # Получаем имя дополнительного профиля
                        from models import AdditionalProfile
                        profile_result = await session.execute(
                            select(AdditionalProfile).where(AdditionalProfile.profile_id == profile_id)
                        )
                        profile = profile_result.scalar_one_or_none()
                        profile_name = profile.full_name if profile else "дополнительный профиль"
                        header = f"{emoji} Разбор {planet.title()} для {profile_name}\n\n"
                    else:
                        header = f"{emoji} **{planet.title()}**\n\n"
                    
                    # Разбиваем длинный текст на части, если нужно
                    max_length = 4000
                    if len(analysis_text) <= max_length:
                        await message_obj.answer(
                            f"{header}{analysis_text}"
                        )
                    else:
                        # Разбиваем на части
                        parts = [
                            analysis_text[i:i+max_length] 
                            for i in range(0, len(analysis_text), max_length)
                        ]
                        for i, part in enumerate(parts):
                            if i == 0:
                                await message_obj.answer(
                                    f"{emoji} **{planet.title()}**\n\n{part}"
                                )
                            else:
                                await message_obj.answer(part)
                    
                    logger.info(
                        f"✅ Existing analysis sent to user {user_id} for planet {planet}"
                    )
                else:
                    await message_obj.answer(
                        f"❌ Разбор для {planet} не найден. "
                        "Попробуйте позже или обратитесь в поддержку."
                    )
            else:
                await message_obj.answer(
                    f"❌ Разбор для {planet} не найден. "
                    "Возможно, он еще генерируется. Попробуйте позже."
                )
                
    except Exception as e:
        logger.error(f"❌ Error sending existing analysis: {e}")
        await message_obj.answer(
            "❌ Произошла ошибка при получении разбора. Попробуйте позже."
        )


# Обработчики для оплаты планет
@dp.callback_query(F.data.startswith("pay_sun"))
async def on_pay_sun(callback: CallbackQuery):
    """Обработчик кнопки оплаты за Солнце"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    user_id = callback.from_user.id
    
    # Извлекаем profile_id из callback_data если есть
    profile_id = None
    if ":" in callback.data:
        try:
            profile_id = int(callback.data.split(":")[1])
        except (ValueError, IndexError):
            profile_id = None
    
    if payment_handler is None:
        await cb_msg.answer(
            "❌ Ошибка: обработчик платежей не инициализирован",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_sun"
                        )
                    ]
                ]
            )
        )
        return
    
    try:
        logger.info(f"🔥 НАЧИНАЕМ СОЗДАНИЕ ПЛАТЕЖА для пользователя {user_id}")
        
        # Создаем данные для платежа
        payment_data = payment_handler.create_payment_data(
            user_id=user_id,
            planet="sun",
            description="Астрологический разбор Солнца",
            profile_id=profile_id
        )
        logger.info(f"🔥 ДАННЫЕ ПЛАТЕЖА СОЗДАНЫ: {payment_data}")
        
        # Создаем платеж через ЮKassa
        payment_result = await payment_handler.create_payment(payment_data)
        logger.info(f"🔥 ПЛАТЕЖ СОЗДАН В YOOKASSA: {payment_result}")
        
        # Извлекаем URL и ID платежа
        payment_url = payment_result.get("payment_url")
        external_payment_id = payment_result.get("payment_id")
        
        # Сохраняем информацию о платеже в БД
        logger.info(f"🔥 НАЧИНАЕМ СОХРАНЕНИЕ В БД...")
        from models import PlanetPayment, PaymentType, PaymentStatus, Planet, User
        from sqlalchemy import select
        async with get_session() as session:
            # Находим user_id по telegram_id
            logger.info(f"🔥 ИЩЕМ ПОЛЬЗОВАТЕЛЯ с telegram_id: {user_id}")
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"❌ User with telegram_id {user_id} not found")
                return
            
            logger.info(f"🔥 ПОЛЬЗОВАТЕЛЬ НАЙДЕН: user_id={user.user_id}, telegram_id={user.telegram_id}")
            
            payment_record = PlanetPayment(
                user_id=user.user_id,  # Используем user_id из таблицы users
                payment_type=PaymentType.single_planet,
                planet=Planet.sun,
                status=PaymentStatus.pending,
                amount_kopecks=1000,  # 10 рублей в копейках
                external_payment_id=external_payment_id,
                payment_url=payment_url,
                profile_id=profile_id,  # Добавляем поддержку дополнительных профилей
                notes="Платеж за разбор Солнца"
            )
            logger.info(f"🔥 СОЗДАЕМ ЗАПИСЬ ПЛАТЕЖА: {payment_record}")
            
            session.add(payment_record)
            await session.commit()
            
            logger.info(f"🔥 ПЛАТЕЖ СОХРАНЕН В БД! ID: {payment_record.payment_id}")
            logger.info(f"Создан платеж для пользователя {user_id} (user_id: {user.user_id}) за Солнце")
        
        # Отправляем сообщение с кнопкой оплаты
        await cb_msg.answer(
            "☀️ Оплата за разбор Солнца\n\n"
            "💰 Стоимость: 10₽\n\n"
            "🎯 Что вы получите:\n"
            "• Прилив энергии и уверенности\n"
            "• Высокая самооценка\n"
            "• Осознание своей уникальности\n"
            "• Понимание жизненной задачи\n\n"
            "💳 Нажмите кнопку ниже для оплаты:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 10₽",
                            url=payment_url
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data=f"explore_sun:{profile_id}" if profile_id else "explore_sun"
                        )
                    ]
                ]
            )
        )
        
    except Exception as e:
        logger.error(f"❌ ОШИБКА ПРИ СОЗДАНИИ ПЛАТЕЖА ЗА СОЛНЦЕ: {e}")
        logger.error(f"❌ ТИП ОШИБКИ: {type(e)}")
        logger.error(f"❌ ДЕТАЛИ ОШИБКИ: {str(e)}")
        import traceback
        logger.error(f"❌ TRACEBACK: {traceback.format_exc()}")
        await cb_msg.answer(
            "❌ Произошла ошибка при создании платежа. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_sun"
                        )
                    ]
                ]
            )
        )


@dp.callback_query(F.data == "pay_mars")
async def on_pay_mars(callback: CallbackQuery):
    """Обработчик кнопки оплаты за Марс"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    user_id = callback.from_user.id
    
    if payment_handler is None:
        await cb_msg.answer(
            "❌ Ошибка: обработчик платежей не инициализирован",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_mars"
                        )
                    ]
                ]
            )
        )
        return
    
    try:
        logger.info(f"🔥 НАЧИНАЕМ СОЗДАНИЕ ПЛАТЕЖА ЗА МАРС для пользователя {user_id}")
        
        # Создаем данные для платежа
        payment_data = payment_handler.create_payment_data(
            user_id=user_id,
            planet="mars",
            description="Астрологический разбор Марса"
        )
        logger.info(f"🔥 ДАННЫЕ ПЛАТЕЖА СОЗДАНЫ: {payment_data}")
        
        # Создаем платеж через ЮKassa
        payment_result = await payment_handler.create_payment(payment_data)
        logger.info(f"🔥 ПЛАТЕЖ СОЗДАН В YOOKASSA: {payment_result}")
        
        # Извлекаем URL и ID платежа
        payment_url = payment_result.get("payment_url")
        external_payment_id = payment_result.get("payment_id")
        
        # Сохраняем информацию о платеже в БД
        logger.info(f"🔥 НАЧИНАЕМ СОХРАНЕНИЕ В БД...")
        from models import PlanetPayment, PaymentType, PaymentStatus, Planet, User
        from sqlalchemy import select
        async with get_session() as session:
            # Находим user_id по telegram_id
            logger.info(f"🔥 ИЩЕМ ПОЛЬЗОВАТЕЛЯ с telegram_id: {user_id}")
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"❌ User with telegram_id {user_id} not found")
                return
            
            logger.info(f"🔥 ПОЛЬЗОВАТЕЛЬ НАЙДЕН: user_id={user.user_id}, telegram_id={user.telegram_id}")
            
            payment_record = PlanetPayment(
                user_id=user.user_id,  # Используем user_id из таблицы users
                payment_type=PaymentType.single_planet,
                planet=Planet.mars,
                status=PaymentStatus.pending,
                amount_kopecks=1000,  # 10 рублей в копейках
                external_payment_id=external_payment_id,
                payment_url=payment_url,
                notes="Платеж за разбор Марса"
            )
            logger.info(f"🔥 СОЗДАЕМ ЗАПИСЬ ПЛАТЕЖА: {payment_record}")
            
            session.add(payment_record)
            await session.commit()
            
            logger.info(f"🔥 ПЛАТЕЖ СОХРАНЕН В БД! ID: {payment_record.payment_id}")
            logger.info(f"Создан платеж для пользователя {user_id} (user_id: {user.user_id}) за Марс")
        
        # Отправляем сообщение с кнопкой оплаты
        await cb_msg.answer(
            "♂️ Оплата за разбор Марса\n\n"
            "💰 Стоимость: 10₽\n\n"
            "🎯 Что вы получите:\n"
            "• Рост мотивации и силы воли\n"
            "• Решительность в действиях\n"
            "• Спортивный дух и выносливость\n"
            "• Умение разрешать конфликты\n"
            "• Уверенность в начинании нового\n\n"
            "💳 Нажмите кнопку ниже для оплаты:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 10₽",
                            url=payment_url
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_mars"
                        )
                    ]
                ]
            )
        )
        
    except Exception as e:
        logger.error(f"❌ ОШИБКА ПРИ СОЗДАНИИ ПЛАТЕЖА ЗА МАРС: {e}")
        logger.error(f"❌ ТИП ОШИБКИ: {type(e)}")
        logger.error(f"❌ ДЕТАЛИ ОШИБКИ: {str(e)}")
        import traceback
        logger.error(f"❌ TRACEBACK: {traceback.format_exc()}")
        await cb_msg.answer(
            "❌ Произошла ошибка при создании платежа. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_mars"
                        )
                    ]
                ]
            )
        )


@dp.callback_query(F.data == "pay_mercury")
async def on_pay_mercury(callback: CallbackQuery):
    """Обработчик кнопки оплаты за Меркурий"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    user_id = callback.from_user.id
    
    if payment_handler is None:
        await cb_msg.answer(
            "❌ Ошибка: обработчик платежей не инициализирован",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_mercury"
                        )
                    ]
                ]
            )
        )
        return
    
    try:
        logger.info(f"🔥 НАЧИНАЕМ СОЗДАНИЕ ПЛАТЕЖА ЗА МЕРКУРИЙ для пользователя {user_id}")
        
        # Создаем данные для платежа
        payment_data = payment_handler.create_payment_data(
            user_id=user_id,
            planet="mercury",
            description="Астрологический разбор Меркурия"
        )
        logger.info(f"🔥 ДАННЫЕ ПЛАТЕЖА СОЗДАНЫ: {payment_data}")
        
        # Создаем платеж через ЮKassa
        payment_result = await payment_handler.create_payment(payment_data)
        logger.info(f"🔥 ПЛАТЕЖ СОЗДАН В YOOKASSA: {payment_result}")
        
        # Извлекаем URL и ID платежа
        payment_url = payment_result.get("payment_url")
        external_payment_id = payment_result.get("payment_id")
        
        # Сохраняем информацию о платеже в БД
        logger.info(f"🔥 НАЧИНАЕМ СОХРАНЕНИЕ В БД...")
        from models import PlanetPayment, PaymentType, PaymentStatus, Planet, User
        from sqlalchemy import select
        async with get_session() as session:
            # Находим user_id по telegram_id
            logger.info(f"🔥 ИЩЕМ ПОЛЬЗОВАТЕЛЯ с telegram_id: {user_id}")
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"❌ User with telegram_id {user_id} not found")
                return
            
            logger.info(f"🔥 ПОЛЬЗОВАТЕЛЬ НАЙДЕН: user_id={user.user_id}, telegram_id={user.telegram_id}")
            
            payment_record = PlanetPayment(
                user_id=user.user_id,  # Используем user_id из таблицы users
                payment_type=PaymentType.single_planet,
                planet=Planet.mercury,
                status=PaymentStatus.pending,
                amount_kopecks=1000,  # 10 рублей в копейках
                external_payment_id=external_payment_id,
                payment_url=payment_url,
                notes="Платеж за разбор Меркурия"
            )
            logger.info(f"🔥 СОЗДАЕМ ЗАПИСЬ ПЛАТЕЖА: {payment_record}")
            
            session.add(payment_record)
            await session.commit()
            
            logger.info(f"🔥 ПЛАТЕЖ СОХРАНЕН В БД! ID: {payment_record.payment_id}")
            logger.info(f"Создан платеж для пользователя {user_id} (user_id: {user.user_id}) за Меркурий")
        
        # Отправляем сообщение с кнопкой оплаты
        await cb_msg.answer(
            "☿️ Оплата за разбор Меркурия\n\n"
            "💰 Стоимость: 10₽\n\n"
            "🎯 Что вы получите:\n"
            "• Развитие речи и мышления\n"
            "• Умение убеждать и договариваться\n"
            "• Лёгкое обучение и ясная подача идей\n"
            "• Улучшение коммуникативных навыков\n\n"
            "💳 Нажмите кнопку ниже для оплаты:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 10₽",
                            url=payment_url
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_mercury"
                        )
                    ]
                ]
            )
        )
        
    except Exception as e:
        logger.error(f"❌ ОШИБКА ПРИ СОЗДАНИИ ПЛАТЕЖА ЗА МЕРКУРИЙ: {e}")
        logger.error(f"❌ ТИП ОШИБКИ: {type(e)}")
        logger.error(f"❌ ДЕТАЛИ ОШИБКИ: {str(e)}")
        import traceback
        logger.error(f"❌ TRACEBACK: {traceback.format_exc()}")
        await cb_msg.answer(
            "❌ Произошла ошибка при создании платежа. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_mercury"
                        )
                    ]
                ]
            )
        )


@dp.callback_query(F.data == "pay_venus")
async def on_pay_venus(callback: CallbackQuery):
    """Обработчик кнопки оплаты за Венеру"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    user_id = callback.from_user.id
    
    if payment_handler is None:
        await cb_msg.answer(
            "❌ Ошибка: обработчик платежей не инициализирован",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_venus"
                        )
                    ]
                ]
            )
        )
        return
    
    try:
        logger.info(f"🔥 НАЧИНАЕМ СОЗДАНИЕ ПЛАТЕЖА ЗА ВЕНЕРУ для пользователя {user_id}")
        
        # Создаем данные для платежа
        payment_data = payment_handler.create_payment_data(
            user_id=user_id,
            planet="venus",
            description="Астрологический разбор Венеры"
        )
        logger.info(f"🔥 ДАННЫЕ ПЛАТЕЖА СОЗДАНЫ: {payment_data}")
        
        # Создаем платеж через ЮKassa
        payment_result = await payment_handler.create_payment(payment_data)
        logger.info(f"🔥 ПЛАТЕЖ СОЗДАН В YOOKASSA: {payment_result}")
        
        # Извлекаем URL и ID платежа
        payment_url = payment_result.get("payment_url")
        external_payment_id = payment_result.get("payment_id")
        
        # Сохраняем информацию о платеже в БД
        logger.info(f"🔥 НАЧИНАЕМ СОХРАНЕНИЕ В БД...")
        from models import PlanetPayment, PaymentType, PaymentStatus, Planet, User
        from sqlalchemy import select
        async with get_session() as session:
            # Находим user_id по telegram_id
            logger.info(f"🔥 ИЩЕМ ПОЛЬЗОВАТЕЛЯ с telegram_id: {user_id}")
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                logger.error(f"❌ User with telegram_id {user_id} not found")
                return
            
            logger.info(f"🔥 ПОЛЬЗОВАТЕЛЬ НАЙДЕН: user_id={user.user_id}, telegram_id={user.telegram_id}")
            
            payment_record = PlanetPayment(
                user_id=user.user_id,  # Используем user_id из таблицы users
                payment_type=PaymentType.single_planet,
                planet=Planet.venus,
                status=PaymentStatus.pending,
                amount_kopecks=1000,  # 10 рублей в копейках
                external_payment_id=external_payment_id,
                payment_url=payment_url,
                notes="Платеж за разбор Венеры"
            )
            logger.info(f"🔥 СОЗДАЕМ ЗАПИСЬ ПЛАТЕЖА: {payment_record}")
            
            session.add(payment_record)
            await session.commit()
            
            logger.info(f"🔥 ПЛАТЕЖ СОХРАНЕН В БД! ID: {payment_record.payment_id}")
            logger.info(f"Создан платеж для пользователя {user_id} (user_id: {user.user_id}) за Венеру")
        
        # Отправляем сообщение с кнопкой оплаты
        await cb_msg.answer(
            "♀️ Оплата за разбор Венеры\n\n"
            "💰 Стоимость: 10₽\n\n"
            "🎯 Что вы получите:\n"
            "• Разбор блоков в отношениях и финансах\n"
            "• Женственность и притягательность\n"
            "• Построение гармоничных отношений\n"
            "• Расширение финансовой ёмкости\n\n"
            "💳 Нажмите кнопку ниже для оплаты:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 10₽",
                            url=payment_url
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_venus"
                        )
                    ]
                ]
            )
        )
        
    except Exception as e:
        logger.error(f"❌ ОШИБКА ПРИ СОЗДАНИИ ПЛАТЕЖА ЗА ВЕНЕРУ: {e}")
        logger.error(f"❌ ТИП ОШИБКИ: {type(e)}")
        logger.error(f"❌ ДЕТАЛИ ОШИБКИ: {str(e)}")
        import traceback
        logger.error(f"❌ TRACEBACK: {traceback.format_exc()}")
        await cb_msg.answer(
            "❌ Произошла ошибка при создании платежа. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_venus"
                        )
                    ]
                ]
            )
        )


@dp.callback_query(F.data.startswith("pay_all_planets"))
async def on_pay_all_planets(callback: CallbackQuery):
    """Обработчик кнопки оплаты за все планеты"""
    from all_planets_handler import get_all_planets_handler
    
    # Извлекаем profile_id из callback_data если есть
    profile_id = None
    if ":" in callback.data:
        try:
            profile_id = int(callback.data.split(":")[1])
        except (ValueError, IndexError):
            profile_id = None
    
    logger.info(f"on_pay_all_planets called with profile_id={profile_id}")
    
    handler = get_all_planets_handler()
    if handler:
        await handler.handle_payment_request(callback, profile_id)
    else:
        await callback.answer()
        cb_msg = cast(Message, callback.message)
        await cb_msg.answer(
            "❌ Ошибка: обработчик всех планет не инициализирован",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_all_planets"
                        )
                    ]
                ]
            )
        )


@dp.callback_query(F.data.startswith("next_planet"))
async def on_next_planet(callback: CallbackQuery):
    """Обработчик кнопки 'Следующая планета'"""
    from all_planets_handler import get_all_planets_handler
    
    # Извлекаем profile_id из callback_data если есть
    profile_id = None
    if ":" in callback.data:
        try:
            profile_id = int(callback.data.split(":")[1])
        except (ValueError, IndexError):
            profile_id = None
    
    logger.info(f"on_next_planet called with profile_id={profile_id}")
    
    handler = get_all_planets_handler()
    if handler:
        await handler.handle_next_planet(callback, profile_id)
    else:
        await callback.answer()
        cb_msg = cast(Message, callback.message)
        await cb_msg.answer(
            "❌ Ошибка: обработчик всех планет не инициализирован",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data="back_to_menu"
                        )
                    ]
                ]
            )
        )


async def check_user_payment_access(user_id: int, planet: str) -> bool:
    """Проверяет, есть ли у пользователя оплаченный доступ к планете"""
    from models import PlanetPayment, PaymentStatus, PaymentType, Planet
    
    async with get_session() as session:
        # Проверяем, есть ли оплата за все планеты
        all_planets_payment = await session.execute(
            select(PlanetPayment).where(
                PlanetPayment.user_id == user_id,
                PlanetPayment.payment_type == PaymentType.all_planets,
                PlanetPayment.status == PaymentStatus.completed
            )
        )
        if all_planets_payment.scalar_one_or_none():
            return True
        
        # Проверяем, есть ли оплата за конкретную планету (только если planet не "all_planets")
        if planet != "all_planets":
            try:
                planet_enum = Planet(planet)
                single_planet_payment = await session.execute(
                    select(PlanetPayment).where(
                        PlanetPayment.user_id == user_id,
                        PlanetPayment.payment_type == PaymentType.single_planet,
                        PlanetPayment.planet == planet_enum,
                        PlanetPayment.status == PaymentStatus.completed
                    )
                )
                return single_planet_payment.scalar_one_or_none() is not None
            except ValueError:
                # Если planet не является валидным значением для enum Planet
                return False
        else:
            return False


async def main():
    """Основная функция запуска бота"""
    logger.info("Запуск бота...")
    # Инициализируем подключение к БД и создаём таблицы при необходимости
    init_engine()
    from db import engine as _engine
    db_engine: AsyncEngine = _engine  # type: ignore[assignment]
    
    # Инициализируем обработчик платежей
    global payment_handler
    payment_handler = init_payment_handler(bot)
    logger.info(
        f"Payment handler инициализирован: {payment_handler is not None}"
    )

    # Инициализируем обработчик всех планет
    all_planets_handler = init_all_planets_handler(bot, payment_handler)
    await all_planets_handler.initialize()
    logger.info(
        f"All planets handler инициализирован: {all_planets_handler is not None}"
    )

    # Автоинициализация схемы (однократно/идемпотентно):
    try:
        await ensure_gender_enum(db_engine)
        await ensure_birth_date_nullable(db_engine)
        await ensure_zodiac_enum_ru(db_engine)
        await ensure_planet_enum(db_engine)
        await ensure_prediction_type_enum(db_engine)
        await ensure_payment_type_enum(db_engine)
        await ensure_payment_status_enum(db_engine)
    # create_all безопасен: создаст отсутствующие таблицы,
    # существующие не тронет
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
