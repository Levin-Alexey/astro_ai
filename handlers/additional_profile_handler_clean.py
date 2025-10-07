"""
Обработчики для создания дополнительных профилей пользователей.

Этот модуль содержит FSM состояния и обработчики для создания
дополнительных профилей (например, для семьи, друзей) с тем же
алгоритмом опроса, что и основной профиль.
"""

import logging
from datetime import datetime, date, time

from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy import select

from models import User, AdditionalProfile, Gender, ZodiacSignRu, Prediction, Planet, PredictionType
from typing import Optional, Dict, Any
from db import get_session
from geocoding import geocode_city_ru, GeocodingError
from timezone_utils import resolve_timezone

logger = logging.getLogger(__name__)


def zodiac_sign_ru_for_date(d: date) -> ZodiacSignRu:
    """Определяет знак зодиака (на русском) по дате рождения."""
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


def format_time_accuracy_message(accuracy: str, time_obj: time | None) -> str:
    """Форматирует сообщение о точности времени рождения."""
    if accuracy == "exact" and time_obj:
        return f"точно {time_obj.strftime('%H:%M')}"
    elif accuracy == "approx" and time_obj:
        return f"примерно {time_obj.strftime('%H:%M')}"
    elif accuracy == "unknown":
        return "неизвестно"
    else:
        return "не указано"


class AdditionalProfileForm(StatesGroup):
    """FSM состояния для создания дополнительного профиля"""
    waiting_for_additional_name = State()
    waiting_for_additional_birth_date = State()
    waiting_for_additional_birth_city = State()
    waiting_for_additional_birth_city_confirm = State()
    waiting_for_additional_birth_time_accuracy = State()
    waiting_for_additional_birth_time_local = State()
    waiting_for_additional_birth_time_confirm = State()
    waiting_for_additional_birth_time_approx_confirm = State()
    waiting_for_additional_birth_time_unknown_confirm = State()


def build_additional_gender_kb(selected: str | None) -> InlineKeyboardMarkup:
    """
    Строит клавиатуру выбора пола для дополнительного профиля.
    Если selected задан — добавляет чек и кнопку 'Подтвердить'.
    """
    female_text = ("✅ " if selected == "female" else "") + "👩🏻 Женский"
    male_text = ("✅ " if selected == "male" else "") + "👨🏼 Мужской"

    rows = [
        [
            InlineKeyboardButton(
                text=female_text, callback_data="additional_gender:female"
            )
        ],
        [
            InlineKeyboardButton(
                text=male_text, callback_data="additional_gender:male"
            )
        ],
    ]

    if selected:
        rows.append([
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data="additional_gender:confirm"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def start_additional_profile_creation(callback: CallbackQuery, state: FSMContext):
    """
    Начинает процесс создания дополнительного профиля.
    Аналогично основному опросу, но для дополнительного профиля.
    """
    # Получаем user_id из callback (пользователь, нажавший кнопку)
    user_id = callback.from_user.id if callback.from_user else 0
    
    # Получаем message для отправки ответа
    message = callback.message
    if not message:
        logger.error("callback.message is None in start_additional_profile_creation")
        return

    # Проверяем, что пользователь существует в БД
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await message.answer(
                "Сначала нужно создать основной профиль. Нажми /start 💫"
            )
            return

    # Начинаем опросник для дополнительного профиля
    await state.set_state(AdditionalProfileForm.waiting_for_additional_name)
    await message.answer(
        "👥 Отлично! Давайте создадим профиль для дополнительной даты рождения.\n\n"
        "📝 Как зовут человека, для которого создаем разбор?\n\n"
        "Например: Мама, Папа, Моя Зайка, Дочь, Сын, Друг"
    )


async def handle_additional_name(message: Message, state: FSMContext):
    """Обработчик ввода имени для дополнительного профиля"""
    name = (message.text or "").strip()
    if not name:
        await message.answer("Пожалуйста, напиши имя текстом ✍️")
        return

    # Сохраняем имя во временных данных
    await state.update_data(additional_name=name)

    # Переходим к выбору пола
    await message.answer(
        f"Отлично, {name}! 👋\n\n"
        "Теперь выбери пол:",
        reply_markup=build_additional_gender_kb(None)
    )


async def handle_additional_birth_date(message: Message, state: FSMContext):
    """Обработчик ввода даты рождения для дополнительного профиля"""
    text = (message.text or "").strip()
    logger.info(f"🔍 Received birth date input: '{text}' from user {message.from_user.id if message.from_user else 'unknown'}")
    
    try:
        dt = datetime.strptime(text, "%d.%m.%Y").date()
        logger.info(f"✅ Successfully parsed date: {dt}")
    except ValueError as e:
        logger.warning(f"❌ Failed to parse date '{text}': {e}")
        await message.answer(
            "Ой... я не могу распознать это 😿\n"
            "👇🏼 Введи дату рождения еще раз в формате ДД.ММ.ГГГГ (например, 23.01.1998)"
        )
        # НЕ сбрасываем состояние - пользователь может исправить дату
        return

    # Сохраняем дату временно
    await state.update_data(additional_pending_birth_date=dt.isoformat())
    logger.info(f"💾 Saved birth date to state: {dt.isoformat()}")

    date_str = dt.strftime("%d.%m.%Y")
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, верно",
                    callback_data="additional_birth_date:confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Нет, исправить",
                    callback_data="additional_birth_date:retry"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Отменить создание",
                    callback_data="additional_profile:cancel"
                )
            ]
        ]
    )

    await message.answer(
        f"📅 Проверь дату рождения: {date_str}\n\n"
        "Всё правильно?",
        reply_markup=kb
    )


async def handle_additional_birth_city(message: Message, state: FSMContext):
    """Обработчик ввода места рождения для дополнительного профиля"""
    city_input = (message.text or "").strip()
    if not city_input:
        await message.answer("Пожалуйста, напиши название города ✍️")
        return

    # Сохраняем введенный город во временных данных
    await state.update_data(additional_birth_city_input=city_input)

    # Показываем индикатор загрузки
    loading_msg = await message.answer("🔍 Ищу город...")

    try:
        # Геокодируем город
        geocode_result = await geocode_city_ru(city_input)

        if not geocode_result:
            await loading_msg.edit_text(
                f"❌ Не удалось найти город '{city_input}'. "
                "Попробуй написать по-другому или укажи страну.\n\n"
                "Например: Москва, Россия или Moscow, Russia"
            )
            return

        # Сохраняем результат геокодирования
        await state.update_data(additional_geocode_result=geocode_result)

        # Показываем найденный город для подтверждения
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Да, это правильно",
                        callback_data="additional_city:confirm"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Нет, другой город",
                        callback_data="additional_city:retry"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🚫 Отменить создание",
                        callback_data="additional_profile:cancel"
                    )
                ]
            ]
        )

        await loading_msg.edit_text(
            f"🏙️ Найден город: {geocode_result['place_name']}\n\n"
            "Это правильный город?",
            reply_markup=kb
        )

    except GeocodingError as e:
        logger.error(f"Ошибка геокодирования для дополнительного профиля: {e}")
        await loading_msg.edit_text(
            "❌ Произошла ошибка при поиске города. "
            "Попробуй ещё раз."
        )
        # НЕ сбрасываем состояние - пользователь может попробовать другой город


async def handle_additional_birth_time_accuracy_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора точности времени рождения для дополнительного профиля"""
    if not callback.data or not callback.message:
        return
    
    data = callback.data.split(":")
    action = data[1]
    
    logger.info(f"🔍 Time accuracy callback: action={action} from user {callback.from_user.id if callback.from_user else 'unknown'}")
    
    if action == "exact":
        # Точное время
        await state.update_data(additional_birth_time_accuracy="exact")
        logger.info("✅ Set time accuracy to 'exact'")
        await state.set_state(
            AdditionalProfileForm.waiting_for_additional_birth_time_local
        )
        try:
            await callback.message.edit_text(
                "⏰ Отлично! В какое время родился человек?\n\n"
                "Напиши время в формате ЧЧ:ММ\n"
                "Например: 14:30 или 09:15"
            )
        except Exception:
            pass
    elif action == "approx":
        # Примерное время
        await state.update_data(additional_birth_time_accuracy="approx")
        logger.info("✅ Set time accuracy to 'approx'")
        await state.set_state(
            AdditionalProfileForm.waiting_for_additional_birth_time_local
        )
        try:
            await callback.message.edit_text(
                "⏰ Примерное время тоже хорошо!\n\n"
                "Напиши примерное время в формате ЧЧ:ММ\n"
                "Например: 14:30 или 09:15"
            )
        except Exception:
            pass
    elif action == "unknown":
        # Время неизвестно
        await state.update_data(additional_birth_time_accuracy="unknown")
        logger.info("✅ Set time accuracy to 'unknown'")
        await state.set_state(
            AdditionalProfileForm.waiting_for_additional_birth_time_unknown_confirm
        )
        
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Да, время неизвестно",
                        callback_data="additional_time_unknown:confirm"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Всё-таки попробую вспомнить",
                        callback_data="additional_time_unknown:retry"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🚫 Отменить создание",
                        callback_data="additional_profile:cancel"
                    )
                ]
            ]
        )
        
        try:
            await callback.message.edit_text(
                "⏰ Ничего страшного! Время рождения влияет на положение планет в домах, "
                "но без него тоже можно сделать хороший разбор.\n\n"
                "Подтверди, что время действительно неизвестно:",
                reply_markup=kb
            )
        except Exception:
            pass
    
    await callback.answer()


async def handle_additional_profile_cancel(callback: CallbackQuery, state: FSMContext):
    """Обработчик отмены создания дополнительного профиля"""
    if not callback.message:
        return
    
    logger.info(f"🚫 User {callback.from_user.id if callback.from_user else 'unknown'} cancelled additional profile creation")
    
    # Сбрасываем состояние FSM
    await state.clear()
    
    # Показываем сообщение об отмене
    try:
        await callback.message.edit_text(
            "❌ Создание дополнительного профиля отменено.\n\n"
            "Если захочешь создать профиль для другого человека, "
            "используй команду /start или кнопку 'Добавить новую дату'."
        )
    except Exception:
        # Если не удалось отредактировать сообщение, отправляем новое
        await callback.message.answer(
            "❌ Создание дополнительного профиля отменено.\n\n"
            "Если захочешь создать профиль для другого человека, "
            "используй команду /start или кнопку 'Добавить новую дату'."
        )
    
    await callback.answer("Создание профиля отменено")


async def handle_additional_birth_time_local(message: Message, state: FSMContext):
    """Обработчик ввода времени рождения для дополнительного профиля"""
    text = (message.text or "").strip()
    logger.info(f"handle_additional_birth_time_local called with text='{text}'")

    # Получаем данные из состояния
    state_data = await state.get_data()
    accuracy = state_data.get("additional_birth_time_accuracy", "exact")
    logger.info(f"Current accuracy: {accuracy}")

    try:
        # Парсим время
        time_obj = datetime.strptime(text, "%H:%M").time()
        logger.info(f"Parsed time: {time_obj}")

        # Сохраняем время во временных данных
        await state.update_data(additional_pending_birth_time=time_obj.isoformat())
        logger.info(f"Saved time to state: {time_obj.isoformat()}")

        # Показываем для подтверждения
        time_str = time_obj.strftime("%H:%M")
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Да, верно",
                        callback_data="additional_birth_time:confirm"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Нет, исправить",
                        callback_data="additional_birth_time:retry"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🚫 Отменить создание",
                        callback_data="additional_profile:cancel"
                    )
                ]
            ]
        )

        accuracy_text = "точное" if accuracy == "exact" else "примерное"
        await message.answer(
            f"⏰ Проверь {accuracy_text} время рождения: {time_str}\n\n"
            "Всё правильно?",
            reply_markup=kb
        )

    except ValueError as e:
        logger.warning(f"❌ Failed to parse time '{text}': {e}")
        await message.answer(
            "Ой... я не могу распознать это 😿\n"
            "👇🏼 Введи время рождения еще раз в формате ЧЧ:ММ (например, 11:05)"
        )
        # НЕ сбрасываем состояние - пользователь может исправить время


async def complete_additional_profile_creation(
    message: Message, state: FSMContext, user_id: int | None = None
):
    """
    Завершает создание дополнительного профиля и запускает анализ Луны.
    Аналогично завершению основного профиля.
    
    Args:
        message: Message объект для отправки ответов
        state: FSM контекст
        user_id: ID пользователя (опционально, если не указан - берется из message.from_user)
    """
    if user_id is None:
        user_id = message.from_user.id if message.from_user else 0
    
    if user_id == 0:
        await message.answer("Ошибка: не удалось определить пользователя")
        await state.clear()
        return
        
    state_data = await state.get_data()

    try:
        # Получаем все данные из состояния
        logger.info(f"Starting profile creation for user_id={user_id}")
        logger.info(f"State data: {state_data.keys()}")
        
        name = state_data.get("additional_name")
        gender = state_data.get("additional_gender")
        birth_date_str = state_data.get("additional_pending_birth_date")
        geocode_result = state_data.get("additional_geocode_result")
        
        logger.info(f"🔍 Profile data check: name={name}, gender={gender}, birth_date_str={birth_date_str}, geocode={geocode_result is not None}")
        birth_time_accuracy = state_data.get(
            "additional_birth_time_accuracy", "unknown"
        )
        birth_time_local = None

        logger.info(
            f"Profile data: name={name}, gender={gender}, "
            f"birth_date_str={birth_date_str}, accuracy={birth_time_accuracy}"
        )

        if not name or not gender or not birth_date_str or not geocode_result:
            logger.error(
                f"Missing data: name={bool(name)}, gender={bool(gender)}, "
                f"birth_date={bool(birth_date_str)}, geocode={bool(geocode_result)}"
            )
            await message.answer("Ошибка: не все данные заполнены")
            await state.clear()
            return

        birth_date = date.fromisoformat(birth_date_str)

        birth_time_str = state_data.get("additional_pending_birth_time")
        logger.info(f"🔍 Birth time string from state: '{birth_time_str}'")
        if birth_time_str:
            birth_time_local = time.fromisoformat(birth_time_str)
            logger.info(f"✅ Parsed birth time: {birth_time_local}")
        
        # Валидация: если выбрано точное/примерное время, оно должно быть введено
        if birth_time_accuracy in ["exact", "approx"] and not birth_time_local:
            logger.error(f"❌ Missing birth time for accuracy={birth_time_accuracy}")
            logger.error(f"❌ Full state data: {state_data}")
            await message.answer(
                "❌ Ошибка: не указано время рождения!\n\n"
                "Пожалуйста, начните создание профиля заново с /start"
            )
            await state.clear()
            return

        # Вычисляем timezone и знак зодиака ДО создания профиля
        birth_datetime_utc = None
        tzid = None
        tz_offset_minutes = None
        
        if birth_time_local and geocode_result:
            try:
                tz_result = resolve_timezone(
                    lat=geocode_result["lat"],
                    lon=geocode_result["lon"],
                    local_date=birth_date,
                    local_time=birth_time_local
                )
                if tz_result:
                    birth_datetime_utc = tz_result.birth_datetime_utc
                    tzid = tz_result.tzid
                    tz_offset_minutes = tz_result.offset_minutes
                    logger.info(
                        f"Timezone resolved: {tzid}, "
                        f"offset={tz_offset_minutes}, "
                        f"utc={birth_datetime_utc}"
                    )
            except Exception as tz_error:
                logger.error(f"Timezone resolve error: {tz_error}")

        # Рассчитываем знак зодиака
        zodiac_sign_enum = zodiac_sign_ru_for_date(birth_date)
        logger.info(f"Zodiac sign enum: {zodiac_sign_enum}, value: {zodiac_sign_enum.value}")

        # Создаем дополнительный профиль в БД
        async with get_session() as session:
            # Находим основного пользователя
            logger.info(f"Looking for user with telegram_id={user_id}")
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            main_user = result.scalar_one_or_none()

            if not main_user:
                logger.error(f"User not found for telegram_id={user_id}")
                await message.answer("Ошибка: пользователь не найден")
                await state.clear()
                return

            logger.info(f"Found user: user_id={main_user.user_id}")

            # Создаем дополнительный профиль со ВСЕМИ полями сразу
            logger.info(
                f"Creating AdditionalProfile with all fields: "
                f"owner_user_id={main_user.user_id}, name={name}, "
                f"gender={gender}, zodiac={zodiac_sign_enum}"
            )
            
            additional_profile = AdditionalProfile(
                owner_user_id=main_user.user_id,
                full_name=name,
                gender=Gender(gender),
                birth_date=birth_date,
                birth_time_local=birth_time_local,
                birth_time_accuracy=birth_time_accuracy,
                birth_city_input=state_data.get("additional_birth_city_input"),
                birth_place_name=geocode_result["place_name"],
                birth_country_code=geocode_result["country_code"],
                birth_lat=geocode_result["lat"],
                birth_lon=geocode_result["lon"],
                birth_datetime_utc=birth_datetime_utc,
                tzid=tzid,
                tz_offset_minutes=tz_offset_minutes,
                zodiac_sign=zodiac_sign_enum,  # Передаем сам enum, как в основном профиле
                is_active=True
            )
            
            logger.info("AdditionalProfile object created with all fields")

            session.add(additional_profile)
            
            # Сохраняем
            try:
                await session.commit()
                logger.info("Additional profile committed successfully")
            except Exception as commit_error:
                logger.error(f"Commit error: {commit_error}", exc_info=True)
                await session.rollback()
                raise

            profile_id = additional_profile.profile_id

        # Очищаем состояние
        await state.clear()

        # Показываем успешное создание профиля
        await message.answer(
            f"✅ Отлично! Профиль для {name} создан!\n\n"
            f"📅 Дата рождения: {birth_date.strftime('%d.%m.%Y')}\n"
            f"🏙️ Место рождения: {geocode_result['place_name']}\n"
            f"⏰ Время: {format_time_accuracy_message(birth_time_accuracy, birth_time_local)}\n\n"
            "🌙 Сейчас создам бесплатный разбор Луны для этого профиля..."
        )

        # Запускаем анализ Луны для дополнительного профиля
        await start_moon_analysis_for_profile(message, profile_id)

        logger.info(
            f"Создан дополнительный профиль {profile_id} для пользователя {user_id}"
        )

    except Exception as e:
        logger.error(f"Ошибка создания дополнительного профиля: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при создании профиля. "
            "Попробуй ещё раз или обратись в поддержку.\n\n"
            f"Детали для поддержки: {type(e).__name__}"
        )
        await state.clear()


async def get_additional_profile_astrology_data(profile_id: int) -> Optional[Dict[str, Any]]:
    """
    Получить данные дополнительного профиля для астрологических расчетов
    
    Args:
        profile_id: ID дополнительного профиля
        
    Returns:
        Dict с данными профиля или None если данные неполные
    """
    async with get_session() as session:
        result = await session.execute(
            select(AdditionalProfile).where(AdditionalProfile.profile_id == profile_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            logger.warning(f"Additional profile {profile_id} not found")
            return None

        # Проверяем, что у нас есть все необходимые данные
        if not all([
            profile.birth_date,
            profile.birth_time_local,
            profile.birth_lat is not None,
            profile.birth_lon is not None,
            profile.tz_offset_minutes is not None
        ]):
            logger.warning(f"Additional profile {profile_id} has incomplete birth data")
            return None

        # Подготавливаем данные для API
        birth_date = profile.birth_date
        birth_time = profile.birth_time_local

        # Проверяем типы (уже проверено выше, но для mypy)
        assert birth_date is not None
        assert birth_time is not None
        assert profile.birth_lat is not None
        assert profile.birth_lon is not None
        assert profile.tz_offset_minutes is not None

        return {
            "day": birth_date.day,
            "month": birth_date.month,
            "year": birth_date.year,
            "hour": birth_time.hour,
            "minute": birth_time.minute,
            "lat": float(profile.birth_lat),
            "lon": float(profile.birth_lon),
            "tzone": float(profile.tz_offset_minutes) / 60.0,  # Минуты->часы
            "profile_id": profile.profile_id,
            "owner_user_id": profile.owner_user_id
        }


async def start_moon_analysis_for_profile(message: Message, profile_id: int):
    """
    Запускает анализ Луны для дополнительного профиля
    
    Args:
        message: Message объект для отправки ответов
        profile_id: ID дополнительного профиля
    """
    try:
        logger.info(f"Starting moon analysis for additional profile {profile_id}")

        # Получаем данные дополнительного профиля
        profile_data = await get_additional_profile_astrology_data(profile_id)
        if not profile_data:
            logger.error(f"No profile data for profile_id={profile_id} - cannot start moon analysis")
            await message.answer(
                "❌ Для анализа Луны необходимо точное время рождения!\n\n"
                "Этот профиль создан без времени рождения, поэтому анализ Луны недоступен."
            )
            return

        # Импортируем необходимые функции
        from astrology_handlers import AstrologyAPIClient, ASTROLOGY_API_USER_ID, ASTROLOGY_API_KEY
        from astrology_handlers import extract_moon_data, format_moon_data_for_llm
        import json

        # Инициализируем клиент AstrologyAPI
        api_client = AstrologyAPIClient(
            user_id=ASTROLOGY_API_USER_ID,
            api_key=ASTROLOGY_API_KEY
        )

        # Получаем данные от AstrologyAPI
        astrology_data = await api_client.get_western_horoscope(
            day=profile_data["day"],
            month=profile_data["month"],
            year=profile_data["year"],
            hour=profile_data["hour"],
            minute=profile_data["minute"],
            lat=profile_data["lat"],
            lon=profile_data["lon"],
            tzone=profile_data["tzone"],
            language="en"  # Английский для стандартных названий
        )

        # Извлекаем данные Луны
        moon_data = extract_moon_data(astrology_data)
        formatted_moon_data = format_moon_data_for_llm(moon_data)

        # Сохраняем отформатированные данные Луны
        raw_content = (
            f"Moon Analysis Data:\n{formatted_moon_data}\n\n"
            f"Raw AstrologyAPI data: {astrology_data}"
        )

        # Сохраняем в базу данных с profile_id
        async with get_session() as session:
            # Получаем telegram_id владельца профиля
            user_result = await session.execute(
                select(User).where(User.user_id == profile_data["owner_user_id"])
            )
            owner = user_result.scalar_one_or_none()
            
            if not owner:
                logger.error(f"Owner user {profile_data['owner_user_id']} not found")
                await message.answer("❌ Ошибка: владелец профиля не найден")
                return
            
            telegram_id = owner.telegram_id
            logger.info(f"Owner telegram_id: {telegram_id}")
            
            prediction = Prediction(
                user_id=profile_data["owner_user_id"],
                profile_id=profile_id,  # Указываем дополнительный профиль
                planet=Planet.moon,
                prediction_type=PredictionType.free,
                content=raw_content,  # Сырые данные от API
                llm_model="astrology_api",
                expires_at=None  # Бесплатное предсказание не истекает
            )

            session.add(prediction)
            await session.commit()

            prediction_id = prediction.prediction_id

        # Отправляем в очередь для обработки LLM с profile_id
        try:
            # Создаем расширенное сообщение с profile_id и telegram_id
            message_data = {
                "prediction_id": prediction_id,
                "user_id": telegram_id,  # ВАЖНО: используем telegram_id!
                "profile_id": profile_id,  # Добавляем profile_id для воркера
                "timestamp": 0  # Временная метка
            }

            # Отправляем в очередь через queue_sender
            from queue_sender import get_queue_sender
            import aio_pika
            
            sender = await get_queue_sender()
            
            # Используем прямой метод для отправки с profile_id
            if not sender.channel:
                await sender.initialize()

            message_queue = aio_pika.Message(
                body=json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await sender.channel.default_exchange.publish(
                message_queue,
                routing_key="moon_predictions"
            )

            logger.info(f"Moon prediction {prediction_id} for profile {profile_id} sent to queue")
            
        except Exception as e:
            logger.error(f"Failed to send moon prediction to queue: {e}", exc_info=True)
            # Продолжаем работу, даже если не удалось отправить в очередь

        # Показываем сообщение о том, что анализ запущен
        await message.answer(
            "🌙 Анализ Луны запущен!\n\n"
            "Это займет несколько минут. Как только разбор будет готов, "
            "я пришлю его тебе с персональными рекомендациями."
        )

        logger.info(f"Moon analysis started for additional profile {profile_id}")

    except Exception as e:
        logger.error(f"Error starting moon analysis for profile {profile_id}: {e}")
        await message.answer(
            "❌ Произошла ошибка при создании анализа Луны. "
            "Попробуй ещё раз или обратись в поддержку."
        )


# Обработчики callback'ов для дополнительного профиля

async def handle_additional_gender_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора пола для дополнительного профиля"""
    if not callback.data or not callback.message:
        return
        
    data = callback.data.split(":")
    action = data[1]

    if action in ["female", "male"]:
        # Сохраняем выбранный пол во временных данных
        await state.update_data(additional_gender_temp=action)
        
        # Показываем клавиатуру с выбранным полом
        try:
            await callback.message.edit_text(
                "👤 Выбери пол:",
                reply_markup=build_additional_gender_kb(action)
            )
        except Exception:
            # Игнорируем ошибку если сообщение не изменилось
            pass
        await callback.answer()
        
    elif action == "confirm":
        # Получаем выбранный пол из временных данных
        state_data = await state.get_data()
        gender = state_data.get("additional_gender_temp")
        
        if not gender:
            await callback.answer("Выбери пол сначала")
            return

        # Сохраняем пол в основных данных профиля
        await state.update_data(additional_gender=gender)

        # Переходим к вводу даты рождения
        await state.set_state(AdditionalProfileForm.waiting_for_additional_birth_date)
        try:
            await callback.message.edit_text(
                "📆 Теперь напиши дату рождения в формате ДД.ММ.ГГГГ\n\n"
                "например: 23.04.1987"
            )
        except Exception:
            # Игнорируем ошибку если сообщение не изменилось
            pass
        await callback.answer()


async def handle_additional_birth_date_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения даты рождения для дополнительного профиля"""
    if not callback.data or not callback.message:
        return
        
    data = callback.data.split(":")
    action = data[1]
    
    logger.info(f"🔍 Birth date callback: action={action} from user {callback.from_user.id if callback.from_user else 'unknown'}")

    if action == "confirm":
        # Подтверждаем дату и переходим к месту рождения
        logger.info("✅ Birth date confirmed, transitioning to city input")
        await state.set_state(AdditionalProfileForm.waiting_for_additional_birth_city)
        try:
            await callback.message.edit_text(
                "🏙️ Отлично! Теперь напиши место рождения (город):\n\n"
                "Например: Москва, Санкт-Петербург, Екатеринбург"
            )
        except Exception:
            # Игнорируем ошибку если сообщение не изменилось
            pass
    elif action == "retry":
        # Возвращаемся к вводу даты
        try:
            await callback.message.edit_text(
                "📆 Напиши дату рождения в формате ДД.ММ.ГГГГ\n\n"
                "например: 23.04.1987"
            )
        except Exception:
            # Игнорируем ошибку если сообщение не изменилось
            pass

    await callback.answer()


async def handle_additional_birth_city_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения города для дополнительного профиля"""
    if not callback.data or not callback.message:
        return
        
    data = callback.data.split(":")
    action = data[1]

    if action == "confirm":
        # Подтверждаем город и переходим к вопросу о времени
        await state.set_state(
            AdditionalProfileForm.waiting_for_additional_birth_time_accuracy
        )
        
        # Создаем клавиатуру с кнопками выбора точности времени
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👍🏼 Знаю точное время",
                        callback_data="additional_timeacc:exact"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🤏🏼 Знаю примерное время",
                        callback_data="additional_timeacc:approx"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="👎🏼 Не знаю время вообще",
                        callback_data="additional_timeacc:unknown"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🚫 Отменить создание",
                        callback_data="additional_profile:cancel"
                    )
                ]
            ]
        )
        
        try:
            await callback.message.edit_text(
                "Для полной информации мне не хватает только времени рождения 🪄\n\n"
                "🕰 Подскажи, знаешь ли ты время рождения?",
                reply_markup=kb
            )
        except Exception:
            pass
    elif action == "retry":
        # Возвращаемся к вводу города
        await state.set_state(AdditionalProfileForm.waiting_for_additional_birth_city)
        try:
            await callback.message.edit_text(
                "🏙️ Напиши место рождения (город):\n\n"
                "Например: Москва, Санкт-Петербург, Екатеринбург"
            )
        except Exception:
            pass

    await callback.answer()


async def handle_additional_birth_time_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения времени рождения для дополнительного профиля"""
    if not callback.data or not callback.message:
        return
        
    data = callback.data.split(":")
    action = data[1]

    if action == "confirm":
        # Завершаем создание профиля
        user_id = callback.from_user.id if callback.from_user else 0
        
        # Логируем состояние перед созданием профиля
        state_data = await state.get_data()
        logger.info(f"Confirming birth time, state keys: {list(state_data.keys())}")
        logger.info(f"additional_pending_birth_time in state: {state_data.get('additional_pending_birth_time')}")
        
        if callback.message:
            await complete_additional_profile_creation(
                callback.message, state, user_id
            )
    elif action == "retry":
        # Возвращаемся к вводу времени
        state_data = await state.get_data()
        accuracy = state_data.get("additional_birth_time_accuracy", "exact")
        accuracy_text = "точное" if accuracy == "exact" else "примерное"

        await state.set_state(
            AdditionalProfileForm.waiting_for_additional_birth_time_local
        )
        try:
            await callback.message.edit_text(
                f"⏰ Напиши {accuracy_text} время рождения в формате ЧЧ:ММ\n\n"
                "Например: 14:30 или 09:15"
            )
        except Exception:
            pass

    await callback.answer()


async def handle_additional_time_unknown_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик неизвестного времени для дополнительного профиля"""
    if not callback.data or not callback.message:
        return
        
    data = callback.data.split(":")
    action = data[1]

    if action == "confirm":
        # Завершаем создание профиля без времени
        user_id = callback.from_user.id if callback.from_user else 0
        if callback.message:
            await complete_additional_profile_creation(
                callback.message, state, user_id
            )
    elif action == "retry":
        # Возвращаемся к выбору точности времени
        await state.set_state(
            AdditionalProfileForm.waiting_for_additional_birth_time_accuracy
        )
        
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👍🏼 Знаю точное время",
                        callback_data="additional_timeacc:exact"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🤏🏼 Знаю примерное время",
                        callback_data="additional_timeacc:approx"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="👎🏼 Не знаю время вообще",
                        callback_data="additional_timeacc:unknown"
                    )
                ]
            ]
        )
        
        try:
            await callback.message.edit_text(
                "⏰ Хорошо! Тогда ответь на вопрос:\n\n"
                "Знаешь ли ты время рождения?\n\n"
                "• Напиши 'Точно знаю' - если знаешь точное время\n"
                "• Напиши 'Примерно' - если знаешь приблизительное время\n"
                "• Напиши 'Не знаю' - если время неизвестно"
            )
        except Exception:
            pass

    await callback.answer()
