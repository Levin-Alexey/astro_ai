"""
SQLAlchemy модели для базы данных проекта.

Соответствуют предоставленной схеме PostgreSQL:
- Тип gender как ENUM('male','female','other','unknown')
- Таблица users с полями, CHECK-ограничениями и индексами

Требования: SQLAlchemy 2.0+
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from datetime import datetime, date, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    SmallInteger,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM, DOUBLE_PRECISION
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncEngine


class Base(DeclarativeBase):
    pass


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"
    unknown = "unknown"

class ZodiacSignRu(str, Enum):
    oven = "Овен"
    telec = "Телец"
    bliznecy = "Близнецы"
    rak = "Рак"
    lev = "Лев"
    deva = "Дева"
    vesy = "Весы"
    skorpion = "Скорпион"
    strelec = "Стрелец"
    kozerog = "Козерог"
    vodolei = "Водолей"
    ryby = "Рыбы"


class User(Base):
    __tablename__ = "users"

    # PK
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Telegram
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(Text)
    first_name: Mapped[Optional[str]] = mapped_column(Text)
    last_name: Mapped[Optional[str]] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(Text, server_default=text("'ru'"))
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    consent_given_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Профиль для астрологии
    full_name: Mapped[Optional[str]] = mapped_column(Text)
    gender: Mapped[Gender] = mapped_column(
        PG_ENUM(Gender, name="gender", create_type=False, native_enum=True),
        server_default=text("'unknown'"),
        nullable=False,
    )

    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    birth_time_local: Mapped[Optional[time]] = mapped_column(Time)
    birth_time_accuracy: Mapped[str] = mapped_column(
        Text, server_default=text("'exact'"), nullable=False
    )
    unknown_time_strategy: Mapped[Optional[str]] = mapped_column(Text)

    # Что ввёл пользователь и что вернул API
    birth_city_input: Mapped[Optional[str]] = mapped_column(Text)
    birth_place_name: Mapped[Optional[str]] = mapped_column(Text)
    birth_country_code: Mapped[Optional[str]] = mapped_column(Text)
    birth_lat: Mapped[Optional[float]] = mapped_column(DOUBLE_PRECISION)
    birth_lon: Mapped[Optional[float]] = mapped_column(DOUBLE_PRECISION)
    tzid: Mapped[Optional[str]] = mapped_column(Text)
    tz_offset_minutes: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # Предрасчитанный момент в UTC (заполняем при точном времени)
    birth_datetime_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Метаданные гео-провайдера
    geo_provider: Mapped[Optional[str]] = mapped_column(Text)
    geo_provider_place_id: Mapped[Optional[str]] = mapped_column(Text)

    # Служебное
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Знак зодиака (рус.)
    zodiac_sign: Mapped[Optional[ZodiacSignRu]] = mapped_column(
        PG_ENUM(
            ZodiacSignRu,
            name="zodiac_sign_ru",
            create_type=False,
            native_enum=True,
            # Важно: используем русские значения Enum как значения PostgreSQL ENUM,
            # иначе SQLAlchemy по умолчанию отправляет имена (oven, bliznecy, ...)
            values_callable=lambda enum: [e.value for e in enum],
            validate_strings=True,
        )
    )

    # Ограничения таблицы (CHECK)
    __table_args__ = (
        # Валидность пары координат
        CheckConstraint(
            "(birth_lat IS NULL AND birth_lon IS NULL) OR "
            "(birth_lat BETWEEN -90 AND 90 AND birth_lon BETWEEN -180 AND 180)",
            name="coord_pair_valid",
        ),
        # Допустимые значения birth_time_accuracy
        CheckConstraint(
            "birth_time_accuracy IN ('exact','approx','unknown')",
            name="birth_time_accuracy_valid",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - вспомогательное
        return f"<User id={self.user_id} tg={self.telegram_id} username={self.username!r}>"


# Индексы (соответствуют заданным)
Index("users_last_seen_idx", User.last_seen_at.desc())
Index("users_birth_utc_idx", User.birth_datetime_utc)
Index("users_tg_username_idx", func.lower(User.username))
Index("users_zodiac_idx", User.zodiac_sign)


async def create_all(engine: AsyncEngine) -> None:
    """Создать все таблицы по моделям (для первичной инициализации без Alembic).

    Примечание: ENUM gender должен существовать в БД. Если его нет — создайте вручную
    миграцией Alembic или через: CREATE TYPE gender AS ENUM ('male','female','other','unknown');
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
