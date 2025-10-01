#!/usr/bin/env python3
"""
Простой тест отправки в очередь рекомендаций по Солнцу
"""

import asyncio
import logging
import sys

# Добавляем путь к проекту
sys.path.append('.')

from queue_sender import send_sun_recommendation_to_queue

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_queue_sender():
    """Тестирует отправку в очередь"""
    try:
        logger.info("🚀 Тестируем отправку в очередь...")
        
        # Тест 1: Отправка с profile_id (дополнительный профиль)
        logger.info("📤 Тест 1: Отправка с profile_id")
        success1 = await send_sun_recommendation_to_queue(
            prediction_id=123,
            user_telegram_id=999999999,
            sun_analysis="Тестовый разбор Солнца для дополнительного профиля",
            profile_id=456
        )
        
        if success1:
            logger.info("✅ Тест 1 прошел: отправка с profile_id работает")
        else:
            logger.error("❌ Тест 1 не прошел: ошибка отправки с profile_id")
        
        # Тест 2: Отправка без profile_id (основной профиль)
        logger.info("📤 Тест 2: Отправка без profile_id")
        success2 = await send_sun_recommendation_to_queue(
            prediction_id=124,
            user_telegram_id=999999999,
            sun_analysis="Тестовый разбор Солнца для основного профиля",
            profile_id=None
        )
        
        if success2:
            logger.info("✅ Тест 2 прошел: отправка без profile_id работает")
        else:
            logger.error("❌ Тест 2 не прошел: ошибка отправки без profile_id")
        
        if success1 and success2:
            logger.info("🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
            logger.info("✅ Отправка в очередь работает для обоих типов профилей")
        else:
            logger.error("❌ Некоторые тесты не прошли")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_queue_sender())

