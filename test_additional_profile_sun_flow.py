#!/usr/bin/env python3
"""
Тестовый скрипт для проверки полного потока дополнительных профилей:
1. Создание дополнительного профиля
2. Бесплатный разбор Луны
3. Покупка разбора Солнца
4. Получение рекомендаций по Солнцу
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

# Добавляем путь к проекту
sys.path.append('.')

from db import get_session, init_engine, dispose_engine
from models import User, AdditionalProfile, Prediction, Planet, PredictionType, Gender
from sqlalchemy import select
from handlers.additional_profile_handler import get_additional_profile_astrology_data
from astrology_handlers import start_sun_analysis
from queue_sender import send_sun_recommendation_to_queue

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Тестовые данные
TEST_TELEGRAM_ID = 123456789
TEST_PROFILE_DATA = {
    "full_name": "Тестовая Зайка",
    "gender": Gender.female,
    "birth_date": "1991-12-10",
    "birth_time_local": "14:30:00",
    "birth_time_accuracy": "exact",
    "birth_city_input": "Москва",
    "birth_place_name": "Москва, Россия",
    "birth_country_code": "RU",
    "birth_lat": 55.7558,
    "birth_lon": 37.6176,
    "tzid": "Europe/Moscow",
    "tz_offset_minutes": 180,
    "birth_datetime_utc": datetime(1991, 12, 10, 11, 30, 0, tzinfo=timezone.utc),
    "geo_provider": "test",
    "geo_provider_place_id": "test_place_id",
    "zodiac_sign": "kozerog"  # Козерог
}

async def create_test_user() -> Optional[User]:
    """Создает тестового пользователя"""
    try:
        async with get_session() as session:
            # Проверяем, существует ли пользователь
            result = await session.execute(
                select(User).where(User.telegram_id == TEST_TELEGRAM_ID)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                # Создаем нового пользователя
                user = User(
                    telegram_id=TEST_TELEGRAM_ID,
                    first_name="Тестовый",
                    last_name="Пользователь",
                    username="test_user",
                    gender=Gender.male,
                    birth_date="1990-01-01",
                    birth_time_local="12:00:00",
                    birth_time_accuracy="exact",
                    birth_city_input="Москва",
                    birth_place_name="Москва, Россия",
                    birth_country_code="RU",
                    birth_lat=55.7558,
                    birth_lon=37.6176,
                    tzid="Europe/Moscow",
                    tz_offset_minutes=180,
                    birth_datetime_utc=datetime(1990, 1, 1, 9, 0, 0, tzinfo=timezone.utc),
                    geo_provider="test",
                    geo_provider_place_id="test_place_id",
                    zodiac_sign="kozerog"
                )
                session.add(user)
                await session.commit()
                logger.info(f"✅ Создан тестовый пользователь: {user.user_id}")
            else:
                logger.info(f"✅ Используем существующего пользователя: {user.user_id}")
            
            return user
    except Exception as e:
        logger.error(f"❌ Ошибка создания пользователя: {e}")
        return None

async def create_test_additional_profile(user: User) -> Optional[AdditionalProfile]:
    """Создает тестовый дополнительный профиль"""
    try:
        async with get_session() as session:
            # Создаем дополнительный профиль
            profile = AdditionalProfile(
                owner_user_id=user.user_id,
                full_name=TEST_PROFILE_DATA["full_name"],
                gender=TEST_PROFILE_DATA["gender"],
                birth_date=TEST_PROFILE_DATA["birth_date"],
                birth_time_local=TEST_PROFILE_DATA["birth_time_local"],
                birth_time_accuracy=TEST_PROFILE_DATA["birth_time_accuracy"],
                birth_city_input=TEST_PROFILE_DATA["birth_city_input"],
                birth_place_name=TEST_PROFILE_DATA["birth_place_name"],
                birth_country_code=TEST_PROFILE_DATA["birth_country_code"],
                birth_lat=TEST_PROFILE_DATA["birth_lat"],
                birth_lon=TEST_PROFILE_DATA["birth_lon"],
                tzid=TEST_PROFILE_DATA["tzid"],
                tz_offset_minutes=TEST_PROFILE_DATA["tz_offset_minutes"],
                birth_datetime_utc=TEST_PROFILE_DATA["birth_datetime_utc"],
                geo_provider=TEST_PROFILE_DATA["geo_provider"],
                geo_provider_place_id=TEST_PROFILE_DATA["geo_provider_place_id"],
                zodiac_sign=TEST_PROFILE_DATA["zodiac_sign"]
            )
            session.add(profile)
            await session.commit()
            logger.info(f"✅ Создан дополнительный профиль: {profile.profile_id}")
            return profile
    except Exception as e:
        logger.error(f"❌ Ошибка создания дополнительного профиля: {e}")
        return None

async def test_moon_analysis(profile: AdditionalProfile):
    """Тестирует создание разбора Луны для дополнительного профиля"""
    try:
        logger.info("🌙 Тестируем создание разбора Луны...")
        
        # Получаем данные астрологии
        astrology_data = await get_additional_profile_astrology_data(profile.profile_id)
        if not astrology_data:
            logger.error("❌ Не удалось получить данные астрологии")
            return False
        
        logger.info(f"✅ Данные астрологии получены: {len(astrology_data)} символов")
        
        # Создаем запись разбора Луны
        async with get_session() as session:
            moon_prediction = Prediction(
                user_id=profile.owner_user_id,
                profile_id=profile.profile_id,
                planet=Planet.moon,
                prediction_type=PredictionType.free,
                content=f"Test Moon Analysis for {profile.full_name}",
                moon_analysis="Тестовый разбор Луны для дополнительного профиля",
                llm_model="test",
                expires_at=None
            )
            session.add(moon_prediction)
            await session.commit()
            
            logger.info(f"✅ Разбор Луны создан: prediction_id={moon_prediction.prediction_id}")
            return True
            
    except Exception as e:
        logger.error(f"❌ Ошибка создания разбора Луны: {e}")
        return False

async def test_sun_analysis(profile: AdditionalProfile):
    """Тестирует создание разбора Солнца для дополнительного профиля"""
    try:
        logger.info("☀️ Тестируем создание разбора Солнца...")
        
        # Запускаем анализ Солнца
        astrology_data = await start_sun_analysis(TEST_TELEGRAM_ID, profile.profile_id)
        if not astrology_data:
            logger.error("❌ Не удалось создать разбор Солнца")
            return False
        
        logger.info(f"✅ Разбор Солнца создан: {len(astrology_data)} символов")
        
        # Проверяем, что запись создана в БД
        async with get_session() as session:
            result = await session.execute(
                select(Prediction).where(
                    Prediction.profile_id == profile.profile_id,
                    Prediction.planet == Planet.sun,
                    Prediction.prediction_type == PredictionType.paid
                ).order_by(Prediction.created_at.desc())
            )
            prediction = result.scalar_one_or_none()
            
            if prediction:
                logger.info(f"✅ Запись разбора Солнца найдена: prediction_id={prediction.prediction_id}")
                return prediction
            else:
                logger.error("❌ Запись разбора Солнца не найдена в БД")
                return False
                
    except Exception as e:
        logger.error(f"❌ Ошибка создания разбора Солнца: {e}")
        return False

async def test_sun_recommendations(prediction: Prediction, profile: AdditionalProfile):
    """Тестирует получение рекомендаций по Солнцу"""
    try:
        logger.info("💡 Тестируем получение рекомендаций по Солнцу...")
        
        # Отправляем запрос в очередь
        success = await send_sun_recommendation_to_queue(
            prediction_id=prediction.prediction_id,
            user_telegram_id=TEST_TELEGRAM_ID,
            sun_analysis="Тестовый разбор Солнца для дополнительного профиля",
            profile_id=profile.profile_id
        )
        
        if success:
            logger.info("✅ Запрос рекомендаций отправлен в очередь")
            return True
        else:
            logger.error("❌ Не удалось отправить запрос рекомендаций")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки запроса рекомендаций: {e}")
        return False

async def test_data_retrieval(profile: AdditionalProfile):
    """Тестирует получение данных для дополнительного профиля"""
    try:
        logger.info("🔍 Тестируем получение данных...")
        
        async with get_session() as session:
            # Проверяем дополнительные профили пользователя
            result = await session.execute(
                select(AdditionalProfile).where(AdditionalProfile.owner_user_id == profile.owner_user_id)
            )
            profiles = result.scalars().all()
            
            logger.info(f"✅ Найдено дополнительных профилей: {len(profiles)}")
            for p in profiles:
                logger.info(f"  - {p.full_name} (ID: {p.profile_id})")
            
            # Проверяем разборы для дополнительного профиля
            result = await session.execute(
                select(Prediction).where(Prediction.profile_id == profile.profile_id)
            )
            predictions = result.scalars().all()
            
            logger.info(f"✅ Найдено разборов для профиля: {len(predictions)}")
            for p in predictions:
                logger.info(f"  - {p.planet.value} ({p.prediction_type.value})")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения данных: {e}")
        return False

async def cleanup_test_data():
    """Очищает тестовые данные"""
    try:
        logger.info("🧹 Очищаем тестовые данные...")
        
        async with get_session() as session:
            # Удаляем разборы
            result = await session.execute(
                select(Prediction).where(Prediction.user_id.in_(
                    select(User.user_id).where(User.telegram_id == TEST_TELEGRAM_ID)
                ))
            )
            predictions = result.scalars().all()
            for p in predictions:
                await session.delete(p)
            
            # Удаляем дополнительные профили
            result = await session.execute(
                select(AdditionalProfile).where(AdditionalProfile.owner_user_id.in_(
                    select(User.user_id).where(User.telegram_id == TEST_TELEGRAM_ID)
                ))
            )
            profiles = result.scalars().all()
            for p in profiles:
                await session.delete(p)
            
            # Удаляем пользователя
            result = await session.execute(
                select(User).where(User.telegram_id == TEST_TELEGRAM_ID)
            )
            user = result.scalar_one_or_none()
            if user:
                await session.delete(user)
            
            await session.commit()
            logger.info("✅ Тестовые данные очищены")
            
    except Exception as e:
        logger.error(f"❌ Ошибка очистки данных: {e}")

async def main():
    """Основная функция тестирования"""
    logger.info("🚀 Начинаем тестирование потока дополнительных профилей...")
    
    # Инициализируем подключение к БД
    init_engine()
    
    try:
        # 1. Создаем тестового пользователя
        user = await create_test_user()
        if not user:
            logger.error("❌ Не удалось создать тестового пользователя")
            return
        
        # 2. Создаем дополнительный профиль
        profile = await create_test_additional_profile(user)
        if not profile:
            logger.error("❌ Не удалось создать дополнительный профиль")
            return
        
        # 3. Тестируем разбор Луны
        moon_success = await test_moon_analysis(profile)
        if not moon_success:
            logger.error("❌ Тест разбора Луны не прошел")
            return
        
        # 4. Тестируем разбор Солнца
        sun_prediction = await test_sun_analysis(profile)
        if not sun_prediction:
            logger.error("❌ Тест разбора Солнца не прошел")
            return
        
        # 5. Тестируем рекомендации по Солнцу
        recommendations_success = await test_sun_recommendations(sun_prediction, profile)
        if not recommendations_success:
            logger.error("❌ Тест рекомендаций не прошел")
            return
        
        # 6. Тестируем получение данных
        data_success = await test_data_retrieval(profile)
        if not data_success:
            logger.error("❌ Тест получения данных не прошел")
            return
        
        logger.info("🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        logger.info("✅ Поток дополнительных профилей работает корректно")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Очищаем тестовые данные
        await cleanup_test_data()
        dispose_engine()

if __name__ == "__main__":
    asyncio.run(main())
