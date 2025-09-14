"""
Воркер для обработки астрологических предсказаний через RabbitMQ.

Получает данные из очереди, отправляет в OpenRouter для анализа,
и обновляет предсказание в базе данных.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional

import aio_pika
import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session, init_engine, dispose_engine
from models import Prediction, User, Planet, PredictionType

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://astro_user:astro_password_123@31.128.40.111:5672/")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
QUEUE_NAME = "moon_predictions"

# Проверяем наличие API ключа
if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY not set! LLM processing will be disabled.")

# Промпт для анализа Луны
MOON_ANALYSIS_PROMPT = """Ты астролог с опытом 10 лет, который делает разбор Луны по знаку, дому и аспектам. Не говори об этом формально, не указывай сухую астрологическую информацию — выдай разбор так, как будто ты смотришь прямо в душу. Твоя задача — дать разбор, который вызовет у человека ощущение: "Это как будто написано про меня". Чтобы захотелось продолжить разбор дальше, потому что откликнулись боли, вопросы и стало интересно — а что дальше? У КОГО? Луна в ЗНАКЕ, В ДОМЕ, + АСПЕКТЫ. Без лишних слов сразу переходи к характеристике по данным вопросам: 
1.	Как человек воспринимает мир? Насколько безопасно себя в нем чувствует? Насколько доверяет миру и людям? Развита ли интуиция? 
2.	Что могло происходить в детстве и как это повлияло на жизнь? 
3.	Характер человека, его внутренний мир, внутренний ребенок 
4.	Как человек воспринимает изменения и кризисы в жизни? Как идет в них? 
5.	Что нужно человеку, чтобы чувствовать себя комфортно и безопасно? 
6.	Ритм жизни человека, биоритмы, его базовые потребности (питание, сон, способность отдыхать) 
7.	Как человек проявляет эмоции? Способен ли на эмпатию и как проявляет заботу и поддержку? Эмоциональный интеллект 
8.	Как человек видит семью и быт? Как он выстраивает это? 
9.	Способность создавать уют? Гасить и разжигать конфликты? Идти на компромисс? 
10.	Если женский пол - какой мамой буду я для своего ребенка? 
11.	Если мужской пол - Какую женщину рассматривает мужчина в качестве жены? 
12.	Что нужно человеку, чтобы чувствовать себя эмоционально спокойно? Как снизить тревожность? От чего наоборот повышается? 
13.	Что важно человеку в профессии? Почему может происходить выгорание и как его не допустить? 
Пиши не как нейтральный психолог, а как близкий друг, который видит суть и не боится говорить честно. Стиль — живой, человеческий, прямой. Ты можешь быть и жёстким, если это поможет человеку очнуться. Но без морали. Не используй заголовки и пункты, пиши одним цельным текстом. Твоя цель — создать ощущение полного узнавания. Используй разговорный стиль без канцеляризмов, добавь якоря реальности 2025г: тревожные ленты соцсетей, ночные мысли о будущем, привычка держать всё под контролем, усталость от «делай лучше», откладывание на потом. Опиши, как это проявляется в повседневной жизни: в реакциях, привычках, мелочах. Обращайся к человеку по имени. Сделай разбор строго до 3000 символов, не больше.

Данные для анализа:
{astrology_data}

Имя пользователя: {user_name}
Пол: {user_gender}"""


class OpenRouterClient:
    """Клиент для работы с OpenRouter API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = OPENROUTER_URL
    
    async def generate_moon_analysis(
        self, 
        astrology_data: str, 
        user_name: str, 
        user_gender: str
    ) -> Dict[str, Any]:
        """
        Генерирует анализ Луны через OpenRouter
        
        Args:
            astrology_data: Данные астрологии для анализа
            user_name: Имя пользователя
            user_gender: Пол пользователя
            
        Returns:
            Dict с результатом генерации
        """
        prompt = MOON_ANALYSIS_PROMPT.format(
            astrology_data=astrology_data,
            user_name=user_name,
            user_gender=user_gender
        )
        
        payload = {
            "model": "deepseek/deepseek-chat-v3.1:free",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 3000,
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
                        logger.info(f"OpenRouter response received for {user_name}")
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


class PredictionWorker:
    """Воркер для обработки предсказаний"""
    
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
        
        logger.info("Worker initialized successfully")
    
    async def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получает информацию о пользователе из БД"""
        async with get_session() as session:
            # Ищем по telegram_id, а не по user_id
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
    
    async def update_prediction(
        self, 
        prediction_id: int, 
        llm_content: str, 
        llm_model: str,
        tokens_used: int,
        temperature: float = 0.7
    ) -> bool:
        """Обновляет предсказание с результатом LLM"""
        async with get_session() as session:
            result = await session.execute(
                select(Prediction).where(Prediction.prediction_id == prediction_id)
            )
            prediction = result.scalar_one_or_none()
            
            if not prediction:
                logger.error(f"Prediction {prediction_id} not found")
                return False
            
            # Обновляем содержимое и метаданные LLM
            prediction.content = llm_content
            prediction.llm_model = llm_model
            prediction.llm_tokens_used = tokens_used
            prediction.llm_temperature = temperature
            
            await session.commit()
            logger.info(f"Prediction {prediction_id} updated with LLM content")
            return True
    
    async def process_prediction(self, message_data: Dict[str, Any]):
        """Обрабатывает одно предсказание"""
        prediction_id = message_data.get("prediction_id")
        user_id = message_data.get("user_id")
        
        if not prediction_id or not user_id:
            logger.error(f"Invalid message data: {message_data}")
            return
        
        logger.info(f"Processing prediction {prediction_id} for user {user_id}")
        
        # Получаем информацию о пользователе по telegram_id
        user_info = await self.get_user_info(user_id)
        if not user_info:
            logger.error(f"User with telegram_id {user_id} not found")
            return
        
        # Получаем данные предсказания
        async with get_session() as session:
            result = await session.execute(
                select(Prediction).where(Prediction.prediction_id == prediction_id)
            )
            prediction = result.scalar_one_or_none()
            
            if not prediction:
                logger.error(f"Prediction {prediction_id} not found")
                return
            
            # Извлекаем данные астрологии из content
            content = prediction.content
            if "Moon Analysis Data:" in content:
                # Извлекаем только данные для LLM
                astrology_data = content.split("Moon Analysis Data:")[1].split("Raw AstrologyAPI data:")[0].strip()
            else:
                astrology_data = content
        
        # Генерируем анализ через OpenRouter (если доступен)
        if self.openrouter_client:
            llm_result = await self.openrouter_client.generate_moon_analysis(
                astrology_data=astrology_data,
                user_name=user_info["first_name"] or "Друг",
                user_gender=user_info["gender"]
            )
            
            if not llm_result["success"]:
                logger.error(f"LLM generation failed: {llm_result['error']}")
                return
            
            # Обновляем предсказание с результатом LLM
            await self.update_prediction(
                prediction_id=prediction_id,
                llm_content=llm_result["content"],
                llm_model=llm_result.get("model", "deepseek-chat-v3.1"),
                tokens_used=llm_result.get("usage", {}).get("total_tokens", 0),
                temperature=0.7
            )
        else:
            logger.info(f"LLM processing skipped for prediction {prediction_id} - no API key")
        
        logger.info(f"Prediction {prediction_id} processed successfully")
    
    async def start_consuming(self):
        """Запускает потребление сообщений из очереди"""
        if not self.channel:
            raise RuntimeError("Worker not initialized")
        
        queue = await self.channel.declare_queue(QUEUE_NAME, durable=True)
        
        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    message_data = json.loads(message.body.decode())
                    await self.process_prediction(message_data)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    # В реальном проекте здесь должна быть логика повторной обработки
        
        await queue.consume(process_message)
        logger.info(f"Started consuming from queue {QUEUE_NAME}")
    
    async def stop(self):
        """Останавливает воркера"""
        if self.connection:
            await self.connection.close()
        logger.info("Worker stopped")


async def main():
    """Основная функция запуска воркера"""
    logger.info("Starting prediction worker...")
    
    # Инициализируем подключение к БД
    init_engine()
    
    worker = PredictionWorker()
    
    try:
        await worker.initialize()
        await worker.start_consuming()
        
        # Держим воркера запущенным
        logger.info("Worker is running. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Worker error: {e}")
    finally:
        await worker.stop()
        await dispose_engine()
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
