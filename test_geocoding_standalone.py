"""
Автономный тестовый скрипт для проверки работы геокодирования Nominatim API.
Не требует зависимостей проекта - работает самостоятельно.
"""

import asyncio
import logging
import time
import aiohttp
from urllib.parse import urlencode

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Настройки для Nominatim
GEOCODER_BASE_URL = "https://nominatim.openstreetmap.org/search"
GEOCODER_USER_AGENT = "AstroBot-Test/1.0 (test script)"
TIMEOUT_SECONDS = 8


async def test_geocoding_direct(city: str) -> dict:
    """
    Прямой тест геокодирования через Nominatim API.
    
    Returns:
        dict с результатами теста
    """
    result = {
        "city": city,
        "success": False,
        "duration": None,
        "error": None,
        "geo_result": None,
        "http_status": None
    }
    
    start_time = time.time()
    
    try:
        logger.info(f"🔍 Тестирую геокодирование для города: '{city}'")
        
        params = {
            "q": city,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 1,
            "accept-language": "ru",
        }
        headers = {
            "User-Agent": GEOCODER_USER_AGENT,
        }
        
        url = f"{GEOCODER_BASE_URL}?{urlencode(params)}"
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
        
        logger.info(f"  URL: {url}")
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url) as resp:
                result["http_status"] = resp.status
                duration = time.time() - start_time
                result["duration"] = duration
                
                if resp.status != 200:
                    text = await resp.text()
                    result["error"] = f"HTTP {resp.status}: {text[:200]}"
                    logger.error(
                        f"❌ HTTP ошибка {resp.status} для '{city}'. "
                        f"Время: {duration:.2f}с"
                    )
                    return result
                
                data = await resp.json()
        
        duration = time.time() - start_time
        result["duration"] = duration
        
        if not data or len(data) == 0:
            result["error"] = "API вернул пустой массив (город не найден)"
            logger.warning(
                f"⚠️ Геокодирование вернуло пустой результат для '{city}'. "
                f"Время: {duration:.2f}с"
            )
            return result
        
        # Берём первый результат
        item = data[0]
        try:
            display_name = item.get("display_name")
            address = item.get("address", {}) or {}
            country_code = address.get("country_code")
            lat = float(item["lat"])
            lon = float(item["lon"])
            
            result["success"] = True
            result["geo_result"] = {
                "place_name": display_name,
                "country_code": country_code,
                "lat": lat,
                "lon": lon
            }
            
            logger.info(
                f"✅ Успешно! Время: {duration:.2f}с. "
                f"Результат: {display_name}"
            )
            
        except Exception as e:
            result["error"] = f"Ошибка парсинга ответа: {str(e)}"
            logger.error(
                f"❌ Ошибка парсинга для '{city}': {e}. "
                f"Время: {duration:.2f}с"
            )
            
    except asyncio.TimeoutError as e:
        duration = time.time() - start_time
        result["duration"] = duration
        result["error"] = f"TimeoutError: {str(e)}"
        logger.error(
            f"⏱️ ТАЙМАУТ для '{city}'! "
            f"Время: {duration:.2f}с (превышен лимит {TIMEOUT_SECONDS} секунд)"
        )
        
    except aiohttp.ClientError as e:
        duration = time.time() - start_time
        result["duration"] = duration
        result["error"] = f"ClientError: {type(e).__name__}: {str(e)}"
        logger.error(
            f"❌ Ошибка клиента для '{city}': {e}. "
            f"Время: {duration:.2f}с"
        )
        
    except Exception as e:
        duration = time.time() - start_time
        result["duration"] = duration
        result["error"] = f"Unexpected error: {type(e).__name__}: {str(e)}"
        logger.error(
            f"💥 Неожиданная ошибка для '{city}': {e}. "
            f"Время: {duration:.2f}с",
            exc_info=True
        )
    
    return result


async def run_tests():
    """Запускает тесты для различных городов"""
    
    # Список городов для тестирования
    test_cities = [
        "Москва",
        "Санкт-Петербург",
        "Екатеринбург",
        "Новосибирск",
        "Краснодар",
        "Сочи",
        "Казань",
        "НесуществующийГород12345",  # Тест на несуществующий город
    ]
    
    logger.info("=" * 70)
    logger.info("🚀 Начинаю тестирование геокодирования Nominatim API")
    logger.info(f"⏱️ Таймаут: {TIMEOUT_SECONDS} секунд")
    logger.info("=" * 70)
    
    results = []
    
    # Тестируем каждый город последовательно
    for i, city in enumerate(test_cities, 1):
        logger.info(f"\n[{i}/{len(test_cities)}] Тестирую: {city}")
        result = await test_geocoding_direct(city)
        results.append(result)
        
        # Небольшая пауза между запросами (чтобы не перегружать API)
        if i < len(test_cities):
            await asyncio.sleep(1)
    
    # Выводим итоговую статистику
    logger.info("")
    logger.info("=" * 70)
    logger.info("📊 ИТОГОВАЯ СТАТИСТИКА")
    logger.info("=" * 70)
    
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    
    logger.info(f"✅ Успешных: {len(successful)}/{len(results)}")
    logger.info(f"❌ Неудачных: {len(failed)}/{len(results)}")
    
    if successful:
        durations = [r["duration"] for r in successful if r["duration"]]
        if durations:
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)
            min_duration = min(durations)
            logger.info(f"⏱️ Среднее время успешных запросов: {avg_duration:.2f}с")
            logger.info(f"⏱️ Минимальное время: {min_duration:.2f}с")
            logger.info(f"⏱️ Максимальное время: {max_duration:.2f}с")
    
    if failed:
        logger.info("")
        logger.info("❌ Детали неудачных запросов:")
        for r in failed:
            logger.info(
                f"  - {r['city']}: {r['error']} "
                f"(HTTP: {r['http_status']}, время: {r['duration']:.2f}с)"
            )
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("📋 ДЕТАЛИЗИРОВАННЫЕ РЕЗУЛЬТАТЫ")
    logger.info("=" * 70)
    
    for r in results:
        logger.info("")
        logger.info(f"Город: {r['city']}")
        logger.info(f"  Успех: {'✅ Да' if r['success'] else '❌ Нет'}")
        logger.info(f"  HTTP статус: {r['http_status']}")
        logger.info(f"  Время: {r['duration']:.2f}с" if r['duration'] else "  Время: N/A")
        if r['success'] and r['geo_result']:
            logger.info(f"  Место: {r['geo_result']['place_name']}")
            logger.info(f"  Страна: {r['geo_result']['country_code']}")
            logger.info(f"  Координаты: {r['geo_result']['lat']}, {r['geo_result']['lon']}")
        elif r['error']:
            logger.info(f"  Ошибка: {r['error']}")
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("✅ Тестирование завершено")
    logger.info("=" * 70)
    
    # Вывод рекомендаций
    timeout_count = sum(1 for r in failed if "TimeoutError" in (r.get("error") or ""))
    if timeout_count > 0:
        logger.info("")
        logger.info("⚠️ ВНИМАНИЕ: Обнаружены таймауты!")
        logger.info(f"   Количество таймаутов: {timeout_count}")
        logger.info("   Рекомендация: Рассмотрите возможность увеличения таймаута")


if __name__ == "__main__":
    try:
        asyncio.run(run_tests())
    except KeyboardInterrupt:
        logger.info("\n⚠️ Тестирование прервано пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}", exc_info=True)
