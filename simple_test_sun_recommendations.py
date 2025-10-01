#!/usr/bin/env python3
"""
Простой тест для проверки поддержки profile_id в sun_recommendations_worker
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
from queue_sender import send_sun_recommendation_to_queue

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Тестовые данные
TEST_TELEGRAM_ID = 999999999
TEST_PROFILE_NAME = "Тестовая Зайка"

async def create_test_data():
    """Создает тестовые данные"""
    try:
        async with get_session() as session:
            # Создаем пользователя
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
            
            # Создаем дополнительный профиль
            profile = AdditionalProfile(
                owner_user_id=user.user_id,
                full_name=TEST_PROFILE_NAME,
                gender=Gender.female,
                birth_date="1991-12-10",
                birth_time_local="14:30:00",
                birth_time_accuracy="exact",
                birth_city_input="Москва",
                birth_place_name="Москва, Россия",
                birth_country_code="RU",
                birth_lat=55.7558,
                birth_lon=37.6176,
                tzid="Europe/Moscow",
                tz_offset_minutes=180,
                birth_datetime_utc=datetime(1991, 12, 10, 11, 30, 0, tzinfo=timezone.utc),
                geo_provider="test",
                geo_provider_place_id="test_place_id",
                zodiac_sign="kozerog"
            )
            session.add(profile)
            await session.commit()
            
            # Создаем разбор Солнца для дополнительного профиля
            sun_prediction = Prediction(
                user_id=user.user_id,
                profile_id=profile.profile_id,
                planet=Planet.sun,
                prediction_type=PredictionType.paid,
                content="Test Sun Analysis",
                sun_analysis="Тестовый разбор Солнца для дополнительного профиля",
                llm_model="test",
                expires_at=None
            )
            session.add(sun_prediction)
            await session.commit()
            
            logger.info(f"✅ Созданы тестовые данные:")
            logger.info(f"  - Пользователь: {user.user_id}")
            logger.info(f"  - Дополнительный профиль: {profile.profile_id}")
            logger.info(f"  - Разбор Солнца: {sun_prediction.prediction_id}")
            
            return user, profile, sun_prediction
            
    except Exception as e:
        logger.error(f"❌ Ошибка создания тестовых данных: {e}")
        return None, None, None

async def test_sun_recommendations_queue(user, profile, sun_prediction):
    """Тестирует отправку запроса рекомендаций в очередь"""
    try:
        logger.info("💡 Тестируем отправку запроса рекомендаций...")
        
        # Отправляем запрос в очередь с profile_id
        success = await send_sun_recommendation_to_queue(
            prediction_id=sun_prediction.prediction_id,
            user_telegram_id=user.telegram_id,
            sun_analysis=sun_prediction.sun_analysis,
            profile_id=profile.profile_id
        )
        
        if success:
            logger.info("✅ Запрос рекомендаций успешно отправлен в очередь")
            logger.info(f"  - prediction_id: {sun_prediction.prediction_id}")
            logger.info(f"  - profile_id: {profile.profile_id}")
            logger.info(f"  - profile_name: {profile.full_name}")
            return True
        else:
            logger.error("❌ Не удалось отправить запрос рекомендаций")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки запроса: {e}")
        return False

async def test_without_profile_id(user, sun_prediction):
    """Тестирует отправку запроса без profile_id (основной профиль)"""
    try:
        logger.info("💡 Тестируем отправку запроса без profile_id...")
        
        # Отправляем запрос в очередь без profile_id
        success = await send_sun_recommendation_to_queue(
            prediction_id=sun_prediction.prediction_id,
            user_telegram_id=user.telegram_id,
            sun_analysis=sun_prediction.sun_analysis,
            profile_id=None
        )
        
        if success:
            logger.info("✅ Запрос рекомендаций (основной профиль) отправлен")
            return True
        else:
            logger.error("❌ Не удалось отправить запрос для основного профиля")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки запроса для основного профиля: {e}")
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
    logger.info("🚀 Начинаем тест поддержки profile_id в sun_recommendations_worker...")
    
    # Инициализируем подключение к БД
    init_engine()
    
    try:
        # 1. Создаем тестовые данные
        user, profile, sun_prediction = await create_test_data()
        if not all([user, profile, sun_prediction]):
            logger.error("❌ Не удалось создать тестовые данные")
            return
        
        # 2. Тестируем отправку с profile_id (дополнительный профиль)
        test1_success = await test_sun_recommendations_queue(user, profile, sun_prediction)
        
        # 3. Тестируем отправку без profile_id (основной профиль)
        test2_success = await test_without_profile_id(user, sun_prediction)
        
        if test1_success and test2_success:
            logger.info("🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
            logger.info("✅ Поддержка profile_id в sun_recommendations_worker работает")
        else:
            logger.error("❌ Некоторые тесты не прошли")
        
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

