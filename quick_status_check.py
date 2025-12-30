#!/usr/bin/env python3
"""
Быстрая проверка статуса после исправления ошибки в sun_worker
"""
import asyncio
from sqlalchemy import select
from db import get_session
from models import User, Prediction

async def quick_check():
    async with get_session() as session:
        user = await session.scalar(
            select(User).where(User.telegram_id == 1151513083)
        )
        
        if not user:
            print("❌ Пользователь не найден")
            return
        
        predictions = await session.scalars(
            select(Prediction).where(Prediction.user_id == user.user_id)
        )
        
        preds = list(predictions)
        with_content = sum(1 for p in preds if p.content)
        
        print(f"\n📊 Статус предсказаний пользователя {user.first_name}:")
        print(f"   Всего: {len(preds)}")
        print(f"   ✅ Готовых (с контентом): {with_content}")
        print(f"   ⏳ Обрабатывается: {len(preds) - with_content}")
        
        if len(preds) - with_content == 0:
            print("\n   🎉 ВСЕ РАЗБОРЫ ГОТОВЫ!")
        else:
            print(f"\n   ⏳ Ждём обработки воркерами...")

async def main():
    from db import init_engine
    init_engine()
    await quick_check()

if __name__ == "__main__":
    asyncio.run(main())
