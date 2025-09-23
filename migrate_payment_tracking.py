"""
Миграция для добавления новых статусов платежей и полей отслеживания
"""

import logging
from sqlalchemy import text
from db import get_session

logger = logging.getLogger(__name__)


async def migrate_payment_tracking():
    """Добавляет новые статусы и поля для отслеживания платежей"""
    try:
        async with get_session() as session:
            # Добавляем новые значения в enum PaymentStatus
            await session.execute(text("""
                ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'processing';
                ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'analysis_failed';
                ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'delivered';
            """))
            
            # Добавляем новые поля в таблицу planet_payments
            try:
                await session.execute(text("""
                    ALTER TABLE planet_payments 
                    ADD COLUMN IF NOT EXISTS analysis_started_at TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS analysis_completed_at TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS retry_count BIGINT DEFAULT 0 NOT NULL,
                    ADD COLUMN IF NOT EXISTS last_error TEXT;
                """))
                logger.info("Added new payment tracking fields")
            except Exception as e:
                logger.warning(f"Some fields might already exist: {e}")
            
            await session.commit()
            logger.info("Payment tracking migration completed successfully")
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate_payment_tracking())