"""
Тестовый скрипт для проверки работы геокодирования.
Проверяет, отвечает ли API Nominatim и как быстро он работает.
"""

import asyncio
import logging
import time
from typing import Optional

from geocoding import geocode_city_ru, GeocodingError

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_geocoding(city: str) -> dict:
    """
    Тестирует геокодирование для одного города.
    
    Returns:
        dict с результатами теста
    """
    result = {
        "city": city,
        "success": False,
        "duration": None,
        "error": None,
        "geo_result": None
    }
    
    start_time = time.time()
    
    try:
        logger.info(f"🔍 Тестирую геокодирование для города: '{city}'")
        geo_result = await geocode_city_ru(city)
        
        duration = time.time() - start_time
        result["duration"] = duration
        
        if geo_result:
            result["success"] = True
            result["geo_result"] = {
                "place_name": geo_result.get("place_name"),
                "country_code": geo_result.get("country_code"),
                "lat": geo_result.get("lat"),
                "lon": geo_result.get("lon")
            }
            logger.info(
                f"✅ Успешно! Время: {duration:.2f}с. "
                f"Результат: {geo_result.get('place_name')}"
            )
        else:
            result["error"] = "API вернул None (город не найден)"
            logger.warning(
                f"⚠️ Геокодирование вернуло None для '{city}'. "
                f"Время: {duration:.2f}с"
            )
            
    except GeocodingError as e:
        duration = time.time() - start_time
        result["duration"] = duration
        result["error"] = f"GeocodingError: {str(e)}"
        logger.error(
            f"❌ Ошибка геокодирования для '{city}': {e}. "
            f"Время: {duration:.2f}с"
        )
        
    except asyncio.TimeoutError as e:
        duration = time.time() - start_time
        result["duration"] = duration
        result["error"] = f"TimeoutError: {str(e)}"
        logger.error(
            f"⏱️ Таймаут для '{city}'! Время: {duration:.2f}с (превышен лимит 8 секунд)"
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
    
    logger.info("=" * 60)
    logger.info("🚀 Начинаю тестирование геокодирования")
    logger.info("=" * 60)
    
    results = []
    
    # Тестируем каждый город последовательно
    for city in test_cities:
        result = await test_geocoding(city)
        results.append(result)
        
        # Небольшая пауза между запросами (чтобы не перегружать API)
        await asyncio.sleep(1)
    
    # Выводим итоговую статистику
    logger.info("")
    logger.info("=" * 60)
    logger.info("📊 ИТОГОВАЯ СТАТИСТИКА")
    logger.info("=" * 60)
    
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
            logger.info(f"  - {r['city']}: {r['error']} (время: {r['duration']:.2f}с)")
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("📋 ДЕТАЛИЗИРОВАННЫЕ РЕЗУЛЬТАТЫ")
    logger.info("=" * 60)
    
    for r in results:
        logger.info("")
        logger.info(f"Город: {r['city']}")
        logger.info(f"  Успех: {'✅ Да' if r['success'] else '❌ Нет'}")
        logger.info(f"  Время: {r['duration']:.2f}с" if r['duration'] else "  Время: N/A")
        if r['success'] and r['geo_result']:
            logger.info(f"  Место: {r['geo_result']['place_name']}")
            logger.info(f"  Страна: {r['geo_result']['country_code']}")
            logger.info(f"  Координаты: {r['geo_result']['lat']}, {r['geo_result']['lon']}")
        elif r['error']:
            logger.info(f"  Ошибка: {r['error']}")
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("✅ Тестирование завершено")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(run_tests())
    except KeyboardInterrupt:
        logger.info("\n⚠️ Тестирование прервано пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}", exc_info=True)
