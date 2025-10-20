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
from handlers.ask_question_handler import handle_ask_question, QuestionForm
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
from handlers.purchase_history_handler import router as purchase_history_router

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

# Подключаем router purchase_history_handler
dp.include_router(purchase_history_router)

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
    
    # Парсим UTM метки из команды /start
    # Формат: /start utm_source_medium_campaign_content_term
    # Или: /start ref_КОД для реферальных ссылок
    utm_data = {}
    command_args = message.text.split(maxsplit=1) if message.text else []
    
    if len(command_args) > 1:
        param = command_args[1]
        
        # Проверяем реферальную ссылку
        if param.startswith("ref_"):
            utm_data["referral_code"] = param[4:]  # Убираем префикс ref_
            logger.info(f"Реферальный код: {utm_data['referral_code']}")
        else:
            # Парсим UTM метки, разделенные подчеркиванием
            # Формат: source_medium_campaign_content_term
            parts = param.split("_")
            
            if len(parts) >= 1 and parts[0]:
                utm_data["utm_source"] = parts[0]
            if len(parts) >= 2 and parts[1]:
                utm_data["utm_medium"] = parts[1]
            if len(parts) >= 3 and parts[2]:
                utm_data["utm_campaign"] = parts[2]
            if len(parts) >= 4 and parts[3]:
                utm_data["utm_content"] = parts[3]
            if len(parts) >= 5 and parts[4]:
                utm_data["utm_term"] = parts[4]
            
            if utm_data:
                logger.info(f"UTM метки: {utm_data}")
    
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
            # Новый пользователь - сохраняем все данные включая UTM
            user = DbUser(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                lang=lang,
                joined_at=now,
                last_seen_at=now,
                **utm_data  # Добавляем UTM метки
            )
            session.add(user)
            logger.info(f"Новый пользователь {tg_user.id} создан с UTM: {utm_data}")
        else:
            # Обновим базовые поля, если изменились, и отметим активность
            user.username = tg_user.username
            user.first_name = tg_user.first_name
            user.last_name = tg_user.last_name
            user.lang = lang or user.lang
            user.last_seen_at = now
            
            # UTM метки обновляем только если их еще не было
            # (сохраняем источник первого прихода)
            if utm_data:
                if not user.utm_source and utm_data.get("utm_source"):
                    user.utm_source = utm_data["utm_source"]
                if not user.utm_medium and utm_data.get("utm_medium"):
                    user.utm_medium = utm_data["utm_medium"]
                if not user.utm_campaign and utm_data.get("utm_campaign"):
                    user.utm_campaign = utm_data["utm_campaign"]
                if not user.utm_content and utm_data.get("utm_content"):
                    user.utm_content = utm_data["utm_content"]
                if not user.utm_term and utm_data.get("utm_term"):
                    user.utm_term = utm_data["utm_term"]
                if not user.referral_code and utm_data.get("referral_code"):
                    user.referral_code = utm_data["referral_code"]
                
                logger.info(f"Существующий пользователь {tg_user.id}, UTM обновлены: {utm_data}")
        
        await session.commit()

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
        # Отправляем картинку перед приветственным сообщением
        from aiogram.types import FSInputFile
        photo = FSInputFile("src/Group 1.png")
        await message.answer_photo(photo)
        
        # Первое сообщение
        await message.answer(
            (
                "<b>Привет! Меня зовут Лилит</b> 🐈‍⬛\n"
                "Я умный бот-астролог на основе искусственного интеллекта 🤖🔮\n\n"
                "🪐 Разбираю натальные карты точно по <u>дате, времени и месту рождения</u> — на основе знаний и опыта профессионального астролога\n\n"
                "😎 Дам личные разборы планет + рекомендации по важным сферам: финансы, отношения, уверенность в себе и не только"
            ),
            parse_mode="HTML",
        )

        # Второе сообщение с кнопками
        # Кнопка политики конфиденциальности временно отключена
        # [
        #     InlineKeyboardButton(
        #         text="Политика конфиденциальности",
        #         url="https://disk.yandex.ru/i/DwatWs4N5h5HFA"
        #     )
        # ],
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Вперед 👌🏼",
                        callback_data="ok",
                    )
                ]
            ]
        )

        await message.answer(
            (
                "Чтобы начать трансформации, мне понадобятся только твои "
                "<b>дата, время и место рождения</b> 🤗🧬"
            ),
            reply_markup=kb,
            parse_mode="HTML",
        )
        logger.info(f"Пользователь {tg_user.id} без разбора запустил анкету")


@dp.callback_query(F.data == "ok")
async def on_ok(callback: CallbackQuery, state: FSMContext):
    """После нажатия на "Вперед" — старт анкеты, спрашиваем пол"""
    logger.info(f"on_ok callback triggered for user {callback.from_user.id}")
    await callback.answer()
    kb = build_gender_kb(selected=None)
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        "Для начала укажи свой пол 👇🏼",
        reply_markup=kb,
    )
    logger.info(f"Gender keyboard sent to user {callback.from_user.id}")


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
    waiting_for_birth_time_unknown_confirm = State()


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
    if isinstance(message_or_callback, CallbackQuery):
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
            
            # Получаем имя пользователя для персонализации
            user_name = None
            if user.first_name:
                user_name = user.first_name.strip()
            
            # Фолбэк к имени из Telegram, если в БД пусто
            if not user_name:
                tg_user = getattr(message_or_callback, "from_user", None)
                if tg_user and getattr(tg_user, "first_name", None):
                    user_name = tg_user.first_name.strip()
            
            if not user_name:
                user_name = "друг"
            
            # Формируем текст сообщения
            text = (
                f"<b>{user_name}, это твой Личный кабинет!</b> 😼\n"
                "🙌🏼 Здесь хранятся твои разборы, прогресс по датам и покупки\n\n"
                "Краткая инструкция:\n"
                "📅 Мои разборы → переходи сюда, если хочешь увидеть свой прогресс по датам и перечитать разборы\n"
                "💵 Купить разбор → переходи сюда, если хочешь приобрести разбор\n"
                "🆕 Начать разбор по новой дате → переходи сюда, если хочешь перейти к разбору по новым данным\n"
                "🖇 История покупок → переходи сюда, если тебе хочешь посмотреть список твоих покупок у НейроАстролога\n\n"
                "<b>Выбирай нужное действие</b>👇🏼"
            )
            
            # Создаем клавиатуру с действиями
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📅 Мои разборы",
                            callback_data="my_analyses"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="💵 Купить разбор",
                            callback_data="buy_analysis"
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
                            text="🖇 История покупок",
                            callback_data="purchase_history"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Перейти в главное меню",
                            callback_data="back_to_menu"
                        )
                    ]
                ]
            )
            
            await answer_method(
                text,
                reply_markup=kb,
                parse_mode="HTML"
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
    # Определяем имя пользователя: сначала пробуем БД, затем Telegram, затем дефолт
    user_name = None
    try:
        tg_user = getattr(message_or_callback, "from_user", None)
        tg_id = getattr(tg_user, "id", None)

        # Пытаемся получить имя из базы данных
        if tg_id is not None:
            from models import User as DbUser  # локальный импорт, как и в других местах файла
            from sqlalchemy import select
            async with get_session() as session:
                res = await session.execute(select(DbUser).where(DbUser.telegram_id == tg_id))
                db_user = res.scalar_one_or_none()
                if db_user and getattr(db_user, "first_name", None):
                    user_name = (db_user.first_name or "").strip()

        # Фолбэк к имени из Telegram, если в БД пусто
        if not user_name and tg_user and getattr(tg_user, "first_name", None):
            user_name = (tg_user.first_name or "").strip()
    except Exception as e:
        # Не критично для вывода меню
        logger.warning(f"Не удалось получить имя пользователя для главного меню: {e}")

    if not user_name:
        user_name = "друг"

    text = (
        f"{user_name}, очень рада видеть тебя в главном меню 😻 \n\n"
        "Краткая инструкция: \n"
        "👤 Личный кабинет → переходи сюда, если хочешь увидеть свой прогресс, перечитать разборы, задать вопросы по планетам и не только \n"
        "💵 Купить разбор → переходи сюда, если хочешь приобрести разбор \n"
        "🔮 Общение с Лилит → переходи сюда, если хочешь задать вопросы по своей карте или просто поговорить о жизни \n"
        "🆕 Начать разбор по новой дате → переходи сюда, если хочешь перейти к разбору по новым данным \n"
        "❔ Частые вопросы → переходи сюда, если хочешь больше узнать о проекте «НейроАстролог 🪐🤖 AI»\n"
        "❤️‍🩹 Служба заботы → переходи сюда, если у тебя есть вопрос любого рода (техническая ошибка, предложение по сотрудничеству и т.д.) \n\n"
        "<b>Выбирай нужное действие</b>👇🏼"
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
                    text="💵 Купить разбор",
                    callback_data="buy_analysis"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔮 Общение с Лилит",
                    callback_data="ask_question"
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
                    text="❔ Частые вопросы",
                    callback_data="faq"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❤️‍🩹 Служба заботы",
                    callback_data="support"
                )
            ]
        ]
    )

    if hasattr(message_or_callback, 'message'):
        # Это callback
        cb_msg = cast(Message, message_or_callback.message)
        await cb_msg.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        # Это message
        await message_or_callback.answer(text, reply_markup=kb, parse_mode="HTML")


async def show_profile_completion_message(message_or_callback):
    """Показывает финальное сообщение после завершения анкеты"""
    text = (
        "<b>Смотри, я предлагаю начать нашу работу с тебя, а именно с разбора твоей Луны</b> 🌙\n\n"
        "Объясню почему👇🏼\n\n"
        "🌒 Луна включается еще в утробе матери и работает всю жизнь, от неё зависят твои эмоции, характер, то, как ты воспринимаешь мир и даже отношения в семье\n\n"
        "🌓 Эта планета является фундаментом твоего внутреннего мира: если он не прочен, остальные планеты работать просто не будут и нет смысла разбирать всеми любимых Венеру и Асцендент ;)\n\n"
        "🌔 Пока все бегут, спешат и забывают про себя, ты сможешь не бояться выгорания на работе, что очень важно с нашей тенденцией к достигаторству, согласись?\n\n"
        "🌕 Никаких больше эмоциональных качелей — только спокойное и уверенное движение по жизни\n\n"
        "<b>Начнем укреплять твою внутреннюю опору?</b> 🧘🏻‍♀️"
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

    if hasattr(message_or_callback, 'message'):
        # Это callback
        cb_msg = cast(Message, message_or_callback.message)
        await cb_msg.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        # Это message
        await message_or_callback.answer(text, reply_markup=kb, parse_mode="HTML")


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
    await cb_msg.answer("*Как тебя зовут?* 💫", parse_mode="Markdown")
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
        "Огонь 😼🔥 \n\n"
        "📆 *Теперь напиши свою дату рождения в формате ДД.ММ.ГГГГ*\n\n"
        "пример: 23.04.1987",
        parse_mode="Markdown"
    )


@dp.message(ProfileForm.waiting_for_birth_date)
async def receive_birth_date(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    try:
        dt = datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer(
            "Ой... я не могу распознать это 😿\n"
            "👇🏼 Введи дату рождения еще раз в формате ДД.ММ.ГГГГ (например, 23.01.1998)"
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
            "Не нашла дату. Пожалуйста, введите дату снова.",
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
        (
            f"Понятно, значит ты у нас {sign} 🤭 интересно, что еще зашифровано в твоей карте \n\n"
            "📍 <b>Далее напиши место своего рождения</b>\n\n"
            "❕ можно указать конкретный населенный пункт или же ближайший крупный город \n"
            "❕ небольшой населенный пункт лучше указать с областью\n"
            "примеры: г. Краснодар / г. Березовский, Свердловская область"
        ),
        parse_mode="HTML"
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
            "Ой... я не могу распознать это 😿\n"
            "👇🏼 Введи место рождения еще раз в формате "
            "Москва (без пробелов и других знаков)",
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

    # Переходим к следующему шагу — спросить про время рождения
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
                    text="👎🏼 Не знаю время вообще",
                    callback_data="timeacc:unknown",
                )
            ],
        ]
    )
    cb_msg = cast(Message, callback.message)
    await cb_msg.answer(
        "Приняла! 😼 Для полной информации мне не хватает только <b>времени рождения</b> 🪄\n\n"
        "<i>/Совет от Лилит: если не знаешь точное время рождения, <u>укажи хотя бы примерное</u> — это всегда лучше, чем ничего!\n"
        "Например: «родился утром» → укажи 07:00, «родился около 12» → укажи 12:00/</i>\n\n"
        "🕰 <b>Подскажи, знаешь ли ты время своего рождения?</b>",
        reply_markup=kb,
        parse_mode="HTML"
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
    if value not in {"exact", "unknown"}:
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
            "Супер! 🤌🏼\n\n"
            "🕰 <b>Напиши время своего рождения по бирке/справке/примерное в формате ЧЧ:ММ</b>\n\n"
            "примеры: 12:45 / «родился утром» → укажи 07:00 / «родился около 12» → укажи 12:00",
            parse_mode="HTML"
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
            "Ой... я не могу распознать это 😿\n"
            "👇🏼 Введи время рождения еще раз в формате ЧЧ:ММ (например, 11:05)"
        )
        return

    # Сохраняем время временно для подтверждения
    await state.update_data(pending_birth_time=t.isoformat())

    # Показываем подтверждение
    time_str = t.strftime("%H:%M")
    display_text = (
        f"Точное время рождения: {time_str}\nВерно? Нажми кнопку 👇🏼"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Верно", callback_data="btime:confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Ввести заново", callback_data="btime:redo"
                )
            ],
        ]
    )
    await message.answer(display_text, reply_markup=kb)
    await state.set_state(ProfileForm.waiting_for_birth_time_confirm)


@dp.callback_query(F.data == "btime:confirm")
async def on_birth_time_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение времени рождения: сохраняем данные и завершаем анкету"""
    data = await state.get_data()
    time_iso = data.get("pending_birth_time")
    if not time_iso:
        await callback.answer(
            "Не нашла время. Пожалуйста, введите время снова.",
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


@dp.callback_query(F.data.startswith("btime_unknown:"))
async def on_birth_time_unknown(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки для подтверждения работы без времени рождения"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    
    # Убираем клавиатуру
    try:
        await cb_msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # Показываем сообщение о завершении
    await cb_msg.answer(
        "<b>Принято, время не учитываю!</b> 🔮  \n\n"
        "Ничего страшного, если ты не знаешь время своего рождения 👌🏼 \n"
        "Информация будет чуть менее детальной, но все равно абсолютно точной! 💯🚀",
        parse_mode="HTML"
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
    logger.info(f"on_start_moon_analysis triggered for user {callback.from_user.id}")
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


@dp.callback_query(F.data == "buy_analysis_additional")
async def on_buy_analysis_additional(callback: CallbackQuery):
    """Обработчик кнопки 'Купить разбор для дополнительных дат'"""
    from handlers.buy_analysis_handler import show_additional_profiles_for_purchase
    
    await show_additional_profiles_for_purchase(callback)


@dp.callback_query(F.data.startswith("buy_for_profile:"))
async def on_buy_for_profile(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора профиля для покупки разборов"""
    from handlers.buy_analysis_handler import handle_buy_for_profile
    
    await handle_buy_for_profile(callback, state)


@dp.callback_query(F.data == "add_new_date")
async def on_add_new_date(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Добавить новую дату'"""
    await callback.answer()
    
    await start_additional_profile_creation(callback, state)


@dp.callback_query(F.data == "new_analysis")
async def on_new_analysis(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Новый разбор' - перенаправляет на создание доп. профиля"""
    await callback.answer()
    
    # Используем тот же обработчик, что и для "Добавить новую дату"
    await start_additional_profile_creation(callback, state)


@dp.callback_query(F.data == "my_analyses")
async def on_my_analyses(callback: CallbackQuery):
    """Обработчик кнопки 'Мои разборы' - показывает выбор типа разборов"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        logger.info(f"User {user_id} requested my analyses")
        
        await cb_msg.answer(
            "📅 <b>Мои разборы</b>\n"
            "Здесь ты можешь увидеть прогресс по каждой дате и перечитать разборы\n\n"
            "Краткая инструкция: \n"
            "👑 Мой профиль → переходи сюда, если хочешь увидеть прогресс по своей дате, перечитать свои разборы и купить новые \n"
            "👥 Другие профили → переходи сюда, если хочешь увидеть прогресс по другим введенным датам, перечитать их разборы и купить новые \n\n"
            "<b>Выбирай нужное действие</b>👇🏼",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="👑 Мой профиль",
                            callback_data="my_main_analyses"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="👥 Другие профили",
                            callback_data="my_additional_analyses"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="← Назад в кабинет",
                            callback_data="personal_cabinet"
                        )
                    ]
                ]
            ),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error in my_analyses for user {user_id}: {e}")
        await cb_msg.answer(
            "❌ Произошла ошибка при загрузке разборов.\n"
            "Попробуйте позже или обратитесь в службу заботы."
        )


@dp.callback_query(F.data == "my_main_analyses")
async def on_my_main_analyses(callback: CallbackQuery):
    """Обработчик для показа основных разборов пользователя по планетам"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        logger.info(f"User {user_id} requested main analyses")
        
        # Получаем информацию о разборах пользователя из БД
        from db import get_session
        from models import User, Prediction
        from sqlalchemy import select
        
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
            
            # Получаем все разборы пользователя
            predictions_result = await session.execute(
                select(Prediction.planet)
                .where(
                    Prediction.user_id == user.user_id,
                    Prediction.is_deleted.is_(False),
                    Prediction.profile_id.is_(None)  # Только основные разборы
                )
                .distinct()
            )
            existing_planets = {row[0] for row in predictions_result.fetchall()}
            
            # Определяем планеты и их эмоджи
            planets = [
                ("moon", "Луна"),
                ("sun", "Солнце"), 
                ("mercury", "Меркурий"),
                ("venus", "Венера"),
                ("mars", "Марс")
            ]
            
            # Создаем кнопки для планет с батарейками
            planet_buttons = []
            for planet_code, planet_name in planets:
                if planet_code in existing_planets:
                    # Полная батарейка - есть разбор
                    button_text = f"{planet_name} 🔋"
                else:
                    # Красная батарейка - нет разбора  
                    button_text = f"{planet_name} 🪫"
                
                planet_buttons.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"view_planet:{planet_code}"
                    )
                ])
            
            # Добавляем кнопку "Назад"
            planet_buttons.append([
                InlineKeyboardButton(
                    text="← Назад к выбору типа разборов",
                    callback_data="my_analyses"
                )
            ])
            
            await cb_msg.answer(
                "👑 Мой профиль\n\n"
                "<b>Твой прогресс</b>:\n"
                "🔋 → эта планета разобрана! При нажатии на кнопку ты сможешь заново прочитать разбор планеты и личные рекомендации + задать мне любые вопросы 💫 \n"
                "🪫 → эта планета не разобрана! При нажатии на кнопку ты сможешь купить разбор со скидкой 💰 \n\n"
                "<b>Краткая памятка по планетам</b>:\n"
                "🌙 Луна — базовые потребности, внутренний мир, семья  \n"
                "☀️ Солнце — энергия, уверенность в себе, предназначение\n"
                "🧠 Меркурий — интеллект, коммуникация, обучение\n"
                "💰💍 Венера — отношения, финансы, удовольствие от жизни \n"
                "🔥 Марс — сила, умение действовать, мотивация\n\n"
                "\n"
                "🔓 Пока бот на тесте, ты получаешь консультацию астролога почти даром:\n\n"
                "💌 <b>Одна планета — 77₽ (вместо 999₽)</b>\n"
                "💣 <b>Все планеты сразу — 222₽ (вместо 5555₽)</b> + 🎁: обсуждение своей натальной карты с Лилит 24/7 \n\n"
                "<b>Попробуй сейчас</b> 👇🏼",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=planet_buttons),
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Error in my_main_analyses for user {user_id}: {e}")
        await cb_msg.answer(
            "❌ Произошла ошибка при загрузке разборов.\n"
            "Попробуйте позже или обратитесь в службу заботы."
        )


@dp.callback_query(F.data.startswith("view_planet:"))
async def on_view_planet(callback: CallbackQuery):
    """Обработчик для просмотра разбора планеты"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        planet_code = callback.data.split(":")[1]
        logger.info(f"User {user_id} requested planet {planet_code}")
        
        # Получаем разбор из БД
        from db import get_session
        from models import User, Prediction
        from sqlalchemy import select
        
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
            
            # Проверяем наличие разбора для планеты
            prediction_result = await session.execute(
                select(Prediction)
                .where(
                    Prediction.user_id == user.user_id,
                    Prediction.planet == planet_code,
                    Prediction.is_deleted.is_(False),
                    Prediction.profile_id.is_(None)  # Только основные
                )
                .limit(1)
            )
            prediction = prediction_result.scalar_one_or_none()
            
            planet_names = {
                "moon": "Луна",
                "sun": "Солнце",
                "mercury": "Меркурий", 
                "venus": "Венера",
                "mars": "Марс"
            }
            planet_name = planet_names.get(planet_code, planet_code)
            
            # Получаем текст разбора в зависимости от планеты
            prediction_text = None
            if prediction:
                if planet_code == "moon":
                    prediction_text = prediction.moon_analysis
                elif planet_code == "sun":
                    prediction_text = prediction.sun_analysis
                elif planet_code == "mercury":
                    prediction_text = prediction.mercury_analysis
                elif planet_code == "venus":
                    prediction_text = prediction.venus_analysis
                elif planet_code == "mars":
                    prediction_text = prediction.mars_analysis
            
            if prediction_text:
                # Есть разбор - показываем его
                await cb_msg.answer(
                    f"📋 **Разбор: {planet_name}**\n\n"
                    f"{prediction_text}",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="← Назад к планетам",
                                    callback_data="my_main_analyses"
                                )
                            ]
                        ]
                    ),
                    parse_mode="Markdown"
                )
            else:
                # Нет разбора - предлагаем купить
                await cb_msg.answer(
                    f"🪫 **Разбор: {planet_name}**\n\n"
                    f"У вас пока нет разбора для планеты {planet_name}.\n\n"
                    f"Хотите приобрести разбор?",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="💳 Купить разбор",
                                    callback_data="buy_analysis"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    text="← Назад к планетам",
                                    callback_data="my_main_analyses"
                                )
                            ]
                        ]
                    ),
                    parse_mode="Markdown"
                )
                
    except Exception as e:
        logger.error(f"Error in view_planet for user {user_id}: {e}")
        await cb_msg.answer(
            "❌ Произошла ошибка при загрузке разбора.\n"
            "Попробуйте позже или обратитесь в службу заботы."
        )


@dp.callback_query(F.data == "my_additional_analyses")
async def on_my_additional_analyses(callback: CallbackQuery):
    """Обработчик для просмотра дополнительных разборов"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        logger.info(f"User {user_id} viewing additional profiles")
        
        # Получаем список дополнительных профилей пользователя
        from db import get_session
        from models import User, AdditionalProfile
        from sqlalchemy import select
        
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
            
            # Получаем все дополнительные профили пользователя
            profiles_result = await session.execute(
                select(AdditionalProfile)
                .where(
                    AdditionalProfile.owner_user_id == user.user_id,
                    AdditionalProfile.is_active.is_(True)
                )
                .order_by(AdditionalProfile.created_at.desc())
            )
            profiles = profiles_result.scalars().all()
            
            if not profiles:
                # Нет дополнительных профилей
                await cb_msg.answer(
                    "👥 **Дополнительные разборы**\n\n"
                    "У вас пока нет дополнительных профилей.\n\n"
                    "Вы можете создать профиль для:\n"
                    "• Члена семьи (мама, папа, брат, сестра)\n"
                    "• Партнера или друга\n"
                    "• Ребенка\n\n"
                    "Для создания профиля нажмите кнопку ниже 👇",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="➕ Создать профиль",
                                    callback_data="add_new_date"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    text="← Назад к выбору типа разборов",
                                    callback_data="my_analyses"
                                )
                            ]
                        ]
                    )
                )
                return
            
            # Формируем список профилей с кнопками
            text = (
                "👥 <b>Другие профили</b>\n"
                "Здесь ты можешь увидеть прогресс по своим дополнительным профилям и перечитать их разборы\n\n"
                "<b>Выбери профиль</b>👇🏼"
            )
            
            # Создаем кнопки для каждого профиля
            buttons = []
            for profile in profiles:
                gender_emoji = {
                    "male": "👨",
                    "female": "👩",
                    "other": "🧑"
                }.get(profile.gender.value if profile.gender else "unknown", "👤")
                
                profile_button = InlineKeyboardButton(
                    text=f"{gender_emoji} {profile.full_name}",
                    callback_data=f"view_profile:{profile.profile_id}"
                )
                buttons.append([profile_button])
            
            # Добавляем кнопки навигации
            buttons.append([
                InlineKeyboardButton(
                    text="➕ Добавить профиль",
                    callback_data="add_new_date"
                )
            ])
            buttons.append([
                InlineKeyboardButton(
                    text="← Назад к выбору типа разборов",
                    callback_data="my_analyses"
                )
            ])
            
            await cb_msg.answer(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Error in on_my_additional_analyses: {e}")
        await cb_msg.answer(
            "❌ Произошла ошибка при загрузке дополнительных профилей.\n"
            "Попробуйте позже или обратитесь в службу заботы.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="← Назад",
                            callback_data="my_analyses"
                        )
                    ]
                ]
            )
        )


@dp.callback_query(F.data.startswith("view_profile:"))
async def on_view_profile(callback: CallbackQuery):
    """Обработчик для просмотра планет дополнительного профиля"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        profile_id = int(callback.data.split(":")[1])
        logger.info(f"User {user_id} viewing profile {profile_id}")
        
        from db import get_session
        from models import AdditionalProfile, Prediction
        from sqlalchemy import select
        
        async with get_session() as session:
            # Получаем профиль
            profile_result = await session.execute(
                select(AdditionalProfile).where(
                    AdditionalProfile.profile_id == profile_id
                )
            )
            profile = profile_result.scalar_one_or_none()
            
            if not profile:
                await cb_msg.answer(
                    "❌ Профиль не найден",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[
                            InlineKeyboardButton(
                                text="← Назад",
                                callback_data="my_additional_analyses"
                            )
                        ]]
                    )
                )
                return
            
            # Проверяем все планеты для этого профиля
            planets_info = []
            for planet_code, planet_data in [
                ("moon", {"name": "Луна", "emoji": "🌙"}),
                ("sun", {"name": "Солнце", "emoji": "☀️"}),
                ("mercury", {"name": "Меркурий", "emoji": "☿️"}),
                ("venus", {"name": "Венера", "emoji": "♀️"}),
                ("mars", {"name": "Марс", "emoji": "♂️"})
            ]:
                # Проверяем наличие разбора
                prediction_result = await session.execute(
                    select(Prediction).where(
                        Prediction.profile_id == profile_id,
                        Prediction.planet == planet_code,
                        Prediction.is_deleted.is_(False)
                    ).limit(1)
                )
                prediction = prediction_result.scalar_one_or_none()
                
                # Проверяем есть ли текст разбора
                has_analysis = False
                if prediction:
                    if planet_code == "moon" and prediction.moon_analysis:
                        has_analysis = True
                    elif planet_code == "sun" and prediction.sun_analysis:
                        has_analysis = True
                    elif planet_code == "mercury" and prediction.mercury_analysis:
                        has_analysis = True
                    elif planet_code == "venus" and prediction.venus_analysis:
                        has_analysis = True
                    elif planet_code == "mars" and prediction.mars_analysis:
                        has_analysis = True
                
                planets_info.append({
                    "code": planet_code,
                    "name": planet_data["name"],
                    "emoji": planet_data["emoji"],
                    "has_analysis": has_analysis
                })
            
            # Формируем сообщение
            gender_emoji = {
                "male": "👨",
                "female": "👩",
                "other": "🧑"
            }.get(profile.gender.value if profile.gender else "unknown", "👤")
            
            text = f"👤 **Профиль: {gender_emoji} {profile.full_name}**\n\n"
            text += "📋 **Доступные разборы:**\n\n"
            
            # Создаем кнопки для планет
            buttons = []
            for planet in planets_info:
                battery = "🔋" if planet["has_analysis"] else "🪫"
                button_text = f"{battery} {planet['emoji']} {planet['name']}"
                buttons.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"view_profile_planet:{profile_id}:{planet['code']}"
                    )
                ])
            
            # Добавляем кнопку "Назад"
            buttons.append([
                InlineKeyboardButton(
                    text="← Назад к профилям",
                    callback_data="my_additional_analyses"
                )
            ])
            
            await cb_msg.answer(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"Error in on_view_profile: {e}")
        await cb_msg.answer(
            "❌ Произошла ошибка при загрузке профиля",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="← Назад",
                        callback_data="my_additional_analyses"
                    )
                ]]
            )
        )


@dp.callback_query(F.data.startswith("view_profile_planet:"))
async def on_view_profile_planet(callback: CallbackQuery):
    """Обработчик для просмотра разбора планеты дополнительного профиля"""
    await callback.answer()
    cb_msg = cast(Message, callback.message)
    
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        parts = callback.data.split(":")
        profile_id = int(parts[1])
        planet_code = parts[2]
        
        logger.info(f"User {user_id} viewing planet {planet_code} for profile {profile_id}")
        
        from db import get_session
        from models import AdditionalProfile, Prediction
        from sqlalchemy import select
        
        async with get_session() as session:
            # Получаем профиль
            profile_result = await session.execute(
                select(AdditionalProfile).where(
                    AdditionalProfile.profile_id == profile_id
                )
            )
            profile = profile_result.scalar_one_or_none()

            if not profile:
                await cb_msg.answer("❌ Профиль не найден")

                return
            
            # Получаем разбор планеты
            prediction_result = await session.execute(
                select(Prediction).where(
                    Prediction.profile_id == profile_id,
                    Prediction.planet == planet_code,
                    Prediction.is_deleted.is_(False)
                ).limit(1)
            )
            prediction = prediction_result.scalar_one_or_none()
            
            planet_names = {
                "moon": "Луна",
                "sun": "Солнце",
                "mercury": "Меркурий",
                "venus": "Венера",
                "mars": "Марс"
            }
            planet_name = planet_names.get(planet_code, planet_code)
            
            # Получаем текст разбора
            prediction_text = None
            if prediction:
                if planet_code == "moon":
                    prediction_text = prediction.moon_analysis
                elif planet_code == "sun":
                    prediction_text = prediction.sun_analysis
                elif planet_code == "mercury":
                    prediction_text = prediction.mercury_analysis
                elif planet_code == "venus":
                    prediction_text = prediction.venus_analysis
                elif planet_code == "mars":
                    prediction_text = prediction.mars_analysis
            
            if prediction_text:
                # Есть разбор - показываем его
                gender_emoji = {
                    "male": "👨",
                    "female": "👩",
                    "other": "🧑"
                }.get(profile.gender.value if profile.gender else "unknown", "👤")
                
                await cb_msg.answer(
                    f"📋 **{planet_name} — {gender_emoji} {profile.full_name}**\n\n"
                    f"{prediction_text}",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="← Назад к планетам",
                                    callback_data=f"view_profile:{profile_id}"
                                )
                            ]
                        ]
                    ),
                    parse_mode="Markdown"
                )
            else:
                # Нет разбора - предлагаем купить
                gender_emoji = {
                    "male": "👨",
                    "female": "👩",
                    "other": "🧑"
                }.get(profile.gender.value if profile.gender else "unknown", "👤")
                
                await cb_msg.answer(
                    f"🪫 **{planet_name} — {gender_emoji} {profile.full_name}**\n\n"
                    f"У профиля пока нет разбора для планеты {planet_name}.\n\n"
                    f"Хотите приобрести разбор?",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="💳 Купить разбор",
                                    callback_data=f"buy_profile_planet:{profile_id}:{planet_code}"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    text="← Назад к планетам",
                                    callback_data=f"view_profile:{profile_id}"
                                )
                            ]
                        ]
                    )
                )
                
    except Exception as e:
        logger.error(f"Error in on_view_profile_planet: {e}")
        await cb_msg.answer(
            "❌ Произошла ошибка при загрузке разбора",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="← Назад",
                        callback_data="my_additional_analyses"
                    )
                ]]
            )
        )


@dp.callback_query(F.data.startswith("buy_profile_planet:"))
async def on_buy_profile_planet(callback: CallbackQuery):
    """Обработчик для покупки разбора планеты дополнительного профиля"""
    await callback.answer()
    
    try:
        parts = callback.data.split(":")
        profile_id = int(parts[1])
        planet_code = parts[2]
        
        # Перенаправляем на соответствующий обработчик покупки с profile_id
        planet_handlers = {
            "sun": f"pay_sun:{profile_id}",
            "mercury": f"pay_mercury:{profile_id}",
            "venus": f"pay_venus:{profile_id}",
            "mars": f"pay_mars:{profile_id}"
        }
        
        if planet_code in planet_handlers:
            # Создаем MockCallback для обхода frozen instance
            class MockCallback:
                def __init__(self, original, new_data):
                    self.data = new_data
                    self.from_user = original.from_user
                    self.message = original.message
                    self.id = original.id
                    self.chat_instance = original.chat_instance
                    self._original = original
                
                async def answer(self, *args, **kwargs):
                    return await self._original.answer(*args, **kwargs)
            
            mock_callback = MockCallback(callback, planet_handlers[planet_code])
            
            # Вызываем соответствующий обработчик
            if planet_code == "sun":
                await on_pay_sun(mock_callback)
            elif planet_code == "mercury":
                await on_pay_mercury(mock_callback)
            elif planet_code == "venus":
                await on_pay_venus(mock_callback)
            elif planet_code == "mars":
                await on_pay_mars(mock_callback)
        else:
            # Луна бесплатная, не должно быть покупки
            cb_msg = cast(Message, callback.message)
            await cb_msg.answer(
                "❌ Разбор Луны бесплатный и доступен всем профилям",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="← Назад",
                                callback_data="view_profile:{profile_id}"
                            )
                        ]
                    ]
                )
            )
            
    except Exception as e:
        logger.error(f"Error in on_buy_profile_planet: {e}")
        cb_msg = cast(Message, callback.message)
        await cb_msg.answer(
            "❌ Произошла ошибка при обработке покупки",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="← Назад",
                            callback_data="my_additional_analyses"
                        )
                    ]
                ]
            )
        )


@dp.message(Command("pay"))
async def cmd_pay(message: Message, state: FSMContext):
    """Обработчик команды /pay — вызывает меню покупки разбора, как и кнопка 'Купить разбор'"""
    from handlers.buy_analysis_handler import show_buy_analysis_menu
    await show_buy_analysis_menu(message)


async def send_faq(message_or_callback):
    """Отправляет раздел FAQ для сообщения или callback-а."""
    # Определяем метод ответа
    if hasattr(message_or_callback, 'message'):
        # Это callback
        cb_msg = cast(Message, message_or_callback.message)
        answer_method = cb_msg.answer
    else:
        # Это обычное сообщение
        answer_method = message_or_callback.answer

    # Клавиатура возврата в меню
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="� Купить разбор",
                    callback_data="buy_analysis"
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Вернуться в главное меню",
                    callback_data="back_to_menu"
                )
            ]
        ]
    )

    faq_text = (
        "⁉️ Ответы на частозадаваемые вопросы\n\n"
        "❔ <b>Откуда берётся информация? Это не копия из интернета?</b>\n"
        "😼: Нет, я не копирую тексты из интернета. Мои разборы основаны на знаниях и практике профессионального астролога, которые встроены в работу ИИ.\n"
        "Бесплатные сайты дают только шаблонные описания — одни и те же для всех (и то неправильные).\n"
        "У меня же разбор индивидуальный: я учитываю не только знак планеты, но и её дом, аспекты, сочетания с другими элементами карты — в итоге даю цельный анализ именно твоей натальной карты, а не общие заготовки.\n\n"
        "❔ <b>Что делать, если я не знаю время рождения / знаю неточно?</b>\n"
        "😼: Если ты не знаешь время рождения — не переживай, всё равно получится сделать ценный разбор! При заполнении анкеты можно указать:\n"
        "▪️ точное время (лучший вариант),\n"
        "▪️ примерное время (например: «утро» → 07:00, «около 12» → 12:00),\n"
        "▪️ или совсем без времени.\n"
        "Что даёт время? Оно влияет на положение планет в домах. С ним разбор получается более полный и детальный. Без него ты всё равно получишь точный анализ планет, просто без домов.\n"
        "Совет от меня: если сомневаешься, пиши хотя бы примерное время — это всегда лучше, чем ничего!\n\n"
        "❔ <b>Как ввести или изменить дату/время/место рождения?</b>\n"
        "😼: В Главном меню (введи в боте /start) есть раздел «Начать разбор по новой дате» — там можно добавить нового человека. Также эта функция есть в твоем Личном кабинете (введи в боте /lk).\n\n"
        "❔ <b>Можно ли добавить несколько дат (для друзей/детей/партнёра)?</b>\n"
        "😼: Да, можно. Более того, планируется обновление: добавим детские разборы и совместимость, не пропусти!\n\n"
        "❔ <b>Луна бесплатна всегда или только первый раз?</b>\n"
        "😼: Разбор Луны всегда бесплатный.\n\n"
        "❔ <b>Какую планету лучше выбрать первой?</b>\n"
        "😼: Я советую взять сразу полный разбор всех планет — так ты увидишь полную картину по всем сферам + у тебя будет возможность общаться с Лилит 24/7 по любому вопросу.\n\n"
        "❔ <b>Почему такие низкие цены?</b>\n"
        "😼: Цены низкие, так как бот находится на тестировании + дополняется функционал. Когда бот начнет работать в «боевом режиме», цена увеличится.\n\n"
        "❔ <b>Как происходит оплата?</b>\n"
        "😼: У нас официальная оплата через платежный сервис «ЮKassa».\n\n"
        "❔ <b>Я оплатил, но ничего не пришло, что делать?</b>\n"
        "😼: По любому вопросу пиши в /help, там быстро помогут.\n\n"
        "❔ <b>Сколько раз я могу читать свой разбор — он сохраняется?</b>\n"
        "😼: Да, разборы сохраняются. В твоем Личном кабинете (введи в боте /lk) есть раздел «Мои разборы» — там можно прочитать любой разбор еще раз.\n\n"
        "❔ <b>Как посмотреть совместимость и прогноз на год?</b>\n"
        "😼: Разбор совместимости, прогнозы на день/месяц/год, разбор детских карт и не только — это все мы добавим в ближайшее время! Следи за новостями!"
    )

    await answer_method(faq_text, reply_markup=kb, parse_mode="HTML")


@dp.message(Command("faq"))
async def cmd_faq(message: Message):
    """Обработчик команды /faq — показывает раздел FAQ, как и кнопка в меню"""
    await send_faq(message)


@dp.callback_query(F.data == "faq")
async def on_faq(callback: CallbackQuery):
    """Обработчик кнопки 'FAQ'"""
    await callback.answer()
    await send_faq(callback)


@dp.callback_query(F.data == "support")
async def on_support(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Служба заботы'"""
    try:
        logger.info("Support button clicked, starting handler")
        await callback.answer()
        
        # Импортируем функцию из обработчика поддержки
        from handlers.support_handler import start_support_conversation
        
        cb_msg = cast(Message, callback.message)
        logger.info("About to call start_support_conversation")
        await start_support_conversation(cb_msg, state)
        logger.info("start_support_conversation completed successfully")
        
    except Exception as e:
        logger.error(f"ERROR in on_support handler: {e}")
        if callback.message:
            await callback.message.answer(
                "❌ Произошла ошибка при отправке сообщения в службу поддержки.\n\n"
                "Попробуйте позже или обратитесь напрямую:\n"
                "📧 Email: support@astro-bot.ru\n"
                "💬 Telegram: @astro_support"
            )


@dp.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    """Обработчик команды /help — запускает диалог со службой заботы, как и кнопка"""
    try:
        logger.info("/help command received, starting support conversation")
        from handlers.support_handler import start_support_conversation
        await start_support_conversation(message, state)
        logger.info("/help -> start_support_conversation completed")
    except Exception as e:
        logger.error(f"ERROR in cmd_help: {e}")
        await message.answer(
            "❌ Произошла ошибка при отправке сообщения в службу поддержки.\n\n"
            "Попробуйте позже или обратитесь напрямую:\n"
            "📧 Email: support@astro-bot.ru\n"
            "💬 Telegram: @astro_support"
        )


@dp.callback_query(F.data == "cancel_support")
async def on_cancel_support(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки отмены отправки в поддержку"""
    await callback.answer()
    
    from handlers.support_handler import cancel_support
    
    await cancel_support(callback, state)


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
    
    user_id = message.from_user.id if message.from_user else 0
    
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
        "<b>Давай выберем планету, с которой начнем прямо сейчас</b> 🌟\n\n"
        "☀️ <b>Солнце</b> + рекомендации\n"
        "результат: прилив энергии, уверенность, высокая самооценка, непоколебимая опора, горящие глаза, осознание своей уникальности и жизненной задачи\n\n"
        "🧠 <b>Меркурий</b> + рекомендации\n"
        "результат: развитие речи и мышления, умение убеждать и договариваться, лёгкое обучение и ясная подача идей\n\n"
        "💰💍 <b>Венера</b> + рекомендации\n"
        "результат: разбор блоков в отношениях и финансах, женственность и притягательность, построение гармоничных отношений, получение удовольствия от жизни, расширение финансовой ёмкости — одним словом, изобилие\n\n"
        "🔥 <b>Марс</b> + рекомендации\n"
        "результат: рост мотивации и силы воли, решительность, спортивный дух, умение разрешать конфликты и уверенно начинать новое\n\n"
        "\n"
        "🔓 Пока бот на тесте, ты получаешь консультацию астролога почти даром:\n\n"
        "💌 <b>Одна планета — 77₽ (вместо 999₽)</b>\n"
        "💣 <b>Все планеты сразу — 222₽ (вместо 5555₽)</b> + 🎁: обсуждение своей натальной карты с Лилит 24/7\n\n"
        "<b>Выбери разбор по кнопке ниже</b> 😼👇🏼",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="😎 Все планеты 222₽",
                        callback_data=create_callback_data("explore_all_planets")
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="☀️ Солнце 77₽",
                        callback_data=create_callback_data("explore_sun")
                    ),
                    InlineKeyboardButton(
                        text="🧠 Меркурий 77₽",
                        callback_data=create_callback_data("explore_mercury")
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="💰💍 Венера 77₽",
                        callback_data=create_callback_data("explore_venus")
                    ),
                    InlineKeyboardButton(
                        text="🔥 Марс 77₽",
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
        ),
        parse_mode="HTML"
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
            "<b>☀️ Солнце — 77₽ (вместо 999₽)</b> + рекомендации\n"
            "результат: прилив энергии, уверенность, высокая самооценка, непоколебимая опора, горящие глаза, осознание своей уникальности и жизненной задачи\n\n"
            "<b>💵 Нажми кнопку ниже для оплаты через официальный сервис «Юкаssа»</b>\n"
            "🔮 После оплаты тебе сразу будет доступен разбор\n"
            "👇🏼👇🏼👇🏼",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 77₽",
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
            ),
            parse_mode="HTML"
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
            "<b>🧠 Меркурий — 77₽ (вместо 999₽)</b> + рекомендации\n"
            "результат: развитие речи и мышления, умение убеждать и договариваться, лёгкое обучение и ясная подача идей\n\n"
            "<b>💵 Нажми кнопку ниже для оплаты через официальный сервис «Юкаssа»</b>\n"
            "🔮 После оплаты тебе сразу будет доступен разбор\n\n"
            "👇🏼👇🏼👇🏼",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 77₽",
                            callback_data=f"pay_mercury:{profile_id}" if profile_id else "pay_mercury"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_other_areas"
                        )
                    ]
                ]
            ),
            parse_mode="HTML"
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
            "<b>💰💍 Венера — 77₽ (вместо 999₽)</b> + рекомендации\n"
            "результат: разбор блоков в отношениях и финансах, женственность и притягательность, построение гармоничных отношений, получение удовольствия от жизни, расширение финансовой ёмкости — одним словом, изобилие\n\n"
            "<b>💵 Нажми кнопку ниже для оплаты через официальный сервис «Юкаssа»</b>\n"
            "🔮 После оплаты тебе сразу будет доступен разбор\n\n"
            "👇🏼👇🏼👇🏼",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 77₽",
                            callback_data=f"pay_venus:{profile_id}" if profile_id else "pay_venus"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_other_areas"
                        )
                    ]
                ]
            ),
            parse_mode="HTML"
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
            "<b>🔥 Марс — 77₽ (вместо 999₽)</b> + рекомендации\n"
            "результат: рост мотивации и силы воли, решительность, спортивный дух, умение разрешать конфликты и уверенно начинать новое\n\n"
            "<b>💵 Нажми кнопку ниже для оплаты через официальный сервис «Юкаssа»</b>\n"
            "🔮 После оплаты тебе сразу будет доступен разбор\n\n"
            "👇🏼👇🏼👇🏼",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 77₽",
                            callback_data=f"pay_mars:{profile_id}" if profile_id else "pay_mars"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="explore_other_areas"
                        )
                    ]
                ]
            ),
            parse_mode="HTML"
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
    
    # Проверяем, находится ли пользователь в состоянии общения со службой заботы
    if current_state == SupportForm.waiting_for_message:
        # Если пользователь пишет в службу заботы, не обрабатываем сообщение здесь
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
        logger.info(f"🔥 НАЧИНАЕМ СОЗДАНИЕ ПЛАТЕЖА ЗА СОЛНЦЕ для пользователя {user_id}")
        
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
            "<b>Солнце</b> является самой главной планетой в гороскопе (наряду с Луной) и отвечает за наш характер\n\n"
            "☀️ Солнце = твой знак зодиака, например, человек по знаку зодиака Весы, значит его Солнце находится в Весах\n\n"
            "☀️ Солнышко – это также твоя жизненная сила, твой внутренний стержень и источник энергии\n"
            "☝🏼 Это то, что делает тебя уникальной личностью, придаёт уверенность и помогает найти свой путь в жизни\n\n"
            "☀️ В нашем мире, где все стремятся соответствовать чужим «инстаграмным» стандартам, именно работа с Солнцем поможет тебе:\n"
            "▫️ найти и принять свою истинную природу,\n"
            "▫️ развить харизму и лидерские качества,\n"
            "▫️ научиться говорить «нет» без чувства вины,\n"
            "▫️ обрести внутреннюю опору и непоколебимую уверенность\n\n"
            "<b>Начнем качать энергию?</b> 😎",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 77₽",
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


@dp.callback_query(F.data.startswith("pay_mars"))
async def on_pay_mars(callback: CallbackQuery):
    """Обработчик кнопки оплаты за Марс"""
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
            description="Астрологический разбор Марса",
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
                planet=Planet.mars,
                status=PaymentStatus.pending,
                amount_kopecks=7700,  # 77 рублей в копейках
                external_payment_id=external_payment_id,
                payment_url=payment_url,
                profile_id=profile_id,  # Добавляем поддержку дополнительных профилей
                notes="Платеж за разбор Марса"
            )
            logger.info(f"🔥 СОЗДАЕМ ЗАПИСЬ ПЛАТЕЖА: {payment_record}")
            
            session.add(payment_record)
            await session.commit()
            
            logger.info(f"🔥 ПЛАТЕЖ СОХРАНЕН В БД! ID: {payment_record.payment_id}")
            logger.info(f"Создан платеж для пользователя {user_id} (user_id: {user.user_id}) за Марс")
        
        # Отправляем сообщение с кнопкой оплаты
        await cb_msg.answer(
            "<b>Марс</b> – это планета, которая отвечает за твою силу воли, решительность и способность действовать 🔥\n\n"
            "� Именно он показывает, как и насколько ты можешь быть активным, инициативным и целеустремленным в жизни\n\n"
            "👹 Марс укажет на то, как ты проявляешь свою агрессию в мир, как ведешь себя в конфликтах и насколько ты физически сильный человек\n\n"
            "💪🏼 Когда Марс работает гармонично:\n"
            "▫️ ты легко воплощаешь идеи в жизнь, потому что знаешь, как именно тебе подходить к начинаниям,\n"
            "▫️ ты умеешь правильно подать себя в конфликтах и уверенно идешь к своим целям\n\n"
            "❤️‍🔥 Я понимаю, как легко растерять запал, поэтому подскажу тебе, как сохранять мотивацию на протяжении всего пути!\n\n"
            "<b>Начнем работу над мотивацией и волей?</b> ⚡️",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 77₽",
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


@dp.callback_query(F.data.startswith("pay_mercury"))
async def on_pay_mercury(callback: CallbackQuery):
    """Обработчик кнопки оплаты за Меркурий"""
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
            description="Астрологический разбор Меркурия",
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
                planet=Planet.mercury,
                status=PaymentStatus.pending,
                amount_kopecks=7700,  # 77 рублей в копейках
                external_payment_id=external_payment_id,
                payment_url=payment_url,
                profile_id=profile_id,  # Добавляем поддержку дополнительных профилей
                notes="Платеж за разбор Меркурия"
            )
            logger.info(f"🔥 СОЗДАЕМ ЗАПИСЬ ПЛАТЕЖА: {payment_record}")
            
            session.add(payment_record)
            await session.commit()
            
            logger.info(f"🔥 ПЛАТЕЖ СОХРАНЕН В БД! ID: {payment_record.payment_id}")
            logger.info(f"Создан платеж для пользователя {user_id} (user_id: {user.user_id}) за Меркурий")
        
        # Отправляем сообщение с кнопкой оплаты
        await cb_msg.answer(
            "<b>Меркурий</b> – это планета интеллекта, общения и мышления в твоей натальной карте\n\n"
            "� Он показывает, как ты учишься, воспринимаешь и перерабатываешь информацию, как формулируешь мысли и как умеешь коммуницировать с людьми\n\n"
            "� Тем, кто стремится в блогерство или уже развивается в данной сфере (а также в продажах) – вам 100% нужно работать с Меркурием\n\n"
            "🫱🏻‍🫲🏼 Когда Меркурий работает гармонично, ты легко находишь общий язык с людьми, успешно ведёшь переговоры и быстро учишься новому\n\n"
            "<b>Начнем работу над мышлением?</b> 🧠",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 77₽",
                            url=payment_url
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


@dp.callback_query(F.data.startswith("pay_venus"))
async def on_pay_venus(callback: CallbackQuery):
    """Обработчик кнопки оплаты за Венеру"""
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
            description="Астрологический разбор Венеры",
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
                planet=Planet.venus,
                status=PaymentStatus.pending,
                amount_kopecks=7700,  # 77 рублей в копейках
                external_payment_id=external_payment_id,
                payment_url=payment_url,
                profile_id=profile_id,  # Добавляем поддержку дополнительных профилей
                notes="Платеж за разбор Венеры"
            )
            logger.info(f"🔥 СОЗДАЕМ ЗАПИСЬ ПЛАТЕЖА: {payment_record}")
            
            session.add(payment_record)
            await session.commit()
            
            logger.info(f"🔥 ПЛАТЕЖ СОХРАНЕН В БД! ID: {payment_record.payment_id}")
            logger.info(f"Создан платеж для пользователя {user_id} (user_id: {user.user_id}) за Венеру")
        
        # Отправляем сообщение с кнопкой оплаты
        await cb_msg.answer(
            "<b>Венера</b> – это планета, которая отвечает за наши финансы и отношения 💰💕\n\n"
            "а также:\n"
            "�🏼 в женской натальной карте Венера – это женственность, манкость, притягательность\n"
            "🤴🏼 в мужской – образ женщины, которая привлекает физически\n\n"
            "🤤 Женская энергия = умение наслаждаться\n"
            "это важно как для женщин (в особенности), так и для мужчин!\n\n"
            "🙌🏼 Благодаря Венере мы можем понять психологию построения гармоничных отношений, психологию финансов, а также наши блоки в этих сферах!\n\n"
            "😍 Когда Венера работает гармонично:\n"
            "▫️ к тебе естественным образом притягиваются нужные люди и возможности,\n"
            "▫️ ты умеешь выстраивать здоровые отношения\n"
            "▫️ ты умеешь грамотно распоряжаться ресурсами – одним словом, находишься в изобилии\n\n"
            "<b>Начнем проработку твоих денежек и отношений?</b> 🤑🥰",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Оплатить 77₽",
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
        # Проверяем, есть ли оплата за все планеты (только для основного профиля)
        all_planets_payment = await session.execute(
            select(PlanetPayment).where(
                PlanetPayment.user_id == user_id,
                PlanetPayment.payment_type == PaymentType.all_planets,
                PlanetPayment.status == PaymentStatus.completed,
                PlanetPayment.profile_id.is_(None)  # Только основной профиль
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
                        PlanetPayment.status == PaymentStatus.completed,
                        PlanetPayment.profile_id.is_(None)  # Только основной профиль
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
