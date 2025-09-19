#!/usr/bin/env python3
"""
Запуск воркера для обработки планет
"""
import asyncio
import logging
from planet_worker import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
