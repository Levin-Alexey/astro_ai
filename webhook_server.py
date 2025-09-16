from fastapi import FastAPI, Request
from sqlalchemy import select
import logging
from datetime import datetime, timedelta
from aiogram import Bot
from config import BOT_TOKEN
from db import engine
from models import User

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
app = FastAPI()

@app.post("/webhook")
async def yookassa_webhook(request: Request):
    try:
        data = await request.json()
        logger.info(f"Webhook received: {data}")

        if data.get("event") == "payment.succeeded":
            # Получаем метаданные из объекта платежа
            metadata = data["object"].get("metadata", {})
            user_id = metadata.get("user_id")
            planet = metadata.get("planet")
            
            if not user_id or not planet:
                logger.error("❌ Missing user_id or planet in metadata")
                return {"status": "error", "detail": "Missing metadata"}
            
            try:
                telegram_id = int(user_id)
            except ValueError:
                logger.error("❌ Invalid Telegram ID in metadata")
                return {"status": "error", "detail": "Invalid Telegram ID"}

            # Просто уведомляем пользователя без базы данных
            try:
                logger.info(f"✅ Payment processed for Telegram ID {telegram_id}, planet: {planet}")
                
                # Уведомляем пользователя
                await bot.send_message(
                    chat_id=telegram_id,
                    text=f"✅ Платеж успешно обработан!\n\n"
                         f"🌍 Планета: {planet}\n"
                         f"💰 Сумма: 10₽\n\n"
                         f"Теперь вы можете получить разбор этой планеты в боте!"
                )
                
                return {"status": "ok"}
            except Exception as bot_error:
                logger.error(f"❌ Bot error: {bot_error}")
                return {"status": "error", "detail": "Bot error"}

        return {"status": "ignored"}
        
    except Exception as e:
        logger.error(f"❌ Error processing webhook: {e}")
        return {"status": "error", "detail": str(e)}

@app.get("/webhook")
async def webhook_get():
    return {"status": "ok", "message": "Webhook endpoint is working"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}
