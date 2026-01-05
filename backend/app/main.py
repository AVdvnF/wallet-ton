"""
Главный модуль FastAPI приложения.

Кастодиальный TON кошелёк с моделью Gas Sponsor.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import init_db
import structlog

from app.config import get_settings

# Настройка структурированного логирования
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()  # Логи в JSON формате
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle менеджер приложения.
    """
    settings = get_settings()
    
    # === STARTUP ===
    logger.info(
        "Starting application",
        network=settings.ton_network,
        debug=settings.debug
    )
    
    # Инициализация БД (создание таблиц)
    await init_db()
    logger.info("Database initialized")
    
    yield  # Приложение работает
    
    # === SHUTDOWN ===
    logger.info("Shutting down application")


def create_app() -> FastAPI:
    """
    Фабрика приложения.
    
    Создаёт и настраивает FastAPI instance.
    """
    settings = get_settings()
    
    app = FastAPI(
        title="TON Custodial Wallet",
        description="""
        Кастодиальный кошелёк TON с поддержкой USDT.
        
        Особенности:
        - Gas Sponsor модель (пользователь не держит TON)
        - Комиссия только за газ (в USDT)
        - Off-chain балансы
        - HD wallet архитектура
        """,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,  # Swagger только в debug
        redoc_url="/redoc" if settings.debug else None,
    )
    
    # CORS настройки для Mini App
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://web.telegram.org",  # Telegram Web App
            "http://localhost:3000",      # Local frontend dev
            "http://localhost:5173",      # Vite dev server
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Health check endpoint
    @app.get("/health", tags=["System"])
    async def health_check():
        """
        Проверка состояния сервиса.
        
        Используется для:
        - Docker healthcheck
        - Load balancer проверок
        - Мониторинга
        """
        return {
            "status": "healthy",
            "network": settings.ton_network,
            "version": "0.1.0"
        }
    
    # TODO: Подключение роутеров
    # app.include_router(transfer_router, prefix="/api/v1")
    # app.include_router(balance_router, prefix="/api/v1")
    
    return app


# Создание приложения
app = create_app()