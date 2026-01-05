"""
Ledger Service — управление балансами.

Off-chain учёт балансов пользователей.
Реализует двойную запись (double-entry bookkeeping).

Каждая операция создаёт записи в ledger:
- DEBIT — списание
- CREDIT — начисление

Сумма всех DEBIT = сумма всех CREDIT (баланс сходится)
"""

from decimal import Decimal
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import User, Balance, Transaction, LedgerEntry
from app.models.balance import Currency
from app.models.ledger import LedgerEntryType, LedgerAccount

logger = structlog.get_logger()


class LedgerService:
    """
    Сервис учёта балансов.
    
    Управляет off-chain балансами пользователей.
    Все операции с балансами проходят через этот сервис.
    """
    
    def __init__(self, db: AsyncSession):
        """
        Args:
            db: Async database session
        """
        self.db = db
    
    async def get_or_create_balance(
        self, 
        user_id: int, 
        currency: str = Currency.USDT.value
    ) -> Balance:
        """
        Получение или создание баланса пользователя.
        
        Args:
            user_id: ID пользователя
            currency: Валюта (USDT, TON)
            
        Returns:
            Balance: Объект баланса
        """
        # Ищем существующий баланс
        query = select(Balance).where(
            Balance.user_id == user_id,
            Balance.currency == currency
        )
        result = await self.db.execute(query)
        balance = result.scalar_one_or_none()
        
        if balance is None:
            # Создаём новый баланс
            balance = Balance(
                user_id=user_id,
                currency=currency,
                available=Decimal("0"),
                locked=Decimal("0")
            )
            self.db.add(balance)
            await self.db.flush()
            logger.info("Balance created", user_id=user_id, currency=currency)
        
        return balance
    
    async def get_balance(
        self, 
        user_id: int, 
        currency: str = Currency.USDT.value
    ) -> Decimal:
        """
        Получение доступного баланса.
        
        Args:
            user_id: ID пользователя
            currency: Валюта
            
        Returns:
            Decimal: Доступный баланс
        """
        balance = await self.get_or_create_balance(user_id, currency)
        return balance.available
    
    async def get_total_balance(
        self, 
        user_id: int, 
        currency: str = Currency.USDT.value
    ) -> dict:
        """
        Получение полной информации о балансе.
        
        Returns:
            dict: {available, locked, total}
        """
        balance = await self.get_or_create_balance(user_id, currency)
        return {
            "available": balance.available,
            "locked": balance.locked,
            "total": balance.available + balance.locked,
        }
    
    async def lock_balance(
        self, 
        user_id: int, 
        amount: Decimal,
        currency: str = Currency.USDT.value
    ) -> bool:
        """
        Блокировка части баланса.
        
        Используется при начале операции перевода.
        Блокирует средства, чтобы избежать double-spend.
        
        Args:
            user_id: ID пользователя
            amount: Сумма для блокировки
            currency: Валюта
            
        Returns:
            bool: True если успешно, False если недостаточно средств
        """
        balance = await self.get_or_create_balance(user_id, currency)
        
        if balance.available < amount:
            logger.warning(
                "Insufficient balance for lock",
                user_id=user_id,
                available=str(balance.available),
                requested=str(amount)
            )
            return False
        
        balance.available -= amount
        balance.locked += amount
        
        await self.db.flush()
        
        logger.info(
            "Balance locked",
            user_id=user_id,
            amount=str(amount),
            new_available=str(balance.available),
            new_locked=str(balance.locked)
        )
        
        return True
    
    async def unlock_balance(
        self, 
        user_id: int, 
        amount: Decimal,
        currency: str = Currency.USDT.value
    ):
        """
        Разблокировка баланса (при отмене операции).
        
        Args:
            user_id: ID пользователя
            amount: Сумма для разблокировки
            currency: Валюта
        """
        balance = await self.get_or_create_balance(user_id, currency)
        
        # Разблокируем (но не больше чем заблокировано)
        unlock_amount = min(amount, balance.locked)
        
        balance.locked -= unlock_amount
        balance.available += unlock_amount
        
        await self.db.flush()
        
        logger.info(
            "Balance unlocked",
            user_id=user_id,
            amount=str(unlock_amount)
        )
    
    async def debit(
        self,
        user_id: int,
        amount: Decimal,
        transaction: Transaction,
        account: str = LedgerAccount.USER_BALANCE.value,
        currency: str = Currency.USDT.value,
        from_locked: bool = False
    ) -> LedgerEntry:
        """
        Списание с баланса (DEBIT).
        
        Args:
            user_id: ID пользователя
            amount: Сумма списания
            transaction: Связанная транзакция
            account: Тип счёта
            currency: Валюта
            from_locked: Списывать из locked (True) или available (False)
            
        Returns:
            LedgerEntry: Запись в ledger
        """
        balance = await self.get_or_create_balance(user_id, currency)
        
        if from_locked:
            if balance.locked < amount:
                raise ValueError(f"Insufficient locked balance: {balance.locked} < {amount}")
            balance.locked -= amount
        else:
            if balance.available < amount:
                raise ValueError(f"Insufficient available balance: {balance.available} < {amount}")
            balance.available -= amount
        
        # Создаём запись в ledger
        entry = LedgerEntry(
            transaction_id=transaction.id,
            entry_type=LedgerEntryType.DEBIT.value,
            account=account,
            user_id=user_id,
            currency=currency,
            amount=amount
        )
        self.db.add(entry)
        
        await self.db.flush()
        
        logger.info(
            "Debit recorded",
            user_id=user_id,
            amount=str(amount),
            account=account,
            transaction_id=transaction.id
        )
        
        return entry
    
    async def credit(
        self,
        user_id: int | None,
        amount: Decimal,
        transaction: Transaction,
        account: str = LedgerAccount.USER_BALANCE.value,
        currency: str = Currency.USDT.value
    ) -> LedgerEntry:
        """
        Начисление на баланс (CREDIT).
        
        Args:
            user_id: ID пользователя (None для системных счетов)
            amount: Сумма начисления
            transaction: Связанная транзакция
            account: Тип счёта
            currency: Валюта
            
        Returns:
            LedgerEntry: Запись в ledger
        """
        if user_id is not None and account == LedgerAccount.USER_BALANCE.value:
            balance = await self.get_or_create_balance(user_id, currency)
            balance.available += amount
        
        # Создаём запись в ledger
        entry = LedgerEntry(
            transaction_id=transaction.id,
            entry_type=LedgerEntryType.CREDIT.value,
            account=account,
            user_id=user_id,
            currency=currency,
            amount=amount
        )
        self.db.add(entry)
        
        await self.db.flush()
        
        logger.info(
            "Credit recorded",
            user_id=user_id,
            amount=str(amount),
            account=account,
            transaction_id=transaction.id
        )
        
        return entry
    
    async def transfer_internal(
        self,
        from_user_id: int,
        to_user_id: int,
        amount: Decimal,
        fee: Decimal,
        transaction: Transaction,
        currency: str = Currency.USDT.value
    ):
        """
        Внутренний перевод между пользователями.
        
        Создаёт записи:
        1. DEBIT from_user (amount + fee) — из locked
        2. CREDIT to_user (amount)
        3. CREDIT fee_revenue (fee)
        
        Args:
            from_user_id: ID отправителя
            to_user_id: ID получателя
            amount: Сумма перевода
            fee: Комиссия
            transaction: Транзакция
            currency: Валюта
        """
        # 1. Списываем с отправителя (amount + fee из locked)
        total_debit = amount + fee
        await self.debit(
            user_id=from_user_id,
            amount=total_debit,
            transaction=transaction,
            from_locked=True,
            currency=currency
        )
        
        # 2. Начисляем получателю
        await self.credit(
            user_id=to_user_id,
            amount=amount,
            transaction=transaction,
            currency=currency
        )
        
        # 3. Начисляем комиссию на системный счёт
        if fee > 0:
            await self.credit(
                user_id=None,
                amount=fee,
                transaction=transaction,
                account=LedgerAccount.FEE_REVENUE.value,
                currency=currency
            )
        
        logger.info(
            "Internal transfer completed",
            from_user=from_user_id,
            to_user=to_user_id,
            amount=str(amount),
            fee=str(fee)
        )