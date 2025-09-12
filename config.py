import os
from dotenv import load_dotenv, find_dotenv

# Автоматически ищет и загружает .env из корня проекта
load_dotenv(find_dotenv())

# Получение переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN", "ваш_токен_здесь")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "%(asctime)s - %(levelname)s - %(message)s")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/dbname")

# Геокодер (по умолчанию — публичный Nominatim OSM)
# Важно: для соблюдения правил Nominatim используйте валидный User-Agent с контактом.
GEOCODER_BASE_URL = os.getenv("GEOCODER_BASE_URL", "https://nominatim.openstreetmap.org/search")
GEOCODER_USER_AGENT = os.getenv(
	"GEOCODER_USER_AGENT",
	"AstroBot/1.0 (+https://example.com; contact@example.com)",
)
