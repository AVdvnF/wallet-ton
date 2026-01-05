"""
User Service — управление пользователями.

Регистрация, создание кошельков, получение данных.
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.models import User, Wallet, Balance
from app.models.wallet import WalletType
from app.models.balance import Currency
from app.core.wallet import WalletManager

logger = structlog.get_logger()


class UserService:
    """
    Сервис управления пользователями.
    
    Отвечает за:
    - Регистрацию пользователей (по Telegram ID)
    - Создание deposit кошельков
    - Получение информации о пользователе
    """
    
    def __init__(self, db: AsyncSession, wallet_manager: WalletManager):
        """
        Args:
            db: Database session
            wallet_manager: Менеджер кошельков для генерации адресов
        """
        self.db = db
        self.wallet_manager = wallet_manager
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """
        Получение пользователя по Telegram ID.
        
        Args:
            telegram_id: ID в Telegram
            
        Returns:
            User | None
        """
        query = select(User).where(User.telegram_id == telegram_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_id(self, user_id: int) -> Optional[User]:
        """
        Получение пользователя по внутреннему ID.
        
        Args:
            user_id: Внутренний ID
            
        Returns:
            User | None
        """
        query = (
            select(User)
            .options(selectinload(User.wallets), selectinload(User.balances))
            .where(User.id == user_id)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_or_create(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> tuple[User, bool]:
        """
        Получение или создание пользователя.
        
        При создании также создаётся deposit wallet и балансы.
        
        Args:
            telegram_id: Telegram ID
            username: Username в Telegram
            first_name: Имя
            last_name: Фамилия
            
        Returns:
            tuple[User, bool]: (user, is_new)
        """
        # Проверяем существует ли пользователь
        user = await self.get_by_telegram_id(telegram_id)
        
        if user is not None:
            # Обновляем данные если изменились
            updated = False
            if username and user.username != username:
                user.username = username
                updated = True
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if last_name and user.last_name != last_name:
                user.last_name = last_name
                updated = True
            
            if updated:
                await self.db.flush()
            
            return (user, False)
        
        # Создаём нового пользователя
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        self.db.add(user)
        await self.db.flush()  # Получаем user.id
        
        logger.info(
            "User created",
            user_id=user.id,
            telegram_id=telegram_id,
            username=username
        )
        
        # Создаём deposit wallet
        await self._create_deposit_wallet(user)
        
        # Создаём балансы
        await self._create_balances(user)
        
        return (user, True)
    
    async def _create_deposit_wallet(self, user: User) -> Wallet:
        """
        Создание deposit wallet для пользователя.
        
        Адрес генерируется детерминированно из master seed + user_id.
        """
        # Генерируем адрес
        address = self.wallet_manager.generate_subwallet_address(user.id)
        
        wallet = Wallet(
            user_id=user.id,
            address=address,
            wallet_index=user.id,  # Используем user_id как index
            wallet_type=WalletType.DEPOSIT.value,
            is_deployed=False  # Контракт не развёрнут пока нет входящих
        )
        self.db.add(wallet)
        await self.db.flush()
        
        logger.info(
            "Deposit wallet created",
            user_id=user.id,
            address=address
        )
        
        return wallet
    
    async def _create_balances(self, user: User):
        """Создание балансов для пользователя."""
        # USDT баланс
        usdt_balance = Balance(
            user_id=user.id,
            currency=Currency.USDT.value
        )
        self.db.add(usdt_balance)
        
        # TON баланс (на будущее)
        ton_balance = Balance(
            user_id=user.id,
            currency=Currency.TON.value
        )
        self.db.add(ton_balance)
        
        await self.db.flush()
        
        logger.info("Balances created", user_id=user.id)
    
    async def get_deposit_address(self, user_id: int) -> Optional[str]:
        """
        Получение deposit адреса пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            str | None: TON адрес или None
        """
        query = select(Wallet).where(
            Wallet.user_id == user_id,
            Wallet.wallet_type == WalletType.DEPOSIT.value
        )
        result = await self.db.execute(query)
        wallet = result.scalar_one_or_none()
        
        if wallet:
            return wallet.address
        return None
    
    async def get_user_by_address(self, address: str) -> Optional[User]:
        """
        Получение пользователя по адресу кошелька.
        
        Используется для идентификации входящих переводов.
        
        Args:
            address: TON адрес
            
        Returns:
            User | None
        """
        query = (
            select(User)
            .join(Wallet)
            .where(Wallet.address == address)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_user_info(self, user_id: int) -> Optional[dict]:
        """
        Получение полной информации о пользователе.
        
        Returns:
            dict: {user, wallets, balances}
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None
        
        # Получаем кошельки
        wallets_query = select(Wallet).where(Wallet.user_id == user_id)
        wallets_result = await self.db.execute(wallets_query)
        wallets = wallets_result.scalars().all()
        
        # Получаем балансы
        balances_query = select(Balance).where(Balance.user_id == user_id)
        balances_result = await self.db.execute(balances_query)
        balances = balances_result.scalars().all()
        
        return {
            "user": user,
            "wallets": wallets,
            "balances": {b.currency: {"available": b.available, "locked": b.locked} for b in balances},
        }