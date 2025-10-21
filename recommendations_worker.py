"""
Воркер для генерации персональных рекомендаций на основе разбора Луны.

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

from db import get_session, init_engine, dispose_engine
from models import Prediction, User, Planet, PredictionType, AdditionalProfile
from config import BOT_TOKEN

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://astro_user:astro_password_123@31.128.40.111:5672/")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
QUEUE_NAME = "recommendations"
BOT_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Проверяем наличие API ключа
if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY not set! LLM processing will be disabled.")

# Промпт для генерации рекомендаций
RECOMMENDATIONS_PROMPT = """Ты опытный астролог-практик. На основе разбора Луны создай персональные рекомендации для гармонизации лунной энергии. 

ВАЖНО: Пиши ТОЛЬКО на русском языке! Никаких английских слов!

Создай рекомендации в формате:

🌙 ЕЖЕДНЕВНЫЕ ПРАКТИКИ:
• [3-4 конкретные практики для ежедневного выполнения]

🏠 ДОМАШНЯЯ ОБСТАНОВКА:
• [2-3 рекомендации по созданию комфортной среды]

😌 ЭМОЦИОНАЛЬНАЯ ГИГИЕНА:
• [3-4 способа работы с эмоциями и тревожностью]

💤 СОН И ОТДЫХ:
• [2-3 рекомендации по режиму сна и восстановлению]

🍃 ПИТАНИЕ И РИТМЫ:
• [2-3 совета по питанию и биоритмам]

👥 ОТНОШЕНИЯ:
• [2-3 рекомендации по выстраиванию отношений]

После рекомендаций напиши раздел:

✨ РЕЗУЛЬТАТЫ ПРАКТИК:
Если будешь следовать этим рекомендациям, {user_name}, ты получишь: [перечисли конкретные позитивные изменения]

Пиши просто, по делу, без воды. Обращайся к пользователю по имени. Учитывай особенности пола при рекомендациях.

Разбор Луны:
{moon_analysis}

Имя: {user_name}
Пол: {user_gender}"""


class OpenRouterClient:
    """Клиент для работы с OpenRouter API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = OPENROUTER_URL
    
    async def generate_recommendations(
        self, 
        moon_analysis: str, 
        user_name: str, 
        user_gender: str
    ) -> Dict[str, Any]:
        """
        Генерирует рекомендации через OpenRouter
        
        Args:
            moon_analysis: Разбор Луны пользователя
            user_name: Имя пользователя
            user_gender: Пол пользователя
            
        Returns:
            Dict с результатом генерации
        """
        # Логируем данные, которые отправляем в LLM
        logger.info(f"Recommendations LLM Input - User: {user_name}, Gender: {user_gender}")
        logger.info(f"Recommendations LLM Input - Moon analysis length: {len(moon_analysis)} characters")
        logger.info(f"Recommendations LLM Input - Moon analysis preview: {moon_analysis[:300]}...")
        
        prompt = RECOMMENDATIONS_PROMPT.format(
            moon_analysis=moon_analysis,
            user_name=user_name,
            user_gender=user_gender
        )
        
        logger.info(f"Recommendations LLM Input - Full prompt length: {len(prompt)} characters")
        
        payload = {
            "model": "deepseek/deepseek-chat-v3.1",
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
                logger.info(f"Sending recommendations request for {user_name}...")
                start_time = asyncio.get_event_loop().time()
                
                async with session.post(
                    self.url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=180)
                ) as response:
                    end_time = asyncio.get_event_loop().time()
                    logger.info(f"Recommendations response time: {end_time - start_time:.2f}s")
                    
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"OpenRouter recommendations response received for {user_name}")
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
                logger.error(f"Recommendations request timeout for {user_name}")
                return {
                    "success": False,
                    "error": "Request timeout - try again later"
                }
            except Exception as e:
                logger.error(f"OpenRouter request failed: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }


class RecommendationsWorker:
    """Воркер для обработки рекомендаций"""
    
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
        
        logger.info("Recommendations worker initialized successfully")
    
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
    
    async def get_additional_profile_info(self, profile_id: int) -> Optional[Dict[str, Any]]:
        """Получает информацию о дополнительном профиле из БД"""
        async with get_session() as session:
            result = await session.execute(
                select(AdditionalProfile).where(AdditionalProfile.profile_id == profile_id)
            )
            profile = result.scalar_one_or_none()
            
            if not profile:
                logger.warning(f"Additional profile with ID {profile_id} not found")
                return None
            
            return {
                "profile_id": profile.profile_id,
                "owner_user_id": profile.owner_user_id,
                "full_name": profile.full_name,
                "gender": profile.gender.value if profile.gender else "unknown"
            }
    
    async def save_recommendations(
        self, 
        prediction_id: int, 
        recommendations: str,
        llm_model: str,
        tokens_used: int,
        temperature: float = 0.7,
        profile_id: Optional[int] = None
    ) -> bool:
        """Сохраняет рекомендации в базу данных"""
        async with get_session() as session:
            # Находим исходное предсказание
            result = await session.execute(
                select(Prediction).where(Prediction.prediction_id == prediction_id)
            )
            prediction = result.scalar_one_or_none()
            
            if not prediction:
                logger.error(f"Prediction {prediction_id} not found")
                return False
            
            # Создаем новую запись для рекомендаций
            recommendations_prediction = Prediction(
                user_id=prediction.user_id,
                profile_id=profile_id,  # Добавляем поддержку profile_id
                planet=Planet.moon,  # Рекомендации привязаны к Луне
                prediction_type=PredictionType.free,
                recommendations=recommendations,
                llm_model=llm_model,
                llm_tokens_used=tokens_used,
                llm_temperature=temperature,
                expires_at=None
            )
            
            session.add(recommendations_prediction)
            await session.commit()
            
            logger.info(f"Recommendations saved for prediction {prediction_id}, profile_id: {profile_id}")
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
                # [
                #     {
                #         "text": "🏠 Главное меню",
                #         "callback_data": "back_to_menu"
                #     }
                # ]
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
    
    def format_recommendations_message(self, recommendations: str, user_name: str, profile_name: Optional[str] = None) -> str:
        """Форматирует сообщение с рекомендациями"""
        
        # Адаптируем заголовок для дополнительного профиля или основного
        if profile_name:
            message = f"💡 Персональные рекомендации для {profile_name}\n\n"
        else:
            message = f"💡 Персональные рекомендации для {user_name}\n\n"
        
        message += recommendations
        
        return message
    
    async def process_recommendation(self, message_data: Dict[str, Any]):
        """Обрабатывает один запрос на рекомендации"""
        prediction_id = message_data.get("prediction_id")
        user_id = message_data.get("user_telegram_id")
        moon_analysis = message_data.get("moon_analysis")
        profile_id = message_data.get("profile_id")  # Новый параметр для дополнительных профилей
        
        if not prediction_id or not user_id or not moon_analysis:
            logger.error(f"Invalid message data: {message_data}")
            return
        
        logger.info(f"Processing recommendations for prediction {prediction_id}, user {user_id}, profile_id: {profile_id}")
        
        # Получаем информацию о пользователе
        user_info = await self.get_user_info(user_id)
        if not user_info:
            logger.error(f"User with telegram_id {user_id} not found")
            return
        
        # Генерируем рекомендации через OpenRouter (если доступен)
        if self.openrouter_client:
            # Определяем имя и пол для LLM в зависимости от типа профиля
            if profile_id:
                # Для дополнительного профиля получаем данные профиля
                profile_info = await self.get_additional_profile_info(profile_id)
                if not profile_info:
                    logger.error(f"Additional profile {profile_id} not found")
                    return
                llm_user_name = profile_info["full_name"] or "Друг"
                llm_user_gender = profile_info["gender"]
                logger.info(f"Using additional profile data for recommendations: {llm_user_name}, gender: {llm_user_gender}")
            else:
                # Для основного профиля используем данные пользователя
                llm_user_name = user_info["first_name"] or "Друг"
                llm_user_gender = user_info["gender"]
                logger.info(f"Using main user data for recommendations: {llm_user_name}, gender: {llm_user_gender}")
            
            llm_result = await self.openrouter_client.generate_recommendations(
                moon_analysis=moon_analysis,
                user_name=llm_user_name,
                user_gender=llm_user_gender
            )
            
            if not llm_result["success"]:
                logger.error(f"LLM generation failed: {llm_result['error']}")
                return
            
            # Сохраняем рекомендации в базу
            await self.save_recommendations(
                prediction_id=prediction_id,
                recommendations=llm_result["content"],
                llm_model=llm_result.get("model", "deepseek-chat-v3.1"),
                tokens_used=llm_result.get("usage", {}).get("total_tokens", 0),
                temperature=0.7,
                profile_id=profile_id
            )
            
            # Отправляем рекомендации пользователю
            try:
                # Определяем имя профиля для форматирования сообщения
                profile_name = None
                if profile_id and profile_info:
                    profile_name = profile_info["full_name"]
                
                message = self.format_recommendations_message(
                    recommendations=llm_result["content"],
                    user_name=user_info["first_name"] or "Друг",
                    profile_name=profile_name
                )
                
                success = await self.send_telegram_message(
                    chat_id=user_id,
                    text=message
                )
                
                if success:
                    logger.info(f"Recommendations sent to user {user_id}")
                else:
                    logger.error(f"Failed to send recommendations to user {user_id}")
                    
            except Exception as e:
                logger.error(f"Error sending recommendations to user: {e}")
        else:
            logger.info(f"LLM processing skipped for recommendations - no API key")
        
        logger.info(f"Recommendations for prediction {prediction_id} processed successfully")
    
    async def start_consuming(self):
        """Запускает потребление сообщений из очереди"""
        if not self.channel:
            raise RuntimeError("Worker not initialized")
        
        queue = await self.channel.declare_queue(QUEUE_NAME, durable=True)
        
        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    message_data = json.loads(message.body.decode())
                    await self.process_recommendation(message_data)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        
        await queue.consume(process_message)
        logger.info(f"Started consuming from queue {QUEUE_NAME}")
    
    async def stop(self):
        """Останавливает воркера"""
        if self.connection:
            await self.connection.close()
        logger.info("Recommendations worker stopped")


async def main():
    """Основная функция запуска воркера"""
    logger.info("Starting recommendations worker...")
    
    # Инициализируем подключение к БД
    init_engine()
    
    worker = RecommendationsWorker()
    
    try:
        await worker.initialize()
        await worker.start_consuming()
        
        # Держим воркера запущенным
        logger.info("Recommendations worker is running. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Worker error: {e}")
    finally:
        await worker.stop()
        await dispose_engine()
        logger.info("Recommendations worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
