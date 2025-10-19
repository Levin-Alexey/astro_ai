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
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from db import get_session
from models import User, Prediction, Planet, PredictionType

logger = logging.getLogger(__name__)


class QuestionForm(StatesGroup):
    """FSM состояния для обработки вопросов"""
    waiting_for_question = State()


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
                Prediction.is_deleted.is_(False)
            ).limit(1)
        )
        prediction = prediction_result.scalar_one_or_none()
        
        if not prediction:
            if callback.message:
                await callback.message.answer(
                    "❌ Астрологический разбор не найден.\n\n"
                    "Сначала получите бесплатный разбор Луны, а затем задайте вопрос."
                )
            return
        
        # Проверяем, есть ли готовый анализ Луны
        # moon_analysis - это основной анализ, который генерируется воркером
        has_analysis = bool(prediction.moon_analysis)
        
        if not has_analysis:
            if callback.message:
                await callback.message.answer(
                    "❌ Астрологический разбор еще не готов.\n\n"
                    "Дождитесь завершения анализа, а затем задайте вопрос."
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
    if callback.message:
        await callback.message.answer(
            "❓ Задай свой вопрос\n\n"
            "Напиши любой вопрос, и я отвечу на основе твоей "
            "астрологической карты! 🔮",
            reply_markup=keyboard
        )
        
        # Устанавливаем состояние ожидания вопроса
        await state.set_state(QuestionForm.waiting_for_question)
