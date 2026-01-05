"""
Подключение к базе данных.

Использует asyncpg для асинхронной работы с PostgreSQL.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """
    Базовый класс для всех моделей.
    
    Все модели наследуются от этого класса,
    что позволяет SQLAlchemy отслеживать их
    и создавать таблицы автоматически.
    """
    pass


# Получаем настройки
settings = get_settings()

# Создаём async engine для PostgreSQL
# echo=True — логирует все SQL запросы (полезно для debug)
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,  # SQL логи только в debug режиме
    pool_size=10,         # Размер пула соединений
    max_overflow=20,      # Дополнительные соединения при нагрузке
)

# Фабрика сессий
# expire_on_commit=False — объекты остаются доступны после commit
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """
    Dependency для получения сессии БД.
    
    Используется в FastAPI endpoints:
    
    @app.get("/users")
    async def get_users(db: AsyncSession = Depends(get_db)):
        ...
    
    Автоматически закрывает сессию после запроса.
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    Инициализация базы данных.
    
    Создаёт все таблицы, если они не существуют.
    Вызывается при старте приложения.
    
    ВАЖНО: В production используй Alembic миграции!
    Этот метод только для быстрого старта в development.
    """
    # ВАЖНО: Импортируем модели, чтобы они зарегистрировались в Base.metadata
    from app.models import User, Wallet, Balance, Transaction, LedgerEntry
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)