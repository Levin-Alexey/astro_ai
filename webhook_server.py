from fastapi import FastAPI, Request
import logging
import asyncio
from datetime import datetime, timezone

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

            # Обновляем статус платежа в БД
            await update_payment_status(telegram_id, planet, payment_id)
            
            # Отправляем уведомление пользователю
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
        from sqlalchemy import select, update
        
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
            
            # Находим платеж по user_id и планете
            if planet == "all_planets":
                result = await session.execute(
                    select(PlanetPayment).where(
                        PlanetPayment.user_id == user.user_id,
                        PlanetPayment.payment_type == PaymentType.all_planets,
                        PlanetPayment.status == PaymentStatus.pending
                    )
                )
            else:
                planet_enum = Planet(planet)
                result = await session.execute(
                    select(PlanetPayment).where(
                        PlanetPayment.user_id == user.user_id,
                        PlanetPayment.payment_type == PaymentType.single_planet,
                        PlanetPayment.planet == planet_enum,
                        PlanetPayment.status == PaymentStatus.pending
                    )
                )
            
            payment_record = result.scalar_one_or_none()
            if payment_record:
                # Обновляем статус на completed
                payment_record.status = PaymentStatus.completed
                payment_record.completed_at = datetime.now(timezone.utc)
                payment_record.external_payment_id = external_payment_id
                await session.commit()
                
                logger.info(f"✅ Payment status updated for user {user_id}, planet {planet}")
            else:
                logger.warning(f"⚠️ Payment record not found for user {user_id}, planet {planet}")
                
    except Exception as e:
        logger.error(f"❌ Error updating payment status: {e}")


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
            f"🎉 Платеж успешно обработан!\n\n"
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
            astrology_data = await start_sun_analysis(user_id)
            
            if astrology_data:
                logger.info(f"✅ Sun analysis data generated for user {user_id}")
            else:
                logger.error(f"❌ Failed to generate sun analysis for user {user_id}")
        
        # Для Меркурия вызываем start_mercury_analysis
        elif planet == "mercury":
            from astrology_handlers import start_mercury_analysis
            astrology_data = await start_mercury_analysis(user_id)
            
            if astrology_data:
                logger.info(f"☿️ Mercury analysis data generated for user {user_id}")
            else:
                logger.error(f"❌ Failed to generate mercury analysis for user {user_id}")
        
        # Для Венеры вызываем start_venus_analysis
        elif planet == "venus":
            from astrology_handlers import start_venus_analysis
            astrology_data = await start_venus_analysis(user_id)
            
            if astrology_data:
                logger.info(f"♀️ Venus analysis data generated for user {user_id}")
            else:
                logger.error(f"❌ Failed to generate venus analysis for user {user_id}")
        
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
