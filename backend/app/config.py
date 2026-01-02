"""
Конфигурация приложения.

Все настройки загружаются из переменных окружения (.env файл).
Pydantic Settings автоматически валидирует и типизирует значения.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """
    Настройки приложения.
    
    Все поля автоматически загружаются из .env файла
    или переменных окружения системы.
    """
    
    # ============================================
    # Database
    # ============================================
    database_url: str = Field(
        default="postgresql+asyncpg://wallet_user:wallet_secret_password@localhost:5432/wallet_db",
        description="PostgreSQL connection string"
    )
    
    # ============================================
    # Redis
    # ============================================
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string"
    )
    
    # ============================================
    # TON Network
    # ============================================
    ton_network: str = Field(
        default="testnet",
        description="TON network: mainnet or testnet"
    )
    ton_center_api_key: str = Field(
        default="",
        description="API key for TON Center"
    )
    
    # ============================================
    # Wallets
    # ============================================
    hot_wallet_mnemonic: str = Field(
        default="",
        description="24-word mnemonic for hot wallet (KEEP SECRET!)"
    )
    cold_wallet_address: str = Field(
        default="",
        description="Cold wallet address for large reserves"
    )
    
    # ============================================
    # USDT Jetton
    # ============================================
    usdt_jetton_master: str = Field(
        default="EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs",
        description="USDT Jetton master contract address"
    )
    
    # ============================================
    # Fee Configuration
    # ============================================
    gas_fee_buffer: float = Field(
        default=0.15,
        description="Buffer for gas fee calculation (15%)"
    )
    min_ton_balance_warning: float = Field(
        default=10.0,
        description="TON balance threshold for warning alert"
    )
    min_ton_balance_critical: float = Field(
        default=2.0,
        description="TON balance threshold for critical alert (block operations)"
    )
    sweep_threshold_usdt: float = Field(
        default=10.0,
        description="Minimum USDT balance to trigger sweep from subwallet"
    )
    
    # ============================================
    # Telegram Alerts
    # ============================================
    telegram_bot_token: str = Field(
        default="",
        description="Telegram bot token for alerts"
    )
    telegram_admin_chat_id: str = Field(
        default="",
        description="Telegram chat ID for admin alerts"
    )
    
    # ============================================
    # Security
    # ============================================
    secret_key: str = Field(
        default="change-me-in-production",
        description="Secret key for JWT and signatures"
    )
    
    # ============================================
    # App
    # ============================================
    debug: bool = Field(
        default=True,
        description="Debug mode"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False  # DATABASE_URL = database_url
    
    @property
    def is_mainnet(self) -> bool:
        """Проверка, работаем ли в mainnet."""
        return self.ton_network.lower() == "mainnet"
    
    @property
    def ton_center_base_url(self) -> str:
        """Базовый URL для TON Center API."""
        if self.is_mainnet:
            return "https://toncenter.com/api/v2"
        return "https://testnet.toncenter.com/api/v2"


@lru_cache()
def get_settings() -> Settings:
    """
    Получение настроек (с кэшированием).
    
    lru_cache гарантирует, что настройки загружаются
    из .env только один раз при старте приложения.
    """
    return Settings()