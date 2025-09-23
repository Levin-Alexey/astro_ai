"""
Скрипт для восстановления неудачных платежей и повторной обработки разборов
"""

import asyncio
import logging
from datetime import datetime, timezone
from payment_access import get_failed_payments, mark_analysis_started
from queue_sender import send_venus_prediction_to_queue, send_sun_prediction_to_queue, send_mercury_prediction_to_queue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def retry_failed_payments():
    """Повторно обрабатывает неудачные платежи"""
    try:
        # Получаем список неудачных платежей
        failed_payments = await get_failed_payments(limit=20)
        
        if not failed_payments:
            logger.info("No failed payments found")
            return
        
        logger.info(f"Found {len(failed_payments)} failed payments to retry")
        
        for payment in failed_payments:
            try:
                logger.info(f"Retrying payment {payment.payment_id} for planet {payment.planet}")
                
                # Отмечаем начало повторной обработки
                await mark_analysis_started(payment.payment_id)
                
                # Получаем данные пользователя
                from db import get_session
                from models import User
                from sqlalchemy import select
                
                async with get_session() as session:
                    user_result = await session.execute(
                        select(User).where(User.user_id == payment.user_id)
                    )
                    user = user_result.scalar_one_or_none()
                    
                    if not user:
                        logger.error(f"User {payment.user_id} not found")
                        continue
                    
                    # Отправляем в очередь в зависимости от планеты
                    if payment.planet == "venus":
                        success = await send_venus_prediction_to_queue(
                            user_telegram_id=user.telegram_id,
                            user_data={
                                "first_name": user.first_name,
                                "gender": user.gender.value if user.gender else "unknown"
                            },
                            astrology_data={} # Заглушка, данные должны восстанавливаться из профиля
                        )
                    elif payment.planet == "sun":
                        success = await send_sun_prediction_to_queue(
                            user_telegram_id=user.telegram_id,
                            user_data={
                                "first_name": user.first_name,
                                "gender": user.gender.value if user.gender else "unknown"
                            },
                            astrology_data={}
                        )
                    elif payment.planet == "mercury":
                        success = await send_mercury_prediction_to_queue(
                            user_telegram_id=user.telegram_id,
                            user_data={
                                "first_name": user.first_name,
                                "gender": user.gender.value if user.gender else "unknown"
                            },
                            astrology_data={}
                        )
                    else:
                        logger.warning(f"Unknown planet: {payment.planet}")
                        continue
                    
                    if success:
                        logger.info(f"Successfully queued retry for payment {payment.payment_id}")
                    else:
                        logger.error(f"Failed to queue retry for payment {payment.payment_id}")
                        
            except Exception as e:
                logger.error(f"Error retrying payment {payment.payment_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error in retry_failed_payments: {e}")


if __name__ == "__main__":
    asyncio.run(retry_failed_payments())