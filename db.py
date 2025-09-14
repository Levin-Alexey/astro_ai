from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text

from config import DATABASE_URL


engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def init_engine() -> None:
    global engine, SessionLocal
    if engine is None:
        engine = create_async_engine(
            DATABASE_URL, echo=False, pool_pre_ping=True
        )
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def dispose_engine() -> None:
    global engine
    if engine is not None:
        await engine.dispose()
        engine = None


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    if SessionLocal is None:
        init_engine()
    assert SessionLocal is not None  # for type checker
    session = SessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def ensure_gender_enum(engine: AsyncEngine) -> None:
    """Создаёт тип ENUM gender в БД, если он отсутствует.

    Не использует CREATE TYPE IF NOT EXISTS для совместимости, вместо этого
    проверяет наличие через системные каталоги.
    """
    async with engine.begin() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_type WHERE typname = 'gender' LIMIT 1")
        )
        if not exists:
            await conn.execute(
                text(
                    "CREATE TYPE gender AS ENUM "
                    "('male','female','other','unknown')"
                )
            )


async def ensure_birth_date_nullable(engine: AsyncEngine) -> None:
    """Снимает NOT NULL с столбца users.birth_date,
    если ограничение установлено.

    Нужно, чтобы создавать профиль пользователя на /start до заполнения
    анкеты.
    """
    check_sql = text(
        """
        SELECT a.attnotnull
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE c.relname = 'users' AND a.attname = 'birth_date' "
        "AND n.nspname = 'public'"
        """
    )
    async with engine.begin() as conn:
        attnotnull = await conn.scalar(check_sql)
        if attnotnull:
            await conn.execute(
                text(
                    "ALTER TABLE public.users "
                    "ALTER COLUMN birth_date DROP NOT NULL"
                )
            )


async def ensure_zodiac_enum_ru(engine: AsyncEngine) -> None:
    """Создаёт ENUM тип zodiac_sign_ru с русскими названиями знаков зодиака,
    если отсутствует."""
    async with engine.begin() as conn:
        exists = await conn.scalar(
            text(
                "SELECT 1 FROM pg_type WHERE typname = 'zodiac_sign_ru' "
                "LIMIT 1"
            )
        )
        if not exists:
            await conn.execute(
                text(
                    "CREATE TYPE zodiac_sign_ru AS ENUM ("
                    "'Овен','Телец','Близнецы','Рак','Лев','Дева',"
                    "'Весы','Скорпион','Стрелец','Козерог','Водолей','Рыбы'"
                    ")"
                )
            )


async def ensure_planet_enum(engine: AsyncEngine) -> None:
    """Создаёт ENUM тип planet для планет, если отсутствует."""
    async with engine.begin() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_type WHERE typname = 'planet' LIMIT 1")
        )
        if not exists:
            await conn.execute(
                text(
                    "CREATE TYPE planet AS ENUM "
                    "('moon','sun','mercury','venus','mars')"
                )
            )


async def ensure_prediction_type_enum(engine: AsyncEngine) -> None:
    """Создаёт ENUM тип prediction_type для типов предсказаний,
    если отсутствует."""
    async with engine.begin() as conn:
        exists = await conn.scalar(
            text(
                "SELECT 1 FROM pg_type WHERE typname = 'prediction_type' "
                "LIMIT 1"
            )
        )
        if not exists:
            await conn.execute(
                text(
                    "CREATE TYPE prediction_type AS ENUM "
                    "('free','paid')"
                )
            )
