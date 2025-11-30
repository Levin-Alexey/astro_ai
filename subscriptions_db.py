from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Subscription, SubscriptionPayment, User, PaymentStatus
from db import get_session # Используем существующую функцию для получения сессии

# --- CRUD операции для подписок ---

async def get_active_subscription(session: AsyncSession, user_id: int) -> Optional[Subscription]:
    """
    Получает активную подписку пользователя.
    """
    now = datetime.now()
    result = await session.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.end_date > now,
            Subscription.is_active == True
        )
        .order_by(Subscription.end_date.desc()) # Получаем самую свежую
    )
    return result.scalars().first()


async def create_or_update_subscription(
    session: AsyncSession,
    user_id: int,
    duration_months: int = 1
) -> Subscription:
    """
    Создает новую подписку или продлевает существующую.
    """
    now = datetime.now()
    existing_sub = await get_active_subscription(session, user_id)

    if existing_sub:
        # Продлеваем существующую подписку
        # Если текущая дата уже после end_date, то отсчитываем от now, иначе от end_date
        new_start_date = max(now, existing_sub.end_date)
        # Упрощенно 30 дней/месяц. В реальном проекте лучше использовать relativedelta из dateutil
        existing_sub.end_date = new_start_date + timedelta(days=30 * duration_months) 
        existing_sub.is_active = True
        subscription = existing_sub
    else:
        # Создаем новую подписку
        new_start_date = now
        end_date = new_start_date + timedelta(days=30 * duration_months)
        subscription = Subscription(
            user_id=user_id,
            start_date=new_start_date,
            end_date=end_date,
            is_active=True
        )
        session.add(subscription)
    
    await session.flush() # Для получения ID, если новый объект
    return subscription


async def record_subscription_payment(
    session: AsyncSession,
    user_id: int,
    amount_kopecks: int,
    external_payment_id: Optional[str] = None,
    payment_url: Optional[str] = None,
    status: PaymentStatus = PaymentStatus.pending
) -> SubscriptionPayment:
    """
    Записывает информацию о платеже за подписку.
    """
    payment = SubscriptionPayment(
        user_id=user_id,
        amount_kopecks=amount_kopecks,
        external_payment_id=external_payment_id,
        payment_url=payment_url,
        status=status,
        created_at=datetime.now()
    )
    session.add(payment)
    await session.flush()
    return payment


async def get_user_id_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[int]:
    """Получает user_id по telegram_id"""
    result = await session.execute(select(User.user_id).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def update_subscription_payment_status(
    session: AsyncSession,
    external_payment_id: str,
    status: PaymentStatus
) -> Optional[SubscriptionPayment]:
    """Обновляет статус платежа подписки"""
    result = await session.execute(
        select(SubscriptionPayment).where(SubscriptionPayment.external_payment_id == external_payment_id)
    )
    payment = result.scalar_one_or_none()
    if payment:
        payment.status = status
        if status == PaymentStatus.completed:
            payment.completed_at = datetime.now()
        # await session.flush() # flush вызывается при коммите сессии в контекстном менеджере
    return payment

