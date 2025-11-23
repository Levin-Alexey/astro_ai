import asyncio
import logging
from geocoding import geocode_city_ru, GeocodingError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

TEST_CITIES = [
    "Пенза",
    "Москва",
    "Санкт-Петербург",
    "Казань",
]


async def main():
    for city in TEST_CITIES:
        try:
            res = await geocode_city_ru(city)
            print(f"{city} -> {res}")
        except GeocodingError as e:
            print(f"{city} ERROR: {e}")
        except Exception as e:
            print(f"{city} UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
