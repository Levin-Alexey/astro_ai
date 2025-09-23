import hashlib
import hmac
import logging
import uuid
from typing import Dict, Any
from aiogram import Bot
from yookassa import Configuration, Payment
from config import (
    PAYMENT_SHOP_ID, PAYMENT_SECRET_KEY, 
    PAYMENT_TEST_AMOUNT, PAYMENT_CURRENCY
)

# Настройка ЮKassa
Configuration.account_id = PAYMENT_SHOP_ID
Configuration.secret_key = PAYMENT_SECRET_KEY

logger = logging.getLogger(__name__)


class PaymentHandler:
    """Класс для обработки платежей через ЮKassa"""
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.shop_id = PAYMENT_SHOP_ID
        self.secret_key = PAYMENT_SECRET_KEY
        self.test_amount = PAYMENT_TEST_AMOUNT
        self.currency = PAYMENT_CURRENCY
    
    def create_payment_data(self, user_id: int, planet: str, description: str) -> Dict[str, Any]:
        """Создает данные для платежа"""
        return {
            "amount": {
                "value": f"{self.test_amount / 100:.2f}",
                "currency": self.currency
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/NeyroAstroBot"
            },
            "capture": True,
            "description": description,
            "metadata": {
                "user_id": str(user_id),
                "planet": planet
            }
        }
    
    async def create_payment(
        self, payment_data: Dict[str, Any]
    ) -> Dict[str, str]:
        """Создает платеж через ЮKassa API"""
        try:
            # Создаем уникальный ID для платежа
            payment_id = str(uuid.uuid4())
            
            logger.info(f"Создание платежа с ID: {payment_id}")
            logger.info(f"Данные платежа: {payment_data}")
            logger.info(f"Configuration account_id: {Configuration.account_id}")
            
            # Создаем платеж через API
            payment = Payment.create({
                "amount": payment_data["amount"],
                "confirmation": payment_data["confirmation"],
                "capture": payment_data["capture"],
                "description": payment_data["description"],
                "metadata": payment_data["metadata"]
            }, payment_id)
            
            logger.info(f"Платеж создан успешно: {payment.id}")
            logger.info(f"URL для оплаты: {payment.confirmation.confirmation_url}")
            
            # Возвращаем как URL, так и payment_id
            return {
                "payment_url": payment.confirmation.confirmation_url,
                "payment_id": payment.id
            }
            
        except Exception as e:
            logger.error(f"Ошибка при создании платежа: {e}")
            logger.error(f"Тип ошибки: {type(e).__name__}")
            # Fallback на старый метод
            fallback_url = self.create_payment_url(payment_data)
            return {
                "payment_url": fallback_url,
                "payment_id": None  # Для тестовых платежей ID не генерируется
            }
    
    def create_payment_url(self, payment_data: Dict[str, Any]) -> str:
        """Создает URL для оплаты (заглушка для тестирования)"""
        # В реальном проекте здесь будет интеграция с ЮKassa API
        # Для тестирования возвращаем заглушку
        description = payment_data['description']
        return (
            f"https://yoomoney.ru/checkout/payments/v2/checkout?"
            f"shopId={self.shop_id}&sum={self.test_amount}&"
            f"quickpay-form=shop&paymentType=AC&targets={description}"
        )
    
    def verify_webhook(self, body: str, signature: str) -> bool:
        """Проверяет подпись webhook от ЮKassa"""
        try:
            expected_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                body.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"Ошибка при проверке подписи webhook: {e}")
            return False
    
    async def process_payment_webhook(self, webhook_data: Dict[str, Any]) -> bool:
        """Обрабатывает webhook от ЮKassa"""
        try:
            logger.info(f"Обработка webhook: {webhook_data}")
            
            event = webhook_data.get('event')
            logger.info(f"Событие: {event}")
            
            if event == 'payment.succeeded':
                payment = webhook_data.get('object', {})
                logger.info(f"Данные платежа: {payment}")
                
                metadata = payment.get('metadata', {})
                logger.info(f"Метаданные: {metadata}")
                
                user_id = int(metadata.get('user_id', 0))
                planet = metadata.get('planet', '')
                
                logger.info(f"User ID: {user_id}, Planet: {planet}")
                
                if user_id and planet:
                    await self._grant_access(user_id, planet)
                    return True
                else:
                    logger.warning(f"Недостаточно данных: user_id={user_id}, planet={planet}")
            else:
                logger.info(f"Событие {event} не обрабатывается")
                
            return False
        except Exception as e:
            logger.error(f"Ошибка при обработке webhook: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    async def _grant_access(self, user_id: int, planet: str):
        """Предоставляет доступ к разбору планеты"""
        try:
            # Здесь должна быть логика предоставления доступа
            # Например, сохранение в БД, отправка уведомления и т.д.
            await self.bot.send_message(
                user_id,
                f"🎉 Платеж успешно обработан!\n\n"
                f"Теперь у тебя есть доступ к разбору {planet}!\n\n"
                f"Разбор будет готов в течение 5-10 минут."
            )
            logger.info(
                f"Доступ предоставлен пользователю {user_id} для планеты {planet}"
            )
        except Exception as e:
            logger.error(f"Ошибка при предоставлении доступа: {e}")


# Создаем экземпляр обработчика (будет инициализирован в main.py)
payment_handler = None


def init_payment_handler(bot: Bot):
    """Инициализирует обработчик платежей"""
    global payment_handler
    payment_handler = PaymentHandler(bot)
    return payment_handler
