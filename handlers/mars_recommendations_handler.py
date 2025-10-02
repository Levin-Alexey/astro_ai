"""
Обработчик кнопки "Получить рекомендации" после разбора Марса.
"""

import logging
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from db import get_session
from models import User, Prediction, Planet, PredictionType, AdditionalProfile
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
    logger.info(f"handle_get_mars_recommendations called for user {user_id}")
    
    # Получаем данные пользователя
    async with get_session() as session:
        # Находим пользователя
        user_result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User with telegram_id={user_id} not found in DB")
            if callback.message:
                await callback.message.answer(
                    "❌ Пользователь не найден. Попробуйте /start"
                )
            return
        
        logger.info(f"User found: user_id={user.user_id}")
        
        # Находим готовый разбор Марса (последний созданный, может быть несколько профилей)
        prediction_result = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.user_id,
                Prediction.planet == Planet.mars,
                Prediction.prediction_type == PredictionType.paid,
                Prediction.is_active.is_(True),
                Prediction.is_deleted.is_(False),
                Prediction.mars_analysis.isnot(None)
            ).order_by(desc(Prediction.created_at))
        )
        prediction = prediction_result.scalars().first()  # Используем first() для множества результатов
        
        logger.info(f"Prediction found: {prediction is not None}, has analysis: {prediction.mars_analysis is not None if prediction else False}")
        
        if not prediction:
            logger.warning(f"No ready mars analysis found for user {user_id}")
            if callback.message:
                await callback.message.answer(
                    "❌ Разбор Марса не найден. Сначала получите разбор Марса."
                )
            return
        
        # Определяем, для какого профиля запрашиваются рекомендации
        profile_id = prediction.profile_id
        profile_name = None
        
        if profile_id:
            # Это дополнительный профиль - получаем его данные
            profile_result = await session.execute(
                select(AdditionalProfile).where(AdditionalProfile.profile_id == profile_id)
            )
            profile = profile_result.scalar_one_or_none()
            if profile:
                profile_name = profile.full_name
    
    # Показываем сообщение о начале генерации рекомендаций
    if callback.message:
        if profile_name:
            message_text = (
                f"♂️ Готовлю персональные рекомендации на основе "
                f"разбора Марса для {profile_name}...\n\n"
                f"⏳ Это займет несколько секунд"
            )
        else:
            message_text = (
                "♂️ Готовлю персональные рекомендации на основе "
                "твоего разбора Марса...\n\n"
                "⏳ Это займет несколько секунд"
            )
        await callback.message.answer(message_text)
    
    logger.info(
        f"Sending mars recommendation to queue: prediction_id={prediction.prediction_id}, "
        f"profile_id={profile_id}, profile_name={profile_name}"
    )
    
    # Отправляем в очередь для генерации рекомендаций
    try:
        success = await send_mars_recommendation_to_queue(
            prediction.prediction_id,
            user_id,
            prediction.mars_analysis,
            profile_id
        )
        
        if success:
            logger.info(f"Mars recommendations request sent to queue for user {user_id}, profile_id={profile_id}")
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
