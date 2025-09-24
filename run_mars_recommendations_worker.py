#!/usr/bin/env python3
"""
Скрипт для запуска воркера генерации рекомендаций по Марсу
"""

import asyncio
import logging
import os
import sys

# Добавляем текущую директорию в путь для импорта модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from mars_recommendations_worker import main

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("🚀 Starting Mars recommendations worker...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Mars recommendations worker stopped by user")
    except Exception as e:
        logger.error(f"❌ Mars recommendations worker error: {e}")
        sys.exit(1)
