"""
Модель баланса.

Off-chain балансы пользователей.
Каждый пользователь имеет баланс для каждой валюты (USDT, TON).
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Numeric, String, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Currency(str, Enum):
    """Поддерживаемые валюты."""
    USDT = "USDT"  # Tether USD (jetton)
    TON = "TON"    # Toncoin (native)


class Balance(Base):
    """
    Модель баланса пользователя.
    
    Хранит off-chain балансы для каждой валюты.
    
    available — доступный баланс для операций
    locked — заблокированный баланс (например, во время отправки)
    
    Реальный баланс = available + locked
    
    Attributes:
        id: Внутренний ID
        user_id: ID владельца
        currency: Валюта (USDT, TON)
        available: Доступный баланс
        locked: Заблокированный баланс
        updated_at: Дата последнего обновления
    """
    __tablename__ = "balances"
    
    # Unique constraint: один баланс на валюту для пользователя
    __table_args__ = (
        UniqueConstraint("user_id", "currency", name="uq_user_currency"),)
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Owner
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Balance owner user ID")
    
    # Currency
    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Currency: USDT, TON")
    
    # Amounts (используем Numeric для точных финансовых расчётов)
    # precision=20 — всего цифр, scale=8 — после запятой
    # Это позволяет хранить до 999,999,999,999.99999999
    available: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        default=Decimal("0"),
        comment="Available balance")

    locked: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        default=Decimal("0"),
        comment="Locked balance (during operations)")

    
    # Timestamps
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last update")

    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="balances")
        
    
    @property
    def total(self) -> Decimal:
        """Общий баланс (available + locked)."""
        return self.available + self.locked
    
    def __repr__(self) -> str:
        return f"<Balance(user_id={self.user_id}, {self.currency}: {self.available})>"