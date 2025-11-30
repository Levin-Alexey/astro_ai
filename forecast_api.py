import logging
import base64
from datetime import date, datetime
from typing import Dict, Any, Optional

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from models import User, AdditionalProfile
from config import ASTROLOGY_API_KEY, ASTROLOGY_API_USER_ID

logger = logging.getLogger(__name__)

# Базовый URL API
BASE_URL = "https://json.astrologyapi.com/v1/"

class AstrologyAPIClient:
    """Клиент для работы с AstrologyAPI.com"""

    def __init__(self, user_id: str, api_key: str):
        self.user_id = user_id
        self.api_key = api_key
        self.base_url = BASE_URL

    async def get_natal_transits_daily(
        self,
        birth_datetime: datetime,
        birth_lat: float,
        birth_lon: float,
        birth_tzid_hours: float,
        current_date: date
    ) -> Dict[str, Any]:
        """
        Получает ежедневные натальные транзиты с AstrologyAPI.
        Метод: /natal_transits/daily
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "API key not set"
            }

        url = f"{self.base_url}natal_transits/daily"
        
        credentials = f"{self.user_id}:{self.api_key}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "day": birth_datetime.day,
            "month": birth_datetime.month,
            "year": birth_datetime.year,
            "hour": birth_datetime.hour,
            "min": birth_datetime.minute,
            "lat": birth_lat,
            "lon": birth_lon,
            "tzone": birth_tzid_hours,
            # Не передаем current_date, так как в примере testapi.js его нет,
            # и API вероятно использует текущую дату сервера.
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=headers, json=payload, timeout=60) as response:
                    if response.status == 200:
                        return {"success": True, "data": await response.json()}
                    else:
                        error_text = await response.text()
                        logger.error(f"AstrologyAPI error {response.status}: {error_text}")
                        return {"success": False, "error": f"API error: {response.status} - {error_text}"}
            except Exception as e:
                logger.error(f"Error calling AstrologyAPI: {e}")
                return {"success": False, "error": str(e)}


async def get_user_profile_data(
    session: AsyncSession, user_id: int, profile_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    Получает данные профиля для запроса к API.
    """
    if profile_id:
        result = await session.execute(
            select(AdditionalProfile).where(
                AdditionalProfile.profile_id == profile_id,
                AdditionalProfile.owner_user_id == user_id
            )
        )
        profile = result.scalar_one_or_none()
        if profile:
            return {
                "birth_datetime": profile.birth_datetime_utc,
                "birth_lat": profile.birth_lat,
                "birth_lon": profile.birth_lon,
                "tz_offset_hours": (profile.tz_offset_minutes or 0) / 60.0,
                "full_name": profile.full_name or "Пользователь",
                "gender": profile.gender.value if profile.gender else "unknown"
            }
    
    # user_id - это PK пользователя
    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user:
        return {
            "birth_datetime": user.birth_datetime_utc,
            "birth_lat": user.birth_lat,
            "birth_lon": user.birth_lon,
            "tz_offset_hours": (user.tz_offset_minutes or 0) / 60.0,
            "full_name": user.first_name or "Пользователь",
            "gender": user.gender.value if user.gender else "unknown"
        }
    return None


async def get_forecast_data(user_id: int, profile_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Основная функция для получения данных прогноза.
    Возвращает результат API.
    """
    async with get_session() as session:
        profile_data = await get_user_profile_data(session, user_id, profile_id)
    
    if not profile_data:
        return {"success": False, "error": "User data not found"}
    
    if not all([profile_data["birth_datetime"], profile_data["birth_lat"]]):
        return {"success": False, "error": "Incomplete birth data"}

    logger.info(f"Using USER_ID: {ASTROLOGY_API_USER_ID}, API_KEY len: {len(str(ASTROLOGY_API_KEY))}")
    client = AstrologyAPIClient(ASTROLOGY_API_USER_ID, ASTROLOGY_API_KEY)
    
    api_response = await client.get_natal_transits_daily(
        birth_datetime=profile_data["birth_datetime"],
        birth_lat=profile_data["birth_lat"],
        birth_lon=profile_data["birth_lon"],
        birth_tzid_hours=profile_data["tz_offset_hours"],
        current_date=date.today()
    )
    
    # Добавляем метаданные профиля к ответу, чтобы воркер знал имя/пол
    if api_response["success"]:
        api_response["profile_data"] = {
            "full_name": profile_data["full_name"],
            "gender": profile_data["gender"]
        }
        
    return api_response
