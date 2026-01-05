"""
Transaction Service — оркестратор операций.

Координирует весь flow перевода:
1. Валидация
2. Расчёт комиссии
3. Блокировка баланса
4. Создание и отправка транзакции
5. Обновление балансов
"""

import time
import uuid
from decimal import Decimal
from typing import Optional
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import User, Transaction, Balance
from app.models.transaction import TransactionType, TransactionStatus
from app.models.balance import Currency
from app.services.fee_engine import FeeEngine
from app.services.gas_manager import GasManager
from app.services.ledger_service import LedgerService
from app.services.user_service import UserService
from app.core.wallet import WalletManager, validate_ton_address, normalize_address
from app.core.ton_client import TonClient
from app.core.jetton import (
    build_jetton_transfer_message,
    usdt_to_nano,
    ton_to_nano,
)

logger = structlog.get_logger()


class TransactionService:
    """
    Сервис обработки транзакций.
    
    Главный оркестратор — координирует все операции.
    
    Attributes:
        db: Database session
        fee_engine: Расчёт комиссий
        gas_manager: Управление газом
        ledger: Управление балансами
        user_service: Управление пользователями
        wallet_manager: Управление кошельками
        ton_client: Взаимодействие с блокчейном
    """
    
    def __init__(
        self,
        db: AsyncSession,
        fee_engine: FeeEngine,
        gas_manager: GasManager,
        ledger: LedgerService,
        user_service: UserService,
        wallet_manager: WalletManager,
        ton_client: TonClient
    ):
        self.db = db
        self.fee_engine = fee_engine
        self.gas_manager = gas_manager
        self.ledger = ledger
        self.user_service = user_service
        self.wallet_manager = wallet_manager
        self.ton_client = ton_client
    
    async def estimate_transfer_fee(self, amount: Decimal) -> dict:
        """
        Оценка комиссии за перевод.
        
        Args:
            amount: Сумма перевода в USDT
            
        Returns:
            dict: {fee_usdt, gas_ton, ton_usdt_rate}
        """
        return await self.fee_engine.calculate_transfer_fee(amount)
    
    async def initiate_transfer(
        self,
        sender_id: int,
        recipient_address: str,
        amount: Decimal,
        idempotency_key: Optional[str] = None,
        memo: Optional[str] = None
    ) -> dict:
        """
        Инициация перевода USDT.
        
        Полный flow:
        1. Проверка idempotency
        2. Валидация адреса
        3. Проверка газа
        4. Расчёт комиссии
        5. Проверка баланса
        6. Блокировка средств
        7. Создание транзакции
        8. Отправка в блокчейн
        9. Обновление балансов
        
        Args:
            sender_id: ID отправителя
            recipient_address: Адрес получателя
            amount: Сумма в USDT
            idempotency_key: Ключ идемпотентности
            memo: Комментарий
            
        Returns:
            dict: {
                "success": bool,
                "transaction_id": int,
                "tx_hash": str,
                "fee": Decimal,
                "error": str (если ошибка)
            }
        """
        # Генерируем idempotency key если не передан
        if not idempotency_key:
            idempotency_key = str(uuid.uuid4())
        
        logger.info(
            "Transfer initiated",
            sender_id=sender_id,
            recipient=recipient_address,
            amount=str(amount),
            idempotency_key=idempotency_key
        )
        
        try:
            # 1. Проверка idempotency
            existing = await self._check_idempotency(idempotency_key)
            if existing:
                logger.info("Duplicate request", idempotency_key=idempotency_key)
                return {
                    "success": True,
                    "transaction_id": existing.id,
                    "tx_hash": existing.tx_hash,
                    "fee": existing.fee,
                    "duplicate": True
                }
            
            # 2. Валидация адреса
            if not validate_ton_address(recipient_address):
                return {"success": False, "error": "Invalid TON address"}
            
            recipient_address = normalize_address(recipient_address)
            
            # 3. Проверка газа
            can_process, gas_message = await self.gas_manager.can_process_transfer()
            if not can_process:
                return {"success": False, "error": gas_message}
            
            # 4. Расчёт комиссии
            fee_info = await self.fee_engine.calculate_transfer_fee(amount)
            fee = fee_info["fee_usdt"]
            
            # 5. Проверка баланса
            sender_balance = await self.ledger.get_balance(sender_id, Currency.USDT.value)
            total_required = amount + fee
            
            if sender_balance < total_required:
                return {
                    "success": False,
                    "error": f"Insufficient balance. Need {total_required} USDT, have {sender_balance} USDT"
                }
            
            # 6. Блокировка средств
            locked = await self.ledger.lock_balance(sender_id, total_required, Currency.USDT.value)
            if not locked:
                return {"success": False, "error": "Failed to lock balance"}
            
            # 7. Создание транзакции в БД
            transaction = Transaction(
                user_id=sender_id,
                idempotency_key=idempotency_key,
                tx_type=TransactionType.WITHDRAWAL.value,
                status=TransactionStatus.PROCESSING.value,
                currency=Currency.USDT.value,
                amount=amount,
                fee=fee,
                from_address=self.wallet_manager.get_hot_wallet_address(),
                to_address=recipient_address,
                memo=memo
            )
            self.db.add(transaction)
            await self.db.flush()
            
            try:
                # 8. Отправка в блокчейн
                tx_hash = await self._send_jetton_transfer(
                    recipient_address=recipient_address,
                    amount=amount,
                    memo=memo
                )
                
                # 9. Обновление транзакции
                transaction.tx_hash = tx_hash
                transaction.status = TransactionStatus.COMPLETED.value
                transaction.completed_at = datetime.utcnow()
                
                # 10. Списание с баланса (из locked)
                await self.ledger.debit(
                    user_id=sender_id,
                    amount=total_required,
                    transaction=transaction,
                    from_locked=True
                )
                
                # 11. Фиксируем комиссию
                if fee > Decimal("0"):
                    from app.models.ledger import LedgerAccount
                    await self.ledger.credit(
                        user_id=None,
                        amount=fee,
                        transaction=transaction,
                        account=LedgerAccount.FEE_REVENUE.value
                    )
                
                await self.db.commit()
                
                logger.info(
                    "Transfer completed",
                    transaction_id=transaction.id,
                    tx_hash=tx_hash,
                    amount=str(amount),
                    fee=str(fee)
                )
                
                return {
                    "success": True,
                    "transaction_id": transaction.id,
                    "tx_hash": tx_hash,
                    "fee": fee,
                    "amount": amount
                }
                
            except Exception as e:
                # Откатываем блокировку при ошибке
                logger.error("Transfer failed, unlocking balance", error=str(e))
                await self.ledger.unlock_balance(sender_id, total_required, Currency.USDT.value)
                
                transaction.status = TransactionStatus.FAILED.value
                transaction.error_message = str(e)
                await self.db.commit()
                
                return {"success": False, "error": str(e)}
                
        except Exception as e:
            logger.exception("Transfer error", error=str(e))
            await self.db.rollback()
            return {"success": False, "error": str(e)}
    
    async def _check_idempotency(self, idempotency_key: str) -> Optional[Transaction]:
        """Проверка на дубликат по idempotency key."""
        query = select(Transaction).where(
            Transaction.idempotency_key == idempotency_key
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def _send_jetton_transfer(
        self,
        recipient_address: str,
        amount: Decimal,
        memo: Optional[str] = None
    ) -> str:
        """
        Отправка USDT через блокчейн.
        
        Returns:
            str: Transaction hash
        """
        # Получаем hot wallet
        hot_wallet, private_key = self.wallet_manager.get_hot_wallet_for_signing()
        hot_address = self.wallet_manager.get_hot_wallet_address()
        
        # Получаем Jetton Wallet адрес hot wallet
        jetton_wallet_address = await self.ton_client.get_jetton_wallet_address(hot_address)
        
        # Конвертируем сумму
        amount_nano = usdt_to_nano(amount)
        
        # Создаём transfer message
        transfer_msg = build_jetton_transfer_message(
            jetton_wallet_address=jetton_wallet_address,
            destination=recipient_address,
            jetton_amount=amount_nano,
            response_destination=hot_address,
            query_id=int(time.time())
        )
        
        # Получаем seqno
        info = await self.ton_client.get_address_info(hot_address)
        seqno = info.get("seqno", 0) or 0
        
        # Создаём и подписываем транзакцию
        query = hot_wallet.create_transfer_message(
            to_addr=transfer_msg["to_addr"],
            amount=transfer_msg["amount"],
            seqno=seqno,
            payload=transfer_msg["payload"]
        )
        
        # Отправляем
        from tonsdk.utils import bytes_to_b64str
        boc = bytes_to_b64str(query["message"].to_boc(False))
        
        result = await self.ton_client.send_boc(boc)
        
        # Возвращаем hash (в TON это обычно hash of BOC)
        import hashlib
        tx_hash = hashlib.sha256(query["message"].to_boc(False)).hexdigest()
        
        return tx_hash
    
    async def get_transaction(self, transaction_id: int) -> Optional[Transaction]:
        """Получение транзакции по ID."""
        query = select(Transaction).where(Transaction.id == transaction_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_user_transactions(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> list[Transaction]:
        """Получение истории транзакций пользователя."""
        query = (
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())


async def get_transaction_service(db: AsyncSession) -> TransactionService:
    """
    Factory для создания TransactionService со всеми зависимостями.
    """
    from app.config import get_settings
    from app.services.price_service import get_price_service
    from app.services.fee_engine import FeeEngine
    from app.core.ton_client import TonClient
    
    settings = get_settings()
    
    # Создаём зависимости
    price_service = await get_price_service()
    fee_engine = FeeEngine(price_service, gas_buffer=settings.gas_fee_buffer)
    
    ton_client = TonClient(
        network=settings.ton_network,
        api_key=settings.ton_center_api_key
    )
    
    wallet_manager = WalletManager(settings.hot_wallet_mnemonic)
    
    gas_manager = GasManager(
        ton_client=ton_client,
        hot_wallet_address=wallet_manager.get_hot_wallet_address()
    )
    
    ledger = LedgerService(db)
    user_service = UserService(db, wallet_manager)
    
    return TransactionService(
        db=db,
        fee_engine=fee_engine,
        gas_manager=gas_manager,
        ledger=ledger,
        user_service=user_service,
        wallet_manager=wallet_manager,
        ton_client=ton_client
    )