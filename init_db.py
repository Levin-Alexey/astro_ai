import asyncio

from db import init_engine, dispose_engine, ensure_gender_enum, ensure_birth_date_nullable
from db import engine as _engine
from models import create_all


async def main():
    init_engine()
    try:
        # Создать тип gender, снять NOT NULL с birth_date (если есть) и создать таблицы
        await ensure_gender_enum(_engine)
        await ensure_birth_date_nullable(_engine)
        await create_all(_engine)
        print("База данных инициализирована: тип gender и таблицы созданы.")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
