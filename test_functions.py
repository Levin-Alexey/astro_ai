#!/usr/bin/env python3
"""
Тест функций дополнительного профиля
"""

print("🧪 Тестирование функций дополнительного профиля...")

try:
    # Тест 1: Проверка функции расчета знака зодиака
    print("\n1. Тест функции zodiac_sign_ru_for_date...")
    from handlers.additional_profile_handler import zodiac_sign_ru_for_date
    from models import ZodiacSignRu
    from datetime import date
    
    test_date = date(1990, 6, 15)  # Близнецы
    zodiac = zodiac_sign_ru_for_date(test_date)
    
    print(f"Дата: {test_date}")
    print(f"Знак зодиака: {zodiac}")
    
    if zodiac == ZodiacSignRu.bliznecy:
        print("✅ Функция zodiac_sign_ru_for_date работает корректно")
    else:
        print(f"❌ Ошибка: ожидался {ZodiacSignRu.bliznecy}, получен {zodiac}")
    
    # Тест 2: Проверка функции форматирования времени
    print("\n2. Тест функции format_time_accuracy_message...")
    from handlers.additional_profile_handler import format_time_accuracy_message
    from datetime import time
    
    test_time = time(14, 30)
    
    exact_msg = format_time_accuracy_message("exact", test_time)
    approx_msg = format_time_accuracy_message("approx", test_time)
    unknown_msg = format_time_accuracy_message("unknown", None)
    
    print(f"Точное время: {exact_msg}")
    print(f"Примерное время: {approx_msg}")
    print(f"Неизвестное время: {unknown_msg}")
    
    if "точно 14:30" in exact_msg and "примерно 14:30" in approx_msg and "неизвестно" in unknown_msg:
        print("✅ Функция format_time_accuracy_message работает корректно")
    else:
        print("❌ Ошибка в функции format_time_accuracy_message")
    
    # Тест 3: Проверка FSM состояний
    print("\n3. Тест FSM состояний...")
    from handlers.additional_profile_handler import AdditionalProfileForm
    
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
    
    print(f"Найдено {len(states)} FSM состояний:")
    for i, state in enumerate(states, 1):
        print(f"  {i}. {state.state}")
    
    # Проверяем уникальность
    state_names = [state.state for state in states]
    unique_names = set(state_names)
    
    if len(state_names) == len(unique_names):
        print("✅ Все FSM состояния уникальны")
    else:
        print("❌ Найдены дублирующиеся FSM состояния")
    
    print("\n🎉 Тестирование функций завершено успешно!")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
