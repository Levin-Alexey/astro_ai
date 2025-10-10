from aiogram import Router, types
from aiogram.filters import CallbackQuery, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from db import get_session
from models import PlanetPayment, PaymentStatus, PaymentType, Planet

router = Router()

# Кнопка для возврата в личный кабинет
def get_back_to_profile_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="profile_menu")]
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
    user_id = callback.from_user.id
    async with get_session() as session:  # type: AsyncSession
        result = await session.execute(
            select(PlanetPayment).where(PlanetPayment.user_id == user_id).order_by(PlanetPayment.created_at.desc())
        )
        payments = result.scalars().all()
    if not payments:
        text = "У вас пока нет покупок.\n\nВы можете приобрести разбор планет в этом меню."
    else:
        text = "<b>История покупок:</b>\n\n" + "\n---------------------\n".join(format_payment(p) for p in payments)
    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_profile_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()
