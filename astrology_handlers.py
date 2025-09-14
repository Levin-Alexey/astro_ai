"""
Обработчики астрологических функций для бота.

Включает:
- Клиент для AstrologyAPI
- Обработчики для анализа планет
- Интеграция с LLM для генерации предсказаний
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import aiohttp
import base64
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from db import get_session
from models import User, Prediction, Planet, PredictionType
from sqlalchemy import select
from queue_sender import send_prediction_to_queue

logger = logging.getLogger(__name__)


def extract_moon_data(astrology_data: dict) -> dict:
    """
    Извлекает данные Луны и её аспектов из ответа AstrologyAPI

    Args:
        astrology_data: Полный ответ от AstrologyAPI

    Returns:
        Dict с данными Луны и её аспектами
    """
    moon_data: dict = {
        "moon": None,
        "moon_aspects": []
    }

    # Извлекаем данные Луны из списка планет
    if "planets" in astrology_data:
        for planet in astrology_data["planets"]:
            if planet.get("name") == "Moon":
                moon_data["moon"] = {
                    "name": planet.get("name"),
                    "sign": planet.get("sign"),
                    "house": planet.get("house"),
                    "full_degree": planet.get("full_degree"),
                    "norm_degree": planet.get("norm_degree"),
                    "speed": planet.get("speed"),
                    "is_retro": planet.get("is_retro"),
                    "sign_id": planet.get("sign_id")
                }
                break

    # Извлекаем аспекты Луны
    if "aspects" in astrology_data:
        for aspect in astrology_data["aspects"]:
            if aspect.get("aspecting_planet") == "Moon":
                moon_data["moon_aspects"].append({
                    "aspecting_planet": aspect.get("aspecting_planet"),
                    "aspected_planet": aspect.get("aspected_planet"),
                    "type": aspect.get("type"),
                    "orb": aspect.get("orb"),
                    "diff": aspect.get("diff")
                })

    return moon_data


def format_moon_data_for_llm(moon_data: dict) -> str:
    """
    Форматирует данные Луны для отправки в LLM

    Args:
        moon_data: Данные Луны из extract_moon_data

    Returns:
        Отформатированная строка для LLM
    """
    if not moon_data["moon"]:
        return "Данные Луны не найдены"

    moon = moon_data["moon"]
    aspects = moon_data["moon_aspects"]

    # Основная информация о Луне
    result = f"""Луна в знаке {moon['sign']}, дом {moon['house']}
Степень: {moon['norm_degree']:.2f}°
Скорость: {moon['speed']:.2f}°/день
Ретроградность: {'Да' if moon['is_retro'] == 'true' else 'Нет'}

Аспекты Луны:
"""

    # Добавляем аспекты
    for aspect in aspects:
        result += (
            f"- {aspect['aspecting_planet']} {aspect['type']} "
            f"{aspect['aspected_planet']} "
            f"(орб: {aspect['orb']:.2f}°)\n"
        )

    return result


class AstrologyAPIClient:
    """Клиент для работы с AstrologyAPI"""

    def __init__(self, user_id: str, api_key: str):
        self.user_id = user_id
        self.api_key = api_key
        self.base_url = "https://json.astrologyapi.com/v1"

        # Создаем Basic Auth заголовок
        credentials = f"{user_id}:{api_key}"
        encoded_credentials = base64.b64encode(
            credentials.encode()
        ).decode()
        self.auth_header = f"Basic {encoded_credentials}"

    async def get_western_horoscope(
        self,
        day: int,
        month: int,
        year: int,
        hour: int,
        minute: int,
        lat: float,
        lon: float,
        tzone: float,
        language: str = "en"
    ) -> Dict[str, Any]:
        """
        Получить западный гороскоп от AstrologyAPI

        Args:
            day, month, year: дата рождения
            hour, minute: время рождения
            lat, lon: координаты места рождения
            tzone: часовой пояс
            language: язык ответа

        Returns:
            Dict с данными гороскопа
        """
        data = {
            "day": day,
            "month": month,
            "year": year,
            "hour": hour,
            "min": minute,
            "lat": lat,
            "lon": lon,
            "tzone": tzone,
        }

        headers = {
            "authorization": self.auth_header,
            "Content-Type": "application/json",
            "Accept-Language": language
        }

        url = f"{self.base_url}/western_horoscope"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    json=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info("AstrologyAPI response received for user")
                        return result
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"AstrologyAPI error {response.status}: "
                            f"{error_text}"
                        )
                        raise Exception(
                            f"API error: {response.status} - {error_text}"
                        )

            except asyncio.TimeoutError:
                logger.error("AstrologyAPI request timeout")
                raise Exception("API request timeout")
            except Exception as e:
                logger.error(f"AstrologyAPI request failed: {e}")
                raise


async def get_user_astrology_data(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Получить данные пользователя для астрологических расчетов

    Args:
        user_id: ID пользователя в Telegram

    Returns:
        Dict с данными пользователя или None если данные неполные
    """
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"User {user_id} not found")
            return None

        # Проверяем, что у нас есть все необходимые данные
        if not all([
            user.birth_date,
            user.birth_time_local,
            user.birth_lat is not None,
            user.birth_lon is not None,
            user.tz_offset_minutes is not None
        ]):
            logger.warning(f"User {user_id} has incomplete birth data")
            return None

        # Подготавливаем данные для API
        birth_date = user.birth_date
        birth_time = user.birth_time_local

        # Проверяем типы (уже проверено выше, но для mypy)
        assert birth_date is not None
        assert birth_time is not None
        assert user.birth_lat is not None
        assert user.birth_lon is not None
        assert user.tz_offset_minutes is not None

        return {
            "day": birth_date.day,
            "month": birth_date.month,
            "year": birth_date.year,
            "hour": birth_time.hour,
            "minute": birth_time.minute,
            "lat": float(user.birth_lat),
            "lon": float(user.birth_lon),
            "tzone": float(user.tz_offset_minutes) / 60.0,  # Минуты->часы
            "user_id": user.user_id,
            "telegram_id": user.telegram_id
        }


async def save_astrology_data(
    user_id: int,
    planet: Planet,
    prediction_type: PredictionType,
    content: str,
    llm_model: Optional[str] = None,
    llm_tokens_used: Optional[int] = None,
    llm_temperature: Optional[float] = None,
    expires_at: Optional[datetime] = None
) -> int:
    """
    Сохранить астрологические данные в базу

    Args:
        user_id: ID пользователя в Telegram
        planet: планета
        prediction_type: тип предсказания
        content: содержимое предсказания
        llm_model: модель LLM
        llm_tokens_used: количество токенов
        llm_temperature: температура генерации
        expires_at: время истечения (для платных)

    Returns:
        ID созданной записи
    """
    async with get_session() as session:
        # Получаем user_id из базы
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User {user_id} not found")

        # Создаем запись предсказания
        prediction = Prediction(
            user_id=user.user_id,
            planet=planet,
            prediction_type=prediction_type,
            content=content,
            llm_model=llm_model,
            llm_tokens_used=llm_tokens_used,
            llm_temperature=llm_temperature,
            expires_at=expires_at
        )

        session.add(prediction)
        await session.commit()

        logger.info(
            f"Saved prediction for user {user_id}, planet {planet.value}"
        )
        return prediction.prediction_id


async def check_existing_moon_prediction(user_id: int) -> bool:
    """
    Проверить, есть ли уже бесплатное предсказание Луны у пользователя

    Args:
        user_id: ID пользователя в Telegram

    Returns:
        True если предсказание уже есть, False если нет
    """
    async with get_session() as session:
        # Получаем user_id из базы
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return False

        # Проверяем наличие активного бесплатного предсказания Луны
        prediction_result = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.user_id,
                Prediction.planet == Planet.moon,
                Prediction.prediction_type == PredictionType.free,
                Prediction.is_active.is_(True),
                Prediction.is_deleted.is_(False)
            )
        )
        existing_prediction = prediction_result.scalar_one_or_none()

        return existing_prediction is not None


async def start_moon_analysis(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки 'Начнем' - запуск анализа Луны

    Args:
        callback: CallbackQuery от кнопки
        state: FSMContext для управления состоянием
    """
    await callback.answer()

    user_id = callback.from_user.id
    logger.info(f"Starting moon analysis for user {user_id}")

    # Проверяем, есть ли уже бесплатное предсказание Луны
    has_existing = await check_existing_moon_prediction(user_id)
    if has_existing:
        if callback.message:
            await callback.message.answer(
                "У тебя уже есть бесплатное предсказание Луны! 🌙\n\n"
                "Хочешь получить платные предсказания для других планет? "
                "Солнце ☀️, Меркурий ☿️, Венера ♀️ или Марс ♂️?"
            )
        return

    # Получаем данные пользователя
    user_data = await get_user_astrology_data(user_id)
    if not user_data:
        if callback.message:
            await callback.message.answer(
                "❌ Не хватает данных для анализа!\n\n"
                "Убедись, что ты заполнил все поля в анкете:\n"
                "• Дата рождения\n"
                "• Время рождения\n"
                "• Место рождения\n\n"
                "Попробуй заполнить анкету заново командой /start"
            )
        return

    # Показываем сообщение о начале анализа
    if callback.message:
        await callback.message.answer(
            "🔮 Начинаю анализ твоей Луны...\n\n"
            "Это может занять несколько секунд ⏳"
        )

    try:
        # Инициализируем клиент AstrologyAPI
        # TODO: Вынести в конфиг
        api_client = AstrologyAPIClient(
            user_id="645005",
            api_key="f6c596e32bb8e29feebbae1c460aaf0913208c7c"
        )

        # Получаем данные от AstrologyAPI
        astrology_data = await api_client.get_western_horoscope(
            day=user_data["day"],
            month=user_data["month"],
            year=user_data["year"],
            hour=user_data["hour"],
            minute=user_data["minute"],
            lat=user_data["lat"],
            lon=user_data["lon"],
            tzone=user_data["tzone"],
            language="en"  # Английский для стандартных названий
        )

        # Извлекаем данные Луны
        moon_data = extract_moon_data(astrology_data)
        formatted_moon_data = format_moon_data_for_llm(moon_data)

        # TODO: Здесь будет интеграция с LLM для генерации описания
        # Пока сохраняем отформатированные данные Луны
        raw_content = (
            f"Moon Analysis Data:\n{formatted_moon_data}\n\n"
            f"Raw AstrologyAPI data: {astrology_data}"
        )

        # Сохраняем в базу данных
        prediction_id = await save_astrology_data(
            user_id=user_id,
            planet=Planet.moon,
            prediction_type=PredictionType.free,
            content=raw_content,
            llm_model="astrology_api",
            expires_at=None  # Бесплатное предсказание не истекает
        )

        # Отправляем в очередь для обработки LLM
        try:
            await send_prediction_to_queue(prediction_id, user_data["telegram_id"])
            logger.info(
                f"Prediction {prediction_id} sent to queue for LLM processing"
            )
        except Exception as e:
            logger.error(f"Failed to send prediction to queue: {e}")
            # Продолжаем работу, даже если не удалось отправить в очередь
            # TODO: Временно отключено до настройки RabbitMQ

        # Отправляем результат пользователю
        if callback.message:
            # Формируем красивое сообщение с данными Луны
            moon_info = moon_data["moon"]
            if moon_info:
                moon_message = f"""✅ Астрологические данные получены!

🌙 Твоя Луна:
• Знак: {moon_info['sign']}
• Дом: {moon_info['house']}
• Степень: {moon_info['norm_degree']:.2f}°
• Скорость: {moon_info['speed']:.2f}°/день
• Ретроградность: {'Да' if moon_info['is_retro'] == 'true' else 'Нет'}

🔗 Аспекты Луны:"""

                # Добавляем аспекты
                for aspect in moon_data["moon_aspects"]:
                    moon_message += (
                        f"\n• {aspect['aspecting_planet']} {aspect['type']} "
                        f"{aspect['aspected_planet']} "
                        f"(орб: {aspect['orb']:.2f}°)"
                    )

                moon_message += f"""

🔮 Сейчас готовлю твой персональный разбор...
Это займет несколько минут ⏳

ID предсказания: {prediction_id}"""
            else:
                moon_message = (
                    f"✅ Данные получены!\n\n"
                    f"🔮 Сейчас готовлю твой персональный разбор...\n"
                    f"Это займет несколько минут ⏳\n\n"
                    f"ID предсказания: {prediction_id}"
                )

            await callback.message.answer(moon_message)

    except Exception as e:
        logger.error(f"Moon analysis failed for user {user_id}: {e}")
        if callback.message:
            await callback.message.answer(
                "❌ Произошла ошибка при анализе Луны.\n\n"
                "Попробуй позже или обратись в поддержку."
            )