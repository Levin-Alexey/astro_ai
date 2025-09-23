"""
Скрипт для запуска воркера разбора Венеры
"""

import asyncio
import sys
import os

# Добавляем путь к проекту в sys.path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from venus_worker import main

if __name__ == "__main__":
    print("♀️ Запуск воркера разбора Венеры...")
    asyncio.run(main())