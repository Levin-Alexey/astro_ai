"""
Скрипт для очистки и исправления данных платежей пользователя
"""
import asyncio
from db import get_session
from models import User, PlanetPayment, Prediction, PaymentStatus
from sqlalchemy import select, delete

async def cleanup_and_reset():
    print("=" * 80)
    print("🧹 ОЧИСТКА И РЕСЕТ ДАННЫХ ПЛАТЕЖЕЙ")
    print("=" * 80)
    
    async with get_session() as session:
        # Найти пользователя
        user_result = await session.execute(
            select(User).where(User.telegram_id == 518337064)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            print("❌ Пользователь не найден")
            return
        
        print(f"\n✅ Найден пользователь: {user.username} (ID: {user.user_id})")
        
        # Удалить старые платежи
        print("\n🗑️ Удаление старых платежей...")
        delete_query = delete(PlanetPayment).where(
            PlanetPayment.user_id == user.user_id
        )
        result = await session.execute(delete_query)
        await session.commit()
        print(f"✅ Удалено платежей: {result.rowcount}")
        
        # Удалить старые предсказания
        print("\n🗑️ Удаление старых предсказаний...")
        delete_query = delete(Prediction).where(
            Prediction.user_id == user.user_id
        )
        result = await session.execute(delete_query)
        await session.commit()
        print(f"✅ Удалено предсказаний: {result.rowcount}")
        
        print("\n" + "=" * 80)
        print("✅ ОЧИСТКА ЗАВЕРШЕНА")
        print("=" * 80)
        print("\nТеперь можешь заново запустить платеж для пользователя")
        print("и система должна корректно обработать его")

if __name__ == "__main__":
    asyncio.run(cleanup_and_reset())
