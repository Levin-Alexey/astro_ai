#!/usr/bin/env python3
"""
Детальная проверка статуса обработки предсказаний пользователя
"""
import asyncio
from sqlalchemy import select
from db import get_session
from models import (
    User, Prediction, Planet, PlanetPayment, PaymentStatus, PaymentType
)

async def check_processing_status(user_id: int):
    """Проверить статус всех этапов обработки"""
    async with get_session() as session:
        # 1. Находим пользователя
        user = await session.scalar(
            select(User).where(User.telegram_id == user_id)
        )
        
        if not user:
            print(f"❌ Пользователь {user_id} не найден!")
            return
        
        print(f"\n{'='*70}")
        print(f"👤 ПОЛЬЗОВАТЕЛЬ: {user.first_name} (ID: {user.user_id}, TelegramID: {user_id})")
        print(f"{'='*70}")
        
        # 2. Проверяем платежи
        print(f"\n💳 ПЛАТЕЖИ:")
        payments = await session.scalars(
            select(PlanetPayment).where(PlanetPayment.user_id == user.user_id)
        )
        payments_list = list(payments)
        
        for payment in payments_list:
            planet_str = payment.planet.value if payment.planet else "all_planets"
            print(f"\n   🔹 {planet_str.upper()}")
            print(f"      - Payment ID: {payment.payment_id}")
            print(f"      - Status: {payment.status.value}")
            print(f"      - Amount: {payment.amount_kopecks / 100} RUB")
            print(f"      - Created: {payment.created_at}")
            print(f"      - Completed: {payment.completed_at}")
        
        # 3. Проверяем предсказания
        print(f"\n🌌 ПРЕДСКАЗАНИЯ:")
        predictions = await session.scalars(
            select(Prediction).where(Prediction.user_id == user.user_id)
        )
        predictions_list = list(predictions)
        
        if not predictions_list:
            print("   ❌ НЕ СОЗДАНЫ ВООБЩЕ!")
        else:
            # Группируем по планетам
            by_planet = {}
            for pred in predictions_list:
                planet = pred.planet.value if pred.planet else "unknown"
                if planet not in by_planet:
                    by_planet[planet] = []
                by_planet[planet].append(pred)
            
            for planet, preds in sorted(by_planet.items()):
                print(f"\n   🔹 {planet.upper()}:")
                for pred in preds:
                    status = "✅ ГОТОВО" if pred.content else "⏳ ОБРАБОТКА"
                    print(f"      {status} ID: {pred.prediction_id}")
                    print(f"         - Created: {pred.created_at}")
                    print(f"         - Is Active: {pred.is_active}")
                    print(f"         - Has Content: {bool(pred.content)}")
                    if pred.content:
                        print(f"         - Content length: {len(pred.content)} chars")
                    else:
                        print(f"         - Content: MISSING (LLM не обработал ещё)")
        
        # 4. Итоговый анализ
        print(f"\n{'='*70}")
        print("📊 АНАЛИЗ:")
        
        if not payments_list:
            print("   ❌ ПРОБЛЕМА 1: Платежи не найдены")
        else:
            completed_payments = sum(1 for p in payments_list if p.status == PaymentStatus.completed)
            print(f"   ✅ Платежи: {completed_payments}/{len(payments_list)} завершены")
            
            if completed_payments < len(payments_list):
                print(f"      ⚠️  {len(payments_list) - completed_payments} платежей ещё не обработано")
        
        if not predictions_list:
            print("   ❌ ПРОБЛЕМА 2: Предсказания не созданы")
            print("      → Webhook не запустил астрологический анализ")
            print("      → Проверьте логи all_planets_handler.py")
        else:
            with_content = sum(1 for p in predictions_list if p.content)
            without_content = len(predictions_list) - with_content
            
            print(f"   ✅ Предсказания: {len(predictions_list)} созданы")
            print(f"      ✅ Готовы: {with_content}")
            print(f"      ⏳ В обработке (ждут LLM): {without_content}")
            
            if without_content > 0:
                print("\n      ⚠️  РАБОЧИЕ ПРОЦЕССЫ РАБОТАЮТ:")
                print("      - Проверьте логи sun_worker.py, mercury_worker.py и т.д.")
                print("      - Проверьте очередь RabbitMQ")
                print("      - Убедитесь, что воркеры запущены на сервере")

async def main():
    from db import init_engine
    init_engine()
    
    user_id = 1151513083
    await check_processing_status(user_id)

if __name__ == "__main__":
    asyncio.run(main())
