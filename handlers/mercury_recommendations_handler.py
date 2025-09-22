"""
Обработчик кнопки "Получить рекомендации" после разбора Меркурия.
"""

import logging
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from db import get_session
from models import User, Prediction, Planet, PredictionType
from sqlalchemy import select, desc
from queue_sender import send_mercury_recommendation_to_queue

logger = logging.getLogger(__name__)


async def handle_get_mercury_recommendations(
    callback: CallbackQuery,
    state: FSMContext
):
    """
    Обработчик кнопки 'Получить рекомендации' для Меркурия
    
    Args:
        callback: CallbackQuery от кнопки
        state: FSMContext для управления состоянием
    """
    await callback.answer()
    
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested mercury recommendations")
    
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
        
        # Находим готовый разбор Меркурия (самый свежий)
        prediction_result = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.user_id,
                Prediction.planet == Planet.mercury,
                Prediction.prediction_type == PredictionType.paid,
                Prediction.is_active.is_(True),
                Prediction.is_deleted.is_(False),
                Prediction.mercury_analysis.is_not(None)  # Готовый анализ
            ).order_by(desc(Prediction.created_at)).limit(1)
        )
        prediction = prediction_result.scalar_one_or_none()
        
        if not prediction or not prediction.mercury_analysis:
            if callback.message:
                await callback.message.answer(
                    "❌ Разбор Меркурия не найден или еще не готов.\n\n"
                    "Сначала получите разбор Меркурия, а затем рекомендации."
                )
            return
    
    # Показываем сообщение о начале генерации рекомендаций
    if callback.message:
        await callback.message.answer(
            "☿️ Готовлю персональные рекомендации на основе "
            "твоего разбора Меркурия...\n\n"
            "⏳ Это займет несколько секунд"
        )
    
    try:
        # Отправляем в очередь для генерации рекомендаций по Меркурию
        await send_mercury_recommendation_to_queue(
            prediction_id=prediction.prediction_id,
            user_telegram_id=user_id,
            mercury_analysis=prediction.mercury_analysis
        )
        
        logger.info(
            f"Mercury recommendation request sent to queue for user {user_id}"
        )
        
    except Exception as e:
        logger.error(f"Failed to send mercury recommendation request: {e}")
        if callback.message:
            await callback.message.answer(
                "❌ Произошла ошибка при создании рекомендаций.\n\n"
                "Попробуйте позже или обратитесь в поддержку."
            )