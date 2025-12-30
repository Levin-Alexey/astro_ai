from fastapi import FastAPI, Request
import logging
import asyncio
from datetime import datetime, timezone
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton # Добавлен импорт
from db import get_session 
from subscriptions_db import (
    create_or_update_subscription, 
    update_subscription_payment_status,
    get_user_id_by_telegram_id
)
from models import PaymentStatus


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.post("/webhook")
async def yookassa_webhook(request: Request):
    try:
        data = await request.json()
        logger.info(f"🔥 WEBHOOK RECEIVED: {data}")
        print(f"🔥 WEBHOOK RECEIVED: {data}")

        if data.get("event") == "payment.succeeded":
            logger.info(f"🔥 PAYMENT SUCCEEDED EVENT!")
            print(f"🔥 PAYMENT SUCCEEDED EVENT!")
            # Получаем метаданные из объекта платежа
            metadata = data["object"].get("metadata", {})
            user_id = metadata.get("user_id")
            planet = metadata.get("planet")
            payment_id = data["object"].get("id")
            
            if not user_id or not planet:
                logger.error("❌ Missing user_id or planet in metadata")
                return {"status": "error", "detail": "Missing metadata"}
            
            try:
                telegram_id = int(user_id)
            except ValueError:
                logger.error("❌ Invalid Telegram ID in metadata")
                return {"status": "error", "detail": "Invalid Telegram ID"}

            # Обработка подписки на персональные прогнозы
            if planet == "personal_forecasts_sub":
                logger.info(f"🔥 Processing SUBSCRIPTION payment for user {telegram_id}")
                async with get_session() as session:
                    # Обновляем статус платежа
                    await update_subscription_payment_status(
                        session, payment_id, PaymentStatus.completed
                    )
                    
                    # Получаем реальный user_id из БД по telegram_id
                    db_user_id = await get_user_id_by_telegram_id(session, telegram_id)
                    
                    if db_user_id:
                        # Активируем/продлеваем подписку на 1 месяц
                        await create_or_update_subscription(session, db_user_id, duration_months=1)
                        logger.info(f"✅ Subscription created/extended for user {telegram_id}")
                        
                        # Отправляем уведомление
                        try:
                            from main import bot
                            await bot.send_message(
                                telegram_id,
                                "🎉 **Подписка успешно оформлена!**\n\n"
                                "Теперь вы будете получать ежедневные персональные прогнозы.\n"
                                "Нажмите кнопку ниже, чтобы получить свой прогноз на сегодня!",
                                reply_markup=InlineKeyboardMarkup(
                                    inline_keyboard=[
                                        [
                                            InlineKeyboardButton(
                                                text="🔥 Получить персональный прогноз",
                                                callback_data="personal_forecasts"
                                            )
                                        ]
                                    ]
                                )
                            )
                        except Exception as e:
                            logger.error(f"❌ Failed to send subscription notification: {e}")
                    else:
                        logger.error(f"❌ User with telegram_id {telegram_id} not found for subscription update")
                
                return {"status": "ok"}

            # Обновляем статус платежа в БД

            logger.info(f"🔥 Updating payment status: telegram_id={telegram_id}, planet={planet}")
            await update_payment_status(telegram_id, planet, payment_id)
            
            # Если это оплата за все планеты, запускаем последовательный разбор
            if planet == "all_planets":
                logger.info(f"🔥 Processing ALL PLANETS payment")
                from all_planets_handler import get_all_planets_handler
                handler = get_all_planets_handler()
                if handler:
                    await handler.handle_payment_success(telegram_id)
                else:
                    logger.error("❌ All planets handler not initialized")
            else:
                # Отправляем уведомление пользователю для отдельных планет
                logger.info(f"🔥 Processing SINGLE PLANET payment: planet={planet}")
                await notify_user_payment_success(telegram_id, planet)
            
            logger.info(f"✅ Payment processed for Telegram ID {telegram_id}, planet: {planet}")
            
            return {"status": "ok"}

        return {"status": "ignored"}
        
    except Exception as e:
        logger.error(f"❌ Error processing webhook: {e}")
        return {"status": "error", "detail": str(e)}


async def update_payment_status(user_id: int, planet: str, external_payment_id: str):
    """Обновляет статус платежа в БД"""
    try:
        from db import get_session
        from models import PlanetPayment, PaymentStatus, PaymentType, Planet
        from sqlalchemy import select
        
        async with get_session() as session:
            # Сначала находим user_id по telegram_id
            from models import User
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                logger.error(f"❌ User with telegram_id {user_id} not found")
                return
            
            # Находим платеж по external_payment_id (основной способ)
            # или по user_id и планете (резервный способ)
            if planet == "all_planets":
                result = await session.execute(
                    select(PlanetPayment).where(
                        (PlanetPayment.external_payment_id == external_payment_id) |
                        (
                            (PlanetPayment.user_id == user.user_id) &  # FIX: используем внутренний ID
                            (PlanetPayment.payment_type == PaymentType.all_planets) &
                            (PlanetPayment.status == PaymentStatus.pending)
                        )
                    ).order_by(PlanetPayment.created_at.desc())
                )
            else:
                planet_enum = Planet(planet)
                result = await session.execute(
                    select(PlanetPayment).where(
                        (PlanetPayment.external_payment_id == external_payment_id) |
                        (
                            (PlanetPayment.user_id == user.user_id) &  # FIX: используем внутренний ID
                            (PlanetPayment.payment_type == PaymentType.single_planet) &
                            (PlanetPayment.planet == planet_enum) &
                            (PlanetPayment.status == PaymentStatus.pending)
                        )
                    ).order_by(PlanetPayment.created_at.desc())
                )
            
            payment_record = result.scalar_one_or_none()
            if payment_record:
                logger.info(f"✅ Payment record found: {payment_record.payment_id}")
                # Обновляем статус на completed
                logger.info(f"🔄 Updating payment {payment_record.payment_id} status from {payment_record.status} to completed")
                payment_record.status = PaymentStatus.completed
                payment_record.completed_at = datetime.now(timezone.utc)
                if not payment_record.external_payment_id:
                    payment_record.external_payment_id = external_payment_id
                
                # Коммитим изменения
                try:
                    await session.commit()
                    logger.info(f"✅ Session committed for payment {payment_record.payment_id}")
                except Exception as commit_error:
                    logger.error(f"❌ Error committing payment status update: {commit_error}", exc_info=True)
                    await session.rollback()
                    raise
                
                logger.info(f"✅ Payment status updated for user {user_id}, planet {planet}")
            else:
                logger.warning(f"⚠️ Payment record not found for user {user_id}, planet {planet}, external_id {external_payment_id}")
                # Попробуем найти хотя бы по пользователю для отладки
                debug_result = await session.execute(
                    select(PlanetPayment).where(
                        PlanetPayment.user_id == user.user_id  # FIX: используем внутренний ID
                    ).order_by(PlanetPayment.created_at.desc()).limit(5)
                )
                debug_payments = debug_result.scalars().all()
                logger.info(f"🔍 Last 5 payments for user {user_id}:")
                for dp in debug_payments:
                    logger.info(f"  - Payment {dp.payment_id}: {dp.planet}, {dp.status}, external_id: {dp.external_payment_id}")
                
    except Exception as e:
        logger.error(f"❌ Error updating payment status: {e}", exc_info=True)
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")


async def notify_user_payment_success(user_id: int, planet: str):
    """Отправляет уведомление пользователю об успешной оплате"""
    try:
        from main import bot
        
        planet_names = {
            "sun": "☀️ Солнце",
            "mercury": "☿️ Меркурий", 
            "venus": "♀️ Венера",
            "mars": "♂️ Марс",
            "all_planets": "🌌 Все планеты"
        }
        
        planet_name = planet_names.get(planet, planet)
        
        message = (
            "Благодарю за доверие 😻\n"
            "Оплата успешно прошла!\n\n"
            "Удачных тебе трансформаций 🐈‍⬛🙌🏼\n\n"
            f"✅ У вас теперь есть доступ к разбору {planet_name}!\n\n"
            f"🔮 Генерирую ваш персональный астрологический разбор...\n\n"
            f"⏳ Пожалуйста, подождите, это может занять несколько минут."
        )
        
        await bot.send_message(user_id, message)
        
        # Запускаем генерацию разбора в фоне
        asyncio.create_task(generate_planet_analysis(user_id, planet))
        
        logger.info(f"✅ Notification sent to user {user_id} for planet {planet}")
        
    except Exception as e:
        logger.error(f"❌ Error sending notification to user {user_id}: {e}")


async def generate_planet_analysis(user_id: int, planet: str):
    """Генерирует астрологический разбор планеты через воркер"""
    try:
        logger.info(f"🚀 Starting planet analysis for user {user_id}, planet {planet}")
        
        # Для Солнца вызываем start_sun_analysis
        if planet == "sun":
            from astrology_handlers import start_sun_analysis
            astrology_data = await start_sun_analysis(user_id, None)
            
            if astrology_data:
                logger.info(f"✅ Sun analysis data generated for user {user_id}")
            else:
                logger.error(f"❌ Failed to generate sun analysis for user {user_id}")
        
        # Для Меркурия используем отдельную функцию как у Луны
        elif planet == "mercury":
            from astrology_handlers import start_mercury_analysis
            logger.info(f"🚀 Calling start_mercury_analysis for user {user_id}")
            astrology_data = await start_mercury_analysis(user_id, None)
        
        # Для Венеры используем отдельную функцию как у Луны
        elif planet == "venus":
            from astrology_handlers import start_venus_analysis
            logger.info(f"🚀 Calling start_venus_analysis for user {user_id}")
            astrology_data = await start_venus_analysis(user_id, None)
        
        # Для Марса используем отдельную функцию как у Луны
        elif planet == "mars":
            from astrology_handlers import start_mars_analysis
            logger.info(f"🚀 Calling start_mars_analysis for user {user_id}")
            astrology_data = await start_mars_analysis(user_id, None)
        
        else:
            logger.warning(f"⚠️ Analysis for {planet} not implemented yet")
                    
    except Exception as e:
        logger.error(f"❌ Error generating planet analysis: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")


async def send_prediction_to_worker_queue(prediction_id: int, user_id: int):
    """Отправляет предсказание в очередь воркера"""
    try:
        import aio_pika
        
        # Подключение к RabbitMQ
        RABBITMQ_URL = "amqp://astro_user:astro_password_123@31.128.40.111:5672/"
        QUEUE_NAME = "sun_predictions"
        
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()
        
        # Объявляем очередь
        await channel.declare_queue(QUEUE_NAME, durable=True)
        
        # Создаем сообщение
        message_data = {
            "prediction_id": prediction_id,
            "user_id": user_id
        }
        
        # Отправляем сообщение
        await channel.default_exchange.publish(
            aio_pika.Message(
                json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=QUEUE_NAME
        )
        
        await connection.close()
        logger.info(f"✅ Prediction {prediction_id} sent to worker queue")
        
    except Exception as e:
        logger.error(f"❌ Error sending prediction to worker queue: {e}")



@app.get("/webhook")
async def webhook_get():
    return {"status": "ok", "message": "Webhook endpoint is working"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}
