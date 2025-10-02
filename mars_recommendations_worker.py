"""
Воркер для генерации персональных рекомендаций на основе разбора Марса.

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
from models import Prediction, User, Planet, PredictionType

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
QUEUE_NAME = "mars_recommendations"
BOT_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Проверяем наличие API ключа
if not OPENROUTER_API_KEY:
    logger.warning(
        "OPENROUTER_API_KEY not set! LLM processing will be disabled."
    )

# Промпт для генерации рекомендаций по Марсу
MARS_RECOMMENDATIONS_PROMPT = """Дай {user_name} личные рекомендации для проработки Марса и его нормальной работы. Просто списком по пунктам, без воды. После списка напиши какие будут положительные результаты, если следовать этим рекомендациям (например, умение защищать свои интересы, уходит прокрастинация, выбор подходящего вида спорта, умение держать мотивацию и так далее)

ВАЖНО: Пиши ТОЛЬКО на русском языке! Никаких английских слов!

Разбор Марса:
{mars_analysis}

Имя: {user_name}
Пол: {user_gender}"""


class OpenRouterClient:
    """Клиент для работы с OpenRouter API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = OPENROUTER_URL
    
    async def generate_mars_recommendations(
        self,
        mars_analysis: str,
        user_name: str,
        user_gender: str
    ) -> Dict[str, Any]:
        """
        Генерирует рекомендации по Марсу через OpenRouter
        
        Args:
            mars_analysis: Разбор Марса для генерации рекомендаций
            user_name: Имя пользователя
            user_gender: Пол пользователя
            
        Returns:
            Dict с результатом генерации
        """
        # Логируем данные, которые отправляем в LLM
        logger.info(f"♂️ LLM Input - User: {user_name}, Gender: {user_gender}")
        logger.info(f"♂️ LLM Input - Mars analysis length: {len(mars_analysis)} characters")
        logger.info(f"♂️ LLM Input - Mars analysis preview: {mars_analysis[:500]}...")
        
        prompt = MARS_RECOMMENDATIONS_PROMPT.format(
            mars_analysis=mars_analysis,
            user_name=user_name,
            user_gender=user_gender
        )
        
        logger.info(f"♂️ LLM Input - Full prompt length: {len(prompt)} characters")
        
        payload = {
            "model": "deepseek/deepseek-chat-v3.1:free",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 2000,
            "temperature": 0.7
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://astro-bot.com",
            "X-Title": "Astro Bot"
        }
        
        async with aiohttp.ClientSession() as session:
            max_retries = 3
            retry_delays = [2, 4, 8]  # Exponential backoff delays
            
            for attempt in range(max_retries):
                try:
                    logger.info(f"♂️ Sending Mars recommendations request to OpenRouter for {user_name} (attempt {attempt + 1}/{max_retries})...")
                    start_time = asyncio.get_event_loop().time()
                    
                    async with session.post(
                        self.url,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=300, connect=30, sock_read=270)
                    ) as response:
                        end_time = asyncio.get_event_loop().time()
                        logger.info(f"♂️ OpenRouter response time: {end_time - start_time:.2f}s")
                        
                        if response.status == 200:
                            # Читаем ответ полностью
                            response_text = await response.text()
                            try:
                                result = json.loads(response_text)
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse JSON response: {e}")
                                logger.error(f"Response text: {response_text[:500]}...")
                                return {
                                    "success": False,
                                    "error": f"Invalid JSON response: {e}"
                                }
                            
                            logger.info(f"♂️ OpenRouter response received for {user_name}")
                            return {
                                "success": True,
                                "content": result["choices"][0]["message"]["content"],
                                "usage": result.get("usage", {}),
                                "model": result.get("model", "unknown")
                            }
                        elif response.status == 429:
                            # Rate limiting - try again with delay
                            if attempt < max_retries - 1:
                                delay = retry_delays[attempt]
                                logger.warning(f"♂️ Rate limited (429), retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                                await asyncio.sleep(delay)
                                continue
                            else:
                                error_text = await response.text()
                                logger.error(f"♂️ Final rate limit error: {error_text}")
                                return {
                                    "success": False,
                                    "error": f"Rate limit exceeded after {max_retries} attempts"
                                }
                        else:
                            error_text = await response.text()
                            logger.error(f"♂️ OpenRouter error {response.status}: {error_text}")
                            return {
                                "success": False,
                                "error": f"API error: {response.status} - {error_text}"
                            }
                            
                except asyncio.TimeoutError:
                    if attempt < max_retries - 1:
                        delay = retry_delays[attempt]
                        logger.warning(f"♂️ Request timeout, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"♂️ Final timeout after all retry attempts for {user_name}")
                        return {
                            "success": False,
                            "error": "Request timeout after retries"
                        }
                except Exception as e:
                    if attempt < max_retries - 1:
                        delay = retry_delays[attempt]
                        logger.warning(f"♂️ Request failed: {e}, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"♂️ Final error after all retry attempts for {user_name}: {e}")
                        return {
                            "success": False,
                            "error": str(e)
                        }


async def process_mars_recommendations(
    data: Dict[str, Any],
    openrouter_client: Optional[OpenRouterClient] = None
) -> bool:
    """
    Обрабатывает запрос на рекомендации по Марсу
    
    Args:
        data: Данные для обработки
        openrouter_client: Клиент OpenRouter (опционально)
    
    Returns:
        bool: True если обработка успешна, False иначе
    """
    try:
        prediction_id = data.get("prediction_id")
        user_telegram_id = data.get("user_telegram_id")
        mars_analysis = data.get("mars_analysis")
        
        if not prediction_id or not user_telegram_id or not mars_analysis:
            logger.error(f"♂️ Missing required data: prediction_id={prediction_id}, user_telegram_id={user_telegram_id}, mars_analysis={'present' if mars_analysis else 'missing'}")
            return False
        
        logger.info(f"♂️ Processing Mars recommendations for prediction {prediction_id}, user {user_telegram_id}")
        
        async with get_session() as session:
            # Получаем предсказание
            result = await session.execute(
                select(Prediction).where(Prediction.prediction_id == prediction_id)
            )
            prediction = result.scalar_one_or_none()
            
            if not prediction:
                logger.error(f"♂️ Prediction {prediction_id} not found")
                return False
            
            # Получаем пользователя по telegram_id
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_telegram_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                logger.error(f"♂️ User with telegram_id {user_telegram_id} not found")
                return False
            
            logger.info(f"♂️ Found user: {user.first_name} (telegram_id: {user.telegram_id})")
            
            # Если нет клиента OpenRouter, создаем тестовые рекомендации
            if not openrouter_client or not OPENROUTER_API_KEY:
                logger.warning("♂️ OpenRouter not available, creating test recommendations")
                recommendations_content = f"""🔥 Тестовые рекомендации по Марсу для {user.first_name}

• Занимайся спортом минимум 3 раза в неделю
• Учись говорить "нет" и защищать свои границы
• Ставь четкие цели и разбивай их на шаги
• Практикуй медитацию для контроля агрессии
• Выбери вид спорта, который тебе нравится

✨ РЕЗУЛЬТАТЫ:
Если будешь следовать этим рекомендациям, ты получишь: умение защищать свои интересы, уходит прокрастинация, выбор подходящего вида спорта, умение держать мотивацию."""
                
                # Сохраняем результат
                prediction.recommendations = recommendations_content
                await session.commit()
                
                # Отправляем пользователю
                await send_mars_recommendations_to_user(user.telegram_id, recommendations_content)
                logger.info(f"♂️ Test Mars recommendations sent to user {user.telegram_id}")
                
                return True
            
            # Генерируем рекомендации через OpenRouter
            llm_result = await openrouter_client.generate_mars_recommendations(
                mars_analysis=mars_analysis,
                user_name=user.first_name or "Друг",
                user_gender=user.gender or "не указан"
            )
            
            if llm_result["success"]:
                # Сохраняем результат
                prediction.recommendations = llm_result["content"]
                await session.commit()
                
                # Отправляем пользователю
                await send_mars_recommendations_to_user(user.telegram_id, llm_result["content"])
                
                logger.info(f"♂️ Mars recommendations generated and sent to user {user.telegram_id}")
                logger.info(f"♂️ LLM usage: {llm_result.get('usage', 'No usage data')}")
                
                return True
            else:
                logger.error(f"♂️ Failed to generate Mars recommendations: {llm_result['error']}")
                
                # Отправляем сообщение об ошибке
                error_message = (
                    "❌ Произошла ошибка при генерации рекомендаций по Марсу.\n"
                    "Мы уже работаем над исправлением. Попробуйте позже."
                )
                await send_mars_recommendations_to_user(user.telegram_id, error_message)
                return False
                
    except Exception as e:
        logger.error(f"♂️ Error processing Mars recommendations: {e}")
        return False


async def send_mars_recommendations_to_user(user_telegram_id: int, recommendations_text: str):
    """
    Отправляет рекомендации по Марсу пользователю через Telegram Bot API
    
    Args:
        user_telegram_id: Telegram ID пользователя
        recommendations_text: Текст рекомендаций
    """
    try:
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
        
        # Разбиваем длинный текст на части если нужно
        max_length = 4000  # Лимит Telegram для одного сообщения
        
        if len(recommendations_text) <= max_length:
            # Отправляем одним сообщением
            payload = {
                "chat_id": user_telegram_id,
                "text": recommendations_text,
                "reply_markup": keyboard,
                "parse_mode": "HTML"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{BOT_API_URL}/sendMessage",
                    json=payload
                ) as response:
                    if response.status == 200:
                        logger.info(f"♂️ Mars recommendations sent to user {user_telegram_id}")
                    else:
                        error_text = await response.text()
                        logger.error(f"♂️ Failed to send Mars recommendations to user {user_telegram_id}: {error_text}")
        else:
            # Разбиваем на части
            parts = []
            for i in range(0, len(recommendations_text), max_length):
                parts.append(recommendations_text[i:i+max_length])
            
            # Отправляем первые части без кнопок
            for i, part in enumerate(parts[:-1]):
                payload = {
                    "chat_id": user_telegram_id,
                    "text": part,
                    "parse_mode": "HTML"
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{BOT_API_URL}/sendMessage",
                        json=payload
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"♂️ Failed to send Mars recommendations part {i+1} to user {user_telegram_id}: {error_text}")
            
            # Отправляем последнюю часть с кнопками
            payload = {
                "chat_id": user_telegram_id,
                "text": parts[-1],
                "reply_markup": keyboard,
                "parse_mode": "HTML"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{BOT_API_URL}/sendMessage",
                    json=payload
                ) as response:
                    if response.status == 200:
                        logger.info(f"♂️ Mars recommendations sent to user {user_telegram_id}")
                    else:
                        error_text = await response.text()
                        logger.error(f"♂️ Failed to send final Mars recommendations part to user {user_telegram_id}: {error_text}")
                        
    except Exception as e:
        logger.error(f"♂️ Error sending Mars recommendations to user {user_telegram_id}: {e}")


async def main():
    """Основная функция воркера"""
    logger.info("♂️ Starting Mars recommendations worker...")
    
    # Инициализируем движок БД
    init_engine()
    
    # Создаем клиент OpenRouter если есть API ключ
    openrouter_client = None
    if OPENROUTER_API_KEY:
        openrouter_client = OpenRouterClient(OPENROUTER_API_KEY)
        logger.info("♂️ OpenRouter client initialized")
    else:
        logger.warning("♂️ OpenRouter API key not found, using test mode")
    
    try:
        # Подключаемся к RabbitMQ
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()
        
        # Объявляем очередь
        queue = await channel.declare_queue(QUEUE_NAME, durable=True)
        
        logger.info(f"♂️ Connected to RabbitMQ, queue: {QUEUE_NAME}")
        
        async def process_message(message: aio_pika.abc.AbstractIncomingMessage):
            async with message.process():
                try:
                    data = json.loads(message.body)
                    logger.info(f"♂️ Received message: {data}")
                    
                    # Обрабатываем рекомендации
                    success = await process_mars_recommendations(data, openrouter_client)
                    
                    if success:
                        logger.info(f"♂️ Mars recommendations processed successfully")
                    else:
                        logger.error(f"♂️ Failed to process Mars recommendations")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"♂️ Failed to decode message: {e}")
                except Exception as e:
                    logger.error(f"♂️ Error processing message: {e}")
        
        # Настраиваем обработку сообщений
        await queue.consume(process_message)
        
        logger.info("♂️ Mars recommendations worker is ready. Waiting for messages...")
        
        # Ожидаем сообщения
        try:
            await asyncio.Future()  # Бесконечное ожидание
        except KeyboardInterrupt:
            logger.info("♂️ Mars recommendations worker stopped by user")
        
    except Exception as e:
        logger.error(f"♂️ Mars recommendations worker error: {e}")
    finally:
        # Закрываем соединение с БД
        dispose_engine()
        logger.info("♂️ Mars recommendations worker finished")


if __name__ == "__main__":
    asyncio.run(main())
