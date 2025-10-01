"""
Обработчик кнопки "Купить разбор" в главном меню.
"""

import logging

from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)


async def show_buy_analysis_menu(message: Message):
    """
    Показывает меню покупки разборов с тремя опциями:
    1. Купить разбор для себя
    2. Добавить новую дату  
    3. Главное меню
    """
    
    # Создаем клавиатуру с тремя кнопками
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Купить разбор для себя",
                    callback_data="buy_analysis_self"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 Добавить новую дату",
                    callback_data="add_new_date"
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

    menu_text = (
        "💳 **Купить разбор**\n\n"
        "Выберите действие:\n\n"
        "💳 **Купить разбор для себя**\n"
        "Персональный астрологический разбор на основе ваших данных рождения\n\n"
        "📅 **Добавить новую дату**\n"
        "Создать разбор для другого человека (друг, ребенок, партнер)\n\n"
        "Все разборы сохраняются в вашем личном кабинете и доступны в любое время!"
    )
    
    await message.answer(
        menu_text,
        reply_markup=kb,
        parse_mode="Markdown"
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
            
            # Получаем уже купленные разборы
            existing_predictions = await session.execute(
                select(Prediction.planet)
                .where(
                    Prediction.user_id == user.user_id,
                    Prediction.is_deleted.is_(False)
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
            
            # Создаем кнопки для доступных планет
            keyboard_buttons = []
            available_count = 0
            
            for planet_info in planets_info:
                if planet_info["planet"] not in owned_planets:
                    keyboard_buttons.append([
                        InlineKeyboardButton(
                            text=f"{planet_info['emoji']} {planet_info['name']} - {planet_info['price']}₽",
                            callback_data=planet_info['callback']
                        )
                    ])
                    available_count += 1
            
            # Добавляем кнопку "Все планеты" если доступны все
            if available_count > 1:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text="🪐 Все планеты - 1500₽ (скидка 25%)",
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
                "💳 **Купить разбор для себя**\n",
                "Выбери планету для персонального астрологического разбора:\n"
            ]
            
            for planet_info in planets_info:
                if planet_info["planet"] in owned_planets:
                    status = "✅ Уже есть"
                else:
                    status = f"💰 {planet_info['price']}₽"
                
                planet_text = (
                    f"{planet_info['emoji']} **{planet_info['name']}** - "
                    f"{planet_info['description']} ({status})"
                )
                text_parts.append(planet_text)
            
            if available_count == 0:
                text_parts.append("\n🎉 У тебя уже есть все разборы планет!")
            else:
                text_parts.append(
                    f"\n💡 **Доступно для покупки:** {available_count} разборов"
                )
                if available_count > 1:
                    text_parts.append(
                        "🎁 **Специальное предложение:** Купи все планеты сразу со скидкой 25%!"
                    )
            
            text_parts.append("\n🔮 Каждый разбор содержит:")
            text_parts.append(
                "• Персональный анализ планеты в твоей натальной карте"
            )
            text_parts.append("• Практические рекомендации")
            text_parts.append("• Ответы на твои вопросы")
            
            await message.answer(
                "\n".join(text_parts),
                reply_markup=kb,
                parse_mode="Markdown"
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


async def handle_add_new_date(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "Добавить новую дату".
    Здесь будет логика создания разбора для другого человека.
    """
    message = callback.message
    if not message:
        return
    
    await message.answer(
        "📅 **Добавить новую дату**\n\n"
        "Эта функция будет реализована в следующих шагах.\n\n"
        "Здесь будет:\n"
        "• Форма ввода данных другого человека\n"
        "• Валидация данных рождения\n"
        "• Создание нового профиля\n"
        "• Возможность покупки разбора\n\n"
        "Пока что используйте кнопку 'Назад' для возврата в меню.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔙 Назад",
                        callback_data="buy_analysis"
                    )
                ]
            ]
        ),
        parse_mode="Markdown"
    )
