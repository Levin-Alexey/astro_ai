"""
Модуль для отправки сообщений в RabbitMQ очередь.
"""

import asyncio
import json
import logging
import os
from typing import Optional

import aio_pika

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL", 
    "amqp://astro_user:astro_password_123@31.128.40.111:5672/"
)
QUEUE_NAME = "moon_predictions"
SUN_QUEUE_NAME = "sun_predictions"
MERCURY_QUEUE_NAME = "mercury_predictions"
VENUS_QUEUE_NAME = "venus_predictions"
MARS_QUEUE_NAME = "mars_predictions"
RECOMMENDATIONS_QUEUE_NAME = "recommendations"
SUN_RECOMMENDATIONS_QUEUE_NAME = "sun_recommendations"
MERCURY_RECOMMENDATIONS_QUEUE_NAME = "mercury_recommendations"
VENUS_RECOMMENDATIONS_QUEUE_NAME = "venus_recommendations"
MARS_RECOMMENDATIONS_QUEUE_NAME = "mars_recommendations"
QUESTIONS_QUEUE_NAME = "questions"


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
        await self.channel.declare_queue(SUN_QUEUE_NAME, durable=True)
        await self.channel.declare_queue(MERCURY_QUEUE_NAME, durable=True)
        await self.channel.declare_queue(VENUS_QUEUE_NAME, durable=True)
        await self.channel.declare_queue(MARS_QUEUE_NAME, durable=True)
        await self.channel.declare_queue(
            RECOMMENDATIONS_QUEUE_NAME, durable=True
        )
        await self.channel.declare_queue(
            SUN_RECOMMENDATIONS_QUEUE_NAME, durable=True
        )
        await self.channel.declare_queue(
            MERCURY_RECOMMENDATIONS_QUEUE_NAME, durable=True
        )
        await self.channel.declare_queue(
            VENUS_RECOMMENDATIONS_QUEUE_NAME, durable=True
        )
        await self.channel.declare_queue(
            MARS_RECOMMENDATIONS_QUEUE_NAME, durable=True
        )
        await self.channel.declare_queue(
            QUESTIONS_QUEUE_NAME, durable=True
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

    async def send_mercury_prediction_for_processing(
        self,
        prediction_id: int,
        user_id: int,
        profile_id: int = None
    ) -> bool:
        """
        Отправляет предсказание Меркурия на обработку в очередь

        Args:
            prediction_id: ID предсказания
            user_id: ID пользователя
            profile_id: ID дополнительного профиля (опционально)

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
        
        # Добавляем profile_id если указан
        if profile_id is not None:
            message_data["profile_id"] = profile_id

        try:
            message = aio_pika.Message(
                body=json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await self.channel.default_exchange.publish(
                message,
                routing_key=MERCURY_QUEUE_NAME
            )

            logger.info(f"☿️ Sent Mercury prediction {prediction_id} to queue")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to send Mercury message to queue: {e}")
            return False

    async def send_recommendation_for_processing(
        self,
        prediction_id: int,
        user_telegram_id: int,
        moon_analysis: str,
        profile_id: Optional[int] = None
    ) -> bool:
        """
        Отправляет запрос на генерацию рекомендаций в очередь

        Args:
            prediction_id: ID исходного предсказания
            user_telegram_id: Telegram ID пользователя
            moon_analysis: Разбор Луны для генерации рекомендаций
            profile_id: ID дополнительного профиля (опционально)

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
        
        # Добавляем profile_id если указан
        if profile_id is not None:
            message_data["profile_id"] = profile_id

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
        sun_analysis: str,
        profile_id: Optional[int] = None
    ) -> bool:
        """
        Отправляет запрос на генерацию рекомендаций по Солнцу в очередь

        Args:
            prediction_id: ID исходного предсказания
            user_telegram_id: Telegram ID пользователя
            sun_analysis: Разбор Солнца для генерации рекомендаций
            profile_id: ID дополнительного профиля (если None, используется основной профиль)

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
        
        # Добавляем profile_id если указан
        if profile_id is not None:
            message_data["profile_id"] = profile_id

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

    async def send_mercury_recommendation_for_processing(
        self,
        prediction_id: int,
        user_telegram_id: int,
        mercury_analysis: str,
        profile_id: int = None
    ) -> bool:
        """
        Отправляет запрос на генерацию рекомендаций по Меркурию в очередь

        Args:
            prediction_id: ID исходного предсказания
            user_telegram_id: Telegram ID пользователя
            mercury_analysis: Разбор Меркурия для генерации рекомендаций
            profile_id: ID дополнительного профиля (опционально)

        Returns:
            True если сообщение отправлено успешно
        """
        if not self.channel:
            await self.initialize()

        message_data = {
            "prediction_id": prediction_id,
            "user_telegram_id": user_telegram_id,
            "mercury_analysis": mercury_analysis,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Добавляем profile_id если указан
        if profile_id is not None:
            message_data["profile_id"] = profile_id

        try:
            message = aio_pika.Message(
                body=json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await self.channel.default_exchange.publish(
                message,
                routing_key=MERCURY_RECOMMENDATIONS_QUEUE_NAME
            )

            logger.info(
                f"Sent mercury recommendation request for prediction "
                f"{prediction_id} to queue"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to send mercury recommendation message to queue: {e}"
            )
            return False

    async def send_venus_prediction_for_processing(
        self,
        prediction_id: int,
        user_id: int,
        profile_id: int = None
    ) -> bool:
        """
        Отправляет предсказание Венеры на обработку в очередь

        Args:
            prediction_id: ID предсказания
            user_id: ID пользователя
            profile_id: ID дополнительного профиля (опционально)

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
        
        # Добавляем profile_id если указан
        if profile_id is not None:
            message_data["profile_id"] = profile_id

        try:
            message = aio_pika.Message(
                body=json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await self.channel.default_exchange.publish(
                message,
                routing_key=VENUS_QUEUE_NAME
            )

            logger.info(f"♀️ Sent Venus prediction {prediction_id} to queue")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to send Venus message to queue: {e}")
            return False

    async def send_mars_prediction_for_processing(
        self,
        prediction_id: int,
        user_id: int,
        profile_id: int = None
    ) -> bool:
        """
        Отправляет предсказание Марса на обработку в очередь

        Args:
            prediction_id: ID предсказания
            user_id: ID пользователя
            profile_id: ID дополнительного профиля (опционально)

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
        
        # Добавляем profile_id если указан
        if profile_id is not None:
            message_data["profile_id"] = profile_id

        try:
            message = aio_pika.Message(
                body=json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await self.channel.default_exchange.publish(
                message,
                routing_key=MARS_QUEUE_NAME
            )

            logger.info(f"♂️ Sent Mars prediction {prediction_id} to queue")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to send Mars message to queue: {e}")
            return False

    async def send_venus_recommendation_for_processing(
        self,
        prediction_id: int,
        user_telegram_id: int,
        venus_analysis: str,
        profile_id: int = None
    ) -> bool:
        """
        Отправляет запрос на генерацию рекомендаций по Венере в очередь

        Args:
            prediction_id: ID исходного предсказания
            user_telegram_id: Telegram ID пользователя
            venus_analysis: Разбор Венеры для генерации рекомендаций
            profile_id: ID дополнительного профиля (опционально)

        Returns:
            True если сообщение отправлено успешно
        """
        if not self.channel:
            await self.initialize()

        message_data = {
            "prediction_id": prediction_id,
            "user_telegram_id": user_telegram_id,
            "venus_analysis": venus_analysis,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Добавляем profile_id если указан
        if profile_id is not None:
            message_data["profile_id"] = profile_id

        try:
            message = aio_pika.Message(
                body=json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await self.channel.default_exchange.publish(
                message,
                routing_key=VENUS_RECOMMENDATIONS_QUEUE_NAME
            )

            logger.info(
                f"Sent venus recommendation request for prediction "
                f"{prediction_id} to queue"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to send venus recommendation message to queue: {e}"
            )
            return False

    async def send_mars_recommendation_for_processing(
        self,
        prediction_id: int,
        user_telegram_id: int,
        mars_analysis: str,
        profile_id: int = None
    ) -> bool:
        """
        Отправляет запрос на генерацию рекомендаций по Марсу в очередь

        Args:
            prediction_id: ID исходного предсказания
            user_telegram_id: Telegram ID пользователя
            mars_analysis: Разбор Марса для генерации рекомендаций
            profile_id: ID дополнительного профиля (опционально)

        Returns:
            True если сообщение отправлено успешно
        """
        if not self.channel:
            await self.initialize()

        message_data = {
            "prediction_id": prediction_id,
            "user_telegram_id": user_telegram_id,
            "mars_analysis": mars_analysis,
            "timestamp": asyncio.get_event_loop().time()
        }
        
        # Добавляем profile_id если указан
        if profile_id is not None:
            message_data["profile_id"] = profile_id

        try:
            message = aio_pika.Message(
                body=json.dumps(message_data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            )

            await self.channel.default_exchange.publish(
                message,
                routing_key=MARS_RECOMMENDATIONS_QUEUE_NAME
            )

            logger.info(
                f"Sent mars recommendation request for prediction "
                f"{prediction_id} to queue"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to send mars recommendation message to queue: {e}"
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
    moon_analysis: str,
    profile_id: Optional[int] = None
) -> bool:
    """
    Удобная функция для отправки запроса на рекомендации в очередь

    Args:
        prediction_id: ID исходного предсказания
        user_telegram_id: Telegram ID пользователя
        moon_analysis: Разбор Луны для генерации рекомендаций
        profile_id: ID дополнительного профиля (опционально)

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_recommendation_for_processing(
        prediction_id, user_telegram_id, moon_analysis, profile_id
    )


async def send_sun_recommendation_to_queue(
    prediction_id: int, 
    user_telegram_id: int, 
    sun_analysis: str,
    profile_id: Optional[int] = None
) -> bool:
    """
    Удобная функция для отправки запроса на рекомендации по Солнцу в очередь

    Args:
        prediction_id: ID исходного предсказания
        user_telegram_id: Telegram ID пользователя
        sun_analysis: Разбор Солнца для генерации рекомендаций
        profile_id: ID дополнительного профиля (если None, используется основной профиль)

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_sun_recommendation_for_processing(
        prediction_id, user_telegram_id, sun_analysis, profile_id
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


async def send_mercury_recommendation_to_queue(
    prediction_id: int,
    user_telegram_id: int,
    mercury_analysis: str,
    profile_id: int = None
) -> bool:
    """
    Удобная функция для отправки запроса на рекомендации по Меркурию в очередь

    Args:
        prediction_id: ID исходного предсказания
        user_telegram_id: Telegram ID пользователя
        mercury_analysis: Разбор Меркурия для генерации рекомендаций
        profile_id: ID дополнительного профиля (опционально)

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_mercury_recommendation_for_processing(
        prediction_id, user_telegram_id, mercury_analysis, profile_id
    )


async def send_mercury_prediction_to_queue(
    prediction_id: int,
    user_id: int,
    profile_id: int = None
) -> bool:
    """
    Удобная функция для отправки Mercury prediction в очередь

    Args:
        prediction_id: ID предсказания
        user_id: ID пользователя
        profile_id: ID дополнительного профиля (опционально)

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_mercury_prediction_for_processing(
        prediction_id, user_id, profile_id
    )


async def send_venus_prediction_to_queue(
    prediction_id: int,
    user_id: int,
    profile_id: int = None
) -> bool:
    """
    Удобная функция для отправки Venus prediction в очередь

    Args:
        prediction_id: ID предсказания
        user_id: ID пользователя
        profile_id: ID дополнительного профиля (опционально)

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_venus_prediction_for_processing(
        prediction_id, user_id, profile_id
    )


async def send_mars_prediction_to_queue(
    prediction_id: int,
    user_id: int,
    profile_id: int = None
) -> bool:
    """
    Удобная функция для отправки Mars prediction в очередь

    Args:
        prediction_id: ID предсказания
        user_id: ID пользователя
        profile_id: ID дополнительного профиля (опционально)

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_mars_prediction_for_processing(
        prediction_id, user_id, profile_id
    )


async def send_venus_recommendation_to_queue(
    prediction_id: int,
    user_telegram_id: int,
    venus_analysis: str,
    profile_id: int = None
) -> bool:
    """
    Удобная функция для отправки запроса на рекомендации по Венере в очередь

    Args:
        prediction_id: ID исходного предсказания
        user_telegram_id: Telegram ID пользователя
        venus_analysis: Разбор Венеры для генерации рекомендаций
        profile_id: ID дополнительного профиля (опционально)

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_venus_recommendation_for_processing(
        prediction_id, user_telegram_id, venus_analysis, profile_id
    )


async def send_mars_recommendation_to_queue(
    prediction_id: int,
    user_telegram_id: int,
    mars_analysis: str,
    profile_id: int = None
) -> bool:
    """
    Удобная функция для отправки запроса на рекомендации по Марсу в очередь

    Args:
        prediction_id: ID исходного предсказания
        user_telegram_id: Telegram ID пользователя
        mars_analysis: Разбор Марса для генерации рекомендаций
        profile_id: ID дополнительного профиля (опционально)

    Returns:
        True если сообщение отправлено успешно
    """
    sender = await get_queue_sender()
    return await sender.send_mars_recommendation_for_processing(
        prediction_id, user_telegram_id, mars_analysis, profile_id
    )


