#!/usr/bin/env python3
"""
Скрипт для запуска воркера рекомендаций по Солнцу.
"""

import asyncio
import sys
import os

# Добавляем текущую директорию в путь Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sun_recommendations_worker import main

if __name__ == "__main__":
    asyncio.run(main())
