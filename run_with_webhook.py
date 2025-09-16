#!/usr/bin/env python3
"""
Скрипт для запуска бота с webhook сервером
"""
import asyncio
import logging
from main import main as bot_main
from webhook_server import start_webhook_server

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Основная функция запуска бота и webhook сервера"""
    logger.info("Запуск бота с webhook сервером...")
    
    # Запускаем webhook сервер
    webhook_runner = await start_webhook_server()
    
    try:
        # Запускаем бота
        await bot_main()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.error(f"Ошибка при запуске: {e}")
    finally:
        # Останавливаем webhook сервер
        await webhook_runner.cleanup()
        logger.info("Webhook сервер остановлен")

if __name__ == "__main__":
    asyncio.run(main())
