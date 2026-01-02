"""
Модель кошелька.

Каждый пользователь имеет свой deposit address (subwallet).
Адреса генерируются детерминированно из master seed + index.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class WalletType(str, Enum):
    """Тип кошелька."""
    DEPOSIT = "deposit"    # Deposit address пользователя (subwallet)
    HOT = "hot"            # Hot wallet системы
    COLD = "cold"          # Cold wallet системы


class Wallet(Base):
    """
    Модель кошелька.
    
    Deposit кошельки генерируются для каждого пользователя.
    Адрес вычисляется из master seed + wallet_index.
    
    Attributes:
        id: Внутренний ID
        user_id: ID владельца (для deposit wallets)
        address: TON адрес кошелька
        wallet_index: Индекс для HD wallet деривации
        wallet_type: Тип кошелька (deposit/hot/cold)
        is_deployed: Развёрнут ли контракт на блокчейне
        created_at: Дата создания
    """
    __tablename__ = "wallets"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Owner (nullable для системных кошельков hot/cold)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Owner user ID (null for system wallets)")

    
    # Wallet data
    address: Mapped[str] = mapped_column(
        String(68),  # TON address length
        unique=True,
        index=True,
        comment="TON wallet address")

    wallet_index: Mapped[int] = mapped_column(
        Integer,
        nullable=True,
        comment="HD wallet derivation index")

    wallet_type: Mapped[str] = mapped_column(
        String(20),
        default=WalletType.DEPOSIT.value,
        comment="Wallet type: deposit, hot, cold")
    
    # Status
    is_deployed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Is wallet contract deployed on-chain")
    
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation date")
    
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="wallets")
    
    def __repr__(self) -> str:
        return f"<Wallet(id={self.id}, address={self.address[:10]}..., type={self.wallet_type})>"