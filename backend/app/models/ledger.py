"""
Модель записи в ledger (книга учёта).

Реализует систему двойной записи (double-entry bookkeeping).
Каждая транзакция создаёт минимум 2 записи: debit и credit.

Сумма всех debit = сумма всех credit (баланс сходится).
"""

from datetime import datetime
from enum import Enum
from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class LedgerEntryType(str, Enum):
    """Тип записи в ledger."""
    DEBIT = "debit"    # Списание (уменьшение актива или увеличение обязательства)
    CREDIT = "credit"  # Начисление (увеличение актива или уменьшение обязательства)


class LedgerAccount(str, Enum):
    """
    Счета в системе учёта.
    
    Структура счетов:
    - USER_BALANCE: Баланс пользователя (актив пользователя)
    - FEE_REVENUE: Доход от комиссий (актив системы)
    - HOT_WALLET: Баланс hot wallet (актив системы)
    - COLD_WALLET: Баланс cold wallet (актив системы)
    - EXTERNAL: Внешние адреса (для входящих/исходящих)
    """
    USER_BALANCE = "user_balance"    # Баланс пользователя
    FEE_REVENUE = "fee_revenue"      # Доход от комиссий
    HOT_WALLET = "hot_wallet"        # Hot wallet баланс
    COLD_WALLET = "cold_wallet"      # Cold wallet баланс
    EXTERNAL = "external"            # Внешний адрес


class LedgerEntry(Base):
    """
    Запись в книге учёта (ledger).
    
    Двойная запись гарантирует целостность:
    - Каждая операция создаёт пару debit/credit
    - Сумма всех debit = сумма всех credit
    
    Пример: Пользователь A отправляет 100 USDT пользователю B
    
    | entry_type | account      | user_id | amount |
    |------------|--------------|---------|--------|
    | DEBIT      | USER_BALANCE | A       | 100    |  <- У A списали
    | CREDIT     | USER_BALANCE | B       | 100    |  <- B получил
    | DEBIT      | USER_BALANCE | A       | 0.10   |  <- Комиссия
    | CREDIT     | FEE_REVENUE  | null    | 0.10   |  <- Доход системы
    
    Attributes:
        id: Внутренний ID
        transaction_id: Связанная транзакция
        entry_type: DEBIT или CREDIT
        account: Тип счёта
        user_id: ID пользователя (если применимо)
        currency: Валюта
        amount: Сумма (всегда положительная)
        created_at: Время записи
    """
    __tablename__ = "ledger_entries"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Related transaction
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Related transaction")

    
    # Entry type
    entry_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Entry type: debit or credit")

    
    # Account
    account: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        comment="Account type: user_balance, fee_revenue, hot_wallet, etc.")

    
    # User (nullable для системных счетов)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Related user (null for system accounts)")

    
    # Amount
    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Currency: USDT, TON")

    amount: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
        comment="Amount (always positive)")

    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Entry creation time")

    
    # Relationships
    transaction: Mapped["Transaction"] = relationship(
        "Transaction",
        back_populates="ledger_entries")
        
    
    def __repr__(self) -> str:
        return f"<LedgerEntry(id={self.id}, {self.entry_type} {self.account} {self.amount} {self.currency})>"