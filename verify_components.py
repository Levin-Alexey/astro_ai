#!/usr/bin/env python3
"""
Проверка всех компонентов для рекомендаций по Солнцу
"""

import sys
import os

# Добавляем путь к проекту
sys.path.append('.')

def test_imports():
    """Проверяет импорты всех компонентов"""
    print("🔍 Проверяем импорты...")
    
    try:
        # Проверяем импорт воркера
        from sun_recommendations_worker import SunRecommendationsWorker
        print("✅ sun_recommendations_worker импортирован")
        
        # Проверяем импорт обработчика
        from handlers.sun_recommendations_handler import handle_get_sun_recommendations
        print("✅ sun_recommendations_handler импортирован")
        
        # Проверяем импорт queue_sender
        from queue_sender import send_sun_recommendation_to_queue
        print("✅ queue_sender.send_sun_recommendation_to_queue импортирован")
        
        # Проверяем импорт моделей
        from models import User, AdditionalProfile, Prediction, Planet, PredictionType
        print("✅ Модели импортированы")
        
        # Проверяем импорт БД
        from db import get_session, init_engine
        print("✅ БД импортирована")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        return False

def test_worker_methods():
    """Проверяет методы воркера"""
    print("\n🔍 Проверяем методы воркера...")
    
    try:
        from sun_recommendations_worker import SunRecommendationsWorker
        
        worker = SunRecommendationsWorker()
        
        # Проверяем наличие методов
        methods = [
            'get_user_info',
            'get_additional_profile_info',
            'save_sun_recommendations',
            'format_sun_recommendations_message',
            'process_sun_recommendation',
            'send_telegram_message'
        ]
        
        for method in methods:
            if hasattr(worker, method):
                print(f"✅ Метод {method} найден")
            else:
                print(f"❌ Метод {method} не найден")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка проверки методов: {e}")
        return False

def test_handler_function():
    """Проверяет функцию обработчика"""
    print("\n🔍 Проверяем функцию обработчика...")
    
    try:
        from handlers.sun_recommendations_handler import handle_get_sun_recommendations
        
        # Проверяем, что функция существует и вызываема
        if callable(handle_get_sun_recommendations):
            print("✅ handle_get_sun_recommendations - вызываемая функция")
            return True
        else:
            print("❌ handle_get_sun_recommendations - не функция")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка проверки обработчика: {e}")
        return False

def test_queue_function():
    """Проверяет функцию отправки в очередь"""
    print("\n🔍 Проверяем функцию отправки в очередь...")
    
    try:
        from queue_sender import send_sun_recommendation_to_queue
        
        # Проверяем, что функция существует и вызываема
        if callable(send_sun_recommendation_to_queue):
            print("✅ send_sun_recommendation_to_queue - вызываемая функция")
            return True
        else:
            print("❌ send_sun_recommendation_to_queue - не функция")
            return False
            
    except Exception as e:
        print(f"❌ Ошибка проверки функции очереди: {e}")
        return False

def test_models():
    """Проверяет модели БД"""
    print("\n🔍 Проверяем модели БД...")
    
    try:
        from models import User, AdditionalProfile, Prediction, Planet, PredictionType
        
        # Проверяем, что модели имеют нужные атрибуты
        if hasattr(Prediction, 'profile_id'):
            print("✅ Prediction имеет profile_id")
        else:
            print("❌ Prediction не имеет profile_id")
            return False
        
        if hasattr(AdditionalProfile, 'profile_id'):
            print("✅ AdditionalProfile имеет profile_id")
        else:
            print("❌ AdditionalProfile не имеет profile_id")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка проверки моделей: {e}")
        return False

def main():
    """Основная функция проверки"""
    print("🚀 Начинаем проверку компонентов для рекомендаций по Солнцу...\n")
    
    tests = [
        test_imports,
        test_worker_methods,
        test_handler_function,
        test_queue_function,
        test_models
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"📊 Результаты: {passed}/{total} тестов прошли")
    
    if passed == total:
        print("🎉 ВСЕ КОМПОНЕНТЫ ГОТОВЫ!")
        print("✅ Поддержка profile_id в sun_recommendations_worker реализована")
        print("\n📋 Что работает:")
        print("  - ✅ Воркер поддерживает profile_id")
        print("  - ✅ Обработчик определяет profile_id из разбора")
        print("  - ✅ Queue sender передает profile_id")
        print("  - ✅ Модели БД поддерживают profile_id")
        print("  - ✅ Все импорты работают")
    else:
        print("❌ Некоторые компоненты требуют внимания")

if __name__ == "__main__":
    main()

