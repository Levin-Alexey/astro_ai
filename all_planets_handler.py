"""
Обработчик для функционала "Все планеты" - последовательный запуск разборов.

Реализует логику:
1. Создание платежа для всех планет
2. Последовательный запуск воркеров: Солнце -> Меркурий -> Венера -> Марс
3. Динамические кнопки с "Следующая планета" для первых трех планет
"""

import logging
from typing import Optional
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import (
    CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from sqlalchemy import select

from db import get_session
from models import (
    Prediction, PlanetPayment, PaymentStatus, PaymentType
)
from payment_handler import PaymentHandler
from queue_sender import get_queue_sender
from astrology_handlers import (
    start_sun_analysis, start_mercury_analysis,
    start_venus_analysis, start_mars_analysis
)

logger = logging.getLogger(__name__)

# Порядок планет для последовательного разбора
PLANET_ORDER = ["sun", "mercury", "venus", "mars"]
PLANET_EMOJIS = {
    "sun": "☀️",
    "mercury": "☿️",
    "venus": "♀️",
    "mars": "♂️"
}
PLANET_NAMES = {
    "sun": "Солнце",
    "mercury": "Меркурий",
    "venus": "Венера",
    "mars": "Марс"
}


class AllPlanetsHandler:
    """Обработчик для функционала 'Все планеты'"""

    def __init__(self, bot: Bot, payment_handler: PaymentHandler):
        self.bot = bot
        self.payment_handler = payment_handler
        self.queue_sender = None

    async def initialize(self):
        """Инициализация обработчика"""
        self.queue_sender = await get_queue_sender()
        logger.info("AllPlanetsHandler initialized")

    async def handle_payment_request(self, callback: CallbackQuery, profile_id: Optional[int] = None) -> None:
        """Обрабатывает запрос на оплату за все планеты"""
        await callback.answer()
        cb_msg = callback.message
        user_id = callback.from_user.id
        
        logger.info(f"🌌 Payment request for all planets: user_id={user_id}, profile_id={profile_id}")

        if self.payment_handler is None:
            await cb_msg.answer(
                "❌ Ошибка: обработчик платежей не инициализирован",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🔙 Назад",
                                callback_data="explore_all_planets"
                            )
                        ]
                    ]
                )
            )
            return

        try:
            logger.info(
                f"🌌 Создание платежа за все планеты для пользователя {user_id}"
            )

            # Создаем данные для платежа
            payment_data = self.payment_handler.create_payment_data(
                user_id=user_id,
                planet="all_planets",
                description="Астрологические разборы всех планет",
                profile_id=profile_id
            )

            # Создаем платеж
            payment_result = await self.payment_handler.create_payment(
                payment_data
            )
            
            logger.info(f"🔍 Payment result type: {type(payment_result)}")
            logger.info(f"🔍 Payment result: {payment_result}")

            # Проверяем, что результат - это словарь
            if isinstance(payment_result, dict) and payment_result.get("success"):
                payment_url = payment_result.get("payment_url")
                payment_id = payment_result.get("payment_id")

                # Сохраняем информацию о платеже в БД
                if payment_id:
                    await self._save_payment_to_db(user_id, payment_id, profile_id)

                # Отправляем ссылку на оплату
                if cb_msg:
                    await cb_msg.answer(
                        "💳 Оплата за все планеты\n\n"
                        "💰 Стоимость: 5₽ (тестовая цена)\n\n"
                        "🎁 Бонус: неограниченное количество вопросов\n\n"
                        "📋 После оплаты вы получите разборы:\n"
                        "☀️ Солнце - энергия, уверенность, самооценка\n"
                        "☿️ Меркурий - речь, мышление, обучение\n"
                        "♀️ Венера - отношения, финансы, изобилие\n"
                        "♂️ Марс - мотивация, сила воли, решительность\n\n"
                        "🔗 Нажмите кнопку ниже для оплаты:",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="💳 Оплатить 5₽",
                                        url=payment_url
                                    )
                                ],
                                [
                                    InlineKeyboardButton(
                                        text="🔙 Назад",
                                        callback_data="explore_all_planets"
                                    )
                                ]
                            ]
                        )
                    )

                logger.info(
                    f"✅ Платеж создан для пользователя {user_id}: {payment_id}"
                )
            else:
                error_msg = "Неизвестная ошибка"
                if isinstance(payment_result, dict):
                    error_msg = payment_result.get("error", "Неизвестная ошибка")
                else:
                    error_msg = f"Неожиданный тип результата: {type(payment_result)}"
                
                logger.error(f"❌ Ошибка создания платежа: {error_msg}")
                
                if cb_msg:
                    await cb_msg.answer(
                        f"❌ Ошибка создания платежа: {error_msg}",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="🔙 Назад",
                                        callback_data="explore_all_planets"
                                    )
                                ]
                            ]
                        )
                    )

        except Exception as e:
            logger.error(
                f"❌ Ошибка при создании платежа за все планеты: {e}"
            )
            if cb_msg:
                await cb_msg.answer(
                    "❌ Произошла ошибка при создании платежа. "
                    "Попробуйте позже.",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="🔙 Назад",
                                    callback_data="explore_all_planets"
                                )
                            ]
                        ]
                    )
                )

    async def handle_payment_success(self, user_id: int, profile_id: Optional[int] = None) -> None:
        """Обрабатывает успешную оплату и запускает разбор планет"""
        try:
            logger.info(
                f"🌌 Начинаем последовательный разбор планет для "
                f"пользователя {user_id}, profile_id: {profile_id}"
            )

            # Обновляем статус платежа в БД
            await self._update_payment_status(user_id, profile_id)

            # Запускаем разбор первой планеты (Солнце)
            await self._start_planet_analysis(user_id, "sun", profile_id)

        except Exception as e:
            logger.error(f"❌ Ошибка при обработке успешной оплаты: {e}")

    async def handle_next_planet(self, callback: CallbackQuery, profile_id: Optional[int] = None) -> None:
        """Обрабатывает нажатие кнопки 'Следующая планета'"""
        await callback.answer()
        cb_msg = callback.message
        user_id = callback.from_user.id

        try:
            logger.info(f"🔍 Next planet button pressed by user {user_id}, profile_id={profile_id}")
            
            # Определяем следующую планету
            next_planet = await self._get_next_planet(user_id, profile_id)
            logger.info(f"🔍 Next planet determined: {next_planet}")

            if next_planet:
                # Запускаем разбор следующей планеты
                logger.info(f"🔍 Starting analysis for planet: {next_planet}, profile_id={profile_id}")
                await self._start_planet_analysis(user_id, next_planet, profile_id)
            else:
                # Все планеты обработаны
                if cb_msg:
                    await cb_msg.answer(
                        "🎉 Поздравляем!\n\n"
                        "✨ Вы получили персональные астрологические разборы "
                        "по всем планетам!\n\n"
                        "🔮 Теперь у вас есть полная картина вашей "
                        "астрологической карты.\n\n"
                        "💡 Используйте кнопки ниже для получения рекомендаций "
                        "или возврата в главное меню.",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[
                                # Временно закомментирована кнопка "Получить рекомендации"
                                # [
                                #     InlineKeyboardButton(
                                #         text="💡 Получить рекомендации",
                                #         callback_data="get_recommendations"
                                #     )
                                # ],
                                [
                                    InlineKeyboardButton(
                                        text="🏠 Главное меню",
                                        callback_data="back_to_menu"
                                    )
                                ]
                            ]
                        )
                    )

        except Exception as e:
            logger.error(f"❌ Ошибка при переходе к следующей планете: {e}")
            if cb_msg:
                await cb_msg.answer(
                    "❌ Произошла ошибка. Попробуйте позже.",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="🏠 Главное меню",
                                    callback_data="back_to_menu"
                                )
                            ]
                        ]
                    )
                )

    async def _save_payment_to_db(self, user_id: int, payment_id: str, profile_id: Optional[int] = None) -> None:
        """Сохраняет информацию о платеже в БД"""
        async with get_session() as session:
            payment = PlanetPayment(
                user_id=user_id,
                planet=None,  # Для всех планет
                payment_type=PaymentType.all_planets,
                external_payment_id=payment_id,
                amount_kopecks=500,  # 5₽ в копейках для тестирования
                status=PaymentStatus.pending,
                profile_id=profile_id,  # Сохраняем profile_id
                created_at=datetime.now(timezone.utc)
            )
            session.add(payment)
            await session.commit()
            logger.info(f"💾 Платеж сохранен в БД: {payment_id}, profile_id={profile_id}")

    async def _update_payment_status(self, user_id: int, profile_id: Optional[int] = None) -> None:
        """Обновляет статус платежа на 'completed'"""
        async with get_session() as session:
            query_conditions = [
                PlanetPayment.user_id == user_id,
                PlanetPayment.payment_type == PaymentType.all_planets,
                PlanetPayment.status == PaymentStatus.pending
            ]
            
            # Добавляем условие для profile_id если указан
            if profile_id:
                query_conditions.append(PlanetPayment.profile_id == profile_id)
            else:
                query_conditions.append(PlanetPayment.profile_id.is_(None))
            
            result = await session.execute(
                select(PlanetPayment).where(*query_conditions)
            )
            payment = result.scalar_one_or_none()

            if payment:
                payment.status = PaymentStatus.completed
                payment.completed_at = datetime.now(timezone.utc)
                await session.commit()
                logger.info(
                    f"✅ Статус платежа обновлен для пользователя {user_id}, profile_id: {profile_id}"
                )

    async def _start_planet_analysis(self, user_id: int, planet: str, profile_id: Optional[int] = None) -> None:
        """Запускает анализ конкретной планеты"""
        try:
            logger.info(
                f"🚀 Запуск анализа {planet} для пользователя {user_id}, profile_id: {profile_id}"
            )

            # Отправляем уведомление о начале анализа
            await self.bot.send_message(
                user_id,
                f"{PLANET_EMOJIS[planet]} {PLANET_NAMES[planet]}\n\n"
                f"🔮 Генерирую ваш персональный астрологический разбор...\n\n"
                f"⏳ Пожалуйста, подождите несколько секунд."
            )

            # Запускаем соответствующий анализ
            if planet == "sun":
                astrology_data = await start_sun_analysis(user_id, profile_id)
            elif planet == "mercury":
                astrology_data = await start_mercury_analysis(user_id, profile_id)
            elif planet == "venus":
                astrology_data = await start_venus_analysis(user_id, profile_id)
            elif planet == "mars":
                astrology_data = await start_mars_analysis(user_id, profile_id)
            else:
                logger.error(f"❌ Неизвестная планета: {planet}")
                return

            if astrology_data:
                logger.info(
                    f"✅ Анализ {planet} запущен для пользователя {user_id}"
                )
            else:
                logger.error(
                    f"❌ Не удалось запустить анализ {planet} для "
                    f"пользователя {user_id}"
                )

        except Exception as e:
            logger.error(f"❌ Ошибка при запуске анализа {planet}: {e}")

    async def _get_next_planet(self, telegram_id: int, profile_id: Optional[int] = None) -> Optional[str]:
        """Определяет следующую планету для анализа"""
        try:
            logger.info(f"🔍 Getting next planet for user {telegram_id}, profile_id={profile_id}")
            
            async with get_session() as session:
                # Сначала получаем внутренний user_id по telegram_id
                from models import User
                user_result = await session.execute(
                    select(User).where(User.telegram_id == telegram_id)
                )
                user = user_result.scalar_one_or_none()
                if not user:
                    logger.warning(f"🔍 User not found for telegram_id {telegram_id}")
                    return None
                
                logger.info(f"🔍 Found user with internal id: {user.user_id}")
                
                # Получаем время оплаты за все планеты для конкретного профиля
                payment_conditions = [
                    PlanetPayment.user_id == telegram_id,
                    PlanetPayment.payment_type == PaymentType.all_planets,
                    PlanetPayment.status == PaymentStatus.completed
                ]
                
                # Добавляем условие по profile_id
                if profile_id:
                    payment_conditions.append(PlanetPayment.profile_id == profile_id)
                else:
                    payment_conditions.append(PlanetPayment.profile_id.is_(None))
                
                payment_result = await session.execute(
                    select(PlanetPayment).where(*payment_conditions).order_by(PlanetPayment.completed_at.desc())
                )
                all_planets_payment = payment_result.scalar_one_or_none()
                
                if not all_planets_payment:
                    logger.warning(f"🔍 No all planets payment found for user {telegram_id}, profile_id={profile_id}")
                    return None
                
                payment_time = all_planets_payment.completed_at
                logger.info(f"🔍 All planets payment completed at: {payment_time}")
                
                # Получаем все разборы для конкретного профиля, созданные после оплаты
                prediction_conditions = [
                    Prediction.user_id == user.user_id,
                    Prediction.created_at >= payment_time,
                    (
                        (Prediction.sun_analysis.isnot(None)) |
                        (Prediction.mercury_analysis.isnot(None)) |
                        (Prediction.venus_analysis.isnot(None)) |
                        (Prediction.mars_analysis.isnot(None))
                    )
                ]
                
                # Фильтруем по profile_id
                if profile_id:
                    prediction_conditions.append(Prediction.profile_id == profile_id)
                else:
                    prediction_conditions.append(Prediction.profile_id.is_(None))
                
                result = await session.execute(
                    select(Prediction).where(*prediction_conditions)
                )
                completed_predictions = result.scalars().all()
                logger.info(f"🔍 Found {len(completed_predictions)} predictions after payment for profile_id={profile_id}")

                # Определяем, какие планеты уже обработаны
                completed_planets = set()
                for prediction in completed_predictions:
                    logger.info(f"🔍 Prediction {prediction.prediction_id}: sun={bool(prediction.sun_analysis)}, mercury={bool(prediction.mercury_analysis)}, venus={bool(prediction.venus_analysis)}, mars={bool(prediction.mars_analysis)}")
                    if prediction.sun_analysis:
                        completed_planets.add("sun")
                    if prediction.mercury_analysis:
                        completed_planets.add("mercury")
                    if prediction.venus_analysis:
                        completed_planets.add("venus")
                    if prediction.mars_analysis:
                        completed_planets.add("mars")

                logger.info(f"🔍 Completed planets: {completed_planets}")
                logger.info(f"🔍 Planet order: {PLANET_ORDER}")

                # Находим следующую планету
                for planet in PLANET_ORDER:
                    if planet not in completed_planets:
                        logger.info(f"🔍 Next planet found: {planet}")
                        return planet

                logger.info(f"🔍 All planets completed")
                return None  # Все планеты обработаны

        except Exception as e:
            logger.error(f"❌ Ошибка при определении следующей планеты: {e}")
            return None

    def create_planet_buttons(self, planet: str, profile_id: Optional[int] = None) -> InlineKeyboardMarkup:
        """Создает кнопки для разбора планеты"""
        buttons = []
        
        # Временно закомментирована кнопка "Получить рекомендации"
        # [
        #     InlineKeyboardButton(
        #         text="💡 Получить рекомендации",
        #         callback_data=f"get_{planet}_recommendations"
        #     )
        # ]

        # Добавляем кнопку "Следующая планета" для всех планет кроме Марса
        if planet != "mars":
            next_planet_callback = f"next_planet:{profile_id}" if profile_id else "next_planet"
            buttons.append([
                InlineKeyboardButton(
                    text="➡️ Следующая планета",
                    callback_data=next_planet_callback
                )
            ])

        buttons.append([
            InlineKeyboardButton(
                text="🏠 Главное меню",
                callback_data="back_to_menu"
            )
        ])

        return InlineKeyboardMarkup(inline_keyboard=buttons)


# Глобальный экземпляр обработчика
_all_planets_handler = None


def init_all_planets_handler(
    bot: Bot, payment_handler: PaymentHandler
) -> AllPlanetsHandler:
    """Инициализирует обработчик всех планет"""
    global _all_planets_handler
    _all_planets_handler = AllPlanetsHandler(bot, payment_handler)
    return _all_planets_handler


def get_all_planets_handler() -> Optional[AllPlanetsHandler]:
    """Возвращает экземпляр обработчика всех планет"""
    return _all_planets_handler


async def check_if_all_planets_payment(telegram_id: int, profile_id: Optional[int] = None) -> bool:
    """
    Универсальная функция для проверки наличия оплаты за все планеты
    
    Args:
        telegram_id: Telegram ID пользователя
        profile_id: ID дополнительного профиля (опционально)
        
    Returns:
        True если есть оплата за все планеты для указанного профиля
    """
    try:
        async with get_session() as session:
            conditions = [
                PlanetPayment.user_id == telegram_id,
                PlanetPayment.payment_type == PaymentType.all_planets,
                PlanetPayment.status == PaymentStatus.completed
            ]
            
            # Фильтруем по profile_id
            if profile_id:
                conditions.append(PlanetPayment.profile_id == profile_id)
            else:
                conditions.append(PlanetPayment.profile_id.is_(None))
            
            result = await session.execute(
                select(PlanetPayment).where(*conditions)
            )
            payment = result.scalar_one_or_none()
            
            logger.info(
                f"Check all planets payment: telegram_id={telegram_id}, "
                f"profile_id={profile_id}, found={payment is not None}"
            )
            
            return payment is not None
            
    except Exception as e:
        logger.error(f"Error checking all planets payment: {e}")
        return False


def create_planet_analysis_buttons(planet: str, is_all_planets: bool = False, profile_id: Optional[int] = None) -> dict:
    """
    Универсальная функция для создания кнопок после разбора планеты
    
    Args:
        planet: Название планеты ("sun", "mercury", "venus", "mars")
        is_all_planets: Если True, показывает кнопку "Следующая планета"
        profile_id: ID дополнительного профиля (опционально)
        
    Returns:
        Словарь с клавиатурой для Telegram API
    """
    buttons = [
        # Временно закомментирована кнопка "Получить рекомендации"
        # [
        #     {
        #         "text": "💡 Получить рекомендации",
        #         "callback_data": f"get_{planet}_recommendations"
        #     }
        # ]
    ]
    
    if is_all_planets:
        next_planet_callback = f"next_planet:{profile_id}" if profile_id else "next_planet"
        buttons.append([
            {
                "text": "➡️ Следующая планета",
                "callback_data": next_planet_callback
            }
        ])
    else:
        buttons.append([
            {
                "text": "🔍 Исследовать другие сферы",
                "callback_data": "explore_other_areas"
            }
        ])
    
    buttons.append([
        {
            "text": "🏠 Главное меню",
            "callback_data": "back_to_menu"
        }
    ])
    
    return {
        "inline_keyboard": buttons
    }
