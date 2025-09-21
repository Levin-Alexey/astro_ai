"""
Воркер для обработки вопросов по Солнцу.
"""

import asyncio
import json
import logging
import os
from typing import Dict, Any

import aio_pika
from aiogram import Bot
from db import get_session
from models import User, Prediction, Planet, PredictionType
from sqlalchemy import select
from config import BOT_TOKEN

logger = logging.getLogger(__name__)


class OpenRouterClient:
    """Клиент для работы с OpenRouter API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://openrouter.ai/api/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://neyroastro.ru",
            "X-Title": "Astro Bot"
        }
    
    async def generate_response(self, prompt: str, model: str = "deepseek-chat-v3.1", 
                              max_tokens: int = 1000, temperature: float = 0.7) -> Dict[str, Any]:
        """Генерирует ответ через OpenRouter API"""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "content": data["choices"][0]["message"]["content"],
                            "model": model,
                            "usage": data.get("usage", {})
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"OpenRouter API error: {response.status} - {error_text}")
                        return {
                            "success": False,
                            "error": f"API error: {response.status}"
                        }
        except Exception as e:
            logger.error(f"Error calling OpenRouter API: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Настройки
RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL", 
    "amqp://astro_user:astro_password_123@31.128.40.111:5672/"
)
SUN_QUESTIONS_QUEUE_NAME = "sun_questions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class SunQuestionWorker:
    """Воркер для обработки вопросов по Солнцу"""
    
    def __init__(self):
        self.connection = None
        self.channel = None
        self.openrouter_client = None
        self.bot = None
        
    async def initialize(self):
        """Инициализация воркера"""
        logger.info("Starting sun question worker...")
        
        # Инициализация OpenRouter
        if OPENROUTER_API_KEY:
            self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY)
            logger.info("OpenRouter client initialized")
        else:
            logger.warning("OpenRouter API key not found - LLM processing disabled")
        
        # Инициализация Telegram Bot
        if BOT_TOKEN:
            self.bot = Bot(token=BOT_TOKEN)
            logger.info("Telegram bot initialized")
        else:
            logger.warning("Bot token not found - Telegram sending disabled")
        
        # Подключение к RabbitMQ
        self.connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self.channel = await self.connection.channel()
        
        # Объявляем очередь
        await self.channel.declare_queue(SUN_QUESTIONS_QUEUE_NAME, durable=True)
        
        logger.info("Sun question worker initialized successfully")
        
    async def process_question(self, message_data: Dict[str, Any]):
        """Обрабатывает вопрос пользователя по Солнцу"""
        try:
            user_telegram_id = message_data.get("user_telegram_id")
            question = message_data.get("question")
            sun_analysis = message_data.get("sun_analysis")
            
            if not all([user_telegram_id, question, sun_analysis]):
                logger.error(f"Missing required data: {message_data}")
                return
            
            logger.info(f"Processing sun question from user {user_telegram_id}: {question[:50]}...")
            
            # Получаем данные пользователя
            async with get_session() as session:
                user_result = await session.execute(
                    select(User).where(User.telegram_id == user_telegram_id)
                )
                user = user_result.scalar_one_or_none()
                
                if not user:
                    logger.error(f"User {user_telegram_id} not found")
                    return
                
                # Находим разбор Солнца
                prediction_result = await session.execute(
                    select(Prediction).where(
                        Prediction.user_id == user.user_id,
                        Prediction.planet == Planet.sun,
                        Prediction.prediction_type == PredictionType.paid,
                        Prediction.is_active.is_(True),
                        Prediction.is_deleted.is_(False)
                    )
                )
                prediction = prediction_result.scalar_one_or_none()
                
                if not prediction:
                    logger.error(f"Sun prediction not found for user {user_telegram_id}")
                    return
                
                # Генерируем ответ через LLM
                if self.openrouter_client:
                    answer = await self.generate_answer(
                        question=question,
                        sun_analysis=sun_analysis,
                        user_name=user.first_name or "Пользователь"
                    )
                    
                    if answer:
                        # Отправляем ответ пользователю
                        await self.send_answer_to_user(user_telegram_id, answer)
                        
                        # Сохраняем вопрос и ответ в БД
                        await self.save_question_and_answer(
                            prediction_id=prediction.prediction_id,
                            question=question,
                            answer=answer
                        )
                    else:
                        logger.error(f"Failed to generate answer for user {user_telegram_id}")
                        await self.send_error_to_user(user_telegram_id)
                else:
                    logger.warning("OpenRouter client not available - skipping LLM processing")
                    await self.send_error_to_user(user_telegram_id)
                    
        except Exception as e:
            logger.error(f"Error processing sun question: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    async def generate_answer(self, question: str, sun_analysis: str, user_name: str) -> str:
        """Генерирует ответ на вопрос пользователя"""
        try:
            prompt = f"""
Ты - профессиональный астролог Лилит. Пользователь {user_name} задал вопрос по своему разбору Солнца.

РАЗБОР СОЛНЦА ПОЛЬЗОВАТЕЛЯ:
{sun_analysis}

ВОПРОС ПОЛЬЗОВАТЕЛЯ:
{question}

ИНСТРУКЦИИ:
1. Ответь на вопрос пользователя, основываясь на его разборе Солнца
2. Дай персональные советы и рекомендации
3. Будь дружелюбной и поддерживающей
4. Используй эмодзи для эмоциональности
5. Ответ должен быть 200-400 слов
6. Пиши от первого лица ("Я вижу", "Твое Солнце говорит")

Ответ:
"""
            
            response = await self.openrouter_client.generate_response(
                prompt=prompt,
                model="deepseek-chat-v3.1",
                max_tokens=500,
                temperature=0.7
            )
            
            if response and response.get("success"):
                return response["content"]
            else:
                logger.error(f"OpenRouter API error: {response.get('error', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return None
    
    async def send_answer_to_user(self, user_telegram_id: int, answer: str):
        """Отправляет ответ пользователю в Telegram"""
        try:
            if self.bot:
                await self.bot.send_message(chat_id=user_telegram_id, text=answer)
                logger.info(f"Answer sent to user {user_telegram_id}")
            else:
                logger.warning("Bot not initialized - cannot send message")
                
        except Exception as e:
            logger.error(f"Error sending answer to user: {e}")
    
    async def send_error_to_user(self, user_telegram_id: int):
        """Отправляет сообщение об ошибке пользователю"""
        try:
            error_message = (
                "❌ Произошла ошибка при обработке твоего вопроса.\n\n"
                "Попробуй позже или обратись в поддержку."
            )
            
            if self.bot:
                await self.bot.send_message(chat_id=user_telegram_id, text=error_message)
                logger.info(f"Error message sent to user {user_telegram_id}")
            else:
                logger.warning("Bot not initialized - cannot send error message")
            
        except Exception as e:
            logger.error(f"Error sending error message: {e}")
    
    async def save_question_and_answer(self, prediction_id: int, question: str, answer: str):
        """Сохраняет вопрос и ответ в БД"""
        try:
            async with get_session() as session:
                # Обновляем предсказание с вопросом и ответом
                result = await session.execute(
                    select(Prediction).where(Prediction.prediction_id == prediction_id)
                )
                prediction = result.scalar_one_or_none()
                
                if prediction:
                    prediction.question = question
                    prediction.answer = answer
                    await session.commit()
                    logger.info(f"Saved question and answer for prediction {prediction_id}")
                else:
                    logger.error(f"Prediction {prediction_id} not found for saving question")
                    
        except Exception as e:
            logger.error(f"Error saving question and answer: {e}")
    
    async def start_consuming(self):
        """Начинает потребление сообщений из очереди"""
        try:
            queue = await self.channel.declare_queue(SUN_QUESTIONS_QUEUE_NAME, durable=True)
            
            async def process_message(message: aio_pika.IncomingMessage):
                async with message.process():
                    try:
                        message_data = json.loads(message.body.decode())
                        await self.process_question(message_data)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
            
            logger.info(f"Started consuming from queue {SUN_QUESTIONS_QUEUE_NAME}")
            
            # Начинаем потребление и ждем бесконечно
            await queue.consume(process_message)
            
            # Ждем бесконечно, пока не будет прервано
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
            
        except Exception as e:
            logger.error(f"Error starting consumer: {e}")
            raise
    
    async def close(self):
        """Закрывает соединения"""
        if self.bot:
            await self.bot.session.close()
        if self.connection:
            await self.connection.close()
        logger.info("Sun question worker closed")


async def main():
    """Главная функция воркера"""
    worker = SunQuestionWorker()
    
    try:
        await worker.initialize()
        logger.info("Sun question worker is running. Press Ctrl+C to stop.")
        await worker.start_consuming()
    except KeyboardInterrupt:
        logger.info("Stopping sun question worker...")
    except Exception as e:
        logger.error(f"Sun question worker error: {e}")
    finally:
        await worker.close()


if __name__ == "__main__":
    asyncio.run(main())
