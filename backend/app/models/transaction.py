"""
Модель транзакции.

Хранит историю всех операций: депозиты, переводы, выводы.
Каждая транзакция связана с записями в ledger (двойная запись).
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from decimal import Decimal
from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.ledger import LedgerEntry


class TransactionType(str, Enum):
    """Тип транзакции."""
    DEPOSIT = "deposit"        # Входящий перевод (на deposit address)
    WITHDRAWAL = "withdrawal"  # Исходящий перевод (на внешний адрес)
    TRANSFER = "transfer"      # Внутренний перевод между пользователями
    FEE = "fee"                # Списание комиссии
    SWEEP = "sweep"            # Sweep с subwallet на hot wallet


class TransactionStatus(str, Enum):
    """Статус транзакции."""
    PENDING = "pending"        # Ожидает обработки
    PROCESSING = "processing"  # В процессе (отправлена в блокчейн)
    CONFIRMING = "confirming"  # Ожидает подтверждений
    COMPLETED = "completed"    # Успешно завершена
    FAILED = "failed"          # Ошибка
    CANCELLED = "cancelled"    # Отменена


class Transaction(Base):
    """
    Модель транзакции.
    
    Хранит все финансовые операции в системе.
    
    Attributes:
        id: Внутренний ID
        user_id: ID пользователя (инициатор)
        idempotency_key: Ключ идемпотентности (защита от дублей)
        tx_type: Тип операции
        status: Текущий статус
        currency: Валюта
        amount: Сумма операции
        fee: Комиссия (в той же валюте)
        
        # Адреса
        from_address: Адрес отправителя
        to_address: Адрес получателя
        
        # On-chain данные
        tx_hash: Hash транзакции в блокчейне
        lt: Logical time в TON
        
        # Metadata
        memo: Комментарий к транзакции
        error_message: Сообщение об ошибке (если failed)
        
        # Timestamps
        created_at: Дата создания
        completed_at: Дата завершения
    """
    __tablename__ = "transactions"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # User (может быть null для системных транзакций)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Transaction initiator")

    
    # Idempotency (защита от повторных запросов)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        nullable=True,
        index=True,
        comment="Unique key to prevent duplicate transactions")

    
    # Transaction info
    tx_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Transaction type: deposit, withdrawal, transfer, fee, sweep")

    status: Mapped[str] = mapped_column(
        String(20),
        default=TransactionStatus.PENDING.value,
        index=True,
        comment="Transaction status")

    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Currency: USDT, TON")

    
    # Amounts
    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
        comment="Transaction amount")
    
    fee: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        default=Decimal("0"),
        comment="Fee amount")
    
    
    # Addresses
    from_address: Mapped[str | None] = mapped_column(
        String(68),
        nullable=True,
        comment="Sender address")
    
    to_address: Mapped[str | None] = mapped_column(
        String(68),
        nullable=True,
        index=True,
        comment="Recipient address")

    
    # On-chain data (заполняется после отправки в блокчейн)
    tx_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        index=True,
        comment="Transaction hash in blockchain")

    lt: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Logical time in TON blockchain")

    
    # Metadata
    memo: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Transaction comment/memo")

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if failed")

    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time")

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Completion time")

    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="transactions")

    ledger_entries: Mapped[list["LedgerEntry"]] = relationship(
        "LedgerEntry",
        back_populates="transaction",
        lazy="selectin")

    
    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, type={self.tx_type}, status={self.status}, amount={self.amount})>"