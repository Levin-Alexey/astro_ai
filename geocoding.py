from __future__ import annotations

import asyncio
import logging
import aiohttp
from typing import Any, Optional, TypedDict
from urllib.parse import urlencode

from config import GEOCODER_BASE_URL, GEOCODER_USER_AGENT

logger = logging.getLogger(__name__)


class GeoResult(TypedDict, total=False):
    place_name: str
    country_code: Optional[str]
    lat: float
    lon: float


class GeocodingError(Exception):
    pass


async def geocode_city_ru(
    query: str,
    max_retries: int = 3,
    timeout_seconds: int = 20
) -> Optional[GeoResult]:
    """Геокодирует название населённого пункта на русском через Nominatim.

    Возвращает первый релевантный результат или None, если ничего не найдено.
    Включает retry-логику с экспоненциальной задержкой.

    Args:
        query: Название города для геокодирования
        max_retries: Максимальное количество попыток (по умолчанию 3)
        timeout_seconds: Таймаут в секундах (по умолчанию 20)

    Поля:
      - place_name: нормализованное имя места ("Краснодар, Россия" и т.п.)
      - country_code: ISO2 (например, "ru")
      - lat, lon: координаты в WGS84
    """
    q = query.strip()
    if not q:
        return None

    params = {
        "q": q,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 1,
        "accept-language": "ru",
    }
    headers = {
        "User-Agent": GEOCODER_USER_AGENT,
    }

    url = f"{GEOCODER_BASE_URL}?{urlencode(params)}"
    timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    # Задержки между попытками: 1, 2, 4 секунды
    retry_delays = [1, 2, 4]

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                delay = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
                logger.info(
                    f"Retrying geocoding for '{q}' "
                    f"(attempt {attempt + 1}/{max_retries}) after {delay}s"
                )
                await asyncio.sleep(delay)
            else:
                logger.info(f"Attempting to geocode city: '{q}'")

            async with aiohttp.ClientSession(
                timeout=timeout, headers=headers
            ) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        error_msg = (
                            f"Geocoder HTTP {resp.status}: {text[:200]}"
                        )
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"HTTP error {resp.status} for '{q}', "
                                f"will retry "
                                f"(attempt {attempt + 1}/{max_retries})"
                            )
                            continue
                        raise GeocodingError(error_msg)

                    data: Any = await resp.json()

            if not data:
                logger.warning(f"No results found for '{q}'")
                return None

            # Берём первый результат
            item = data[0]
            try:
                display_name = item.get("display_name")
                address = item.get("address", {}) or {}
                country_code = address.get("country_code")
                lat = float(item["lat"])  # type: ignore[index]
                lon = float(item["lon"])  # type: ignore[index]
            except Exception as e:
                error_msg = f"Invalid geocoder payload: {e}"
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Parsing error for '{q}', "
                        f"will retry (attempt {attempt + 1}/{max_retries})"
                    )
                    continue
                raise GeocodingError(error_msg)

            place_name = display_name or q
            logger.info(
                f"Geocoding successful for '{q}': {place_name} "
                f"(attempt {attempt + 1})"
            )
            return GeoResult(
                place_name=place_name,
                country_code=country_code,
                lat=lat,
                lon=lon
            )

        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                logger.warning(
                    f"Timeout for '{q}', retrying in {delay}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                continue
            else:
                logger.error(
                    f"Geocoding timeout for '{q}' after "
                    f"{max_retries} attempts"
                )
                raise GeocodingError(
                    f"Geocoding timeout after {max_retries} attempts"
                )

        except aiohttp.ClientError as e:
            if attempt < max_retries - 1:
                delay = retry_delays[min(attempt, len(retry_delays) - 1)]
                logger.warning(
                    f"Client error for '{q}': {e}, retrying in {delay}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                continue
            else:
                logger.error(
                    f"Client error for '{q}' after {max_retries} attempts: {e}"
                )
                raise GeocodingError(f"Client error: {e}")

    # Если все попытки исчерпаны (не должно достигнуть сюда)
    return None
