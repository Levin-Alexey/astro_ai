"""
Обработчик кнопки "Получить рекомендации" после разбора Марса.
"""

import logging
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from db import get_session
from models import User, Prediction, Planet, PredictionType
from sqlalchemy import select, desc
from queue_sender import send_mars_recommendation_to_queue

logger = logging.getLogger(__name__)


async def handle_get_mars_recommendations(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки 'Получить рекомендации' для Марса
    
    Args:
        callback: CallbackQuery от кнопки
        state: FSMContext для управления состоянием
    """
    await callback.answer()
    
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested mars recommendations")
    
    # Получаем данные пользователя
    async with get_session() as session:
        # Находим пользователя
        user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            if callback.message:
                await callback.message.answer(
                    "❌ Пользователь не найден. Попробуйте /start"
                )
            return
        
        # Находим готовый разбор Марса (самый свежий)
        prediction_result = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.user_id,
                Prediction.planet == Planet.mars,
                Prediction.prediction_type == PredictionType.paid,
                Prediction.mars_analysis.isnot(None)
            ).order_by(desc(Prediction.created_at))
        )
        prediction = prediction_result.scalar_one_or_none()
        
        if not prediction:
            if callback.message:
                await callback.message.answer(
                    "❌ Разбор Марса не найден. Сначала получите разбор Марса."
                )
            return
        
        # Отправляем в очередь для генерации рекомендаций
        try:
            success = await send_mars_recommendation_to_queue(
                prediction.prediction_id,
                user_id,
                prediction.mars_analysis
            )
            
            if success:
                if callback.message:
                    await callback.message.answer(
                        "💡 Генерирую персональные рекомендации по Марсу...\n\n"
                        "⏳ Это займет несколько секунд"
                    )
                logger.info(f"Mars recommendations request sent to queue for user {user_id}")
            else:
                if callback.message:
                    await callback.message.answer(
                        "❌ Ошибка при отправке запроса на рекомендации. Попробуйте позже."
                    )
                logger.error(f"Failed to send Mars recommendations request for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error sending Mars recommendations request: {e}")
            if callback.message:
                await callback.message.answer(
                    "❌ Произошла ошибка. Попробуйте позже."
                )
