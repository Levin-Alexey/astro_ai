#!/usr/bin/env python3
"""
Запуск бота с FastAPI webhook
"""
import asyncio
import logging
import uvicorn
from main import main as start_bot

logger = logging.getLogger(__name__)

async def main_with_webhook():
    logger.info("Запуск бота и FastAPI webhook сервера...")
    
    # Запускаем бота в фоне
    bot_task = asyncio.create_task(start_bot())
    
    # Запускаем FastAPI webhook сервер
    config = uvicorn.Config(
        "webhook_server:app",
        host="0.0.0.0",
        port=8080,
        log_level="info"
    )
    server = uvicorn.Server(config)
    
    # Запускаем оба сервиса параллельно
    await asyncio.gather(bot_task, server.serve())

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main_with_webhook())
