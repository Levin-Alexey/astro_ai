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


class Planet(str, Enum):
    moon = "moon"  # Луна - бесплатная
    sun = "sun"    # Солнце - платная
    mercury = "mercury"  # Меркурий - платная
    venus = "venus"      # Венера - платная
    mars = "mars"        # Марс - платная


class PredictionType(str, Enum):
    free = "free"    # Бесплатное предсказание (только для Луны)
    paid = "paid"    # Платное предсказание


class PaymentType(str, Enum):
    single_planet = "single_planet"  # Оплата за одну планету
    all_planets = "all_planets"      # Оплата за все планеты сразу


class PaymentStatus(str, Enum):
    pending = "pending"           # Ожидает оплаты
    completed = "completed"       # Оплачено успешно
    failed = "failed"            # Ошибка оплаты
    refunded = "refunded"        # Возврат средств
    processing = "processing"     # Обрабатывается LLM
    analysis_failed = "analysis_failed"  # Оплата прошла, но LLM не сработал
    delivered = "delivered"       # Разбор доставлен пользователю


class User(Base):
    __tablename__ = "users"

    # PK
    user_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    # Telegram
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False
    )
    username: Mapped[Optional[str]] = mapped_column(Text)
    first_name: Mapped[Optional[str]] = mapped_column(Text)
    last_name: Mapped[Optional[str]] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(
        Text, server_default=text("'ru'")
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    consent_given_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # Профиль для астрологии
    full_name: Mapped[Optional[str]] = mapped_column(Text)
    gender: Mapped[Gender] = mapped_column(
        PG_ENUM(
            Gender, name="gender", create_type=False, native_enum=True
        ),
        server_default=text("'unknown'"),
        nullable=False,
    )

    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    birth_time_local: Mapped[Optional[time]] = mapped_column(Time)
    birth_time_accuracy: Mapped[str] = mapped_column(
        Text,
        server_default=text("'exact'"),
        nullable=False,
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
    birth_datetime_utc: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # Метаданные гео-провайдера
    geo_provider: Mapped[Optional[str]] = mapped_column(Text)
    geo_provider_place_id: Mapped[Optional[str]] = mapped_column(Text)

    # Служебное
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Знак зодиака (рус.)
    zodiac_sign: Mapped[Optional[ZodiacSignRu]] = mapped_column(
        PG_ENUM(
            ZodiacSignRu,
            name="zodiac_sign_ru",
            create_type=False,
            native_enum=True,
            # Важно: используем русские значения Enum как значения
            # PostgreSQL ENUM, иначе SQLAlchemy по умолчанию отправляет
            # имена (oven, bliznecy, ...)
            values_callable=lambda enum: [e.value for e in enum],
            validate_strings=True,
        )
    )

    # Ограничения таблицы (CHECK)
    __table_args__ = (
        # Валидность пары координат
        CheckConstraint(
            "(birth_lat IS NULL AND birth_lon IS NULL) OR "
            "(birth_lat BETWEEN -90 AND 90 AND "
            "birth_lon BETWEEN -180 AND 180)",
            name="coord_pair_valid",
        ),
        # Допустимые значения birth_time_accuracy
        CheckConstraint(
            "birth_time_accuracy IN ('exact','approx','unknown')",
            name="birth_time_accuracy_valid",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - вспомогательное
        return (
            f"<User id={self.user_id} tg={self.telegram_id} "
            f"username={self.username!r}>"
        )


class Prediction(Base):
    __tablename__ = "predictions"

    # PK
    prediction_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    # Связь с пользователем
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Планета для которой делается предсказание
    planet: Mapped[Planet] = mapped_column(
        PG_ENUM(
            Planet, name="planet", create_type=False, native_enum=True
        ),
        nullable=False,
    )

    # Тип предсказания (бесплатное/платное)
    prediction_type: Mapped[PredictionType] = mapped_column(
        PG_ENUM(
            PredictionType,
            name="prediction_type",
            create_type=False,
            native_enum=True,
        ),
        nullable=False,
    )

    # Содержимое предсказания от LLM (разделено по типам)
    content: Mapped[Optional[str]] = mapped_column(Text)  # Совместимость

    # Анализы планет (каждый в своем столбце)
    moon_analysis: Mapped[Optional[str]] = mapped_column(Text)
    sun_analysis: Mapped[Optional[str]] = mapped_column(Text)
    mercury_analysis: Mapped[Optional[str]] = mapped_column(Text)
    venus_analysis: Mapped[Optional[str]] = mapped_column(Text)
    mars_analysis: Mapped[Optional[str]] = mapped_column(Text)

    # Рекомендации по темам
    recommendations: Mapped[Optional[str]] = mapped_column(Text)

    # Вопросы и ответы пользователя
    question: Mapped[Optional[str]] = mapped_column(Text)  # Вопрос
    answer: Mapped[Optional[str]] = mapped_column(Text)    # Ответ астролога
    qa_responses: Mapped[Optional[str]] = mapped_column(Text)  # Совместимость

    # Метаданные LLM
    llm_model: Mapped[Optional[str]] = mapped_column(Text)
    llm_tokens_used: Mapped[Optional[int]] = mapped_column(BigInteger)
    llm_temperature: Mapped[Optional[float]] = mapped_column(
        DOUBLE_PRECISION
    )  # Температура генерации

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )  # Для платных предсказаний

    # Статус предсказания
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    # Дополнительные данные
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Ограничения таблицы (CHECK)
    __table_args__ = (
        # Луна может быть только бесплатной
        CheckConstraint(
            "(planet != 'moon') OR "
            "(planet = 'moon' AND prediction_type = 'free')",
            name="moon_only_free",
        ),
        # Платные предсказания должны иметь срок действия
        CheckConstraint(
            "(prediction_type = 'free') OR "
            "(prediction_type = 'paid' AND expires_at IS NOT NULL)",
            name="paid_predictions_must_expire",
        ),
        # Температура должна быть в разумных пределах
        CheckConstraint(
            "llm_temperature IS NULL OR "
            "(llm_temperature >= 0.0 AND llm_temperature <= 2.0)",
            name="temperature_range_valid",
        ),
        # Должен быть хотя бы один тип контента
        CheckConstraint(
            "content IS NOT NULL OR moon_analysis IS NOT NULL OR "
            "sun_analysis IS NOT NULL OR mercury_analysis IS NOT NULL OR "
            "venus_analysis IS NOT NULL OR mars_analysis IS NOT NULL OR "
            "recommendations IS NOT NULL OR answer IS NOT NULL OR "
            "question IS NOT NULL OR qa_responses IS NOT NULL",
            name="at_least_one_content_type",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - вспомогательное
        return (
            f"<Prediction id={self.prediction_id} user={self.user_id} "
            f"planet={self.planet.value} type={self.prediction_type.value}>"
        )


class PlanetPayment(Base):
    __tablename__ = "planet_payments"

    # PK
    payment_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )

    # Связь с пользователем
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Тип платежа
    payment_type: Mapped[PaymentType] = mapped_column(
        PG_ENUM(
            PaymentType,
            name="payment_type",
            create_type=False,
            native_enum=True
        ),
        nullable=False,
    )

    # Планета (заполняется только для single_planet)
    planet: Mapped[Optional[Planet]] = mapped_column(
        PG_ENUM(
            Planet, name="planet", create_type=False, native_enum=True
        ),
        nullable=True,
    )

    # Статус платежа
    status: Mapped[PaymentStatus] = mapped_column(
        PG_ENUM(
            PaymentStatus,
            name="payment_status",
            create_type=False,
            native_enum=True
        ),
        nullable=False,
        server_default=text("'pending'"),
    )

    # Сумма платежа в копейках
    amount_kopecks: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )

    # ID платежа в платежной системе (YooKassa)
    external_payment_id: Mapped[Optional[str]] = mapped_column(Text)

    # URL для оплаты
    payment_url: Mapped[Optional[str]] = mapped_column(Text)

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    # Отслеживание обработки LLM
    analysis_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    
    analysis_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    
    retry_count: Mapped[int] = mapped_column(
        BigInteger, server_default=text("0"), nullable=False
    )
    
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    # Дополнительные данные
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Ограничения таблицы (CHECK)
    __table_args__ = (
        # Для single_planet должна быть указана планета
        CheckConstraint(
            "(payment_type = 'all_planets') OR "
            "(payment_type = 'single_planet' AND planet IS NOT NULL)",
            name="single_planet_must_have_planet",
        ),
        # Сумма должна быть положительной
        CheckConstraint(
            "amount_kopecks > 0",
            name="amount_positive",
        ),
        # Для completed статуса должно быть время завершения
        CheckConstraint(
            "(status != 'completed') OR "
            "(status = 'completed' AND completed_at IS NOT NULL)",
            name="completed_must_have_completion_time",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - вспомогательное
        planet_str = self.planet.value if self.planet else 'all'
        return (
            f"<PlanetPayment id={self.payment_id} user={self.user_id} "
            f"type={self.payment_type.value} planet={planet_str} "
            f"status={self.status.value}>"
        )


# Индексы (соответствуют заданным)
Index("users_last_seen_idx", User.last_seen_at.desc())
Index("users_birth_utc_idx", User.birth_datetime_utc)
Index("users_tg_username_idx", func.lower(User.username))
Index("users_zodiac_idx", User.zodiac_sign)

# Индексы для таблицы predictions
Index("predictions_user_id_idx", Prediction.user_id)
Index("predictions_planet_idx", Prediction.planet)
Index("predictions_type_idx", Prediction.prediction_type)
Index("predictions_created_at_idx", Prediction.created_at.desc())
Index("predictions_expires_at_idx", Prediction.expires_at)
Index("predictions_active_idx", Prediction.is_active)

# Индексы для таблицы planet_payments
Index("planet_payments_user_id_idx", PlanetPayment.user_id)
Index("planet_payments_type_idx", PlanetPayment.payment_type)
Index("planet_payments_planet_idx", PlanetPayment.planet)
Index("planet_payments_status_idx", PlanetPayment.status)
Index("planet_payments_created_at_idx", PlanetPayment.created_at.desc())
Index("planet_payments_external_id_idx", PlanetPayment.external_payment_id)


async def create_all(engine: AsyncEngine) -> None:
    """Создать все таблицы по моделям (для первичной инициализации
    без Alembic).

    Примечание: ENUM gender должен существовать в БД. Если его нет — создайте
    вручную миграцией Alembic или через:
    CREATE TYPE gender AS ENUM ('male','female','other','unknown');
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
