"""
Диагностический скрипт для проверки проблемы с платежами и анализами
"""
import asyncio
from datetime import datetime, timezone
from db import get_session
from models import User, PlanetPayment, Prediction, PaymentStatus, PaymentType
from sqlalchemy import select

async def diagnose():
    print("=" * 80)
    print("🔍 ДИАГНОСТИКА СИСТЕМЫ ПЛАТЕЖЕЙ И АНАЛИЗОВ")
    print("=" * 80)
    
    async with get_session() as session:
        # 1. Найти пользователя
        print("\n1️⃣ ПОИСК ПОЛЬЗОВАТЕЛЯ")
        print("-" * 80)
        user_result = await session.execute(
            select(User).where(User.telegram_id == 518337064)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            print("❌ Пользователь не найден!")
            return
        
        print(f"✅ Найден пользователь:")
        print(f"   - Internal user_id: {user.user_id}")
        print(f"   - Telegram ID: {user.telegram_id}")
        print(f"   - Username: {user.username}")
        print(f"   - Joined: {user.joined_at}")
        
        # 2. Проверить платежи
        print("\n2️⃣ ПРОВЕРКА ПЛАТЕЖЕЙ")
        print("-" * 80)
        
        payments_result = await session.execute(
            select(PlanetPayment)
            .where(PlanetPayment.user_id == user.user_id)
            .order_by(PlanetPayment.created_at.desc())
        )
        payments = payments_result.scalars().all()
        
        print(f"Всего платежей: {len(payments)}\n")
        
        for i, p in enumerate(payments, 1):
            print(f"Платеж #{i}:")
            print(f"   - Payment ID: {p.payment_id}")
            print(f"   - Payment Type: {p.payment_type.value}")
            print(f"   - Planet: {p.planet.value if p.planet else 'None (all_planets)'}")
            print(f"   - Status: {p.status.value}")
            print(f"   - Amount: {p.amount_kopecks / 100:.2f} RUB")
            print(f"   - External Payment ID: {p.external_payment_id}")
            print(f"   - Created: {p.created_at}")
            print(f"   - Completed: {p.completed_at}")
            print(f"   - Profile ID: {p.profile_id}")
            
            # Проверить статус
            if p.status == PaymentStatus.pending:
                print(f"   ⚠️  ПРОБЛЕМА: Статус остался 'pending'!")
            elif p.status == PaymentStatus.completed:
                print(f"   ✅ Статус правильный: 'completed'")
            else:
                print(f"   ⚠️  Статус: {p.status.value}")
            print()
        
        # 3. Проверить предсказания
        print("\n3️⃣ ПРОВЕРКА ПРЕДСКАЗАНИЙ")
        print("-" * 80)
        
        predictions_result = await session.execute(
            select(Prediction)
            .where(Prediction.user_id == user.user_id)
            .order_by(Prediction.created_at.desc())
        )
        predictions = predictions_result.scalars().all()
        
        print(f"Всего предсказаний: {len(predictions)}\n")
        
        for i, pred in enumerate(predictions, 1):
            print(f"Предсказание #{i}:")
            print(f"   - Prediction ID: {pred.prediction_id}")
            print(f"   - Planet: {pred.planet.value}")
            print(f"   - Type: {pred.prediction_type.value}")
            print(f"   - Created: {pred.created_at}")
            print(f"   - Profile ID: {pred.profile_id}")
            
            # Проверить анализы
            analyses = {
                'sun': pred.sun_analysis,
                'mercury': pred.mercury_analysis,
                'venus': pred.venus_analysis,
                'mars': pred.mars_analysis
            }
            
            print(f"   - Анализы:")
            for planet_name, analysis in analyses.items():
                if analysis:
                    length = len(analysis)
                    preview = analysis[:50].replace('\n', ' ') + "..."
                    print(f"     ✅ {planet_name:8s}: {length:5d} символов | {preview}")
                else:
                    print(f"     ❌ {planet_name:8s}: НЕТ ДАННЫХ")
            
            print()
        
        # 4. Анализ проблемы
        print("\n4️⃣ АНАЛИЗ ПРОБЛЕМЫ")
        print("-" * 80)
        
        if payments:
            # Проверка 1: Статус платежей
            pending_payments = [p for p in payments if p.status == PaymentStatus.pending]
            completed_payments = [p for p in payments if p.status == PaymentStatus.completed]
            
            print(f"\n📊 Статистика платежей:")
            print(f"   - Pending (ожидание): {len(pending_payments)}")
            print(f"   - Completed (завершено): {len(completed_payments)}")
            
            if pending_payments:
                print(f"\n❌ ПРОБЛЕМА: Есть платежи со статусом 'pending'")
                print(f"   Причины:")
                print(f"   1. Webhook обработал платеж, но статус не обновился")
                print(f"   2. Функция update_payment_status() в webhook_server.py не была вызвана")
                print(f"   3. Ошибка при обновлении статуса в БД")
            
            # Проверка 2: Анализы
            all_planets_payments = [p for p in payments if p.payment_type == PaymentType.all_planets]
            
            if all_planets_payments:
                latest_all_planets_payment = all_planets_payments[0]
                payment_time = latest_all_planets_payment.completed_at or latest_all_planets_payment.created_at
                
                # Найти предсказания после платежа
                relevant_predictions = [
                    p for p in predictions
                    if p.created_at >= payment_time
                ]
                
                print(f"\n📊 Анализ планет после платежа 'all_planets':")
                print(f"   - Платеж завершен: {payment_time}")
                print(f"   - Найдено предсказаний после платежа: {len(relevant_predictions)}")
                
                if relevant_predictions:
                    latest_pred = relevant_predictions[0]
                    has_analyses = {
                        'sun': bool(latest_pred.sun_analysis),
                        'mercury': bool(latest_pred.mercury_analysis),
                        'venus': bool(latest_pred.venus_analysis),
                        'mars': bool(latest_pred.mars_analysis)
                    }
                    
                    completed = sum(has_analyses.values())
                    print(f"   - Анализы в последнем предсказании: {completed}/4")
                    
                    for planet, has_analysis in has_analyses.items():
                        status = "✅" if has_analysis else "❌"
                        print(f"     {status} {planet}")
                    
                    if completed < 4:
                        print(f"\n❌ ПРОБЛЕМА: Не все анализы были созданы!")
                        print(f"   Причины:")
                        print(f"   1. Воркеры (sun_worker, mercury_worker и т.д.) не запустились")
                        print(f"   2. Ошибка в astrology_handlers.py при запуске анализа")
                        print(f"   3. Ошибка при сохранении анализа в БД")
                        print(f"   4. Функция handle_payment_success() не была вызвана")
                        print(f"   5. Функция _start_planet_analysis() упала с ошибкой")
                else:
                    print(f"\n❌ КРИТИЧЕСКАЯ ПРОБЛЕМА: Нет предсказаний после платежа!")
                    print(f"   Это означает, что запуск анализов не произошел")
        
        # 5. Рекомендации
        print("\n5️⃣ РЕКОМЕНДАЦИИ")
        print("-" * 80)
        print("""
1. Проверьте логи webhook_server.py:
   - Ищите сообщение: "🔥 WEBHOOK RECEIVED: payment.succeeded"
   - Ищите сообщение: "🔥 Updating payment status"
   - Ищите ошибки: "❌ Error updating payment status"

2. Проверьте логи all_planets_handler.py:
   - Ищите сообщение: "🌌 Начинаем последовательный разбор"
   - Ищите сообщение: "🚀 Запуск анализа"
   - Ищите ошибки: "❌ Ошибка при обработке успешной оплаты"

3. Проверьте инициализацию handler'а:
   - убедитесь, что AllPlanetsHandler инициализирован в main.py
   - убедитесь, что await all_planets_handler.initialize() был вызван

4. Проверьте логи астрологических обработчиков:
   - Ищите ошибки при запуске start_sun_analysis и других функций

5. Проверьте очередь сообщений (RabbitMQ):
   - Убедитесь, что сообщения попадают в очередь
   - Убедитесь, что воркеры обрабатывают сообщения

6. Если всё остальное в порядке, может быть проблема:
   - С асинхронностью (asyncio.create_task не завершился до выхода)
   - С обработкой исключений (ошибка скрывается)
   - С БД (транзакция не коммитилась)
        """)

if __name__ == "__main__":
    asyncio.run(diagnose())
