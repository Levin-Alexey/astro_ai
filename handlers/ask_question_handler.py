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
                Prediction.is_deleted.is_(False),
                Prediction.moon_analysis.is_not(None)
            ).limit(1)
        )
        prediction = prediction_result.scalar_one_or_none()
        
        if not prediction:
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
            "😼 поболтать я люблю!\n"
            "Только так мы можем глубже понять себя или какую-то тему 🤌🏼 ты можешь задать вопрос или поделиться своими переживаниями — а я отвечу тебе на основе твоей натальной карты 🔮 \n\n"
            "👇🏼 <b>Напиши, что тебя интересует</b>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        # Устанавливаем состояние ожидания вопроса
        await state.set_state(QuestionForm.waiting_for_question)
