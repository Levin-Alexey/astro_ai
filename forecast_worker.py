"""
Воркер для обработки запросов на персональные прогнозы через RabbitMQ.

Получает астрологические данные из очереди, генерирует прогноз через LLM,
сохраняет прогноз в базе данных и отправляет его пользователю.
"""

import asyncio
import json
import logging
import os
from datetime import date
from typing import Dict, Any, Optional

import aio_pika
import aiohttp
from sqlalchemy import select

from db import get_session, init_engine, dispose_engine
from models import User, DailyForecast
from config import BOT_TOKEN
from queue_sender import PERSONAL_FORECASTS_QUEUE_NAME

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://astro_user:astro_password_123@31.128.40.111:5672/")
BOT_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") # Берем из окружения

DAILY_FORECAST_PROMPT = """Ты астролог с опытом 10 лет, который составляет индивидуальные прогнозы на день. Не говори об этом формально, не указывай сухую астрологическую информацию. Пиши, как близкий друг, который видит суть и не боится говорить честно. Стиль — живой, человеческий, прямой. Ты можешь быть и жёстким, если это поможет человеку очнуться. Но без морали. Используй разговорный стиль без канцеляризмов. Опиши, как положение может проявляться в повседневной жизни: в реакциях, привычках, мелочах. Обращайся к человеку по имени. 

У {user_name} транзитная Луна идет по НОМЕР натальному дому, делает аспекты к личным натальным планетам: ________. Транзитное Солнце идет по НОМЕР натальному дому, делает аспекты к личным натальным планетам: ________. Транзитный Меркурий идет по НОМЕР натальному дому, делает аспекты к личным натальным планетам: ________. Транзитная Венера идет по НОМЕР натальному дому, делает аспекты к личным натальным планетам: ________. Транзитный Марс идет по НОМЕР натальному дому, делает аспекты к личным натальным планетам: ________.
На основе этих положений выдай прогноз на сегодня по следующему алгоритму: 
Упоминание о дате прогноза 
В заголовках сферы, за которые отвечает планета: Луна – эмоции, внутренний комфорт, базовые потребности. Солнце – уверенность в себе, энергия, яркость. Меркурий – общение, рутина, документы, мелкие обучения, поездки. Венера – отношения, финансы, удовольствие от жизни, женская энергия. Марс – мотивация, умение брать и начать делать, конфликты. 
Транзитная Луна в натальном доме = сфера, где ты наиболее чувствительна, импульсивна, реагируешь сердцем, а не логикой. Аспекты транзитной Луны — это «как ты чувствуешь ситуацию» и «к чему реагируешь».
Транзитное Солнце в натальном доме = сфера, где ты хочешь проявиться, сделать результат, привлечь внимание. Аспекты транзитного Солнца — «какую часть личности оно активирует». 
Транзитный Меркурий в натальном доме = сфера, которую ты изучаешь, обсуждаешь, анализируешь, где может быть рутина. Аспекты транзитного Меркурия — «как ты думаешь и как коммуницируешь». 
Транзитная Венера в натальном доме = сфера, где ты хочешь красоты, лёгкости, удовольствия и хороших отношений, куда стоит потратить деньги. Аспекты транзитного Венеры — «как ты взаимодействуешь с людьми и желаниями, финансами.  
Транзитный Марс в натальном доме = сфера, где включается желание делать, менять или бороться. Аспекты транзитного Марса — «как и куда ты направляешь силу». 
Общие рекомендации на день на основе всего вышесказанного. 
Сделай прогноз строго до 3000 символов, не больше!
"""

class OpenRouterClient:
    """Клиент для работы с OpenRouter API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = OPENROUTER_URL
    
    async def generate_daily_forecast(
        self, 
        astrology_data: str, 
        user_name: str, 
        user_gender: str
    ) -> Dict[str, Any]:
        """
        Генерирует ежедневный прогноз через OpenRouter
        """
        prompt = DAILY_FORECAST_PROMPT.format(
            astrology_data=astrology_data,
            user_name=user_name,
            user_gender=user_gender
        )
        
        payload = {
            "model": "google/gemini-2.5-flash",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 2000,
            "temperature": 0.7
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://astro-bot.com",
            "X-Title": "Astro Bot"
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return {
                            "success": True,
                            "content": result["choices"][0]["message"]["content"],
                            "model": result.get("model", "unknown")
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"OpenRouter error {response.status}: {error_text}")
                        return {"success": False, "error": f"API error: {response.status}"}
            except Exception as e:
                logger.error(f"OpenRouter request failed: {e}")
                return {"success": False, "error": str(e)}


async def send_telegram_message(chat_id: int, text: str):
    """
    Отправляет сообщение в Telegram, разбивая его на части, если оно слишком длинное.
    """
    url = f"{BOT_API_URL}/sendMessage"
    max_length = 4096 # Лимит Telegram для одного сообщения
    
    # Разделяем текст на части, если он превышает max_length
    if len(text) <= max_length:
        parts = [text]
    else:
        parts = []
        for i in range(0, len(text), max_length):
            parts.append(text[i:i+max_length])
            
    async with aiohttp.ClientSession() as session:
        for i, part in enumerate(parts):
            payload = {"chat_id": chat_id, "text": part, "parse_mode": "Markdown"}
            try:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Telegram error sending part {i+1}: {await response.text()}")
            except Exception as e:
                logger.error(f"Telegram request failed sending part {i+1}: {e}")


async def process_personal_forecast(data: Dict[str, Any], openrouter_client: OpenRouterClient) -> bool:
    """Обработка сообщения из очереди"""
    user_id = data.get("user_id") # Это telegram_id
    astrology_data_raw = data.get("astrology_data", {})
    
    if not user_id:
        logger.error("Missing user_id in message")
        return False

    # Получаем профиль из данных (если передали) или ставим дефолт
    user_profile = astrology_data_raw.get("user_profile", {})
    user_name = user_profile.get("full_name", "Друг")
    user_gender = user_profile.get("gender", "unknown")
    
    # Преобразуем данные транзитов в строку для промпта (можно оптимизировать, убрав лишнее)
    # API возвращает { "date": ..., "transits": [...] }
    # Берем только транзиты для экономии токенов
    transits_data = astrology_data_raw.get("transits", [])
    astrology_data_str = json.dumps(transits_data, ensure_ascii=False, indent=2)
    
    logger.info(f"🔥 Generating forecast for {user_id} ({user_name})")
    
    # Генерация
    llm_result = await openrouter_client.generate_daily_forecast(
        astrology_data=astrology_data_str,
        user_name=user_name,
        user_gender=user_gender
    )
    
    if llm_result["success"]:
        content = llm_result["content"]
        
        # Сохранение в БД
        async with get_session() as session:
            # Нам нужен user_id (PK) для сохранения в DailyForecast
            # В data['user_id'] лежит telegram_id.
            result = await session.execute(select(User.user_id).where(User.telegram_id == user_id))
            pk_user_id = result.scalar_one_or_none()
            
            if pk_user_id:
                # Проверяем, нет ли уже записи на сегодня (чтобы не дублировать при повторном запуске)
                today = date.today()
                existing = await session.execute(
                    select(DailyForecast).where(
                        DailyForecast.user_id == pk_user_id,
                        DailyForecast.date == today
                    )
                )
                if not existing.scalar_one_or_none():
                    forecast = DailyForecast(
                        user_id=pk_user_id,
                        date=today,
                        content=content
                    )
                    session.add(forecast)
                    await session.commit()
                    logger.info(f"✅ Forecast saved to DB for user {user_id}")
            else:
                logger.warning(f"User PK not found for telegram_id {user_id}, skipping DB save")

        # Отправка пользователю
        await send_telegram_message(user_id, content)
        return True
    else:
        logger.error(f"Failed to generate forecast: {llm_result.get('error')}")
        await send_telegram_message(user_id, "⚠️ Не удалось составить прогноз. Звезды сегодня туманны. Попробуйте позже.")
        return False


async def main():
    """Запуск воркера"""
    logger.info("🔥 Starting Personal Forecasts LLM Worker...")
    
    init_engine()
    
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not set!")
        return

    client = OpenRouterClient(OPENROUTER_API_KEY)
    
    try:
        connection = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await connection.channel()
        queue = await channel.declare_queue(PERSONAL_FORECASTS_QUEUE_NAME, durable=True)
        
        logger.info(f"🔥 Connected to RabbitMQ: {PERSONAL_FORECASTS_QUEUE_NAME}")
        
        async def process_message(message: aio_pika.abc.AbstractIncomingMessage):
            async with message.process():
                try:
                    data = json.loads(message.body)
                    await process_personal_forecast(data, client)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        await queue.consume(process_message)
        await asyncio.Future()
        
    except Exception as e:
        logger.error(f"Worker error: {e}")
    finally:
        dispose_engine()

if __name__ == "__main__":
    asyncio.run(main())