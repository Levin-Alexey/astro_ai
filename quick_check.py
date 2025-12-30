#!/usr/bin/env python3
"""
Быстрая проверка системы платежей после исправлений
"""
import asyncio
from db import get_session
from models import User, PlanetPayment, Prediction, PaymentStatus
from sqlalchemy import select

async def quick_check():
    print("=" * 80)
    print("⚡ БЫСТРАЯ ПРОВЕРКА СИСТЕМЫ")
    print("=" * 80)
    
    async with get_session() as session:
        # 1. Пользователь
        user_result = await session.execute(
            select(User).where(User.telegram_id == 518337064)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            print("❌ Пользователь не найден")
            return False
        
        print(f"\n✅ Пользователь: {user.username}")
        
        # 2. Платежи
        payments_result = await session.execute(
            select(PlanetPayment)
            .where(PlanetPayment.user_id == user.user_id)
            .order_by(PlanetPayment.created_at.desc())
        )
        payments = payments_result.scalars().all()
        
        print(f"\n💰 ПЛАТЕЖИ:")
        if not payments:
            print("   ℹ️ Нет платежей (нормально, если ты не делал платеж)")
        else:
            for p in payments:
                status_emoji = "✅" if p.status == PaymentStatus.completed else "⚠️"
                print(f"   {status_emoji} {p.payment_id}: {p.status.value} ({p.amount_kopecks/100:.2f} RUB)")
                if p.status == PaymentStatus.pending:
                    print(f"      ⚠️  ОШИБКА: Статус все еще pending!")
        
        # 3. Предсказания
        predictions_result = await session.execute(
            select(Prediction)
            .where(Prediction.user_id == user.user_id)
            .order_by(Prediction.created_at.desc())
        )
        predictions = predictions_result.scalars().all()
        
        print(f"\n🔮 ПРЕДСКАЗАНИЯ:")
        if not predictions:
            print("   ℹ️ Нет предсказаний")
        else:
            for pred in predictions:
                has_sun = "✅" if pred.sun_analysis else "❌"
                has_merc = "✅" if pred.mercury_analysis else "❌"
                has_venus = "✅" if pred.venus_analysis else "❌"
                has_mars = "✅" if pred.mars_analysis else "❌"
                
                print(f"   {pred.planet.value}: {has_sun}Sun {has_merc}Merc {has_venus}Ven {has_mars}Mars")
        
        # 4. Итоговая проверка
        print("\n" + "=" * 80)
        print("📊 ИТОГОВЫЙ СТАТУС:")
        print("=" * 80)
        
        has_pending = any(p.status == PaymentStatus.pending for p in payments)
        has_completed = any(p.status == PaymentStatus.completed for p in payments)
        has_all_analyses = all(
            pred.sun_analysis and pred.mercury_analysis and 
            pred.venus_analysis and pred.mars_analysis
            for pred in predictions
        )
        
        if has_pending:
            print("❌ Проблема: Есть платежи со статусом 'pending'")
            return False
        
        if payments and not has_completed:
            print("❌ Проблема: Нет завершённых платежей")
            return False
        
        if payments and predictions and not has_all_analyses:
            print("⚠️  Внимание: Не все анализы созданы")
            return False
        
        if not payments and not predictions:
            print("ℹ️  Система чистая, готова к новому платежу")
            return True
        
        if payments and has_completed and (not predictions or has_all_analyses):
            print("✅ ВСЁ ХОРОШО! Система работает корректно")
            return True
        
        print("⚠️  Неизвестный статус")
        return None

if __name__ == "__main__":
    result = asyncio.run(quick_check())
    exit(0 if result else 1)
