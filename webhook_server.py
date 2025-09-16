from fastapi import FastAPI, Request
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

            # Просто логируем успешный платеж
            logger.info(f"✅ Payment processed for Telegram ID {telegram_id}, planet: {planet}")
            logger.info(f"✅ Payment successful: user {telegram_id} paid for {planet}")
            
            return {"status": "ok"}

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
