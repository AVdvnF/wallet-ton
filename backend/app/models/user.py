"""
Модель пользователя.

Пользователь идентифицируется по Telegram ID.
Один пользователь может иметь несколько кошельков и балансов.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

# Избегаем circular imports
if TYPE_CHECKING:
    from app.models.wallet import Wallet
    from app.models.balance import Balance
    from app.models.transaction import Transaction


class UserStatus(str, Enum):
    """Статус пользователя."""
    ACTIVE = "active"          # Активный пользователь
    SUSPENDED = "suspended"    # Приостановлен (например, за нарушения)
    BLOCKED = "blocked"        # Заблокирован


class User(Base):
    """
    Модель пользователя.
    
    Attributes:
        id: Внутренний ID в нашей системе
        telegram_id: ID пользователя в Telegram (уникальный)
        username: Username в Telegram (может быть None)
        first_name: Имя из Telegram
        last_name: Фамилия из Telegram
        status: Статус аккаунта
        created_at: Дата регистрации
        updated_at: Дата последнего обновления
    """
    __tablename__ = "users"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Telegram данные
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, 
        unique=True, 
        index=True,
        comment="Telegram user ID")

    username: Mapped[str | None] = mapped_column(
        String(255), 
        nullable=True,
        comment="Telegram username without @")

    first_name: Mapped[str | None] = mapped_column(
        String(255), 
        nullable=True,
        comment="First name from Telegram")

    last_name: Mapped[str | None] = mapped_column(
        String(255), 
        nullable=True,
        comment="Last name from Telegram")
    

    # Статус
    status: Mapped[str] = mapped_column(
        String(20),
        default=UserStatus.ACTIVE.value,
        comment="User status: active, suspended, blocked")

    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Registration date")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update date")

    
    # Relationships (связи с другими таблицами)
    wallets: Mapped[list["Wallet"]] = relationship(
        "Wallet",
        back_populates="user",
        lazy="selectin")  # Автоматически загружать при запросе

    balances: Mapped[list["Balance"]] = relationship(
        "Balance",
        back_populates="user",
        lazy="selectin")

    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="user",
        lazy="dynamic")  # Ленивая загрузка для больших списков
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id})>"