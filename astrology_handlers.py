"""
Обработчики астрологических функций для бота.

Включает:
- Клиент для AstrologyAPI
- Обработчики для анализа планет
- Интеграция с LLM для генерации предсказаний
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import aiohttp
import base64
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from db import get_session
from models import User, Prediction, Planet, PredictionType
from config import ASTROLOGY_API_USER_ID, ASTROLOGY_API_KEY
from sqlalchemy import select
from queue_sender import send_prediction_to_queue
import aio_pika
import json

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

    # Добавляем аспекты (сумма орбов не более 4 градусов)
    # Сортируем по орбу по возрастанию
    sorted_aspects = sorted(aspects, key=lambda x: x['orb'])
    filtered_aspects = []
    total_orb = 0.0
    
    # Логируем исходные аспекты
    logger.info(f"Original aspects count: {len(aspects)}")
    for i, aspect in enumerate(sorted_aspects):
        logger.info(f"Aspect {i+1}: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°)")
    
    for aspect in sorted_aspects:
        if total_orb + aspect['orb'] <= 4.0:
            filtered_aspects.append(aspect)
            total_orb += aspect['orb']
            logger.info(f"Added aspect: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°), total_orb: {total_orb:.2f}°")
        else:
            logger.info(f"Skipped aspect: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°) - would exceed 4° limit")
            break
    
    logger.info(f"Final filtered aspects count: {len(filtered_aspects)}, total_orb: {total_orb:.2f}°")
    
    for aspect in filtered_aspects:
        result += (
            f"- {aspect['aspecting_planet']} {aspect['type']} "
            f"{aspect['aspected_planet']} "
            f"(орб: {aspect['orb']:.2f}°)\n"
        )

    return result


def extract_sun_data(astrology_data: dict) -> dict:
    """
    Извлекает данные Солнца и его аспектов из ответа AstrologyAPI

    Args:
        astrology_data: Полный ответ от AstrologyAPI

    Returns:
        Dict с данными Солнца и его аспектами
    """
    sun_data: dict = {
        "sun": None,
        "sun_aspects": []
    }

    # Извлекаем данные Солнца из списка планет
    if "planets" in astrology_data:
        for planet in astrology_data["planets"]:
            if planet.get("name") == "Sun":
                sun_data["sun"] = {
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

    # Извлекаем аспекты Солнца
    if "aspects" in astrology_data:
        for aspect in astrology_data["aspects"]:
            if aspect.get("aspecting_planet") == "Sun":
                sun_data["sun_aspects"].append({
                    "aspecting_planet": aspect.get("aspecting_planet"),
                    "aspected_planet": aspect.get("aspected_planet"),
                    "type": aspect.get("type"),
                    "orb": aspect.get("orb"),
                    "diff": aspect.get("diff")
                })

    return sun_data


def format_sun_data_for_llm(sun_data: dict) -> str:
    """
    Форматирует данные Солнца для отправки в LLM

    Args:
        sun_data: Данные Солнца из extract_sun_data

    Returns:
        Отформатированная строка для LLM
    """
    if not sun_data["sun"]:
        return "Данные Солнца не найдены"

    sun = sun_data["sun"]
    aspects = sun_data["sun_aspects"]

    # Основная информация о Солнце
    result = f"""Солнце в знаке {sun['sign']}, дом {sun['house']}
Степень: {sun['norm_degree']:.2f}°
Скорость: {sun['speed']:.2f}°/день
Ретроградность: {'Да' if sun['is_retro'] == 'true' else 'Нет'}

Аспекты Солнца:
"""

    # Добавляем аспекты (сумма орбов не более 4 градусов)
    # Сортируем по орбу по возрастанию
    sorted_aspects = sorted(aspects, key=lambda x: x['orb'])
    filtered_aspects = []
    total_orb = 0.0
    
    # Логируем исходные аспекты
    logger.info(f"Original Sun aspects count: {len(aspects)}")
    for i, aspect in enumerate(sorted_aspects):
        logger.info(f"Sun Aspect {i+1}: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°)")
    
    for aspect in sorted_aspects:
        if total_orb + aspect['orb'] <= 4.0:
            filtered_aspects.append(aspect)
            total_orb += aspect['orb']
            logger.info(f"Added Sun aspect: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°), total_orb: {total_orb:.2f}°")
        else:
            logger.info(f"Skipped Sun aspect: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°) - would exceed 4° limit")
            break
    
    logger.info(f"Final filtered Sun aspects count: {len(filtered_aspects)}, total_orb: {total_orb:.2f}°")
    
    for aspect in filtered_aspects:
        result += (
            f"- {aspect['aspecting_planet']} {aspect['type']} "
            f"{aspect['aspected_planet']} "
            f"(орб: {aspect['orb']:.2f}°)\n"
        )

    return result


def extract_mercury_data(astrology_data: dict) -> dict:
    """
    Извлекает данные Меркурия и его аспектов из ответа AstrologyAPI

    Args:
        astrology_data: Полный ответ от AstrologyAPI

    Returns:
        Dict с данными Меркурия и его аспектами
    """
    mercury_data: dict = {
        "mercury": None,
        "mercury_aspects": []
    }

    # Извлекаем данные Меркурия из списка планет
    if "planets" in astrology_data:
        for planet in astrology_data["planets"]:
            if planet.get("name") == "Mercury":
                mercury_data["mercury"] = {
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

    # Извлекаем аспекты Меркурия
    if "aspects" in astrology_data:
        for aspect in astrology_data["aspects"]:
            if aspect.get("aspecting_planet") == "Mercury":
                mercury_data["mercury_aspects"].append({
                    "aspecting_planet": aspect.get("aspecting_planet"),
                    "aspected_planet": aspect.get("aspected_planet"),
                    "type": aspect.get("type"),
                    "orb": aspect.get("orb"),
                    "diff": aspect.get("diff")
                })

    return mercury_data


def format_mercury_data_for_llm(mercury_data: dict) -> str:
    """
    Форматирует данные Меркурия для отправки в LLM

    Args:
        mercury_data: Данные Меркурия из extract_mercury_data

    Returns:
        Отформатированная строка для LLM
    """
    if not mercury_data["mercury"]:
        return "Данные Меркурия не найдены"

    mercury = mercury_data["mercury"]
    aspects = mercury_data["mercury_aspects"]

    # Основная информация о Меркурии
    result = f"""Меркурий в знаке {mercury['sign']}, дом {mercury['house']}
Степень: {mercury['norm_degree']:.2f}°
Скорость: {mercury['speed']:.2f}°/день
Ретроградность: {'Да' if mercury['is_retro'] == 'true' else 'Нет'}

Аспекты Меркурия:
"""

    # Добавляем аспекты (сумма орбов не более 4 градусов)
    # Сортируем по орбу по возрастанию
    sorted_aspects = sorted(aspects, key=lambda x: x['orb'])
    filtered_aspects = []
    total_orb = 0.0
    
    # Логируем исходные аспекты
    logger.info(f"Original Mercury aspects count: {len(aspects)}")
    for i, aspect in enumerate(sorted_aspects):
        logger.info(f"Mercury Aspect {i+1}: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°)")
    
    for aspect in sorted_aspects:
        if total_orb + aspect['orb'] <= 4.0:
            filtered_aspects.append(aspect)
            total_orb += aspect['orb']
            logger.info(f"Added Mercury aspect: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°), total_orb: {total_orb:.2f}°")
        else:
            logger.info(f"Skipped Mercury aspect: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°) - would exceed 4° limit")
            break
    
    logger.info(f"Final filtered Mercury aspects count: {len(filtered_aspects)}, total_orb: {total_orb:.2f}°")
    
    for aspect in filtered_aspects:
        result += (
            f"- {aspect['aspecting_planet']} {aspect['type']} "
            f"{aspect['aspected_planet']} "
            f"(орб: {aspect['orb']:.2f}°)\n"
        )

    return result


def extract_venus_data(astrology_data: dict) -> dict:
    """
    Извлекает данные Венеры и её аспектов из ответа AstrologyAPI

    Args:
        astrology_data: Полный ответ от AstrologyAPI

    Returns:
        Dict с данными Венеры и её аспектами
    """
    venus_data: dict = {
        "venus": None,
        "venus_aspects": []
    }

    # Извлекаем данные Венеры из списка планет
    if "planets" in astrology_data:
        for planet in astrology_data["planets"]:
            if planet.get("name") == "Venus":
                venus_data["venus"] = {
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

    # Извлекаем аспекты Венеры
    if "aspects" in astrology_data:
        for aspect in astrology_data["aspects"]:
            if aspect.get("aspecting_planet") == "Venus":
                venus_data["venus_aspects"].append({
                    "aspecting_planet": aspect.get("aspecting_planet"),
                    "aspected_planet": aspect.get("aspected_planet"),
                    "type": aspect.get("type"),
                    "orb": aspect.get("orb"),
                    "diff": aspect.get("diff")
                })

    return venus_data


def format_venus_data_for_llm(venus_data: dict) -> str:
    """
    Форматирует данные Венеры для отправки в LLM

    Args:
        venus_data: Данные Венеры из extract_venus_data

    Returns:
        Отформатированная строка для LLM
    """
    if not venus_data["venus"]:
        return "Данные Венеры не найдены"

    venus = venus_data["venus"]
    aspects = venus_data["venus_aspects"]

    # Основная информация о Венере
    result = f"""Венера в знаке {venus['sign']}, дом {venus['house']}
Степень: {venus['norm_degree']:.2f}°
Скорость: {venus['speed']:.2f}°/день
Ретроградность: {'Да' if venus['is_retro'] == 'true' else 'Нет'}

Аспекты Венеры:
"""

    # Добавляем аспекты (сумма орбов не более 4 градусов)
    # Сортируем по орбу по возрастанию
    sorted_aspects = sorted(aspects, key=lambda x: x['orb'])
    filtered_aspects = []
    total_orb = 0.0
    
    # Логируем исходные аспекты
    logger.info(f"Original Venus aspects count: {len(aspects)}")
    for i, aspect in enumerate(sorted_aspects):
        logger.info(f"Venus Aspect {i+1}: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°)")
    
    # Отбираем аспекты с общим орбом не более 4 градусов
    for aspect in sorted_aspects:
        if total_orb + aspect['orb'] <= 4.0:
            filtered_aspects.append(aspect)
            total_orb += aspect['orb']
            logger.info(f"Venus Aspect INCLUDED: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°)")
        else:
            logger.info(f"Venus Aspect EXCLUDED (total orb would be {total_orb + aspect['orb']:.2f}°): {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°)")

    # Если нет подходящих аспектов, берем самый сильный (с минимальным орбом)
    if not filtered_aspects and aspects:
        filtered_aspects = [sorted_aspects[0]]
        logger.info(f"Venus: No aspects under 4° total, taking strongest: {sorted_aspects[0]['aspecting_planet']} {sorted_aspects[0]['type']} {sorted_aspects[0]['aspected_planet']}")

    # Форматируем отобранные аспекты
    logger.info(f"Final filtered Venus aspects count: {len(filtered_aspects)}, total_orb: {total_orb:.2f}°")
    
    for aspect in filtered_aspects:
        result += (
            f"- {aspect['aspecting_planet']} {aspect['type']} "
            f"{aspect['aspected_planet']} "
            f"(орб: {aspect['orb']:.2f}°)\n"
        )

    return result


def extract_mars_data(astrology_data: dict) -> dict:
    """
    Извлекает данные Марса и его аспектов из ответа AstrologyAPI

    Args:
        astrology_data: Полный ответ от AstrologyAPI

    Returns:
        Dict с данными Марса и его аспектами
    """
    mars_data: dict = {
        "mars": None,
        "mars_aspects": []
    }

    # Извлекаем данные Марса из списка планет
    if "planets" in astrology_data:
        for planet in astrology_data["planets"]:
            if planet.get("name") == "Mars":
                mars_data["mars"] = {
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

    # Извлекаем аспекты Марса
    if "aspects" in astrology_data:
        for aspect in astrology_data["aspects"]:
            if aspect.get("aspecting_planet") == "Mars":
                mars_data["mars_aspects"].append({
                    "aspecting_planet": aspect.get("aspecting_planet"),
                    "aspected_planet": aspect.get("aspected_planet"),
                    "type": aspect.get("type"),
                    "orb": aspect.get("orb"),
                    "diff": aspect.get("diff")
                })

    return mars_data


def format_mars_data_for_llm(mars_data: dict) -> str:
    """
    Форматирует данные Марса для отправки в LLM

    Args:
        mars_data: Данные Марса из extract_mars_data

    Returns:
        Отформатированная строка для LLM
    """
    if not mars_data["mars"]:
        return "Данные Марса не найдены"

    mars = mars_data["mars"]
    aspects = mars_data["mars_aspects"]

    # Основная информация о Марсе
    result = f"""Марс в знаке {mars['sign']}, дом {mars['house']}
Степень: {mars['norm_degree']:.2f}°
Скорость: {mars['speed']:.2f}°/день
Ретроградность: {'Да' if mars['is_retro'] == 'true' else 'Нет'}

Аспекты Марса:
"""

    # Добавляем аспекты (сумма орбов не более 4 градусов)
    # Сортируем по орбу по возрастанию
    sorted_aspects = sorted(aspects, key=lambda x: x['orb'])
    filtered_aspects = []
    total_orb = 0.0
    
    # Логируем исходные аспекты
    logger.info(f"Original Mars aspects count: {len(aspects)}")
    for i, aspect in enumerate(sorted_aspects):
        logger.info(f"Mars Aspect {i+1}: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°)")
    
    # Отбираем аспекты с общим орбом не более 4 градусов
    for aspect in sorted_aspects:
        if total_orb + aspect['orb'] <= 4.0:
            filtered_aspects.append(aspect)
            total_orb += aspect['orb']
            logger.info(f"Mars Aspect INCLUDED: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°)")
        else:
            logger.info(f"Mars Aspect EXCLUDED (total orb would be {total_orb + aspect['orb']:.2f}°): {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°)")

    # Если нет подходящих аспектов, берем самый сильный (с минимальным орбом)
    if not filtered_aspects and aspects:
        filtered_aspects = [sorted_aspects[0]]
        logger.info(f"Mars: No aspects under 4° total, taking strongest: {sorted_aspects[0]['aspecting_planet']} {sorted_aspects[0]['type']} {sorted_aspects[0]['aspected_planet']}")

    # Форматируем отобранные аспекты
    logger.info(f"Final filtered Mars aspects count: {len(filtered_aspects)}, total_orb: {total_orb:.2f}°")
    
    for aspect in filtered_aspects:
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

        # Создаем запись предсказания - сохраняем сырые данные в content
        # Результат LLM будет сохранен в соответствующий столбец воркером
        prediction = Prediction(
            user_id=user.user_id,
            planet=planet,
            prediction_type=prediction_type,
            content=content,  # Сырые данные от API
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


async def save_recommendations(
    user_id: int,
    recommendations: str,
    llm_model: Optional[str] = None,
    llm_tokens_used: Optional[int] = None,
    llm_temperature: Optional[float] = None
) -> int:
    """
    Сохранить рекомендации в базу

    Args:
        user_id: ID пользователя в Telegram
        recommendations: текст рекомендаций
        llm_model: модель LLM
        llm_tokens_used: количество токенов
        llm_temperature: температура генерации

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

        # Создаем запись предсказания для рекомендаций
        prediction = Prediction(
            user_id=user.user_id,
            planet=Planet.moon,  # Рекомендации привязаны к Луне
            prediction_type=PredictionType.free,
            recommendations=recommendations,
            llm_model=llm_model,
            llm_tokens_used=llm_tokens_used,
            llm_temperature=llm_temperature,
            expires_at=None
        )

        session.add(prediction)
        await session.commit()

        logger.info(f"Saved recommendations for user {user_id}")
        return prediction.prediction_id


async def save_qa_response(
    user_id: int,
    question: str,
    answer: str,
    llm_model: Optional[str] = None,
    llm_tokens_used: Optional[int] = None,
    llm_temperature: Optional[float] = None
) -> int:
    """
    Сохранить ответ на вопрос пользователя

    Args:
        user_id: ID пользователя в Telegram
        question: вопрос пользователя
        answer: ответ от LLM
        llm_model: модель LLM
        llm_tokens_used: количество токенов
        llm_temperature: температура генерации

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

        # Формируем полный текст Q&A
        qa_content = f"Вопрос: {question}\n\nОтвет: {answer}"

        # Создаем запись предсказания для Q&A
        prediction = Prediction(
            user_id=user.user_id,
            planet=Planet.moon,  # Q&A привязаны к Луне
            prediction_type=PredictionType.free,
            qa_responses=qa_content,
            llm_model=llm_model,
            llm_tokens_used=llm_tokens_used,
            llm_temperature=llm_temperature,
            expires_at=None
        )

        session.add(prediction)
        await session.commit()

        logger.info(f"Saved Q&A response for user {user_id}")
        return prediction.prediction_id


async def get_user_predictions(user_id: int) -> Dict[str, Optional[str]]:
    """
    Получить все предсказания пользователя из разных столбцов

    Args:
        user_id: ID пользователя в Telegram

    Returns:
        Dict с данными из всех столбцов
    """
    async with get_session() as session:
        # Получаем user_id из базы
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return {}

        # Получаем все активные предсказания пользователя
        predictions_result = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.user_id,
                Prediction.is_active.is_(True),
                Prediction.is_deleted.is_(False)
            )
        )
        predictions = predictions_result.scalars().all()

        # Объединяем данные из всех предсказаний
        result_data: Dict[str, Optional[str]] = {
            "moon_analysis": None,
            "sun_analysis": None,
            "mercury_analysis": None,
            "venus_analysis": None,
            "mars_analysis": None,
            "recommendations": None,
            "qa_responses": None
        }

        for prediction in predictions:
            if prediction.moon_analysis:
                result_data["moon_analysis"] = prediction.moon_analysis
            if prediction.sun_analysis:
                result_data["sun_analysis"] = prediction.sun_analysis
            if prediction.mercury_analysis:
                result_data["mercury_analysis"] = prediction.mercury_analysis
            if prediction.venus_analysis:
                result_data["venus_analysis"] = prediction.venus_analysis
            if prediction.mars_analysis:
                result_data["mars_analysis"] = prediction.mars_analysis
            if prediction.recommendations:
                result_data["recommendations"] = prediction.recommendations
            if prediction.qa_responses:
                result_data["qa_responses"] = prediction.qa_responses

        return result_data


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
        # с готовым анализом
        prediction_result = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.user_id,
                Prediction.planet == Planet.moon,
                Prediction.prediction_type == PredictionType.free,
                Prediction.is_active.is_(True),
                Prediction.is_deleted.is_(False),
                # Проверяем, что анализ готов
                Prediction.moon_analysis.is_not(None)
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
        api_client = AstrologyAPIClient(
            user_id=ASTROLOGY_API_USER_ID,
            api_key=ASTROLOGY_API_KEY
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
            await send_prediction_to_queue(
                prediction_id, user_data["telegram_id"]
            )
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

                # Добавляем аспекты (сумма орбов не более 4 градусов)
                # Сортируем по орбу по возрастанию
                sorted_aspects = sorted(
                    moon_data["moon_aspects"], 
                    key=lambda x: x['orb']
                )
                filtered_aspects = []
                total_orb = 0.0
                
                # Логируем исходные аспекты
                logger.info(f"Moon analysis - Original aspects count: {len(moon_data['moon_aspects'])}")
                for i, aspect in enumerate(sorted_aspects):
                    logger.info(f"Moon analysis - Aspect {i+1}: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°)")
                
                for aspect in sorted_aspects:
                    if total_orb + aspect['orb'] <= 4.0:
                        filtered_aspects.append(aspect)
                        total_orb += aspect['orb']
                        logger.info(f"Moon analysis - Added aspect: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°), total_orb: {total_orb:.2f}°")
                    else:
                        logger.info(f"Moon analysis - Skipped aspect: {aspect['aspecting_planet']} {aspect['type']} {aspect['aspected_planet']} (орб: {aspect['orb']:.2f}°) - would exceed 4° limit")
                        break
                
                logger.info(f"Moon analysis - Final filtered aspects count: {len(filtered_aspects)}, total_orb: {total_orb:.2f}°")
                
                for aspect in filtered_aspects:
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


async def start_sun_analysis(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Запускает анализ Солнца для пользователя

    Args:
        user_id: ID пользователя в Telegram

    Returns:
        Dict с данными астрологического API или None при ошибке
    """
    try:
        # Получаем данные пользователя
        user_data = await get_user_astrology_data(user_id)
        if not user_data:
            logger.warning(f"Cannot get astrology data for user {user_id}")
            return None

        # Инициализируем клиент AstrologyAPI
        api_client = AstrologyAPIClient(
            user_id=ASTROLOGY_API_USER_ID,
            api_key=ASTROLOGY_API_KEY
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

        # Извлекаем данные Солнца
        sun_data = extract_sun_data(astrology_data)
        formatted_sun_data = format_sun_data_for_llm(sun_data)

        # Сохраняем отформатированные данные Солнца
        raw_content = (
            f"Sun Analysis Data:\n{formatted_sun_data}\n\n"
            f"Raw AstrologyAPI data: {astrology_data}"
        )

        # Сохраняем в базу данных
        prediction_id = await save_astrology_data(
            user_id=user_id,
            planet=Planet.sun,
            prediction_type=PredictionType.paid,
            content=raw_content,
            llm_model="astrology_api",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30)  # 30 дней доступа
        )

        # Отправляем в очередь для обработки LLM
        try:
            await send_sun_prediction_to_queue(
                prediction_id, user_data["telegram_id"]
            )
            logger.info(
                f"Sun prediction {prediction_id} sent to queue for LLM processing"
            )
        except Exception as e:
            logger.error(f"Failed to send Sun prediction to queue: {e}")

        return astrology_data

    except Exception as e:
        logger.error(f"Error in start_sun_analysis: {e}")
        return None


async def start_mercury_analysis(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Запускает анализ Меркурия для пользователя

    Args:
        user_id: ID пользователя в Telegram

    Returns:
        Dict с данными астрологического API или None при ошибке
    """
    try:
        # Получаем данные пользователя
        user_data = await get_user_astrology_data(user_id)
        if not user_data:
            logger.warning(f"Cannot get astrology data for user {user_id}")
            return None

        # Инициализируем клиент AstrologyAPI
        api_client = AstrologyAPIClient(
            user_id=ASTROLOGY_API_USER_ID,
            api_key=ASTROLOGY_API_KEY
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

        # Извлекаем данные Меркурия
        mercury_data = extract_mercury_data(astrology_data)
        formatted_mercury_data = format_mercury_data_for_llm(mercury_data)

        # Сохраняем отформатированные данные Меркурия
        raw_content = (
            f"Mercury Analysis Data:\n{formatted_mercury_data}\n\n"
            f"Raw AstrologyAPI data: {astrology_data}"
        )

        # Сохраняем в базу данных
        prediction_id = await save_astrology_data(
            user_id=user_id,
            planet=Planet.mercury,
            prediction_type=PredictionType.paid,
            content=raw_content,
            llm_model="astrology_api",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30)  # 30 дней доступа
        )

        # Отправляем в очередь для обработки LLM
        try:
            await send_mercury_prediction_to_queue(
                prediction_id, user_data["telegram_id"]
            )
            logger.info(
                f"☿️ Mercury prediction {prediction_id} sent to queue for LLM processing"
            )
        except Exception as e:
            logger.error(f"Failed to send Mercury prediction to queue: {e}")

        return astrology_data

    except Exception as e:
        logger.error(f"Error in start_mercury_analysis: {e}")
        return None


async def send_sun_prediction_to_queue(prediction_id: int, user_id: int) -> bool:
    """Отправляет предсказание Солнца в очередь sun_predictions"""
    try:
        # Подключение к RabbitMQ
        RABBITMQ_URL = "amqp://astro_user:astro_password_123@31.128.40.111:5672/"
        QUEUE_NAME = "sun_predictions"
        
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()
        
        # Объявляем очередь
        await channel.declare_queue(QUEUE_NAME, durable=True)
        
        # Создаем сообщение
        message_data = {
            "prediction_id": prediction_id,
            "user_id": user_id
        }
        
        # Отправляем сообщение
        await channel.default_exchange.publish(
            aio_pika.Message(
                json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=QUEUE_NAME
        )
        
        await connection.close()
        logger.info(f"✅ Sun prediction {prediction_id} sent to sun_predictions queue")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error sending sun prediction to queue: {e}")
        return False


async def send_mercury_prediction_to_queue(prediction_id: int, user_id: int) -> bool:
    """Отправляет предсказание Меркурия в очередь mercury_predictions"""
    try:
        from queue_sender import send_mercury_prediction_to_queue as queue_send
        
        success = await queue_send(prediction_id, user_id)
        if success:
            logger.info(f"☿️ Mercury prediction {prediction_id} sent to mercury_predictions queue")
        else:
            logger.error(f"❌ Failed to send Mercury prediction {prediction_id} to queue")
        return success
        
    except Exception as e:
        logger.error(f"❌ Error sending mercury prediction to queue: {e}")
        return False


async def start_venus_analysis(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Запускает анализ Венеры для пользователя

    Args:
        user_id: ID пользователя в Telegram

    Returns:
        Dict с данными астрологического API или None при ошибке
    """
    try:
        # Получаем данные пользователя
        user_data = await get_user_astrology_data(user_id)
        if not user_data:
            logger.warning(f"Cannot get astrology data for user {user_id}")
            return None

        # Инициализируем клиент AstrologyAPI
        api_client = AstrologyAPIClient(
            user_id=ASTROLOGY_API_USER_ID,
            api_key=ASTROLOGY_API_KEY
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

        # Извлекаем данные Венеры
        venus_data = extract_venus_data(astrology_data)
        formatted_venus_data = format_venus_data_for_llm(venus_data)

        # Сохраняем отформатированные данные Венеры
        raw_content = (
            f"Venus Analysis Data:\n{formatted_venus_data}\n\n"
            f"Raw AstrologyAPI data: {astrology_data}"
        )

        # Сохраняем в базу данных
        prediction_id = await save_astrology_data(
            user_id=user_id,
            planet=Planet.venus,
            prediction_type=PredictionType.paid,
            content=raw_content,
            llm_model="astrology_api",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30)  # 30 дней доступа
        )

        # Отправляем в очередь для обработки LLM
        try:
            await send_venus_prediction_to_queue(
                prediction_id, user_data["telegram_id"]
            )
            logger.info(
                f"♀️ Venus prediction {prediction_id} sent to queue for LLM processing"
            )
        except Exception as e:
            logger.error(f"Failed to send Venus prediction to queue: {e}")

        return astrology_data

    except Exception as e:
        logger.error(f"Error in start_venus_analysis: {e}")
        return None


async def send_venus_prediction_to_queue(prediction_id: int, user_id: int) -> bool:
    """Отправляет предсказание Венеры в очередь venus_predictions"""
    try:
        from queue_sender import send_venus_prediction_to_queue as queue_send
        
        success = await queue_send(prediction_id, user_id)
        if success:
            logger.info(f"♀️ Venus prediction {prediction_id} sent to venus_predictions queue")
        else:
            logger.error(f"❌ Failed to send Venus prediction {prediction_id} to queue")
        return success
        
    except Exception as e:
        logger.error(f"❌ Error sending venus prediction to queue: {e}")
        return False


async def start_mars_analysis(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Запускает анализ Марса для пользователя

    Args:
        user_id: ID пользователя в Telegram

    Returns:
        Dict с данными астрологического API или None при ошибке
    """
    try:
        # Получаем данные пользователя
        user_data = await get_user_astrology_data(user_id)
        if not user_data:
            logger.warning(f"Cannot get astrology data for user {user_id}")
            return None

        # Инициализируем клиент AstrologyAPI
        api_client = AstrologyAPIClient(
            user_id=ASTROLOGY_API_USER_ID,
            api_key=ASTROLOGY_API_KEY
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

        # Извлекаем данные Марса
        mars_data = extract_mars_data(astrology_data)
        formatted_mars_data = format_mars_data_for_llm(mars_data)

        # Сохраняем отформатированные данные Марса
        raw_content = (
            f"Mars Analysis Data:\n{formatted_mars_data}\n\n"
            f"Raw AstrologyAPI data: {astrology_data}"
        )

        # Сохраняем в базу данных
        prediction_id = await save_astrology_data(
            user_id=user_id,
            planet=Planet.mars,
            prediction_type=PredictionType.paid,
            content=raw_content,
            llm_model="astrology_api",
            expires_at=datetime.now(timezone.utc) + timedelta(days=30)  # 30 дней доступа
        )

        # Отправляем в очередь для обработки LLM
        try:
            await send_mars_prediction_to_queue(
                prediction_id, user_data["telegram_id"]
            )
            logger.info(
                f"♂️ Mars prediction {prediction_id} sent to queue for LLM processing"
            )
        except Exception as e:
            logger.error(f"Failed to send Mars prediction to queue: {e}")

        return astrology_data

    except Exception as e:
        logger.error(f"Error in start_mars_analysis: {e}")
        return None


async def send_mars_prediction_to_queue(prediction_id: int, user_id: int) -> bool:
    """Отправляет предсказание Марса в очередь mars_predictions"""
    try:
        from queue_sender import send_mars_prediction_to_queue as queue_send
        
        success = await queue_send(prediction_id, user_id)
        if success:
            logger.info(f"♂️ Mars prediction {prediction_id} sent to mars_predictions queue")
        else:
            logger.error(f"❌ Failed to send Mars prediction {prediction_id} to queue")
        return success
        
    except Exception as e:
        logger.error(f"❌ Error sending mars prediction to queue: {e}")
        return False