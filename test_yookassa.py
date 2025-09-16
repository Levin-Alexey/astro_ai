#!/usr/bin/env python3
"""
Тест интеграции с ЮKassa
"""
import asyncio
import logging
from yookassa import Configuration, Payment
from config import PAYMENT_SHOP_ID, PAYMENT_SECRET_KEY

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_yookassa_config():
    """Тестирует конфигурацию ЮKassa"""
    logger.info("Тестирование конфигурации ЮKassa...")
    
    # Настройка ЮKassa
    Configuration.account_id = PAYMENT_SHOP_ID
    Configuration.secret_key = PAYMENT_SECRET_KEY
    
    logger.info(f"Shop ID: {PAYMENT_SHOP_ID}")
    logger.info(f"Secret Key: {PAYMENT_SECRET_KEY[:10]}...")
    logger.info(f"Configuration account_id: {Configuration.account_id}")
    logger.info(f"Configuration secret_key: {Configuration.secret_key[:10]}...")

def test_create_payment():
    """Тестирует создание платежа"""
    logger.info("Тестирование создания платежа...")
    
    try:
        # Настройка ЮKassa
        Configuration.account_id = PAYMENT_SHOP_ID
        Configuration.secret_key = PAYMENT_SECRET_KEY
        
        # Данные для платежа
        payment_data = {
            "amount": {
                "value": "10.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://pay.neyroastro.ru/webhook/success"
            },
            "capture": True,
            "description": "Тестовый платеж - Астрологический разбор Солнца",
            "metadata": {
                "user_id": "12345",
                "planet": "sun"
            }
        }
        
        logger.info(f"Данные платежа: {payment_data}")
        
        # Создаем платеж
        payment = Payment.create(payment_data)
        
        logger.info(f"✅ Платеж создан успешно!")
        logger.info(f"ID платежа: {payment.id}")
        logger.info(f"Статус: {payment.status}")
        logger.info(f"URL для оплаты: {payment.confirmation.confirmation_url}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании платежа: {e}")
        logger.error(f"Тип ошибки: {type(e).__name__}")
        return False

def test_payment_info():
    """Тестирует получение информации о платеже"""
    logger.info("Тестирование получения информации о платеже...")
    
    try:
        # Настройка ЮKassa
        Configuration.account_id = PAYMENT_SHOP_ID
        Configuration.secret_key = PAYMENT_SECRET_KEY
        
        # Получаем список платежей
        payments = Payment.list({"limit": 1})
        
        if payments.items:
            payment = payments.items[0]
            logger.info(f"✅ Найден платеж: {payment.id}")
            logger.info(f"Статус: {payment.status}")
            logger.info(f"Сумма: {payment.amount.value} {payment.amount.currency}")
        else:
            logger.info("Платежи не найдены")
            
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка при получении информации о платеже: {e}")
        return False

if __name__ == "__main__":
    logger.info("=== ТЕСТ ИНТЕГРАЦИИ С ЮKASSA ===")
    
    # Тест 1: Конфигурация
    test_yookassa_config()
    print()
    
    # Тест 2: Создание платежа
    success = test_create_payment()
    print()
    
    # Тест 3: Информация о платежах
    test_payment_info()
    print()
    
    if success:
        logger.info("🎉 Интеграция с ЮKassa работает!")
    else:
        logger.error("💥 Проблемы с интеграцией ЮKassa")
