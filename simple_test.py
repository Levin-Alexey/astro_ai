#!/usr/bin/env python3
"""
Простой тест для проверки импортов
"""

print("🧪 Тестирование импортов...")

try:
    print("1. Импорт models...")
    from models import AdditionalProfile, User, Gender, ZodiacSignRu
    print("✅ models импортированы успешно")
    
    print("2. Импорт handlers...")
    from handlers.additional_profile_handler import AdditionalProfileForm
    print("✅ handlers импортированы успешно")
    
    print("3. Проверка FSM состояний...")
    states = [
        AdditionalProfileForm.waiting_for_additional_name,
        AdditionalProfileForm.waiting_for_additional_birth_date,
        AdditionalProfileForm.waiting_for_additional_birth_city,
    ]
    print(f"✅ Найдено {len(states)} FSM состояний")
    
    print("4. Импорт геокодирования...")
    from geocoding import geocode_city_ru
    print("✅ geocoding импортирован успешно")
    
    print("5. Импорт timezone_utils...")
    from timezone_utils import resolve_timezone
    print("✅ timezone_utils импортирован успешно")
    
    print("\n🎉 Все основные импорты работают корректно!")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
