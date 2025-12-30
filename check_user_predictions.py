#!/usr/bin/env python3
"""
Проверка статуса всех предсказаний и платежей пользователя
"""
import asyncio
from sqlalchemy import select, and_
from db import get_session
from models import (
    User, Prediction, PlanetPayment, PaymentStatus
)

async def check_user_data(user_id: int):
    """Проверить всё для пользователя"""
    async with get_session() as session:
        # 1. Проверим пользователя
        print(f"\n🔍 Проверка данных пользователя {user_id}...")
        user = await session.scalar(
            select(User).where(User.telegram_id == user_id)
        )
        
        if not user:
            print(f"❌ Пользователь {user_id} не найден!")
            return
            
        print(f"✅ Пользователь найден: {user.telegram_id}")
        print(f"   - ID: {user.user_id}")
        print(f"   - Имя: {user.first_name}")
        
        # 2. Проверим платежи
        print(f"\n💳 Платежи пользователя:")
        payments = await session.scalars(
            select(PlanetPayment).where(PlanetPayment.user_id == user.user_id)
        )
        payments_list = list(payments)
        
        if not payments_list:
            print("   ❌ Платежей не найдено")
        else:
            for payment in payments_list:
                status_emoji = "✅" if payment.status == PaymentStatus.completed else "⏳"
                amount_rub = payment.amount_kopecks / 100
                planet_str = payment.planet.value if payment.planet else "all_planets"
                print(f"   {status_emoji} {planet_str}: {amount_rub} RUB")
                print(f"      - ID: {payment.payment_id}")
                print(f"      - Статус: {payment.status}")
                print(f"      - Дата: {payment.created_at}")
        
        # 3. Проверим предсказания
        print(f"\n🌌 Предсказания пользователя:")
        predictions = await session.scalars(
            select(Prediction).where(Prediction.user_id == user.user_id)
        )
        predictions_list = list(predictions)
        
        if not predictions_list:
            print("   ❌ Предсказаний не найдено!")
            print("\n   ⚠️  ПРОБЛЕМА: Предсказания не были созданы")
            print("   Проверьте логи рабочих процессов (workers)")
        else:
            planets_status = {}
            for pred in predictions_list:
                planet = pred.planet or "moon"
                status_emoji = {
                    True: "✅",
                    False: "❌"
                }.get(pred.is_active, "❓")
                
                if planet not in planets_status:
                    planets_status[planet] = []
                planets_status[planet].append({
                    'id': pred.prediction_id,
                    'is_active': pred.is_active,
                    'emoji': status_emoji,
                    'created': pred.created_at,
                    'has_content': bool(pred.content or pred.sun_analysis or pred.moon_analysis or pred.mercury_analysis or pred.venus_analysis or pred.mars_analysis)
                })
            
            for planet, preds in planets_status.items():
                print(f"\n   {planet}:")
                for p in preds:
                    print(f"      {p['emoji']} ID: {p['id']}, Active: {p['is_active']}")
                    print(f"         Created: {p['created']}")
                    
                    # Проверим, есть ли content
                    if not p.get('has_content'):
                        print(f"         ⚠️  Контент не заполнен")
        
        # 4. Итоговый статус
        print(f"\n{'='*60}")
        if not predictions_list:
            print("❌ ПРОБЛЕМА: Предсказания не созданы")
            print("\nЧто проверить:")
            print("1. Логи sun_worker.py")
            print("2. Логи moon_worker.py")
            print("3. Логи mercury_worker.py")
            print("4. Логи venus_worker.py")
            print("5. Логи mars_worker.py")
            print("\nВозможные причины:")
            print("- Рабочие процессы не запущены")
            print("- Очередь сообщений не работает")
            print("- Ошибка при обработке запроса")
        else:
            completed = sum(1 for p in predictions_list if p.is_active and p.content)
            pending = sum(1 for p in predictions_list if p.is_active and not p.content)
            inactive = sum(1 for p in predictions_list if not p.is_active)
            
            print(f"✅ Создано: {len(predictions_list)} предсказаний")
            print(f"   ✅ Завершено (с контентом): {completed}")
            print(f"   ⏳ В процессе (без контента): {pending}")
            print(f"   ❌ Неактивные: {inactive}")
            
            if inactive > 0 or pending > 0:
                print("\n⚠️  Разборы обрабатываются - проверьте логи workers")

async def main():
    from config import DATABASE_URL
    from db import init_engine
    
    init_engine()
    
    # Проверяем пользователя из логов
    user_id = 1151513083
    await check_user_data(user_id)

if __name__ == "__main__":
    asyncio.run(main())
