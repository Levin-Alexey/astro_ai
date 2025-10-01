"""
Обработчик кнопки "Получить рекомендации" после разбора Солнца.
"""

import logging
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from db import get_session
from models import User, Prediction, Planet, PredictionType, AdditionalProfile
from sqlalchemy import select, desc
from queue_sender import send_sun_recommendation_to_queue

logger = logging.getLogger(__name__)


async def handle_get_sun_recommendations(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки 'Получить рекомендации' для Солнца
    
    Args:
        callback: CallbackQuery от кнопки
        state: FSMContext для управления состоянием
    """
    await callback.answer()
    
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested sun recommendations")
    
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
        
        # Находим готовый разбор Солнца (самый свежий)
        # Сначала ищем разборы с profile_id (дополнительные профили), потом без (основной)
        prediction_result = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.user_id,
                Prediction.planet == Planet.sun,
                Prediction.prediction_type == PredictionType.paid,
                Prediction.is_active.is_(True),
                Prediction.is_deleted.is_(False),
                Prediction.sun_analysis.is_not(None),  # Готовый анализ
                Prediction.profile_id.is_not(None)  # Сначала дополнительные профили
            ).order_by(desc(Prediction.created_at)).limit(1)
        )
        prediction = prediction_result.scalar_one_or_none()
        
        # Если не нашли разбор дополнительного профиля, ищем основной
        if not prediction:
            prediction_result = await session.execute(
                select(Prediction).where(
                    Prediction.user_id == user.user_id,
                    Prediction.planet == Planet.sun,
                    Prediction.prediction_type == PredictionType.paid,
                    Prediction.is_active.is_(True),
                    Prediction.is_deleted.is_(False),
                    Prediction.sun_analysis.is_not(None),  # Готовый анализ
                    Prediction.profile_id.is_(None)  # Основной профиль
                ).order_by(desc(Prediction.created_at)).limit(1)
            )
            prediction = prediction_result.scalar_one_or_none()
        
        if not prediction or not prediction.sun_analysis:
            if callback.message:
                await callback.message.answer(
                    "❌ Разбор Солнца не найден или еще не готов.\n\n"
                    "Сначала получите разбор Солнца, а затем рекомендации."
                )
            return
    
    # Определяем profile_id из найденного разбора
    profile_id = prediction.profile_id
    profile_name = None
    
    # Если это дополнительный профиль, получаем его имя
    if profile_id:
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
                f"☀️ Готовлю персональные рекомендации на основе "
                f"разбора Солнца для {profile_name}...\n\n"
                f"⏳ Это займет несколько секунд"
            )
        else:
            message_text = (
                "☀️ Готовлю персональные рекомендации на основе "
                "твоего разбора Солнца...\n\n"
                "⏳ Это займет несколько секунд"
            )
        await callback.message.answer(message_text)
    
    try:
        # Отправляем в очередь для генерации рекомендаций по Солнцу
        await send_sun_recommendation_to_queue(
            prediction_id=prediction.prediction_id,
            user_telegram_id=user_id,
            sun_analysis=prediction.sun_analysis,
            profile_id=profile_id
        )
        
        logger.info(f"Sun recommendation request sent to queue for user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to send sun recommendation request: {e}")
        if callback.message:
            await callback.message.answer(
                "❌ Произошла ошибка при создании рекомендаций.\n\n"
                "Попробуйте позже или обратитесь в поддержку."
            )
