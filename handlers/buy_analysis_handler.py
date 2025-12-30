"""
Обработчик кнопки "Купить разбор" в главном меню.
"""

import logging

from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)


async def show_buy_analysis_menu(message: Message):
    """
    Показывает меню покупки разборов с четырьмя опциями:
    1. Купить разбор для себя
    2. Главное меню
    """
    
    # Создаем клавиатуру с двумя кнопками
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👑 Купить для себя",
                    callback_data="buy_analysis_self"
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Перейти в главное меню",
                    callback_data="back_to_menu"
                )
            ]
        ]
    )

    menu_text = (
        "<b>💵 Купить разбор</b>\n\n"
        "Краткая инструкция:\n"
        "👑 Купить для себя → переходи сюда, если хочешь купить разбор "
        "по своей дате \n\n"
        "<b>Выбирай нужное действие</b>👇🏼"
    )
    
    await message.answer(
        menu_text,
        reply_markup=kb,
        parse_mode="HTML"
    )


async def handle_buy_analysis_self(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Купить разбор для себя".
    Показывает выбор планет для покупки на основе текущих данных пользователя.
    """
    try:
        # Получаем ID пользователя из callback (пользователь, нажавший кнопку)
        user_id = callback.from_user.id if callback.from_user else 0
        logger.info(f"handle_buy_analysis_self вызвана для user_id={user_id}")
        
        # Получаем message для отправки ответа
        message = callback.message
        if not message:
            logger.error("callback.message is None")
            return
        
        # Получаем информацию о пользователе и его разборах
        from db import get_session
        from models import User, Prediction, Planet
        from sqlalchemy import select
        
        async with get_session() as session:
            # Находим пользователя
            logger.info(f"Ищем пользователя с telegram_id={user_id}")
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            logger.info(f"Результат поиска пользователя: {user}")
            
            if not user:
                logger.error(f"Пользователь с telegram_id={user_id} не найден в БД")
                await message.answer(
                    "❌ Пользователь не найден в базе данных.\n"
                    "Попробуйте перезапустить бота командой /start"
                )
                return
            
            # Получаем уже купленные разборы (только основного профиля)
            existing_predictions = await session.execute(
                select(Prediction.planet)
                .where(
                    Prediction.user_id == user.user_id,
                    Prediction.is_deleted.is_(False),
                    Prediction.profile_id.is_(None)  # Только основные разборы
                )
                .distinct()
            )
            owned_planets = {
                pred.planet for pred in existing_predictions.fetchall()
            }
            
            # Определяем доступные планеты и их цены
            planets_info = [
                {
                    "planet": Planet.sun,
                    "emoji": "☀️",
                    "name": "Солнце",
                    "description": "Твоя сущность и жизненная сила",
                    "price": 500,
                    "callback": "pay_sun"
                },
                {
                    "planet": Planet.mercury,
                    "emoji": "☿️",
                    "name": "Меркурий", 
                    "description": "Мышление и общение",
                    "price": 500,
                    "callback": "pay_mercury"
                },
                {
                    "planet": Planet.venus,
                    "emoji": "♀️",
                    "name": "Венера",
                    "description": "Любовь и красота",
                    "price": 500,
                    "callback": "pay_venus"
                },
                {
                    "planet": Planet.mars,
                    "emoji": "♂️",
                    "name": "Марс",
                    "description": "Энергия и действия",
                    "price": 500,
                    "callback": "pay_mars"
                }
            ]
            
            # Создаем кнопки для всех планет с батарейками
            keyboard_buttons = []
            available_count = 0
            
            for planet_info in planets_info:
                if planet_info["planet"] in owned_planets:
                    # Планета куплена - зеленая батарейка
                    battery = "🔋"
                else:
                    # Планета не куплена - красная батарейка
                    battery = "🪫"
                    available_count += 1
                
                btn_text = f"{battery} {planet_info['name']}"
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=btn_text,
                        callback_data=planet_info['callback']
                    )
                ])
            
            # Добавляем кнопку "Все планеты" если доступны все
            if available_count > 1:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text="Все планеты 222₽",
                        callback_data="pay_all_planets"
                    )
                ])
            
            # Добавляем кнопку возврата в меню
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data="buy_analysis"
                )
            ])
            
            kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            
            # Формируем текст сообщения
            text_parts = [
                "� <b>Купить разбор для себя</b>\n\n",
                "Твой прогресс:\n",
                "🔋 → эта планета разобрана! При нажатии на кнопку ты сможешь заново прочитать разбор планеты и личные рекомендации + задать мне любые вопросы 💫\n",
                "🪫 → эта планета не разобрана! При нажатии на кнопку ты сможешь купить разбор со скидкой 💰\n\n",
                "Краткая памятка по планетам:\n",
                "🌙 Луна — базовые потребности, внутренний мир, семья\n",
                "☀️ Солнце — энергия, уверенность в себе, предназначение\n",
                "🧠 Меркурий — интеллект, коммуникация, обучение\n",
                "💰� Венера — отношения, финансы, удовольствие от жизни\n",
                "⚡️ Марс — сила, умение действовать, мотивация\n\n",
                "🔓 Пока бот на тесте, ты получаешь консультацию астролога почти даром:\n\n",
                "� <b>Одна планета — 77₽ (вместо 999₽)</b>\n",
                "💣 <b>Все планеты сразу — 222₽ (вместо 5555₽)</b> + 🎁: обсуждение своей натальной карты с Лилит 24/7\n\n",
                "<b>Выбери разбор по кнопке</b>👇🏼"
            ]
            
            await message.answer(
                "".join(text_parts),
                reply_markup=kb,
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(
            f"Ошибка в покупке разборов для пользователя {user_id}: {e}"
        )
        if message:
            await message.answer(
                "❌ Произошла ошибка при загрузке каталога разборов.\n"
                "Попробуйте позже или обратитесь в службу заботы.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🔙 Назад",
                                callback_data="buy_analysis"
                            )
                        ]
                    ]
                )
            )

