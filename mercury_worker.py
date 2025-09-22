"""
Воркер для обработки астрологических разборов Меркурия через RabbitMQ.

Получает данные из очереди, отправляет в OpenRouter для анализа,
обновляет предсказание в базе данных и сразу отправляет пользователю.
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
from config import BOT_TOKEN

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://astro_user:astro_password_123@31.128.40.111:5672/")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
QUEUE_NAME = "mercury_predictions"
BOT_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Проверяем наличие API ключа
if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY not set! LLM processing will be disabled.")

# Промпт для анализа Меркурия
MERCURY_ANALYSIS_PROMPT = """Ты астролог с опытом 10 лет, который делает разбор Меркурия по знаку, дому и аспектам. Не говори об этом формально, не указывай сухую астрологическую информацию — выдай разбор так, как будто ты смотришь прямо в душу. Твоя задача — дать разбор, который вызовет у человека ощущение: "Это как будто написано про меня". Чтобы захотелось продолжить разбор дальше, потому что откликнулись боли, вопросы и стало интересно — а что дальше? У КОГО? Меркурий в ЗНАКЕ, В ДОМЕ, + АСПЕКТЫ. Без лишних слов сразу переходи к характеристике по данным вопросам:
Как человек воспринимает и обрабатывает информацию? Его мышление и аналитические способности
Насколько человек легко и эффективно выражает свои мысли?
Как человек усваивает новые знания, как обучается наиболее эффективно?
Речь человека, как он общается?
Как человек заводит новые контакты? умение вести дела, заключать сделки, договариваться?
Есть ли потенциал в блогерстве и как он может проявиться?
Пиши не как нейтральный психолог, а как близкий друг, который видит суть и не боится говорить честно. Стиль — живой, человеческий, прямой. Ты можешь быть и жёстким, если это поможет человеку очнуться. Но без морали. Не используй заголовки и пункты, пиши одним цельным текстом. Твоя цель — создать ощущение полного узнавания. Используй разговорный стиль без канцеляризмов. Опиши, как это проявляется в повседневной жизни: в реакциях, привычках, мелочах. Обращайся к человеку по имени. Сделай разбор строго до 2500 символов, не больше.

Данные: {astrology_data}
Имя: {user_name}
Пол: {user_gender}"""


class OpenRouterClient:
    """Клиент для работы с OpenRouter API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = OPENROUTER_URL
    
    async def generate_mercury_analysis(
        self, 
        astrology_data: str, 
        user_name: str, 
        user_gender: str
    ) -> Dict[str, Any]:
        """
        Генерирует анализ Меркурия через OpenRouter
        
        Args:
            astrology_data: Данные астрологии для анализа
            user_name: Имя пользователя
            user_gender: Пол пользователя
            
        Returns:
            Dict с результатом генерации
        """
        # Логируем данные, которые отправляем в LLM
        logger.info(f"LLM Input - User: {user_name}, Gender: {user_gender}")
        logger.info(f"LLM Input - Astrology data length: {len(astrology_data)} characters")
        logger.info(f"LLM Input - Astrology data preview: {astrology_data[:500]}...")
        
        prompt = MERCURY_ANALYSIS_PROMPT.format(
            astrology_data=astrology_data,
            user_name=user_name,
            user_gender=user_gender
        )
        
        logger.info(f"LLM Input - Full prompt length: {len(prompt)} characters")
        
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
            try:
                logger.info(f"☿️ Sending Mercury request to OpenRouter for {user_name}...")
                start_time = asyncio.get_event_loop().time()
                
                async with session.post(
                    self.url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=180)
                ) as response:
                    end_time = asyncio.get_event_loop().time()
                    logger.info(f"☿️ OpenRouter response time: {end_time - start_time:.2f}s")
                    
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"☿️ OpenRouter response received for {user_name}")
                        return {
                            "success": True,
                            "content": result["choices"][0]["message"]["content"],
                            "usage": result.get("usage", {}),
                            "model": result.get("model", "unknown")
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"☿️ OpenRouter error {response.status}: {error_text}")
                        return {
                            "success": False,
                            "error": f"API error: {response.status} - {error_text}"
                        }
                        
            except asyncio.TimeoutError:
                logger.error(f"☿️ OpenRouter request timeout for {user_name}")
                return {
                    "success": False,
                    "error": "Request timeout - try again later"
                }
            except Exception as e:
                logger.error(f"☿️ OpenRouter error for {user_name}: {e}")
                return {
                    "success": False,
                    "error": f"Request failed: {str(e)}"
                }


async def process_mercury_prediction(
    data: Dict[str, Any],
    openrouter_client: Optional[OpenRouterClient] = None
) -> bool:
    """
    Обрабатывает одно предсказание Меркурия
    
    Args:
        data: Данные для обработки
        openrouter_client: Клиент OpenRouter (опционально)
    
    Returns:
        bool: True если обработка успешна, False иначе
    """
    try:
        prediction_id = data.get("prediction_id")
        user_telegram_id = data.get("user_telegram_id")
        
        if not prediction_id or not user_telegram_id:
            logger.error(f"☿️ Missing required data: prediction_id={prediction_id}, user_telegram_id={user_telegram_id}")
            return False
        
        logger.info(f"☿️ Processing Mercury prediction {prediction_id} for user {user_telegram_id}")
        
        async with get_session() as session:
            # Получаем предсказание
            result = await session.execute(
                select(Prediction).where(Prediction.prediction_id == prediction_id)
            )
            prediction = result.scalar_one_or_none()
            
            if not prediction:
                logger.error(f"☿️ Prediction {prediction_id} not found")
                return False
            
            # Получаем пользователя
            user_result = await session.execute(
                select(User).where(User.user_id == prediction.user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                logger.error(f"☿️ User not found for prediction {prediction_id}")
                return False
            
            logger.info(f"☿️ Found user: {user.first_name} (telegram_id: {user.telegram_id})")
            
            # Если нет клиента OpenRouter, создаем тестовый разбор
            if not openrouter_client or not OPENROUTER_API_KEY:
                logger.warning("☿️ OpenRouter not available, creating test analysis")
                analysis_content = f"""☿️ Тестовый разбор Меркурия для {user.first_name}

Привет, {user.first_name}! 

Твой Меркурий показывает уникальные особенности твоего мышления и общения:

🧠 **Стиль мышления**: Ты обрабатываешь информацию по-особенному, и это твоя суперсила.

💬 **Общение**: У тебя есть свой неповторимый способ выражать мысли.

📚 **Обучение**: Знания усваиваются у тебя определенным образом - важно это учитывать.

🤝 **Переговоры**: Ты можешь быть очень убедительным, когда понимаешь свои сильные стороны.

Это тестовый разбор. После оплаты ты получишь персональный анализ на основе точных астрологических данных!"""
                
                # Сохраняем результат
                prediction.mercury_analysis = analysis_content
                prediction.status = "completed"
                await session.commit()
                
                # Отправляем пользователю
                await send_mercury_analysis_to_user(user.telegram_id, analysis_content)
                logger.info(f"☿️ Test Mercury analysis sent to user {user.telegram_id}")
                return True
            
            # Генерируем разбор через OpenRouter
            astrology_data = prediction.astrology_data or "Нет данных астрологии"
            
            llm_result = await openrouter_client.generate_mercury_analysis(
                astrology_data=astrology_data,
                user_name=user.first_name or "Друг",
                user_gender=user.gender or "не указан"
            )
            
            if llm_result["success"]:
                # Сохраняем результат
                prediction.mercury_analysis = llm_result["content"]
                prediction.status = "completed"
                await session.commit()
                
                # Отправляем пользователю
                await send_mercury_analysis_to_user(user.telegram_id, llm_result["content"])
                
                logger.info(f"☿️ Mercury analysis generated and sent to user {user.telegram_id}")
                logger.info(f"☿️ LLM usage: {llm_result.get('usage', 'No usage data')}")
                return True
            else:
                logger.error(f"☿️ Failed to generate Mercury analysis: {llm_result['error']}")
                
                # Обновляем статус на ошибку
                prediction.status = "error"
                await session.commit()
                
                # Отправляем сообщение об ошибке
                error_message = (
                    "❌ Произошла ошибка при генерации разбора Меркурия.\n"
                    "Мы уже работаем над исправлением. Попробуйте позже."
                )
                await send_mercury_analysis_to_user(user.telegram_id, error_message)
                return False
                
    except Exception as e:
        logger.error(f"☿️ Error processing Mercury prediction: {e}")
        return False


async def send_mercury_analysis_to_user(user_telegram_id: int, analysis_text: str):
    """
    Отправляет анализ Меркурия пользователю через Telegram Bot API
    
    Args:
        user_telegram_id: Telegram ID пользователя
        analysis_text: Текст анализа
    """
    try:
        # Подготавливаем кнопки после разбора Меркурия
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "💡 Получить рекомендации",
                        "callback_data": "get_mercury_recommendations"
                    }
                ],
                [
                    {
                        "text": "❓ Задать вопрос",
                        "callback_data": "ask_mercury_question"
                    }
                ],
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
        
        if len(analysis_text) <= max_length:
            # Отправляем одним сообщением
            payload = {
                "chat_id": user_telegram_id,
                "text": analysis_text,
                "reply_markup": keyboard,
                "parse_mode": "HTML"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{BOT_API_URL}/sendMessage",
                    json=payload
                ) as response:
                    if response.status == 200:
                        logger.info(f"☿️ Mercury analysis sent to user {user_telegram_id}")
                    else:
                        error_text = await response.text()
                        logger.error(f"☿️ Failed to send Mercury analysis to user {user_telegram_id}: {error_text}")
        else:
            # Разбиваем на части
            parts = []
            for i in range(0, len(analysis_text), max_length):
                parts.append(analysis_text[i:i+max_length])
            
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
                            logger.error(f"☿️ Failed to send Mercury analysis part {i+1} to user {user_telegram_id}: {error_text}")
            
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
                        logger.info(f"☿️ Mercury analysis sent to user {user_telegram_id}")
                    else:
                        error_text = await response.text()
                        logger.error(f"☿️ Failed to send final Mercury analysis part to user {user_telegram_id}: {error_text}")
                        
    except Exception as e:
        logger.error(f"☿️ Error sending Mercury analysis to user {user_telegram_id}: {e}")


async def main():
    """Основная функция воркера"""
    logger.info("☿️ Starting Mercury predictions worker...")
    
    # Инициализируем движок БД
    init_engine()
    
    # Создаем клиент OpenRouter если есть API ключ
    openrouter_client = None
    if OPENROUTER_API_KEY:
        openrouter_client = OpenRouterClient(OPENROUTER_API_KEY)
        logger.info("☿️ OpenRouter client initialized")
    else:
        logger.warning("☿️ OpenRouter API key not found, using test mode")
    
    try:
        # Подключаемся к RabbitMQ
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()
        
        # Объявляем очередь
        queue = await channel.declare_queue(QUEUE_NAME, durable=True)
        
        logger.info(f"☿️ Connected to RabbitMQ, queue: {QUEUE_NAME}")
        
        async def process_message(message: aio_pika.abc.AbstractIncomingMessage):
            async with message.process():
                try:
                    data = json.loads(message.body)
                    logger.info(f"☿️ Received message: {data}")
                    
                    # Обрабатываем предсказание
                    success = await process_mercury_prediction(data, openrouter_client)
                    
                    if success:
                        logger.info(f"☿️ Mercury prediction processed successfully")
                    else:
                        logger.error(f"☿️ Failed to process Mercury prediction")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"☿️ Failed to decode message: {e}")
                except Exception as e:
                    logger.error(f"☿️ Error processing message: {e}")
        
        # Настраиваем обработку сообщений
        await queue.consume(process_message)
        
        logger.info("☿️ Mercury worker is ready. Waiting for messages...")
        
        # Ожидаем сообщения
        try:
            await asyncio.Future()  # Бесконечное ожидание
        except KeyboardInterrupt:
            logger.info("☿️ Mercury worker stopped by user")
        
    except Exception as e:
        logger.error(f"☿️ Mercury worker error: {e}")
    finally:
        # Закрываем соединение с БД
        dispose_engine()
        logger.info("☿️ Mercury worker finished")


if __name__ == "__main__":
    asyncio.run(main())