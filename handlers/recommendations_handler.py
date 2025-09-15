"""
Обработчик кнопки "Получить рекомендации" после разбора Луны.
"""

import logging
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from db import get_session
from models import User, Prediction, Planet, PredictionType
from sqlalchemy import select
from queue_sender import send_recommendation_to_queue

logger = logging.getLogger(__name__)


async def handle_get_recommendations(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки 'Получить рекомендации'
    
    Args:
        callback: CallbackQuery от кнопки
        state: FSMContext для управления состоянием
    """
    await callback.answer()
    
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested recommendations")
    
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
        
        # Находим готовый разбор Луны
        prediction_result = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.user_id,
                Prediction.planet == Planet.moon,
                Prediction.prediction_type == PredictionType.free,
                Prediction.is_active.is_(True),
                Prediction.is_deleted.is_(False),
                Prediction.moon_analysis.is_not(None)  # Готовый анализ
            )
        )
        prediction = prediction_result.scalar_one_or_none()
        
        if not prediction or not prediction.moon_analysis:
            if callback.message:
                await callback.message.answer(
                    "❌ Разбор Луны не найден или еще не готов.\n\n"
                    "Сначала получите разбор Луны, а затем рекомендации."
                )
            return
    
    # Показываем сообщение о начале генерации рекомендаций
    if callback.message:
        await callback.message.answer(
            "💡 Готовлю персональные рекомендации на основе "
            "твоего разбора Луны...\n\n"
            "⏳ Это займет несколько секунд"
        )
    
    try:
        # Отправляем в очередь для генерации рекомендаций
        await send_recommendation_to_queue(
            prediction_id=prediction.prediction_id,
            user_telegram_id=user_id,
            moon_analysis=prediction.moon_analysis
        )
        
        logger.info(f"Recommendation request sent to queue for user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to send recommendation request: {e}")
        if callback.message:
            await callback.message.answer(
                "❌ Произошла ошибка при создании рекомендаций.\n\n"
                "Попробуйте позже или обратитесь в поддержку."
            )
