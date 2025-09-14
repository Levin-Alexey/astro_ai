"""
Модуль для отправки сообщений в RabbitMQ очередь.
"""

import asyncio
import json
import logging
import os

import aio_pika

logger = logging.getLogger(__name__)

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://astro_user:astro_password_123@31.128.40.111:5672/")
QUEUE_NAME = "moon_predictions"


class QueueSender:
    """Отправитель сообщений в очередь"""

    def __init__(self):
        self.connection = None
        self.channel = None

    async def initialize(self):
        """Инициализация подключения к RabbitMQ"""
        self.connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self.channel = await self.connection.channel()

        # Объявляем очередь
        await self.channel.declare_queue(QUEUE_NAME, durable=True)

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
