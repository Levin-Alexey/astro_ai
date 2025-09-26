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

    async def handle_payment_request(self, callback: CallbackQuery) -> None:
        """Обрабатывает запрос на оплату за все планеты"""
        await callback.answer()
        cb_msg = callback.message
        user_id = callback.from_user.id

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
                description="Астрологические разборы всех планет"
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
                    await self._save_payment_to_db(user_id, payment_id)

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

    async def handle_payment_success(self, user_id: int) -> None:
        """Обрабатывает успешную оплату и запускает разбор планет"""
        try:
            logger.info(
                f"🌌 Начинаем последовательный разбор планет для "
                f"пользователя {user_id}"
            )

            # Обновляем статус платежа в БД
            await self._update_payment_status(user_id)

            # Запускаем разбор первой планеты (Солнце)
            await self._start_planet_analysis(user_id, "sun")

        except Exception as e:
            logger.error(f"❌ Ошибка при обработке успешной оплаты: {e}")

    async def handle_next_planet(self, callback: CallbackQuery) -> None:
        """Обрабатывает нажатие кнопки 'Следующая планета'"""
        await callback.answer()
        cb_msg = callback.message
        user_id = callback.from_user.id

        try:
            logger.info(f"🔍 Next planet button pressed by user {user_id}")
            
            # Определяем следующую планету
            next_planet = await self._get_next_planet(user_id)
            logger.info(f"🔍 Next planet determined: {next_planet}")

            if next_planet:
                # Запускаем разбор следующей планеты
                logger.info(f"🔍 Starting analysis for planet: {next_planet}")
                await self._start_planet_analysis(user_id, next_planet)
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
                                [
                                    InlineKeyboardButton(
                                        text="💡 Получить рекомендации",
                                        callback_data="get_recommendations"
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

    async def _save_payment_to_db(self, user_id: int, payment_id: str) -> None:
        """Сохраняет информацию о платеже в БД"""
        async with get_session() as session:
            payment = PlanetPayment(
                user_id=user_id,
                planet=None,  # Для всех планет
                payment_type=PaymentType.all_planets,
                external_payment_id=payment_id,
                amount_kopecks=500,  # 5₽ в копейках для тестирования
                status=PaymentStatus.pending,
                created_at=datetime.now(timezone.utc)
            )
            session.add(payment)
            await session.commit()
            logger.info(f"💾 Платеж сохранен в БД: {payment_id}")

    async def _update_payment_status(self, user_id: int) -> None:
        """Обновляет статус платежа на 'completed'"""
        async with get_session() as session:
            result = await session.execute(
                select(PlanetPayment).where(
                    PlanetPayment.user_id == user_id,
                    PlanetPayment.payment_type == PaymentType.all_planets,
                    PlanetPayment.status == PaymentStatus.pending
                )
            )
            payment = result.scalar_one_or_none()

            if payment:
                payment.status = PaymentStatus.completed
                payment.completed_at = datetime.now(timezone.utc)
                await session.commit()
                logger.info(
                    f"✅ Статус платежа обновлен для пользователя {user_id}"
                )

    async def _start_planet_analysis(self, user_id: int, planet: str) -> None:
        """Запускает анализ конкретной планеты"""
        try:
            logger.info(
                f"🚀 Запуск анализа {planet} для пользователя {user_id}"
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
                astrology_data = await start_sun_analysis(user_id)
            elif planet == "mercury":
                astrology_data = await start_mercury_analysis(user_id)
            elif planet == "venus":
                astrology_data = await start_venus_analysis(user_id)
            elif planet == "mars":
                astrology_data = await start_mars_analysis(user_id)
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

    async def _get_next_planet(self, telegram_id: int) -> Optional[str]:
        """Определяет следующую планету для анализа"""
        try:
            logger.info(f"🔍 Getting next planet for user {telegram_id}")
            
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
                
                # Получаем все завершенные разборы пользователя
                # Проверяем наличие анализа в соответствующих столбцах
                result = await session.execute(
                    select(Prediction).where(
                        Prediction.user_id == user.user_id,
                        (Prediction.sun_analysis.isnot(None)) |
                        (Prediction.mercury_analysis.isnot(None)) |
                        (Prediction.venus_analysis.isnot(None)) |
                        (Prediction.mars_analysis.isnot(None))
                    )
                )
                completed_predictions = result.scalars().all()

                # Определяем, какие планеты уже обработаны
                completed_planets = set()
                for prediction in completed_predictions:
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

    def create_planet_buttons(self, planet: str) -> InlineKeyboardMarkup:
        """Создает кнопки для разбора планеты"""
        buttons = [
            [
                InlineKeyboardButton(
                    text="💡 Получить рекомендации",
                    callback_data=f"get_{planet}_recommendations"
                )
            ]
        ]

        # Добавляем кнопку "Следующая планета" для всех планет кроме Марса
        if planet != "mars":
            buttons.append([
                InlineKeyboardButton(
                    text="➡️ Следующая планета",
                    callback_data="next_planet"
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
