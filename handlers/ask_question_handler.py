"""
Универсальный обработчик кнопки "Задать вопрос" для всех планет.
"""

import logging

from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func

from db import get_session
from models import User, Prediction, Planet, PredictionType

logger = logging.getLogger(__name__)

# Максимальное количество вопросов для пользователя
MAX_QUESTIONS_PER_USER = 2


async def get_user_question_count(user_id: int) -> int:
    """Получает количество уже заданных вопросов пользователем"""
    async with get_session() as session:
        result = await session.execute(
            select(func.count(Prediction.prediction_id)).where(
                Prediction.user_id == user_id,
                Prediction.planet == Planet.moon,
                Prediction.prediction_type == PredictionType.free,
                Prediction.is_active.is_(True),
                Prediction.is_deleted.is_(False),
                Prediction.question.is_not(None)  # Только записи с вопросами
            )
        )
        return result.scalar() or 0


async def handle_ask_question(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки 'Задать вопрос'
    
    Args:
        callback: CallbackQuery от кнопки
        state: FSMContext для управления состоянием
    """
    await callback.answer()
    
    user_id = callback.from_user.id
    logger.info(f"User {user_id} clicked 'Ask question' button")
    
    # Проверяем количество уже заданных вопросов
    question_count = await get_user_question_count(user_id)
    
    if question_count >= MAX_QUESTIONS_PER_USER:
        if callback.message:
            await callback.message.answer(
                f"❌ Лимит вопросов исчерпан\n\n"
                f"Ты уже задал {question_count} вопросов. "
                f"Максимальное количество: {MAX_QUESTIONS_PER_USER}\n\n"
                
                "Но ты можешь получить рекомендации или исследовать "
                "другие сферы:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="💡 Получить рекомендации",
                                callback_data="get_recommendations"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="🔍 Исследовать другие сферы",
                                callback_data="explore_other_areas"
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="🏠 Главное меню",
                                callback_data="back_to_menu"
                            )
                        ]
                    ]
                )
            )
        return
    
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
        
        # Находим готовый разбор Луны (используем как основу для всех вопросов)
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
                    "❌ Астрологический разбор не найден или еще не готов.\n\n"
                    "Сначала получите разбор, а затем задайте вопрос."
                )
            return
    
    # Создаем простую клавиатуру только с кнопкой "Главное меню"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="back_to_menu"
                )
            ]
        ]
    )
    
    # Отправляем сообщение с предложением задать вопрос
    remaining_questions = MAX_QUESTIONS_PER_USER - question_count
    if callback.message:
        await callback.message.answer(
            f"❓ Задай свой вопрос\n\n"
            f"Осталось вопросов: {remaining_questions} из "
            f"{MAX_QUESTIONS_PER_USER}\n\n"
            "Напиши любой вопрос, и я отвечу на основе твоей "
            "астрологической карты! 🔮",
            reply_markup=keyboard
        )
        
        # Устанавливаем состояние ожидания вопроса
        # Импортируем здесь, чтобы избежать циклических импортов
        from main import QuestionForm
        await state.set_state(QuestionForm.waiting_for_question)
