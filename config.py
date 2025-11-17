import os
from dotenv import load_dotenv, find_dotenv

# Автоматически ищет и загружает .env из корня проекта
load_dotenv(find_dotenv())

# Получение переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN", "ваш_токен_здесь")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv(
    "LOG_FORMAT", "%(asctime)s - %(levelname)s - %(message)s"
)
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/dbname"
)

# Геокодер TomTom
TOMTOM_API_KEY = os.getenv(
    "TOMTOM_API_KEY", "your_tomtom_api_key_here"
)
GEOCODER_BASE_URL = os.getenv(
    "GEOCODER_BASE_URL", "https://api.tomtom.com/search/2/geocode"
)

# Настройки платежей
PAYMENT_SHOP_ID = os.getenv("PAYMENT_SHOP_ID", "1139243")
PAYMENT_SECRET_KEY = os.getenv(
    "PAYMENT_SECRET_KEY",
    "live_3l8CSTav7iq2-3IO4YyLNnIQN6Fe7Nw8j4wOnzAlxm8"
)
PAYMENT_TEST_AMOUNT = 7700  # 77 рублей в копейках
PAYMENT_CURRENCY = "RUB"

# Настройки AstrologyAPI
ASTROLOGY_API_USER_ID = os.getenv("ASTROLOGY_API_USER_ID", "645593")
ASTROLOGY_API_KEY = os.getenv(
    "ASTROLOGY_API_KEY",
    "ded745efefef2a72f117e0c32d1f1c853dc485ac"
)
