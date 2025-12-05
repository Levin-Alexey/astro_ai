from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import logging
from datetime import datetime, date # Добавляем date

from db import get_session
from subscriptions_db import get_active_subscription, record_subscription_payment, get_user_id_by_telegram_id
from queue_sender import send_personal_forecast_to_queue # Импортируем функцию отправки
from models import PaymentStatus
from forecast_api import get_forecast_data

logger = logging.getLogger(__name__)

async def handle_buy_subscription(callback: CallbackQuery, payment_handler):
    """
    Обрабатывает нажатие кнопки 'Купить подписку'.
    """
    telegram_id = callback.from_user.id
    amount_kopecks = 9900 # 99 рублей
    description = "Подписка на персональные прогнозы (1 месяц)"
    
    # Формируем данные для ЮКассы
    # Используем planet="personal_forecasts_sub" как маркер для webhook
    payment_data = payment_handler.create_payment_data(
        user_id=telegram_id,
        planet="personal_forecasts_sub",
        description=description,
        amount_kopecks=amount_kopecks
    )
    
    # Создаем платеж в ЮКассе
    payment_result = await payment_handler.create_payment(payment_data)
    
    if payment_result["success"]:
        payment_url = payment_result["payment_url"]
        payment_id = payment_result["payment_id"]
        
        # Записываем платеж в БД (subscriptions_payments)
        async with get_session() as session:
            # Нам нужен user_id (PK), а не telegram_id
            user_id = await get_user_id_by_telegram_id(session, telegram_id)
            
            if user_id:
                await record_subscription_payment(
                    session=session,
                    user_id=user_id,
                    amount_kopecks=amount_kopecks,
                    external_payment_id=payment_id,
                    payment_url=payment_url,
                    status=PaymentStatus.pending
                )
            else:
                logger.error(f"User not found for telegram_id {telegram_id}")
                await callback.message.answer("Ошибка: пользователь не найден.")
                return
        
        # Отправляем кнопку оплаты
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить 99 ₽", url=payment_url)]
            ]
        )
        await callback.message.answer(
            "🔥 Персональные прогнозы на каждый день — 99₽ в месяц\n\n"
            "💵 Нажми кнопку ниже для оплаты через официальный сервис «Юкаssа»\n"
            "🔮 После оплаты тебе сразу придет прогноз на сегодня\n\n"
            "👇🏼👇🏼👇🏼",
            reply_markup=kb
        )
    else:
        logger.error(f"Payment creation failed: {payment_result.get('error')}")
        await callback.message.answer("Ошибка при создании платежа. Попробуйте позже.")


async def handle_personal_forecasts(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик нажатия на кнопку '🔥 Персональные прогнозы'
    """
    telegram_id = callback.from_user.id
    logger.info(f"handle_personal_forecasts вызвана для telegram_id={telegram_id}")

    # Ответ на callback, чтобы убрать часики
    await callback.answer()

    async with get_session() as session:
        # Сначала получаем user_id (PK) из БД
        user_db_id = await get_user_id_by_telegram_id(session, telegram_id)
        
        if not user_db_id:
            await callback.message.answer("❌ Ошибка: пользователь не найден в базе данных. Попробуйте перезапустить бота через /start")
            return

        # Проверяем подписку по user_db_id (PK)
        active_subscription = await get_active_subscription(session, user_db_id)

        if active_subscription:
            await callback.message.answer("⏳ Генерирую ваш прогноз на сегодня...")
            
            # Получаем данные от AstrologyAPI
            api_result = await get_forecast_data(user_db_id)
            
            if api_result.get("success"):
                # Формируем полные данные для воркера
                full_data = api_result["data"]
                # Добавляем данные профиля, если они есть (добавлены в get_forecast_data)
                full_data["user_profile"] = api_result.get("profile_data")
                
                # Подписка активна, отправляем запрос на генерацию прогноза в RabbitMQ
                success = await send_personal_forecast_to_queue(
                    user_id=telegram_id, # telegram_id для отправки сообщения в чат
                    astrology_data=full_data
                )

                if success:
                    # Уведомление, что процесс пошел
                    pass
                else:
                    await callback.message.answer(
                        "Произошла ошибка при отправке запроса на прогноз. Пожалуйста, попробуйте позже."
                    )
            else:
                error_msg = api_result.get("error", "Unknown error")
                logger.error(f"Forecast API error for user {telegram_id}: {error_msg}")
                await callback.message.answer(f"❌ Не удалось получить астрологические данные: {error_msg}")
        else:
            # Подписка неактивна, предлагаем купить
            buy_forecast_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💰 Купить подписку на прогнозы",
                            callback_data="buy_personal_forecasts_sub" # Новый callback для покупки
                        )
                    ]
                ]
            )
            await callback.message.answer(
                "🔥 <b>ПЕРСОНАЛЬНЫЕ ПРОГНОЗЫ НА КАЖДЫЙ ДЕНЬ</b>\n\n"
                "Ежедневно ты будешь получать:\n\n"
                "🪐 Точный разбор транзитов на сегодня: что включено в небесах и как это может отыграться именно у тебя\n\n"
                "⭐️ Персональные рекомендации на день по сферам\n\n"
                "И все это по твоим личным данным, а не просто по знаку зодиака! 🤩\n\n"
                "💵 <b>Подписка — всего 99₽ в месяц</b>\n"
                "*без автопродления\n\n"
                "<b>ОПЛАТИТЬ по кнопке ниже</b> 👇🏼",
                reply_markup=buy_forecast_kb
            )
