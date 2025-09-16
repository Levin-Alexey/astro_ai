#!/usr/bin/env python3
"""
Тестовый скрипт для проверки системы оплаты
"""
import asyncio
import logging
from aiogram import Bot
from payment_handler import PaymentHandler

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_payment_system():
    """Тестирует систему оплаты"""
    logger.info("Тестирование системы оплаты...")
    
    # Создаем заглушку бота для тестирования
    bot = Bot(token="test_token")
    
    # Создаем обработчик платежей
    payment_handler = PaymentHandler(bot)
    
    # Тестируем создание данных платежа
    test_user_id = 12345
    test_planet = "sun"
    test_description = "Тестовый разбор Солнца"
    
    payment_data = payment_handler.create_payment_data(
        user_id=test_user_id,
        planet=test_planet,
        description=test_description
    )
    
    logger.info(f"Данные платежа: {payment_data}")
    
    # Тестируем создание URL
    payment_url = payment_handler.create_payment_url(payment_data)
    logger.info(f"URL платежа: {payment_url}")
    
    # Тестируем проверку подписи webhook
    test_body = '{"event": "payment.succeeded", "object": {"metadata": {"user_id": "12345", "planet": "sun"}}}'
    test_signature = "test_signature"
    
    is_valid = payment_handler.verify_webhook(test_body, test_signature)
    logger.info(f"Проверка подписи (ожидается False): {is_valid}")
    
    # Тестируем обработку webhook
    webhook_data = {
        "event": "payment.succeeded",
        "object": {
            "metadata": {
                "user_id": "12345",
                "planet": "sun"
            }
        }
    }
    
    success = await payment_handler.process_payment_webhook(webhook_data)
    logger.info(f"Обработка webhook (ожидается True): {success}")
    
    logger.info("Тестирование завершено!")

if __name__ == "__main__":
    asyncio.run(test_payment_system())
