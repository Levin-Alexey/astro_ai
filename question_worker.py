"""
Воркер для обработки вопросов пользователей на основе разбора Луны.

Получает данные из очереди, отправляет в OpenRouter для генерации ответов,
сохраняет результат в базу данных и отправляет пользователю.
"""

import asyncio
import json
import logging
import os
from typing import Dict, Any, Optional

import aio_pika
import aiohttp
from sqlalchemy import select

from db import get_session, init_engine, dispose_engine
from models import Prediction, User, Planet, PredictionType
from config import BOT_TOKEN

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL", 
    "amqp://astro_user:astro_password_123@31.128.40.111:5672/"
)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
QUEUE_NAME = "questions"
BOT_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Проверяем наличие API ключа
if not OPENROUTER_API_KEY:
    logger.warning(
        "OPENROUTER_API_KEY not set! LLM processing will be disabled."
    )

# Промпт для генерации ответов на вопросы
QUESTION_PROMPT = (
    "Ты профессиональный астролог. Пользователь задал вопрос на основе "
    "своего астрологического разбора.\n\n"
    "Астрологический разбор пользователя:\n"
    "{analysis}\n\n"
    "Вопрос пользователя: {user_question}\n\n"
    "Имя пользователя: {user_name}\n"
    "Пол: {user_gender}\n\n"
    "Ответь на вопрос пользователя, основываясь на его астрологической карте. "
    "Будь конкретным, полезным и вдохновляющим. "
    "Используй астрологические знания для объяснения ситуации и дай практические советы. "
    "В ответе НЕ упоминай конкретные планеты (Луну, Солнце и т.д.), "
    "говори об астрологических аспектах в общем. "
    "Ответ должен быть на русском языке, объемом 200-400 слов."
)


class OpenRouterClient:
    """Клиент для работы с OpenRouter API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = OPENROUTER_URL
    
    async def generate_answer(
        self, 
        analysis: str, 
        user_question: str,
        user_name: str, 
        user_gender: str
    ) -> Dict[str, Any]:
        """
        Генерирует ответ на вопрос через OpenRouter
        
        Args:
            analysis: Астрологический разбор пользователя
            user_question: Вопрос пользователя
            user_name: Имя пользователя
            user_gender: Пол пользователя
            
        Returns:
            Dict с результатом генерации
        """
        # Логируем данные, которые отправляем в LLM
        logger.info(f"Question LLM Input - User: {user_name}, Gender: {user_gender}")
        logger.info(f"Question LLM Input - Question: {user_question}")
        logger.info(f"Question LLM Input - Analysis length: {len(analysis)} characters")
        logger.info(f"Question LLM Input - Analysis preview: {analysis[:300]}...")
        
        prompt = QUESTION_PROMPT.format(
            analysis=analysis,
            user_question=user_question,
            user_name=user_name,
            user_gender=user_gender
        )
        
        logger.info(f"Question LLM Input - Full prompt length: {len(prompt)} characters")
        
        payload = {
            "model": "deepseek/deepseek-chat-v3.1:free",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 1500,
            "temperature": 0.7
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://astro-bot.com",
            "X-Title": "Astro Bot"
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"OpenRouter answer response received for {user_name}")
                        return {
                            "success": True,
                            "content": result["choices"][0]["message"]["content"],
                            "usage": result.get("usage", {}),
                            "model": result.get("model", "unknown")
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"OpenRouter error {response.status}: {error_text}")
                        return {
                            "success": False,
                            "error": f"API error: {response.status} - {error_text}"
                        }
                        
            except asyncio.TimeoutError:
                logger.error("OpenRouter request timeout")
                return {
                    "success": False,
                    "error": "Request timeout"
                }
            except Exception as e:
                logger.error(f"OpenRouter request failed: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }


class QuestionWorker:
    """Воркер для обработки вопросов"""
    
    def __init__(self):
        self.openrouter_client = None
        self.connection = None
        self.channel = None
    
    async def initialize(self):
        """Инициализация воркера"""
        if OPENROUTER_API_KEY:
            self.openrouter_client = OpenRouterClient(OPENROUTER_API_KEY)
            logger.info("OpenRouter client initialized")
        else:
            logger.warning("OpenRouter API key not set - LLM processing disabled")
            self.openrouter_client = None
        
        # Подключение к RabbitMQ
        self.connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self.channel = await self.connection.channel()
        
        # Объявляем очередь
        await self.channel.declare_queue(QUEUE_NAME, durable=True)
        
        logger.info("Question worker initialized successfully")
    
    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получает информацию о пользователе из БД"""
        async with get_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                logger.warning(f"User with telegram_id {user_id} not found")
                return None
            
            return {
                "user_id": user.user_id,
                "telegram_id": user.telegram_id,
                "first_name": user.first_name,
                "gender": user.gender.value if user.gender else "unknown"
            }
    
    async def get_moon_analysis(self, user_id: int) -> Optional[str]:
        """Получает разбор Луны пользователя"""
        async with get_session() as session:
            result = await session.execute(
                select(Prediction).where(
                    Prediction.user_id == user_id,
                    Prediction.planet == Planet.moon,
                    Prediction.prediction_type == PredictionType.free,
                    Prediction.is_active.is_(True),
                    Prediction.is_deleted.is_(False),
                    Prediction.moon_analysis.is_not(None)
                )
            )
            prediction = result.scalar_one_or_none()
            
            if not prediction or not prediction.moon_analysis:
                logger.warning(f"Moon analysis not found for user {user_id}")
                return None
            
            return prediction.moon_analysis
    
    async def save_question_answer(
        self, 
        user_id: int,
        question: str,
        answer: str,
        llm_model: str,
        tokens_used: int,
        temperature: float = 0.7
    ) -> bool:
        """Сохраняет вопрос и ответ в базу данных"""
        async with get_session() as session:
            # Создаем новую запись для вопроса-ответа
            question_prediction = Prediction(
                user_id=user_id,
                planet=Planet.moon,  # Вопросы привязаны к Луне
                prediction_type=PredictionType.free,
                content=answer,  # Сохраняем ответ в content для совместимости
                question=question,
                answer=answer,
                llm_model=llm_model,
                llm_tokens_used=tokens_used,
                llm_temperature=temperature,
                expires_at=None
            )
            
            session.add(question_prediction)
            await session.commit()
            
            logger.info(f"Question and answer saved for user {user_id}")
            return True
    
    async def send_telegram_message(
        self, 
        chat_id: int, 
        text: str
    ) -> bool:
        """Отправляет сообщение через Telegram Bot API"""
        url = f"{BOT_API_URL}/sendMessage"
        
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("ok"):
                            return True
                        else:
                            logger.error(f"Telegram API error: {result}")
                            return False
                    else:
                        error_text = await response.text()
                        logger.error(f"HTTP error {response.status}: {error_text}")
                        return False
                        
            except asyncio.TimeoutError:
                logger.error("Telegram API request timeout")
                return False
            except Exception as e:
                logger.error(f"Telegram API request failed: {e}")
                return False
    
    def format_answer_message(self, answer: str, user_name: str) -> str:
        """Форматирует сообщение с ответом"""
        message = f"🔮 Ответ для {user_name}\n\n"
        message += answer
        return message
    
    async def process_question(self, message_data: Dict[str, Any]):
        """Обрабатывает один вопрос"""
        user_id = message_data.get("user_telegram_id")
        question = message_data.get("question")
        
        if not user_id or not question:
            logger.error(f"Invalid message data: {message_data}")
            return
        
        logger.info(f"Processing question for user {user_id}: {question[:50]}...")
        
        # Получаем информацию о пользователе
        user_info = await self.get_user_info(user_id)
        if not user_info:
            logger.error(f"User with telegram_id {user_id} not found")
            return
        
        # Всегда используем разбор Луны как основу для ответов
        analysis = await self.get_moon_analysis(user_info["user_id"])
        if not analysis:
            logger.error(f"Moon analysis not found for user {user_id}")
            return
        
        # Генерируем ответ через OpenRouter (если доступен)
        if self.openrouter_client:
            llm_result = await self.openrouter_client.generate_answer(
                analysis=analysis,
                user_question=question,
                user_name=user_info["first_name"] or "Друг",
                user_gender=user_info["gender"]
            )
            
            if not llm_result["success"]:
                logger.error(f"LLM generation failed: {llm_result['error']}")
                return
            
            # Сохраняем вопрос и ответ в базу
            await self.save_question_answer(
                user_id=user_info["user_id"],
                question=question,
                answer=llm_result["content"],
                llm_model=llm_result.get("model", "deepseek-chat-v3.1"),
                tokens_used=llm_result.get("usage", {}).get("total_tokens", 0),
                temperature=0.7
            )
            
            # Отправляем ответ пользователю
            try:
                message = self.format_answer_message(
                    answer=llm_result["content"],
                    user_name=user_info["first_name"] or "Друг"
                )
                
                success = await self.send_telegram_message(
                    chat_id=user_id,
                    text=message
                )
                
                if success:
                    logger.info(f"Answer sent to user {user_id}")
                else:
                    logger.error(f"Failed to send answer to user {user_id}")
                    
            except Exception as e:
                logger.error(f"Error sending answer to user: {e}")
        else:
            logger.info(f"LLM processing skipped for question - no API key")
        
        logger.info(f"Question for user {user_id} processed successfully")
    
    async def start_consuming(self):
        """Запускает потребление сообщений из очереди"""
        if not self.channel:
            raise RuntimeError("Worker not initialized")
        
        queue = await self.channel.declare_queue(QUEUE_NAME, durable=True)
        
        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    logger.info(f"Received message from queue: {message.body.decode()[:100]}...")
                    message_data = json.loads(message.body.decode())
                    logger.info(f"Parsed message data: {message_data}")
                    await self.process_question(message_data)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        
        await queue.consume(process_message)
        logger.info(f"Started consuming from queue {QUEUE_NAME}")
    
    async def stop(self):
        """Останавливает воркера"""
        if self.connection:
            await self.connection.close()
        logger.info("Question worker stopped")


async def main():
    """Основная функция запуска воркера"""
    logger.info("Starting question worker...")
    
    # Инициализируем подключение к БД
    init_engine()
    
    worker = QuestionWorker()
    
    try:
        await worker.initialize()
        await worker.start_consuming()
        
        # Держим воркера запущенным
        logger.info("Question worker is running. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Worker error: {e}")
    finally:
        await worker.stop()
        await dispose_engine()
        logger.info("Question worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
