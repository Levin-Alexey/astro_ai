#!/usr/bin/env python3
"""
Запуск воркера для обработки Солнца
"""
import asyncio
import logging
from sun_worker import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
