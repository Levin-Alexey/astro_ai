"""
Воркер для обработки астрологических предсказаний Солнца через RabbitMQ.

Получает данные из очереди, отправляет в OpenRouter для анализа,
обновляет предсказание в базе данных и сразу отправляет пользователю.
"""

import asyncio
import json
import logging
import os
import time
import random
from datetime import datetime
from typing import Dict, Any, Optional

import aio_pika
import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

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
QUEUE_NAME = "sun_predictions"
BOT_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Проверяем наличие API ключа
if not OPENROUTER_API_KEY:
    logger.warning("OPENROUTER_API_KEY not set! LLM processing will be disabled.")

# Промпт для анализа Солнца
SUN_ANALYSIS_PROMPT = """Ты астролог с опытом 10 лет, который делает разбор Солнца по знаку, дому и аспектам. Не говори об этом формально, не указывай сухую астрологическую информацию — выдай разбор так, как будто ты смотришь прямо в душу. Твоя задача — дать разбор, который вызовет у человека ощущение: "Это как будто написано про меня". Чтобы захотелось продолжить разбор дальше, потому что откликнулись боли, вопросы и стало интересно — а что дальше? У КОГО? Солнце в ЗНАКЕ, В ДОМЕ, + АСПЕКТЫ. Без лишних слов сразу переходи к характеристике по данным вопросам: 
1.	Жизненная энергия и активность, как проявляются? 
2.	От чего светятся мои глаза? 
3.	Как человек проявляет себя в мире? Какие у него уникальные таланты и способности? 
4.	Характер человека в плюсе и минусе 
5.	Самооценка человека и от чего она зависит? 
6.	Какая у человека задача по жизни? 
7.	Как человеку проявлять свою уникальность и индивидуальность? Через что? Какая в нем есть уникальность? что делает его особенным и отличным от других? 
8.	Жизненные цели и амбиции, к чему человек стремится и что для него важно в жизни? 
9.	Способность человека вести за собой других и быть влиятельным, как это проявляется? 
10.	Насколько человек способен принимать решения и следовать своим целям? 
11.	Если это женщина - какого мужчину я вижу в качестве своего мужа? 
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
    
    async def generate_sun_analysis(
        self, 
        astrology_data: str, 
        user_name: str, 
        user_gender: str
    ) -> Dict[str, Any]:
        """
        Генерирует анализ Солнца через OpenRouter
        
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
        
        prompt = SUN_ANALYSIS_PROMPT.format(
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
            max_retries = 3
            retry_delays = [2, 4, 8]  # Exponential backoff delays
            
            for attempt in range(max_retries):
                try:
                    async with session.post(
                        self.url,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=120)
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
                        elif response.status == 429:
                            # Rate limiting - try again with delay
                            if attempt < max_retries - 1:
                                delay = retry_delays[attempt]
                                logger.warning(f"Rate limited (429), retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                                await asyncio.sleep(delay)
                                continue
                            else:
                                error_text = await response.text()
                                logger.error(f"Final rate limit error: {error_text}")
                                return {
                                    "success": False,
                                    "error": f"Rate limit exceeded after {max_retries} attempts"
                                }
                        else:
                            error_text = await response.text()
                            logger.error(f"OpenRouter error {response.status}: {error_text}")
                            return {
                                "success": False,
                                "error": f"API error: {response.status} - {error_text}"
                            }
                            
                except asyncio.TimeoutError:
                    if attempt < max_retries - 1:
                        delay = retry_delays[attempt]
                        logger.warning(f"Request timeout, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error("Final timeout after all retry attempts")
                        return {
                            "success": False,
                            "error": "Request timeout after retries"
                        }
                except Exception as e:
                    if attempt < max_retries - 1:
                        delay = retry_delays[attempt]
                        logger.warning(f"Request failed: {e}, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"Final error after all retry attempts: {e}")
                        return {
                            "success": False,
                            "error": str(e)
                        }


class SunWorker:
    """Воркер для обработки предсказаний Солнца"""
    
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
        
        logger.info("Sun worker initialized successfully")
    
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
    
    async def update_prediction(
        self, 
        prediction_id: int, 
        llm_content: str, 
        llm_model: str,
        tokens_used: int,
        temperature: float = 0.7
    ) -> bool:
        """Обновляет предсказание с результатом LLM в столбец sun_analysis"""
        async with get_session() as session:
            result = await session.execute(
                select(Prediction).where(Prediction.prediction_id == prediction_id)
            )
            prediction = result.scalar_one_or_none()
            
            if not prediction:
                logger.error(f"Prediction {prediction_id} not found")
                return False
            
            # Сохраняем результат LLM в столбец sun_analysis
            prediction.sun_analysis = llm_content
            
            # Обновляем метаданные LLM
            prediction.llm_model = llm_model
            prediction.llm_tokens_used = tokens_used
            prediction.llm_temperature = temperature
            
            await session.commit()
            logger.info(f"Prediction {prediction_id} updated with LLM content in sun_analysis column")
            return True
    
    async def send_telegram_message(
        self, 
        chat_id: int, 
        text: str, 
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Отправляет сообщение через Telegram Bot API
        
        Args:
            chat_id: ID чата
            text: Текст сообщения
            reply_markup: Клавиатура для сообщения (опционально)
            
        Returns:
            True если отправлено успешно, False иначе
        """
        url = f"{BOT_API_URL}/sendMessage"
        
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        
        if reply_markup:
            payload["reply_markup"] = reply_markup
        
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
    
    def format_prediction_message(self, prediction: Prediction, user: User, profile_name: Optional[str] = None) -> str:
        """
        Форматирует сообщение с предсказанием
        
        Args:
            prediction: Объект предсказания
            user: Объект пользователя
            profile_name: Имя дополнительного профиля (если есть)
            
        Returns:
            Отформатированное сообщение
        """
        if profile_name:
            message = f"☀️ Разбор Солнца для {profile_name}\n\n"
        else:
            message = f"☀️ Твой персональный разбор Солнца\n\n"
        
        # Добавляем имя пользователя если есть (только для основного профиля)
        if not profile_name and user.first_name:
            message = f"Привет, {user.first_name}! {message}"
        
        # Добавляем содержимое предсказания из столбца sun_analysis
        content = prediction.sun_analysis or "Содержимое недоступно"
        
        # Обрезаем если слишком длинное (Telegram лимит 4096 символов)
        max_length = 4096 - len(message) - 100  # Оставляем место для подписи
        if len(content) > max_length:
            content = content[:max_length] + "..."
        
        message += content
        
        # Добавляем подпись
        message += f"\n\n✨ Создано: {prediction.created_at.strftime('%d.%m.%Y %H:%M')}"
        
        if prediction.llm_model:
            message += f"\n🤖 Модель: {prediction.llm_model}"
        
        return message
    
    def create_sun_analysis_buttons(self, is_all_planets: bool = False) -> Dict[str, Any]:
        """
        Создает кнопки для сообщения с разбором Солнца
        
        Args:
            is_all_planets: Если True, показывает кнопку "Следующая планета" вместо "Исследовать другие сферы"
        
        Returns:
            Словарь с клавиатурой для Telegram API
        """
        buttons = [
            [
                {
                    "text": "💡 Получить рекомендации",
                    "callback_data": "get_sun_recommendations"
                }
            ]
        ]
        
        if is_all_planets:
            buttons.append([
                {
                    "text": "➡️ Следующая планета",
                    "callback_data": "next_planet"
                }
            ])
        else:
            buttons.append([
                {
                    "text": "🔍 Исследовать другие сферы",
                    "callback_data": "explore_other_areas"
                }
            ])
        
        return {
            "inline_keyboard": buttons
        }
    
    async def _check_if_all_planets_analysis(self, telegram_id: int) -> bool:
        """Проверяет, является ли это частью разбора всех планет"""
        try:
            from models import PlanetPayment, PaymentStatus, PaymentType
            
            async with get_session() as session:
                result = await session.execute(
                    select(PlanetPayment).where(
                        PlanetPayment.user_id == telegram_id,
                        PlanetPayment.payment_type == PaymentType.all_planets,
                        PlanetPayment.status == PaymentStatus.completed
                    )
                )
                payment = result.scalar_one_or_none()
                
                logger.info(f"🔍 Checking all planets analysis for user {telegram_id}")
                logger.info(f"🔍 Found payment: {payment is not None}")
                if payment:
                    logger.info(f"🔍 Payment details: id={payment.payment_id}, status={payment.status}, type={payment.payment_type}")
                
                return payment is not None
        except Exception as e:
            logger.error(f"Error checking all planets analysis: {e}")
            return False
    
    async def process_prediction(self, message_data: Dict[str, Any]):
        """Обрабатывает одно предсказание"""
        prediction_id = message_data.get("prediction_id")
        user_id = message_data.get("user_id")
        profile_id = message_data.get("profile_id")
        
        if not prediction_id or not user_id:
            logger.error(f"Invalid message data: {message_data}")
            return
        
        logger.info(f"Processing sun prediction {prediction_id} for user {user_id}, profile_id: {profile_id}")
        
        # Импортируем и отмечаем начало анализа
        try:
            import sys
            sys.path.append('.')
            from payment_access import mark_analysis_started, mark_analysis_completed, mark_analysis_failed
            
            # Отмечаем начало анализа
            await mark_analysis_started(user_id, "sun")
            logger.info(f"Marked Sun analysis as started for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to mark analysis as started: {e}")
            # Продолжаем выполнение, даже если не удалось обновить статус
        
        # Получаем информацию о пользователе по telegram_id
        user_info = await self.get_user_info(user_id)
        if not user_info:
            logger.error(f"User with telegram_id {user_id} not found")
            try:
                await mark_analysis_failed(user_id, "sun", "User not found")
            except:
                pass
            return
        
        # Получаем данные предсказания
        async with get_session() as session:
            result = await session.execute(
                select(Prediction).where(Prediction.prediction_id == prediction_id)
            )
            prediction = result.scalar_one_or_none()
            
            if not prediction:
                logger.error(f"Prediction {prediction_id} not found")
                try:
                    await mark_analysis_failed(user_id, "sun", "Prediction not found")
                except:
                    pass
                return
            
            # Извлекаем данные астрологии из content
            content = prediction.content
            if "Sun Analysis Data:" in content:
                # Извлекаем только данные для LLM
                astrology_data = content.split("Sun Analysis Data:")[1].split("Raw AstrologyAPI data:")[0].strip()
            else:
                astrology_data = content
        
        # Генерируем анализ через OpenRouter (если доступен)
        if self.openrouter_client:
            # Определяем данные для LLM в зависимости от типа профиля
            if profile_id:
                profile_info = await self.get_additional_profile_info(profile_id)
                if not profile_info:
                    logger.error(f"Additional profile {profile_id} not found")
                    try:
                        await mark_analysis_failed(user_id, "sun", "Additional profile not found")
                    except:
                        pass
                    return
                llm_user_name = profile_info["full_name"] or "Друг"
                llm_user_gender = profile_info["gender"]
                logger.info(f"Using additional profile data: {llm_user_name}, gender: {llm_user_gender}")
            else:
                llm_user_name = user_info["first_name"] or "Друг"
                llm_user_gender = user_info["gender"]
                logger.info(f"Using main user data: {llm_user_name}, gender: {llm_user_gender}")
            
            llm_result = await self.openrouter_client.generate_sun_analysis(
                astrology_data=astrology_data,
                user_name=llm_user_name,
                user_gender=llm_user_gender
            )
            
            if not llm_result["success"]:
                logger.error(f"LLM generation failed: {llm_result['error']}")
                try:
                    await mark_analysis_failed(user_id, "sun", f"LLM error: {llm_result['error']}")
                except:
                    pass
                return
            
            # Обновляем предсказание с результатом LLM
            await self.update_prediction(
                prediction_id=prediction_id,
                llm_content=llm_result["content"],
                llm_model=llm_result.get("model", "deepseek-chat-v3.1"),
                tokens_used=llm_result.get("usage", {}).get("total_tokens", 0),
                temperature=0.7
            )
            
            # Сразу отправляем готовое предсказание пользователю
            try:
                # Получаем обновленное предсказание
                async with get_session() as session:
                    result = await session.execute(
                        select(Prediction).where(Prediction.prediction_id == prediction_id)
                    )
                    updated_prediction = result.scalar_one_or_none()
                    
                    if updated_prediction:
                        # Получаем данные пользователя
                        user_result = await session.execute(
                            select(User).where(User.telegram_id == user_id)
                        )
                        user = user_result.scalar_one_or_none()
                        
                        if user:
                            # Определяем имя профиля для сообщения
                            profile_name = None
                            if profile_id:
                                # Получаем информацию о профиле заново
                                profile_info_for_message = await self.get_additional_profile_info(profile_id)
                                if profile_info_for_message:
                                    profile_name = profile_info_for_message["full_name"]
                            
                            # Формируем и отправляем сообщение
                            message = self.format_prediction_message(updated_prediction, user, profile_name)
                            
                            # Проверяем, является ли это частью разбора всех планет
                            is_all_planets = await self._check_if_all_planets_analysis(user.telegram_id)
                            logger.info(f"🔍 Sun worker: is_all_planets = {is_all_planets} for user {user.telegram_id}")
                            
                            # Добавляем кнопки для разбора Солнца
                            reply_markup = self.create_sun_analysis_buttons(is_all_planets)
                            logger.info(f"🔍 Sun worker: created buttons with is_all_planets = {is_all_planets}")
                            
                            success = await self.send_telegram_message(
                                chat_id=user.telegram_id,
                                text=message,
                                reply_markup=reply_markup
                            )
                            
                            if success:
                                logger.info(f"Sun prediction {prediction_id} sent to user {user.telegram_id}")
                                # Отмечаем анализ как завершенный и доставленный
                                try:
                                    await mark_analysis_completed(user_id, "sun")
                                    logger.info(f"Marked Sun analysis as delivered for user {user_id}")
                                except Exception as e:
                                    logger.error(f"Failed to mark analysis as delivered: {e}")
                            else:
                                logger.error(f"Failed to send sun prediction {prediction_id} to user {user.telegram_id}")
                                try:
                                    await mark_analysis_failed(user_id, "sun", "Failed to send message")
                                except:
                                    pass
                        else:
                            logger.error(f"User {user_id} not found for sending prediction")
                    else:
                        logger.error(f"Updated prediction {prediction_id} not found")
                        
            except Exception as e:
                logger.error(f"Error sending prediction to user: {e}")
        else:
            logger.info(f"LLM processing skipped for prediction {prediction_id} - no API key")
        
        logger.info(f"Sun prediction {prediction_id} processed successfully")
    
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
        logger.info("Sun worker stopped")


async def main():
    """Основная функция запуска воркера"""
    logger.info("Starting sun prediction worker...")
    
    # Инициализируем подключение к БД
    init_engine()
    
    worker = SunWorker()
    
    try:
        await worker.initialize()
        await worker.start_consuming()
        
        # Держим воркера запущенным
        logger.info("Sun worker is running. Press Ctrl+C to stop.")
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Sun worker error: {e}")
    finally:
        await worker.stop()
        dispose_engine()
        logger.info("Sun worker shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
