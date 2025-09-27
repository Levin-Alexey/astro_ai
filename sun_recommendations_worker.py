"""
Воркер для генерации персональных рекомендаций на основе разбора Солнца.

Получает данные из очереди, отправляет в OpenRouter для генерации рекомендаций,
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
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

from db import get_session, init_engine, dispose_engine
from models import Prediction, User, Planet, PredictionType
from config import BOT_TOKEN

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://astro_user:astro_password_123@31.128.40.111:5672/")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
QUEUE_NAME = "sun_recommendations"
BOT_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Проверяем наличие API ключа
if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY not set! LLM processing will be disabled.")

# Промпт для генерации рекомендаций по Солнцу
SUN_RECOMMENDATIONS_PROMPT = """Ты опытный астролог-практик. На основе разбора Солнца создай персональные рекомендации для гармонизации солнечной энергии. 

ВАЖНО: Пиши ТОЛЬКО на русском языке! Никаких английских слов!

Создай рекомендации в формате:

☀️ ЕЖЕДНЕВНЫЕ ПРАКТИКИ:
• [3-4 конкретные практики для повышения энергии и уверенности]

🎯 САМОРЕАЛИЗАЦИЯ:
• [2-3 рекомендации по проявлению талантов и уникальности]

💪 ЭНЕРГИЯ И АКТИВНОСТЬ:
• [3-4 способа поддержания жизненной силы]

🌟 САМООЦЕНКА И УВЕРЕННОСТЬ:
• [2-3 практики для укрепления внутренней опоры]

🎨 ТВОРЧЕСТВО И САМОВЫРАЖЕНИЕ:
• [2-3 совета по раскрытию творческого потенциала]

👑 ЛИДЕРСТВО И ВЛИЯНИЕ:
• [2-3 рекомендации по проявлению лидерских качеств]

После рекомендаций напиши раздел:

✨ РЕЗУЛЬТАТЫ ПРАКТИК:
Если будешь следовать этим рекомендациям, {user_name}, ты получишь: [перечисли конкретные позитивные изменения - уверенность, внутренняя опора, яркость жизни, радость]

Пиши просто, по делу, без воды. Обращайся к пользователю по имени. Учитывай особенности пола при рекомендациях.

Разбор Солнца:
{sun_analysis}

Имя: {user_name}
Пол: {user_gender}"""


class OpenRouterClient:
    """Клиент для работы с OpenRouter API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = OPENROUTER_URL
    
    async def generate_sun_recommendations(
        self, 
        sun_analysis: str, 
        user_name: str, 
        user_gender: str
    ) -> Dict[str, Any]:
        """
        Генерирует рекомендации по Солнцу через OpenRouter
        
        Args:
            sun_analysis: Разбор Солнца пользователя
            user_name: Имя пользователя
            user_gender: Пол пользователя
            
        Returns:
            Dict с результатом генерации
        """
        # Логируем данные, которые отправляем в LLM
        logger.info(f"Sun Recommendations LLM Input - User: {user_name}, Gender: {user_gender}")
        logger.info(f"Sun Recommendations LLM Input - Sun analysis length: {len(sun_analysis)} characters")
        logger.info(f"Sun Recommendations LLM Input - Sun analysis preview: {sun_analysis[:300]}...")
        
        prompt = SUN_RECOMMENDATIONS_PROMPT.format(
            sun_analysis=sun_analysis,
            user_name=user_name,
            user_gender=user_gender
        )
        
        logger.info(f"Sun Recommendations LLM Input - Full prompt length: {len(prompt)} characters")
        
        payload = {
            "model": "tngtech/deepseek-r1t-chimera",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 2500,
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
                    timeout=aiohttp.ClientTimeout(total=180)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"OpenRouter sun recommendations response received for {user_name}")
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


class SunRecommendationsWorker:
    """Воркер для обработки рекомендаций по Солнцу"""
    
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
        
        logger.info("Sun recommendations worker initialized successfully")
    
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
    
    async def save_sun_recommendations(
        self, 
        prediction_id: int, 
        recommendations: str,
        llm_model: str,
        tokens_used: int,
        temperature: float = 0.7
    ) -> bool:
        """Сохраняет рекомендации по Солнцу в базу данных"""
        async with get_session() as session:
            # Находим исходное предсказание
            result = await session.execute(
                select(Prediction).where(Prediction.prediction_id == prediction_id)
            )
            prediction = result.scalar_one_or_none()
            
            if not prediction:
                logger.error(f"Prediction {prediction_id} not found")
                return False
            
            # Создаем новую запись для рекомендаций по Солнцу
            recommendations_prediction = Prediction(
                user_id=prediction.user_id,
                planet=Planet.sun,  # Рекомендации привязаны к Солнцу
                prediction_type=PredictionType.paid,  # Платные рекомендации
                recommendations=recommendations,
                llm_model=llm_model,
                llm_tokens_used=tokens_used,
                llm_temperature=temperature,
                expires_at=prediction.expires_at  # Наследуем срок действия от основного предсказания
            )
            
            session.add(recommendations_prediction)
            await session.commit()
            
            logger.info(f"Sun recommendations saved for prediction {prediction_id}")
            return True
    
    async def send_telegram_message(
        self, 
        chat_id: int, 
        text: str
    ) -> bool:
        """Отправляет сообщение через Telegram Bot API"""
        url = f"{BOT_API_URL}/sendMessage"
        
        # Подготавливаем кнопки после рекомендаций
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "🔍 Исследовать другие сферы",
                        "callback_data": "explore_other_areas"
                    }
                ],
                [
                    {
                        "text": "🏠 Главное меню",
                        "callback_data": "back_to_menu"
                    }
                ]
            ]
        }
        
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": keyboard
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
    
    def format_sun_recommendations_message(self, recommendations: str, user_name: str) -> str:
        """Форматирует сообщение с рекомендациями по Солнцу"""
        from datetime import datetime
        
        message = f"☀️ Персональные рекомендации по Солнцу для {user_name}\n\n"
        message += recommendations
        
        # Добавляем время создания
        now = datetime.now()
        message += f"\n\n✨ Создано: {now.strftime('%d.%m.%Y в %H:%M')}"
        
        return message
    
    async def process_sun_recommendation(self, message_data: Dict[str, Any]):
        """Обрабатывает один запрос на рекомендации по Солнцу"""
        prediction_id = message_data.get("prediction_id")
        user_id = message_data.get("user_telegram_id")
        sun_analysis = message_data.get("sun_analysis")
        
        if not prediction_id or not user_id or not sun_analysis:
            logger.error(f"Invalid message data: {message_data}")
            return
        
        logger.info(f"Processing sun recommendations for prediction {prediction_id}, user {user_id}")
        
        # Получаем информацию о пользователе
        user_info = await self.get_user_info(user_id)
        if not user_info:
            logger.error(f"User with telegram_id {user_id} not found")
            return
        
        # Генерируем рекомендации через OpenRouter (если доступен)
        if self.openrouter_client:
            llm_result = await self.openrouter_client.generate_sun_recommendations(
                sun_analysis=sun_analysis,
                user_name=user_info["first_name"] or "Друг",
                user_gender=user_info["gender"]
            )
            
            if not llm_result["success"]:
                logger.error(f"LLM generation failed: {llm_result['error']}")
                return
            
            # Сохраняем рекомендации в базу
            await self.save_sun_recommendations(
                prediction_id=prediction_id,
                recommendations=llm_result["content"],
                llm_model=llm_result.get("model", "deepseek-chat-v3.1"),
                tokens_used=llm_result.get("usage", {}).get("total_tokens", 0),
                temperature=0.7
            )
            
            # Отправляем рекомендации пользователю
            try:
                message = self.format_sun_recommendations_message(
                    recommendations=llm_result["content"],
                    user_name=user_info["first_name"] or "Друг"
                )
                
                success = await self.send_telegram_message(
                    chat_id=user_id,
                    text=message
                )
                
                if success:
                    logger.info(f"Sun recommendations sent to user {user_id}")
                else:
                    logger.error(f"Failed to send sun recommendations to user {user_id}")
                    
            except Exception as e:
                logger.error(f"Error sending sun recommendations to user: {e}")
        else:
            logger.info(f"LLM processing skipped for sun recommendations - no API key")
        
        logger.info(f"Sun recommendations for prediction {prediction_id} processed successfully")
    
    async def start_consuming(self):
        """Запускает потребление сообщений из очереди"""
        if not self.channel:
            raise RuntimeError("Worker not initialized")
        
        queue = await self.channel.declare_queue(QUEUE_NAME, durable=True)
        
        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    message_data = json.loads(message.body.decode())
                    await self.process_sun_recommendation(message_data)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        
        await queue.consume(process_message)
        logger.info(f"Started consuming from queue {QUEUE_NAME}")
    
    async def stop(self):
        """Останавливает воркера"""
        if self.connection:
            await self.connection.close()
        logger.info("Sun recommendations worker stopped")


async def main():
    """Основная функция запуска воркера"""
    logger.info("Starting sun recommendations worker...")
    
    # Инициализируем подключение к БД
    init_engine()
    
    worker = SunRecommendationsWorker()
    
    try:
        await worker.initialize()
        await worker.start_consuming()
        
        # Держим воркера запущенным
        logger.info("Sun recommendations worker is running. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Worker error: {e}")
    finally:
        await worker.stop()
        dispose_engine()
        logger.info("Sun recommendations worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
