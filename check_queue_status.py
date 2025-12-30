#!/usr/bin/env python3
"""
Проверка сообщений в очередях RabbitMQ
"""
import asyncio
import aio_pika
import os
import json

RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL", 
    "amqp://astro_user:astro_password_123@31.128.40.111:5672/"
)

QUEUE_NAMES = [
    "moon_predictions",
    "sun_predictions",
    "mercury_predictions",
    "venus_predictions",
    "mars_predictions",
    "recommendations",
    "sun_recommendations",
    "mercury_recommendations",
    "venus_recommendations",
    "mars_recommendations",
    "questions",
    "personal_forecasts"
]

async def check_queues():
    """Проверить размер всех очередей"""
    try:
        print(f"Подключаемся к RabbitMQ: {RABBITMQ_URL[:50]}...")
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()
        
        print("\n📊 Статус очередей:\n")
        
        total_messages = 0
        for queue_name in QUEUE_NAMES:
            try:
                # Просто получаем очередь без переобъявления
                queue = await channel.declare_queue(queue_name, durable=True, passive=True)
                
                # Используем правильные атрибуты
                print(f"📨 {queue_name:30} - {len(queue):3} сообщений")
                        
            except Exception as e:
                print(f"❌ {queue_name:30} - Ошибка: {str(e)[:50]}")
        
        print(f"\n{'='*60}")
        print(f"📈 ВСЕГО сообщений в очередях: {total_messages}")
        
        if total_messages == 0:
            print("\n⚠️  ПРОБЛЕМА: В очередях нет сообщений!")
            print("   Возможные причины:")
            print("   1. Webhook не отправил задачи рабочим процессам")
            print("   2. Рабочие процессы обработали и удалили сообщения")
            print("   3. RabbitMQ недоступен")
        else:
            print(f"\n✅ В очередях {total_messages} ожидающих задач")
            print("   Рабочие процессы должны их обработать")
        
        await connection.close()
        
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        print("\nПроверьте:")
        print("1. RabbitMQ работает и доступен")
        print("2. RABBITMQ_URL в .env правильный")
        print("3. Логины/пароли верны")

async def main():
    await check_queues()

if __name__ == "__main__":
    asyncio.run(main())
