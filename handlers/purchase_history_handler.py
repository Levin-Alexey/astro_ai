from aiogram import Router, types
 # Удалено: CallbackQuery, Command из aiogram.filters
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from db import get_session
from models import PlanetPayment, PaymentStatus, PaymentType, Planet, User

router = Router()

# Кнопка для возврата в личный кабинет
def get_back_to_profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="personal_cabinet")]
        ]
    )

# Форматирование одной записи платежа
def format_payment(payment: PlanetPayment) -> str:
    dt = payment.created_at.strftime('%d.%m.%Y %H:%M') if payment.created_at else "-"
    status = {
        PaymentStatus.pending: "🕒 В ожидании",
        PaymentStatus.completed: "✅ Оплачен",
        PaymentStatus.failed: "❌ Ошибка",
        PaymentStatus.refunded: "↩️ Возврат",
        PaymentStatus.processing: "⚙️ Обработка",
        PaymentStatus.analysis_failed: "⚠️ Ошибка разбора",
        PaymentStatus.delivered: "📦 Доставлен"
    }.get(payment.status, str(payment.status))
    
    if payment.payment_type == PaymentType.single_planet:
        planet = {
            Planet.moon: "Луна",
            Planet.sun: "Солнце",
            Planet.mercury: "Меркурий",
            Planet.venus: "Венера",
            Planet.mars: "Марс"
        }.get(payment.planet, str(payment.planet))
        type_str = f"Одна планета ({planet})"
    else:
        type_str = "Все планеты"
    amount = f"{payment.amount_kopecks // 100} руб. {payment.amount_kopecks % 100:02d} коп."
    return f"{dt}\nТип: {type_str}\nСумма: {amount}\nСтатус: {status}\n"

@router.callback_query(lambda c: c.data == "purchase_history")
async def purchase_history_handler(callback: CallbackQuery):
    telegram_id = callback.from_user.id
    async with get_session() as session:  # type: AsyncSession
        # Сначала находим пользователя по telegram_id
        user_result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден в базе данных")
            return
        
        # Теперь ищем платежи по внутреннему user_id
        result = await session.execute(
            select(PlanetPayment).where(PlanetPayment.user_id == user.user_id).order_by(PlanetPayment.created_at.desc())
        )
        payments = result.scalars().all()

    if not payments:
        text = "Покупок пока нет.\n\nВы можете приобрести разбор планет в этом меню."
    else:
        text = "Вот список твоих покупок 🛍👇🏼\n\n" + "\n".join(
            [f"⭐️ {p.created_at.strftime('%d.%m.%Y %H:%M') if p.created_at else '-'}\nТип: {'Одна планета (' + {Planet.moon: 'Луна', Planet.sun: 'Солнце', Planet.mercury: 'Меркурий', Planet.venus: 'Венера', Planet.mars: 'Марс'}.get(p.planet, str(p.planet)) + ')' if p.payment_type == PaymentType.single_planet else 'Все планеты'}\nСумма: {p.amount_kopecks // 100} руб. {p.amount_kopecks % 100:02d} коп.\nСтатус: {'🕒 В ожидании' if p.status == PaymentStatus.pending else '✅ Оплачен' if p.status == PaymentStatus.completed else '❌ Ошибка' if p.status == PaymentStatus.failed else '↩️ Возврат' if p.status == PaymentStatus.refunded else '⚙️ Обработка' if p.status == PaymentStatus.processing else '⚠️ Ошибка разбора' if p.status == PaymentStatus.analysis_failed else '📦 Доставлен' if p.status == PaymentStatus.delivered else str(p.status)}\n" for p in payments]
        )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❤️‍🩹 Служба заботы",
                    callback_data="support"
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Вернуться в личный кабинет",
                    callback_data="personal_cabinet"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        text,
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()
