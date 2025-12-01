"""
Воркер для генерации персональных рекомендаций на основе разбора Венеры.

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
from dotenv import load_dotenv
from sqlalchemy import select

from config import BOT_TOKEN
from db import get_session, init_engine, dispose_engine
from models import Prediction, User, Planet, PredictionType, AdditionalProfile

# Загружаем переменные окружения из .env файла
load_dotenv()

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
QUEUE_NAME = "venus_recommendations"
BOT_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Проверяем наличие API ключа
if not OPENROUTER_API_KEY:
    logger.warning(
        "OPENROUTER_API_KEY not set! LLM processing will be disabled."
    )

# Промпт для генерации рекомендаций по Венере
VENUS_RECOMMENDATIONS_PROMPT = """Дай {user_name} личные рекомендации для проработки Венеры и ее нормальной работы. Просто списком по пунктам, без воды. После списка напиши какие будут положительные результаты, если следовать этим рекомендациям (например, понимание гармоничных отношений для себя лично, своих блоков в отношениях и финансах, создание своего стиля в одежде, умение быть притягательным человеком и так далее).

ВАЖНО: Пиши ТОЛЬКО на русском языке! Никаких английских слов!

Учитывай пол пользователя при составлении рекомендаций - для женщин больше акцент на женственность и привлекательность, для мужчин - на понимание женской энергии и отношений.

Разбор Венеры:
{venus_analysis}

Имя: {user_name}
Пол: {user_gender}"""


class OpenRouterClient:
    """Клиент для работы с OpenRouter API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = OPENROUTER_URL
    
    async def generate_venus_recommendations(
        self,
        venus_analysis: str,
        user_name: str,
        user_gender: str,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Генерирует рекомендации по Венере через OpenRouter
        
        Args:
            venus_analysis: Разбор Венеры пользователя
            user_name: Имя пользователя
            user_gender: Пол пользователя
            max_retries: Максимальное количество попыток
            
        Returns:
            Dict с результатом генерации
        """
        # Логируем данные, которые отправляем в LLM
        logger.info(
            f"Venus Recommendations LLM Input - User: {user_name}, "
            f"Gender: {user_gender}"
        )
        logger.info(
            f"Venus Recommendations LLM Input - Venus analysis length: "
            f"{len(venus_analysis)} characters"
        )
        logger.info(
            f"Venus Recommendations LLM Input - Venus analysis preview: "
            f"{venus_analysis[:300]}..."
        )
        
        prompt = VENUS_RECOMMENDATIONS_PROMPT.format(
            venus_analysis=venus_analysis,
            user_name=user_name,
            user_gender=user_gender
        )
        
        logger.info(
            f"Venus Recommendations LLM Input - Full prompt length: "
            f"{len(prompt)} characters"
        )
        
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
        
        # Retry логика
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=300, connect=30, sock_read=270)
                ) as session:
                    async with session.post(
                        self.url,
                        headers=headers,
                        json=payload
                    ) as response:
                        if response.status == 200:
                            # Читаем ответ полностью
                            response_text = await response.text()
                            try:
                                result = json.loads(response_text)
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse JSON response (attempt {attempt + 1}): {e}")
                                logger.error(f"Response text: {response_text[:500]}...")
                                if attempt == max_retries - 1:
                                    return {
                                        "success": False,
                                        "error": f"Invalid JSON response: {e}"
                                    }
                                continue
                            
                            logger.info(
                                f"OpenRouter venus recommendations response "
                                f"received for {user_name} (attempt {attempt + 1})"
                            )
                            return {
                                "success": True,
                                "content": result["choices"][0]["message"]["content"],
                                "usage": result.get("usage", {}),
                                "model": result.get("model", "unknown")
                            }
                        else:
                            error_text = await response.text()
                            logger.error(f"OpenRouter error {response.status} (attempt {attempt + 1}): {error_text}")
                            if attempt == max_retries - 1:
                                return {
                                    "success": False,
                                    "error": f"API error: {response.status} - {error_text}"
                                }
                            # Ждем перед повтором
                            await asyncio.sleep(2 ** attempt)
                            
            except asyncio.TimeoutError:
                logger.error(f"OpenRouter request timeout (attempt {attempt + 1})")
                if attempt == max_retries - 1:
                    return {
                        "success": False,
                        "error": "Request timeout"
                    }
                # Ждем перед повтором
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"OpenRouter request failed (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return {
                        "success": False,
                        "error": str(e)
                    }
                # Ждем перед повтором
                await asyncio.sleep(2 ** attempt)
        
        # Если все попытки исчерпаны
        return {
            "success": False,
            "error": f"All {max_retries} attempts failed"
        }


class VenusRecommendationsWorker:
    """Воркер для обработки рекомендаций по Венере"""
    
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
        
        logger.info("Venus recommendations worker initialized successfully")
    
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
    
    async def save_venus_recommendations(
        self, 
        prediction_id: int, 
        recommendations: str,
        llm_model: str,
        tokens_used: int,
        temperature: float = 0.7,
        profile_id: Optional[int] = None
    ) -> bool:
        """Сохраняет рекомендации по Венере в базу данных"""
        async with get_session() as session:
            # Находим исходное предсказание
            result = await session.execute(
                select(Prediction).where(Prediction.prediction_id == prediction_id)
            )
            prediction = result.scalar_one_or_none()
            
            if not prediction:
                logger.error(f"Prediction {prediction_id} not found")
                return False
            
            # Создаем новую запись для рекомендаций по Венере
            recommendations_prediction = Prediction(
                user_id=prediction.user_id,
                planet=Planet.venus,  # Рекомендации привязаны к Венере
                prediction_type=PredictionType.paid,  # Платные рекомендации
                recommendations=recommendations,
                llm_model=llm_model,
                llm_tokens_used=tokens_used,
                llm_temperature=temperature,
                expires_at=prediction.expires_at,  # Наследуем срок действия от основного предсказания
                profile_id=profile_id  # Добавляем поддержку дополнительных профилей
            )
            
            session.add(recommendations_prediction)
            await session.commit()
            
            logger.info(f"Venus recommendations saved for prediction {prediction_id}")
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
    
    def format_venus_recommendations_message(self, recommendations: str, user_name: str, profile_name: Optional[str] = None) -> str:
        """Форматирует сообщение с рекомендациями по Венере"""
        
        if profile_name:
            message = f"♀️ Персональные рекомендации по Венере для {profile_name}\n\n"
        else:
            message = f"♀️ Персональные рекомендации по Венере для {user_name}\n\n"
        
        message += recommendations
        
        return message
    
    async def process_venus_recommendation(self, message_data: Dict[str, Any]):
        """Обрабатывает один запрос на рекомендации по Венере"""
        prediction_id = message_data.get("prediction_id")
        user_id = message_data.get("user_telegram_id")
        venus_analysis = message_data.get("venus_analysis")
        profile_id = message_data.get("profile_id")
        
        if not prediction_id or not user_id or not venus_analysis:
            logger.error(f"Invalid message data: {message_data}")
            return
        
        logger.info(f"Processing venus recommendations for prediction {prediction_id}, user {user_id}, profile_id: {profile_id}")
        
        # Определяем данные для LLM в зависимости от типа профиля
        if profile_id:
            profile_info = await self.get_additional_profile_info(profile_id)
            if not profile_info:
                logger.error(f"Additional profile {profile_id} not found")
                return
            llm_user_name = profile_info["full_name"] or "Друг"
            llm_user_gender = profile_info["gender"]
            logger.info(f"Using additional profile data for recommendations: {llm_user_name}, gender: {llm_user_gender}")
        else:
            user_info = await self.get_user_info(user_id)
            if not user_info:
                logger.error(f"User with telegram_id {user_id} not found")
                return
            llm_user_name = user_info["first_name"] or "Друг"
            llm_user_gender = user_info["gender"]
            logger.info(f"Using main user data for recommendations: {llm_user_name}, gender: {llm_user_gender}")
        
        # Генерируем рекомендации через OpenRouter (если доступен)
        if self.openrouter_client:
            llm_result = await self.openrouter_client.generate_venus_recommendations(
                venus_analysis=venus_analysis,
                user_name=llm_user_name,
                user_gender=llm_user_gender
            )
            
            if not llm_result["success"]:
                logger.error(f"LLM generation failed: {llm_result['error']}")
                return
            
            # Сохраняем рекомендации в базу
            await self.save_venus_recommendations(
                prediction_id=prediction_id,
                recommendations=llm_result["content"],
                llm_model=llm_result.get("model", "deepseek-chat-v3.1"),
                tokens_used=llm_result.get("usage", {}).get("total_tokens", 0),
                temperature=0.7,
                profile_id=profile_id
            )
            
            # Отправляем рекомендации пользователю
            try:
                # Определяем имя для сообщения
                profile_name = None
                if profile_id:
                    # Для дополнительного профиля используем имя профиля
                    profile_name = llm_user_name
                
                message = self.format_venus_recommendations_message(
                    recommendations=llm_result["content"],
                    user_name=llm_user_name,
                    profile_name=profile_name
                )
                
                success = await self.send_telegram_message(
                    chat_id=user_id,
                    text=message
                )
                
                if success:
                    logger.info(f"Venus recommendations sent to user {user_id}")
                else:
                    logger.error(f"Failed to send venus recommendations to user {user_id}")
                    
            except Exception as e:
                logger.error(f"Error sending venus recommendations to user: {e}")
        else:
            logger.info("LLM processing skipped for venus recommendations - no API key")
        
        logger.info(f"Venus recommendations for prediction {prediction_id} processed successfully")
    
    async def start_consuming(self):
        """Запускает потребление сообщений из очереди"""
        if not self.channel:
            raise RuntimeError("Worker not initialized")
        
        queue = await self.channel.declare_queue(QUEUE_NAME, durable=True)
        
        async def process_message(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    message_data = json.loads(message.body.decode())
                    await self.process_venus_recommendation(message_data)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        
        await queue.consume(process_message)
        logger.info(f"Started consuming from queue {QUEUE_NAME}")
    
    async def stop(self):
        """Останавливает воркера"""
        if self.connection:
            await self.connection.close()
        logger.info("Venus recommendations worker stopped")


async def main():
    """Основная функция запуска воркера"""
    logger.info("Starting venus recommendations worker...")
    
    # Инициализируем подключение к БД
    init_engine()
    
    worker = VenusRecommendationsWorker()
    
    try:
        await worker.initialize()
        await worker.start_consuming()
        
        # Держим воркера запущенным
        logger.info("Venus recommendations worker is running. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Worker error: {e}")
    finally:
        await worker.stop()
        dispose_engine()
        logger.info("Venus recommendations worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())