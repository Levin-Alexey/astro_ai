"""
Модуль для отправки сообщений в RabbitMQ очередь.
"""

import asyncio
import json
import logging
import os

import aio_pika

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL", 
    "amqp://astro_user:astro_password_123@31.128.40.111:5672/"
)
QUEUE_NAME = "moon_predictions"
RECOMMENDATIONS_QUEUE_NAME = "recommendations"
SUN_RECOMMENDATIONS_QUEUE_NAME = "sun_recommendations"
QUESTIONS_QUEUE_NAME = "questions"
SUN_QUESTIONS_QUEUE_NAME = "sun_questions"


class QueueSender:
    """Отправитель сообщений в очередь"""

    def __init__(self):
        self.connection = None
        self.channel = None

    async def initialize(self):
        """Инициализация подключения к RabbitMQ"""
        self.connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self.channel = await self.connection.channel()

        # Объявляем очереди
        await self.channel.declare_queue(QUEUE_NAME, durable=True)
        await self.channel.declare_queue(RECOMMENDATIONS_QUEUE_NAME, durable=True)
        await self.channel.declare_queue(SUN_RECOMMENDATIONS_QUEUE_NAME, durable=True)
        await self.channel.declare_queue(
            QUESTIONS_QUEUE_NAME, durable=True
        )
        await self.channel.declare_queue(
            SUN_QUESTIONS_QUEUE_NAME, durable=True
        )

        logger.info("Queue sender initialized")

    async def send_prediction_for_processing(
        self,
        prediction_id: int,
        user_id: int
    ) -> bool:
        """
        Отправляет предсказание на обработку в очередь

        Args:
            prediction_id: ID предсказания
            user_id: ID пользователя

        Returns:
            True если сообщение отправлено успешно
        """
        if not self.channel:
            await self.initialize()

        message_data = {
            "prediction_id": prediction_id,
            "user_id": user_id,
            "timestamp": asyncio.get_event_loop().time()
        }

        try:
            message = aio_pika.Message(
                body=json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await self.channel.default_exchange.publish(
                message,
                routing_key=QUEUE_NAME
            )

            logger.info(f"Sent prediction {prediction_id} to queue")
            return True

        except Exception as e:
            logger.error(f"Failed to send message to queue: {e}")
            return False

    async def send_recommendation_for_processing(
        self,
        prediction_id: int,
        user_telegram_id: int,
        moon_analysis: str
    ) -> bool:
        """
        Отправляет запрос на генерацию рекомендаций в очередь

        Args:
            prediction_id: ID исходного предсказания
            user_telegram_id: Telegram ID пользователя
            moon_analysis: Разбор Луны для генерации рекомендаций

        Returns:
            True если сообщение отправлено успешно
        """
        if not self.channel:
            await self.initialize()

        message_data = {
            "prediction_id": prediction_id,
            "user_telegram_id": user_telegram_id,
            "moon_analysis": moon_analysis,
            "timestamp": asyncio.get_event_loop().time()
        }

        try:
            message = aio_pika.Message(
                body=json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await self.channel.default_exchange.publish(
                message,
                routing_key=RECOMMENDATIONS_QUEUE_NAME
            )

            logger.info(
                f"Sent recommendation request for prediction {prediction_id} "
                "to queue"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to send recommendation message to queue: {e}"
            )
            return False

    async def send_sun_recommendation_for_processing(
        self,
        prediction_id: int,
        user_telegram_id: int,
        sun_analysis: str
    ) -> bool:
        """
        Отправляет запрос на генерацию рекомендаций по Солнцу в очередь

        Args:
            prediction_id: ID исходного предсказания
            user_telegram_id: Telegram ID пользователя
            sun_analysis: Разбор Солнца для генерации рекомендаций

        Returns:
            True если сообщение отправлено успешно
        """
        if not self.channel:
            await self.initialize()

        message_data = {
            "prediction_id": prediction_id,
            "user_telegram_id": user_telegram_id,
            "sun_analysis": sun_analysis,
            "timestamp": asyncio.get_event_loop().time()
        }

        try:
            message = aio_pika.Message(
                body=json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await self.channel.default_exchange.publish(
                message,
                routing_key=SUN_RECOMMENDATIONS_QUEUE_NAME
            )

            logger.info(
                f"Sent sun recommendation request for prediction {prediction_id} "
                "to queue"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to send sun recommendation message to queue: {e}"
            )
            return False

    async def send_question_for_processing(
        self,
        user_telegram_id: int,
        question: str
    ) -> bool:
        """
        Отправляет вопрос пользователя в очередь для обработки

        Args:
            user_telegram_id: Telegram ID пользователя
            question: Текст вопроса пользователя

        Returns:
            True если сообщение отправлено успешно
        """
        logger.info(f"send_question_for_processing called: user={user_telegram_id}, question='{question[:50]}...'")
        
        if not self.channel:
            logger.info("Channel not initialized, initializing...")
            await self.initialize()

        message_data = {
            "user_telegram_id": user_telegram_id,
            "question": question,
            "timestamp": asyncio.get_event_loop().time()
        }

        try:
            message = aio_pika.Message(
                body=json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            logger.info(f"Publishing message to queue '{QUESTIONS_QUEUE_NAME}'")
            await self.channel.default_exchange.publish(
                message,
                routing_key=QUESTIONS_QUEUE_NAME
            )

            logger.info(f"Successfully sent question from user {user_telegram_id} to queue")
            return True

        except Exception as e:
            logger.error(f"Failed to send question message to queue: {e}")
            return False

    async def send_sun_question_for_processing(
        self,
        user_telegram_id: int,
        question: str,
        sun_analysis: str
    ) -> bool:
        """
        Отправляет вопрос пользователя по Солнцу в очередь для обработки

        Args:
            user_telegram_id: Telegram ID пользователя
            question: Текст вопроса пользователя
            sun_analysis: Разбор Солнца для контекста

        Returns:
            True если сообщение отправлено успешно
        """
        logger.info(f"send_sun_question_for_processing called: user={user_telegram_id}, question='{question[:50]}...'")
        
        if not self.channel:
            logger.info("Channel not initialized, initializing...")
            await self.initialize()

        message_data = {
            "user_telegram_id": user_telegram_id,
            "question": question,
            "sun_analysis": sun_analysis,
            "timestamp": asyncio.get_event_loop().time()
        }

        try:
            message = aio_pika.Message(
                body=json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            logger.info(f"Publishing message to queue '{SUN_QUESTIONS_QUEUE_NAME}'")
            await self.channel.default_exchange.publish(
                message,
                routing_key=SUN_QUESTIONS_QUEUE_NAME
            )

            logger.info(f"Successfully sent sun question from user {user_telegram_id} to queue")
            return True

        except Exception as e:
            logger.error(f"Failed to send sun question message to queue: {e}")
            return False

    async def close(self):
        """Закрывает подключение"""
        if self.connection:
            await self.connection.close()
        logger.info("Queue sender closed")


# Глобальный экземпляр отправителя
_queue_sender = None


async def get_queue_sender() -> QueueSender:
    """Получает глобальный экземпляр отправителя очереди"""
    global _queue_sender
    if _queue_sender is None:
        _queue_sender = QueueSender()
        await _queue_sender.initialize()
    return _queue_sender


async def send_prediction_to_queue(prediction_id: int, user_id: int) -> bool:
    """
    Удобная функция для отправки предсказания в очередь

    Args:
        prediction_id: ID предсказания
        user_id: ID пользователя

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_prediction_for_processing(prediction_id, user_id)


async def send_recommendation_to_queue(
    prediction_id: int, 
    user_telegram_id: int, 
    moon_analysis: str
) -> bool:
    """
    Удобная функция для отправки запроса на рекомендации в очередь

    Args:
        prediction_id: ID исходного предсказания
        user_telegram_id: Telegram ID пользователя
        moon_analysis: Разбор Луны для генерации рекомендаций

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_recommendation_for_processing(
        prediction_id, user_telegram_id, moon_analysis
    )


async def send_sun_recommendation_to_queue(
    prediction_id: int, 
    user_telegram_id: int, 
    sun_analysis: str
) -> bool:
    """
    Удобная функция для отправки запроса на рекомендации по Солнцу в очередь

    Args:
        prediction_id: ID исходного предсказания
        user_telegram_id: Telegram ID пользователя
        sun_analysis: Разбор Солнца для генерации рекомендаций

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_sun_recommendation_for_processing(
        prediction_id, user_telegram_id, sun_analysis
    )


async def send_question_to_queue(
    user_telegram_id: int, 
    question: str
) -> bool:
    """
    Удобная функция для отправки вопроса пользователя в очередь

    Args:
        user_telegram_id: Telegram ID пользователя
        question: Текст вопроса пользователя

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_question_for_processing(
        user_telegram_id, question
    )


async def send_sun_question_to_queue(
    user_telegram_id: int, 
    question: str,
    sun_analysis: str
) -> bool:
    """
    Удобная функция для отправки вопроса по Солнцу в очередь

    Args:
        user_telegram_id: Telegram ID пользователя
        question: Текст вопроса пользователя
        sun_analysis: Разбор Солнца для контекста

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_sun_question_for_processing(
        user_telegram_id, question, sun_analysis
    )
