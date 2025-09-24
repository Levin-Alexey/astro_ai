#!/usr/bin/env python3
"""
Скрипт для запуска воркера обработки разборов Марса
"""

import asyncio
import logging
import os
import sys

# Добавляем текущую директорию в путь для импорта модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from mars_worker import main

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        logger.info("🚀 Starting Mars worker...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Mars worker stopped by user")
    except Exception as e:
        logger.error(f"❌ Mars worker error: {e}")
        sys.exit(1)
