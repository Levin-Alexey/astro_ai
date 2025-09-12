from __future__ import annotations

import aiohttp
from typing import Any, Dict, Optional, TypedDict
from urllib.parse import urlencode

from config import GEOCODER_BASE_URL, GEOCODER_USER_AGENT


class GeoResult(TypedDict, total=False):
    place_name: str
    country_code: Optional[str]
    lat: float
    lon: float


class GeocodingError(Exception):
    pass


async def geocode_city_ru(query: str) -> Optional[GeoResult]:
    """Геокодирует название населённого пункта на русском через Nominatim.

    Возвращает первый релевантный результат или None, если ничего не найдено.
    
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
    timeout = aiohttp.ClientTimeout(total=8)

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise GeocodingError(f"Geocoder HTTP {resp.status}: {text[:200]}")
            data: Any = await resp.json()

    if not data:
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
        raise GeocodingError(f"Invalid geocoder payload: {e}")

    place_name = display_name or q
    return GeoResult(place_name=place_name, country_code=country_code, lat=lat, lon=lon)
