"""
Модуль для проверки доступа к платным разборам планет
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from models import User, PlanetPayment, PaymentStatus, Planet, PaymentType

logger = logging.getLogger(__name__)


async def check_planet_access(telegram_user_id: int, planet: str) -> Dict[str, Any]:
    """
    Проверяет доступ пользователя к разбору планеты
    
    Args:
        telegram_user_id: ID пользователя в Telegram
        planet: Название планеты (sun, mercury, venus, mars)
        
    Returns:
        Dict с информацией о доступе:
        {
            "has_access": bool,
            "status": str,  # "paid", "processing", "failed", "expired", "not_paid"
            "payment_id": int or None,
            "can_retry": bool,  # можно ли повторить обработку
            "message": str  # сообщение для пользователя
        }
    """
    try:
        async with get_session() as session:
            # Находим пользователя
            user_result = await session.execute(
                select(User).where(User.telegram_id == telegram_user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                return {
                    "has_access": False,
                    "status": "user_not_found",
                    "payment_id": None,
                    "can_retry": False,
                    "message": "Пользователь не найден"
                }
            
            # Ищем оплаченные платежи для данной планеты
            planet_enum = getattr(Planet, planet, None)
            if not planet_enum:
                return {
                    "has_access": False,
                    "status": "invalid_planet",
                    "payment_id": None,
                    "can_retry": False,
                    "message": f"Неизвестная планета: {planet}"
                }
            
            # Проверяем платежи для конкретной планеты
            single_planet_result = await session.execute(
                select(PlanetPayment).where(
                    and_(
                        PlanetPayment.user_id == user.user_id,
                        PlanetPayment.planet == planet_enum,
                        PlanetPayment.payment_type == PaymentType.single_planet,
                        PlanetPayment.status.in_([
                            PaymentStatus.completed,
                            PaymentStatus.processing,
                            PaymentStatus.analysis_failed,
                            PaymentStatus.delivered
                        ])
                    )
                ).order_by(PlanetPayment.created_at.desc())
            )
            single_planet_payment = single_planet_result.scalar_one_or_none()
            
            # Проверяем платеж за все планеты
            all_planets_result = await session.execute(
                select(PlanetPayment).where(
                    and_(
                        PlanetPayment.user_id == user.user_id,
                        PlanetPayment.payment_type == PaymentType.all_planets,
                        PlanetPayment.status.in_([
                            PaymentStatus.completed,
                            PaymentStatus.processing,
                            PaymentStatus.analysis_failed,
                            PaymentStatus.delivered
                        ])
                    )
                ).order_by(PlanetPayment.created_at.desc())
            )
            all_planets_payment = all_planets_result.scalar_one_or_none()
            
            # Определяем актуальный платеж (приоритет у all_planets)
            active_payment = all_planets_payment or single_planet_payment
            
            if not active_payment:
                return {
                    "has_access": False,
                    "status": "not_paid",
                    "payment_id": None,
                    "can_retry": False,
                    "message": f"Разбор {planet.title()} не оплачен"
                }
            
            # Анализируем статус платежа
            if active_payment.status == PaymentStatus.delivered:
                return {
                    "has_access": True,
                    "status": "delivered",
                    "payment_id": active_payment.payment_id,
                    "can_retry": False,
                    "message": f"Разбор {planet.title()} уже доставлен"
                }
            
            elif active_payment.status == PaymentStatus.processing:
                return {
                    "has_access": True,
                    "status": "processing",
                    "payment_id": active_payment.payment_id,
                    "can_retry": False,
                    "message": f"Разбор {planet.title()} обрабатывается..."
                }
            
            elif active_payment.status == PaymentStatus.analysis_failed:
                return {
                    "has_access": True,
                    "status": "failed",
                    "payment_id": active_payment.payment_id,
                    "can_retry": True,
                    "message": f"Разбор {planet.title()} не удалось создать. Попробуем еще раз?"
                }
            
            elif active_payment.status == PaymentStatus.completed:
                return {
                    "has_access": True,
                    "status": "paid",
                    "payment_id": active_payment.payment_id,
                    "can_retry": True,
                    "message": f"Разбор {planet.title()} оплачен, начинаем обработку"
                }
            
            else:
                return {
                    "has_access": False,
                    "status": "unknown",
                    "payment_id": active_payment.payment_id,
                    "can_retry": False,
                    "message": f"Неизвестный статус платежа: {active_payment.status}"
                }
                
    except Exception as e:
        logger.error(f"Error checking planet access for user {telegram_user_id}, planet {planet}: {e}")
        return {
            "has_access": False,
            "status": "error",
            "payment_id": None,
            "can_retry": False,
            "message": "Ошибка при проверке доступа"
        }


async def mark_analysis_started(payment_id: int) -> bool:
    """Отмечает начало обработки разбора"""
    try:
        async with get_session() as session:
            result = await session.execute(
                select(PlanetPayment).where(PlanetPayment.payment_id == payment_id)
            )
            payment = result.scalar_one_or_none()
            
            if payment:
                payment.status = PaymentStatus.processing
                payment.analysis_started_at = datetime.now(timezone.utc)
                payment.retry_count += 1
                await session.commit()
                logger.info(f"Marked analysis started for payment {payment_id}")
                return True
            
        return False
    except Exception as e:
        logger.error(f"Error marking analysis started for payment {payment_id}: {e}")
        return False


async def mark_analysis_completed(payment_id: int) -> bool:
    """Отмечает завершение обработки разбора"""
    try:
        async with get_session() as session:
            result = await session.execute(
                select(PlanetPayment).where(PlanetPayment.payment_id == payment_id)
            )
            payment = result.scalar_one_or_none()
            
            if payment:
                payment.status = PaymentStatus.delivered
                payment.analysis_completed_at = datetime.now(timezone.utc)
                payment.delivered_at = datetime.now(timezone.utc)
                payment.last_error = None
                await session.commit()
                logger.info(f"Marked analysis completed for payment {payment_id}")
                return True
            
        return False
    except Exception as e:
        logger.error(f"Error marking analysis completed for payment {payment_id}: {e}")
        return False


async def mark_analysis_failed(payment_id: int, error_message: str) -> bool:
    """Отмечает ошибку при обработке разбора"""
    try:
        async with get_session() as session:
            result = await session.execute(
                select(PlanetPayment).where(PlanetPayment.payment_id == payment_id)
            )
            payment = result.scalar_one_or_none()
            
            if payment:
                payment.status = PaymentStatus.analysis_failed
                payment.last_error = error_message[:1000]  # Ограничиваем длину
                await session.commit()
                logger.info(f"Marked analysis failed for payment {payment_id}: {error_message}")
                return True
            
        return False
    except Exception as e:
        logger.error(f"Error marking analysis failed for payment {payment_id}: {e}")
        return False


async def get_failed_payments(limit: int = 10) -> list:
    """Получает список платежей с ошибками для повторной обработки"""
    try:
        async with get_session() as session:
            result = await session.execute(
                select(PlanetPayment).where(
                    and_(
                        PlanetPayment.status == PaymentStatus.analysis_failed,
                        PlanetPayment.retry_count < 5  # Максимум 5 попыток
                    )
                ).order_by(PlanetPayment.created_at.asc()).limit(limit)
            )
            return result.scalars().all()
    except Exception as e:
        logger.error(f"Error getting failed payments: {e}")
        return []