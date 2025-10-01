#!/usr/bin/env python3
"""
Тестовый скрипт для проверки создания дополнительного профиля.

Этот скрипт тестирует:
1. Импорты всех модулей
2. Создание FSM состояний
3. Работу функций обработчиков
4. Интеграцию с базой данных
"""

import asyncio
import sys
import logging
from datetime import date, time

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_imports():
    """Тест 1: Проверка импортов"""
    print("🧪 Тест 1: Проверка импортов...")
    
    try:
        # Тестируем импорт основного модуля
        import main
        print("✅ main.py импортирован успешно")
        
        # Тестируем импорт обработчиков
        from handlers.additional_profile_handler import (
            AdditionalProfileForm,
            start_additional_profile_creation,
            handle_additional_name,
            zodiac_sign_ru_for_date,
            format_time_accuracy_message
        )
        print("✅ handlers.additional_profile_handler импортирован успешно")
        
        # Тестируем импорт моделей
        from models import AdditionalProfile, User, Gender, ZodiacSignRu
        print("✅ models импортированы успешно")
        
        # Тестируем импорт БД
        from db import get_session
        print("✅ db импортирован успешно")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        return False


async def test_fsm_states():
    """Тест 2: Проверка FSM состояний"""
    print("\n🧪 Тест 2: Проверка FSM состояний...")
    
    try:
        from handlers.additional_profile_handler import AdditionalProfileForm
        
        # Проверяем, что все состояния определены
        states = [
            AdditionalProfileForm.waiting_for_additional_name,
            AdditionalProfileForm.waiting_for_additional_birth_date,
            AdditionalProfileForm.waiting_for_additional_birth_city,
            AdditionalProfileForm.waiting_for_additional_birth_city_confirm,
            AdditionalProfileForm.waiting_for_additional_birth_time_accuracy,
            AdditionalProfileForm.waiting_for_additional_birth_time_local,
            AdditionalProfileForm.waiting_for_additional_birth_time_confirm,
            AdditionalProfileForm.waiting_for_additional_birth_time_approx_confirm,
            AdditionalProfileForm.waiting_for_additional_birth_time_unknown_confirm,
        ]
        
        print(f"✅ Найдено {len(states)} FSM состояний")
        
        # Проверяем уникальность состояний
        state_names = [state.state for state in states]
        unique_names = set(state_names)
        
        if len(state_names) == len(unique_names):
            print("✅ Все состояния уникальны")
        else:
            print("❌ Найдены дублирующиеся состояния")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Ошибка FSM состояний: {e}")
        return False


async def test_helper_functions():
    """Тест 3: Проверка вспомогательных функций"""
    print("\n🧪 Тест 3: Проверка вспомогательных функций...")
    
    try:
        from handlers.additional_profile_handler import (
            zodiac_sign_ru_for_date,
            format_time_accuracy_message
        )
        from models import ZodiacSignRu
        
        # Тест функции расчета знака зодиака
        test_date = date(1990, 6, 15)  # Близнецы
        zodiac = zodiac_sign_ru_for_date(test_date)
        
        if zodiac == ZodiacSignRu.bliznecy:
            print("✅ Функция zodiac_sign_ru_for_date работает корректно")
        else:
            print(f"❌ Неверный знак зодиака: ожидался {ZodiacSignRu.bliznecy}, получен {zodiac}")
            return False
        
        # Тест функции форматирования времени
        test_time = time(14, 30)
        
        exact_msg = format_time_accuracy_message("exact", test_time)
        if "точно 14:30" in exact_msg:
            print("✅ Функция format_time_accuracy_message работает корректно")
        else:
            print(f"❌ Неверное форматирование времени: {exact_msg}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Ошибка вспомогательных функций: {e}")
        return False


async def test_database_connection():
    """Тест 4: Проверка подключения к базе данных"""
    print("\n🧪 Тест 4: Проверка подключения к базе данных...")
    
    try:
        from db import get_session
        from models import User, AdditionalProfile
        
        async with get_session() as session:
            # Простая проверка подключения
            result = await session.execute("SELECT 1")
            if result.scalar() == 1:
                print("✅ Подключение к базе данных работает")
            else:
                print("❌ Проблема с подключением к базе данных")
                return False
                
        return True
        
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        return False


async def test_geocoding():
    """Тест 5: Проверка геокодирования"""
    print("\n🧪 Тест 5: Проверка геокодирования...")
    
    try:
        from geocoding import geocode_city_ru
        
        # Тест геокодирования
        result = await geocode_city_ru("Москва")
        
        if result and "place_name" in result and "lat" in result and "lon" in result:
            print(f"✅ Геокодирование работает: {result['place_name']}")
            return True
        else:
            print("❌ Проблема с геокодированием")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка геокодирования: {e}")
        return False


async def test_timezone_calculation():
    """Тест 6: Проверка расчета часовых поясов"""
    print("\n🧪 Тест 6: Проверка расчета часовых поясов...")
    
    try:
        from timezone_utils import resolve_timezone
        
        # Тест расчета часового пояса для Москвы
        result = resolve_timezone(
            lat=55.7558,
            lon=37.6176,
            local_date=date(1990, 6, 15),
            local_time=time(14, 30)
        )
        
        if result and hasattr(result, 'tzid') and hasattr(result, 'offset_minutes'):
            print(f"✅ Расчет часового пояса работает: {result.tzid}")
            return True
        else:
            print("❌ Проблема с расчетом часового пояса")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка расчета часового пояса: {e}")
        return False


async def run_all_tests():
    """Запуск всех тестов"""
    print("🚀 Запуск тестов создания дополнительного профиля\n")
    
    tests = [
        test_imports,
        test_fsm_states,
        test_helper_functions,
        test_database_connection,
        test_geocoding,
        test_timezone_calculation,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            result = await test()
            if result:
                passed += 1
        except Exception as e:
            print(f"❌ Неожиданная ошибка в тесте {test.__name__}: {e}")
    
    print(f"\n📊 Результаты тестирования: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты пройдены успешно! Система готова к работе.")
        return True
    else:
        print("⚠️ Некоторые тесты не пройдены. Требуется дополнительная настройка.")
        return False


if __name__ == "__main__":
    # Запускаем тесты
    result = asyncio.run(run_all_tests())
    sys.exit(0 if result else 1)
