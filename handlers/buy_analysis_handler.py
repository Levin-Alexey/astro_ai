"""
Обработчик кнопки "Купить разбор" в главном меню.
"""

import logging

from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)


async def show_buy_analysis_menu(message: Message):
    """
    Показывает меню покупки разборов с четырьмя опциями:
    1. Купить разбор для себя
    2. Купить разбор для дополнительных дат
    3. Добавить новую дату  
    4. Главное меню
    """
    
    # Создаем клавиатуру с четырьмя кнопками
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
                    text="👥 Купить разбор для дополнительных дат",
                    callback_data="buy_analysis_additional"
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


async def show_additional_profiles_for_purchase(callback: CallbackQuery):
    """
    Показывает список дополнительных профилей для покупки разборов.
    Переиспользует логику из личного кабинета.
    """
    await callback.answer()
    cb_msg = callback.message
    
    try:
        user_id = callback.from_user.id if callback.from_user else 0
        logger.info(f"User {user_id} selecting additional profile for purchase")
        
        # Получаем список дополнительных профилей пользователя
        from db import get_session
        from models import User, AdditionalProfile
        from sqlalchemy import select
        
        async with get_session() as session:
            # Находим пользователя
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                await cb_msg.answer(
                    "❌ Пользователь не найден в базе данных.\n"
                    "Попробуйте перезапустить бота командой /start"
                )
                return
            
            # Получаем все дополнительные профили пользователя
            profiles_result = await session.execute(
                select(AdditionalProfile)
                .where(
                    AdditionalProfile.owner_user_id == user.user_id,
                    AdditionalProfile.is_active.is_(True)
                )
                .order_by(AdditionalProfile.created_at.desc())
            )
            profiles = profiles_result.scalars().all()
            
            if not profiles:
                # Нет дополнительных профилей
                await cb_msg.answer(
                    "👥 **Покупка разборов для дополнительных дат**\n\n"
                    "У вас пока нет дополнительных профилей.\n\n"
                    "Вы можете создать профиль для:\n"
                    "• Члена семьи (мама, папа, брат, сестра)\n"
                    "• Партнера или друга\n"
                    "• Ребенка\n\n"
                    "Для создания профиля нажмите кнопку ниже 👇",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="➕ Создать профиль",
                                    callback_data="add_new_date"
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    text="← Назад к выбору покупки",
                                    callback_data="buy_analysis"
                                )
                            ]
                        ]
                    )
                )
                return
            
            # Формируем список профилей с кнопками
            text = "👥 **Покупка разборов для дополнительных дат**\n\n"
            text += f"У вас {len(profiles)} "
            if len(profiles) == 1:
                text += "дополнительный профиль"
            elif len(profiles) < 5:
                text += "дополнительных профиля"
            else:
                text += "дополнительных профилей"
            text += ".\n\nВыберите профиль, чтобы купить разборы:"
            
            # Создаем кнопки для каждого профиля
            buttons = []
            for profile in profiles:
                gender_emoji = {
                    "male": "👨",
                    "female": "👩", 
                    "other": "🧑"
                }.get(profile.gender.value if profile.gender else "unknown", "👤")
                
                profile_button = InlineKeyboardButton(
                    text=f"{gender_emoji} {profile.full_name}",
                    callback_data=f"buy_for_profile:{profile.profile_id}"
                )
                buttons.append([profile_button])
            
            # Добавляем кнопки управления
            buttons.extend([
                [
                    InlineKeyboardButton(
                        text="➕ Создать новый профиль",
                        callback_data="add_new_date"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="← Назад к выбору покупки",
                        callback_data="buy_analysis"
                    )
                ]
            ])
            
            await cb_msg.answer(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"Error in show_additional_profiles_for_purchase: {e}")
        await cb_msg.answer(
            "❌ Произошла ошибка при загрузке профилей.\n"
            "Попробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="← Назад к выбору покупки",
                            callback_data="buy_analysis"
                        )
                    ]
                ]
            )
        )


async def handle_buy_for_profile(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик покупки разборов для дополнительного профиля.
    Показывает список планет для покупки на основе данных профиля.
    """
    try:
        # Извлекаем profile_id из callback_data
        profile_id = int(callback.data.split(":")[1])
        user_id = callback.from_user.id if callback.from_user else 0
        
        logger.info(f"User {user_id} buying analysis for profile {profile_id}")
        
        from db import get_session
        from models import User, AdditionalProfile, Prediction, Planet
        from sqlalchemy import select
        
        async with get_session() as session:
            # Проверяем права пользователя на этот профиль
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                await callback.message.answer(
                    "❌ Пользователь не найден в базе данных."
                )
                return
            
            # Получаем профиль
            profile_result = await session.execute(
                select(AdditionalProfile)
                .where(
                    AdditionalProfile.profile_id == profile_id,
                    AdditionalProfile.owner_user_id == user.user_id,
                    AdditionalProfile.is_active.is_(True)
                )
            )
            profile = profile_result.scalar_one_or_none()
            
            if not profile:
                await callback.message.answer(
                    "❌ Профиль не найден или у вас нет доступа к нему.",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="← Назад к профилям",
                                    callback_data="buy_analysis_additional"
                                )
                            ]
                        ]
                    )
                )
                return
            
            # Получаем информацию о разборах для этого профиля
            predictions_result = await session.execute(
                select(Prediction)
                .where(
                    Prediction.profile_id == profile_id,
                    Prediction.is_active.is_(True)
                )
            )
            existing_predictions = predictions_result.scalars().all()
            
            # Определяем какие планеты уже есть
            existing_planets = {pred.planet for pred in existing_predictions}
            
            # Информация о планетах и ценах
            planets_info = {
                Planet.sun: {
                    "emoji": "☀️",
                    "name": "Солнце", 
                    "price": 500,
                    "description": "Ядро личности и жизненный путь"
                },
                Planet.moon: {
                    "emoji": "🌙",
                    "name": "Луна",
                    "price": 500, 
                    "description": "Эмоции и внутренний мир"
                },
                Planet.mercury: {
                    "emoji": "☿️",
                    "name": "Меркурий",
                    "price": 500,
                    "description": "Общение и мышление"
                },
                Planet.venus: {
                    "emoji": "♀️", 
                    "name": "Венера",
                    "price": 500,
                    "description": "Любовь и отношения"
                },
                Planet.mars: {
                    "emoji": "♂️",
                    "name": "Марс", 
                    "price": 500,
                    "description": "Энергия и действия"
                }
            }
            
            # Создаем кнопки для доступных планет
            available_buttons = []
            total_available = 0
            
            for planet, info in planets_info.items():
                if planet not in existing_planets:
                    # Новые тексты кнопок с ценой и эмодзи
                    if planet == Planet.sun:
                        btn_text = "☀️ Солнце 77₽"
                    elif planet == Planet.mercury:
                        btn_text = "🧠 Меркурий 77₽"
                    elif planet == Planet.venus:
                        btn_text = "💰💍 Венера 77₽"
                    elif planet == Planet.mars:
                        btn_text = "🔥 Марс 77₽"
                    elif planet == Planet.moon:
                        btn_text = "🌙 Луна 77₽"
                    else:
                        btn_text = f"{info['emoji']} {info['name']} 77₽"
                    available_buttons.append([
                        InlineKeyboardButton(
                            text=btn_text,
                            callback_data=f"buy_planet:{profile_id}:{planet.value}"
                        )
                    ])
                    total_available += 1
            
            if total_available == 0:
                # Все планеты уже куплены
                await callback.message.answer(
                    f"🎉 **{profile.full_name}**\n\n"
                    f"Все планеты уже куплены для этого профиля!\n\n"
                    f"Вы можете посмотреть разборы в разделе "
                    f"'Личный кабинет → Дополнительные разборы'.",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="← Назад к профилям",
                                    callback_data="buy_analysis_additional"
                                )
                            ]
                        ]
                    ),
                    parse_mode="Markdown"
                )
                return
            
            # Добавляем кнопку "Купить все планеты со скидкой" если доступно больше 1
            if total_available > 1:
                # Новая кнопка "Все планеты"
                available_buttons.append([
                    InlineKeyboardButton(
                        text="😎 Все планеты 222₽",
                        callback_data=f"buy_all_planets:{profile_id}"
                    )
                ])
            
            # Добавляем навигационные кнопки
            available_buttons.extend([
                [
                    InlineKeyboardButton(
                        text="← Назад к профилям",
                        callback_data="buy_analysis_additional"
                    )
                ]
            ])
            
            gender_emoji = {
                "male": "👨",
                "female": "👩",
                "other": "🧑"
            }.get(profile.gender.value if profile.gender else "unknown", "👤")
            
            # Формируем список всех планет с батарейками
            text_parts = [
                f"💳 **Покупка разборов для {profile.full_name}**\n",
                f"{gender_emoji} Состояние планет:\n"
            ]
            
            for planet, info in planets_info.items():
                if planet in existing_planets:
                    battery = "🔋"  # Зеленая батарейка - есть разбор
                else:
                    battery = "🪫"  # Красная батарейка - нет разбора
                
                planet_text = (
                    f"{battery} {info['emoji']} **{info['name']}** - "
                    f"{info['description']}"
                )
                text_parts.append(planet_text)
            
            if total_available > 0:
                text_parts.extend([
                    f"\n📋 **Доступно для покупки:** {total_available} разборов",
                    "💰 **Цена за планету:** 500₽"
                ])
            
            text_parts.append(
                "\n🔋 - разбор есть  🪫 - разбор доступен для покупки"
            )
            text_parts.append("\nВыберите планету для покупки:")
            
            await callback.message.answer(
                "\n".join(text_parts),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=available_buttons),
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logger.error(f"Error in handle_buy_for_profile: {e}")
        await callback.message.answer(
            "❌ Произошла ошибка при загрузке данных профиля.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="← Назад к профилям", 
                            callback_data="buy_analysis_additional"
                        )
                    ]
                ]
            )
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
            
            # Создаем кнопки для доступных планет
            keyboard_buttons = []
            available_count = 0
            
            for planet_info in planets_info:
                if planet_info["planet"] not in owned_planets:
                    # Новые тексты кнопок с ценой и эмодзи
                    if planet_info["planet"].name.lower() == "sun":
                        btn_text = "☀️ Солнце 77₽"
                    elif planet_info["planet"].name.lower() == "mercury":
                        btn_text = "🧠 Меркурий 77₽"
                    elif planet_info["planet"].name.lower() == "venus":
                        btn_text = "💰💍 Венера 77₽"
                    elif planet_info["planet"].name.lower() == "mars":
                        btn_text = "🔥 Марс 77₽"
                    elif planet_info["planet"].name.lower() == "moon":
                        btn_text = "🌙 Луна 77₽"
                    else:
                        btn_text = f"{planet_info['emoji']} {planet_info['name']} 77₽"
                    keyboard_buttons.append([
                        InlineKeyboardButton(
                            text=btn_text,
                            callback_data=planet_info['callback']
                        )
                    ])
                    available_count += 1
            
            # Добавляем кнопку "Все планеты" если доступны все
            if available_count > 1:
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text="😎 Все планеты 222₽",
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
                    battery = "🔋"  # Зеленая батарейка - есть разбор
                else:
                    battery = "🪫"  # Красная батарейка - нет разбора
                
                planet_text = (
                    f"{battery} {planet_info['emoji']} "
                    f"**{planet_info['name']}** - {planet_info['description']}"
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
            
            text_parts.append(
                "\n🔋 - разбор есть  🪫 - разбор доступен для покупки"
            )
            
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
