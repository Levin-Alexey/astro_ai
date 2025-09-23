"""
Скрипт для запуска воркера рекомендаций по Венере.
"""

import asyncio
from venus_recommendations_worker import main

if __name__ == "__main__":
    asyncio.run(main())