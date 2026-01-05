"""
Управление TON кошельками.

HD Wallet генерация — все subwallets генерируются из одного master seed.
Это позволяет:
- Восстановить все адреса из одной мнемоники
- Генерировать адреса детерминированно (seed + index = address)
- Не хранить приватные ключи отдельно
"""

from typing import Tuple
from tonsdk.contract.wallet import Wallets, WalletVersionEnum
from tonsdk.crypto import mnemonic_new, mnemonic_to_wallet_key
from tonsdk.utils import Address, bytes_to_b64str

from app.core.constants import WORKCHAIN, WALLET_VERSION


def generate_mnemonic() -> list[str]:
    """
    Генерация новой 24-словной мнемоники.
    
    ВАЖНО: Используй только для создания нового hot wallet!
    Храни мнемонику в безопасном месте!
    
    Returns:
        list[str]: 24 слова мнемоники
    """
    return mnemonic_new(words_count=24)


def mnemonic_to_keypair(mnemonic: list[str]) -> Tuple[bytes, bytes]:
    """
    Получение ключевой пары из мнемоники.
    
    Args:
        mnemonic: 24 слова мнемоники
        
    Returns:
        Tuple[public_key, secret_key]
    """
    public_key, secret_key = mnemonic_to_wallet_key(mnemonic)
    return public_key, secret_key


def get_wallet_version() -> WalletVersionEnum:
    """Получение версии wallet контракта."""
    versions = {
        "v3r1": WalletVersionEnum.v3r1,
        "v3r2": WalletVersionEnum.v3r2,
        "v4r1": WalletVersionEnum.v4r1,
        "v4r2": WalletVersionEnum.v4r2,
    }
    return versions.get(WALLET_VERSION, WalletVersionEnum.v4r2)


class WalletManager:
    """
    Менеджер кошельков.
    
    Управляет hot wallet и генерацией subwallets для пользователей.
    
    Архитектура:
    - Hot Wallet: основной кошелёк системы (хранит TON для газа + USDT)
    - Subwallets: deposit адреса пользователей (генерируются из master seed + index)
    
    Attributes:
        mnemonic: 24-словная мнемоника master seed
        hot_wallet: Объект hot wallet
        hot_address: Адрес hot wallet
    """
    
    def __init__(self, mnemonic: str | list[str]):
        """
        Инициализация менеджера.
        
        Args:
            mnemonic: Мнемоника (строка через пробел или список слов)
        """
        if isinstance(mnemonic, str):
            self.mnemonic = mnemonic.split()
        else:
            self.mnemonic = mnemonic
            
        if len(self.mnemonic) != 24:
            raise ValueError("Mnemonic must be 24 words")
        
        # Создаём hot wallet (index = 0)
        self._init_hot_wallet()
    
    def _init_hot_wallet(self):
        """Инициализация hot wallet."""
        _mnemonics, _pub_k, _priv_k, wallet = Wallets.from_mnemonics(
            mnemonics=self.mnemonic,
            version=get_wallet_version(),
            workchain=WORKCHAIN
        )
        self.hot_wallet = wallet
        self.hot_address = wallet.address.to_string(True, True, True)  # user-friendly bounceable
        self._hot_public_key = _pub_k
        self._hot_private_key = _priv_k
    
    def get_hot_wallet_address(self, bounceable: bool = True) -> str:
        """
        Получение адреса hot wallet.
        
        Args:
            bounceable: True для обычных переводов, False для депозитов
            
        Returns:
            str: TON адрес в user-friendly формате
        """
        return self.hot_wallet.address.to_string(
            is_user_friendly=True,
            is_url_safe=True,
            is_bounceable=bounceable
        )
    
    def generate_subwallet_address(self, index: int) -> str:
        """
        Генерация deposit адреса для пользователя.
        
        Использует wallet_id для создания уникального адреса.
        Каждый index даёт уникальный адрес, но все они
        контролируются из одной мнемоники.
        
        Args:
            index: Уникальный индекс пользователя (user_id)
            
        Returns:
            str: TON адрес subwallet
        """
        # Используем wallet_id = 698983191 + index для уникальности
        # 698983191 — дефолтный wallet_id в TON
        wallet_id = 698983191 + index
        
        _mnemonics, _pub_k, _priv_k, wallet = Wallets.from_mnemonics(
            mnemonics=self.mnemonic,
            version=get_wallet_version(),
            workchain=WORKCHAIN,
            wallet_id=wallet_id
        )
        
        # Non-bounceable для депозитов (безопаснее)
        return wallet.address.to_string(
            is_user_friendly=True,
            is_url_safe=True,
            is_bounceable=False
        )
    
    def get_subwallet(self, index: int):
        """
        Получение объекта subwallet для подписи транзакций.
        
        Args:
            index: Индекс subwallet
            
        Returns:
            Wallet object с методами для создания транзакций
        """
        wallet_id = 698983191 + index
        
        _mnemonics, _pub_k, _priv_k, wallet = Wallets.from_mnemonics(
            mnemonics=self.mnemonic,
            version=get_wallet_version(),
            workchain=WORKCHAIN,
            wallet_id=wallet_id
        )
        
        return wallet, _priv_k
    
    def get_hot_wallet_for_signing(self):
        """
        Получение hot wallet для подписи транзакций.
        
        Returns:
            Tuple[wallet, private_key]
        """
        return self.hot_wallet, self._hot_private_key


def validate_ton_address(address: str) -> bool:
    """
    Валидация TON адреса.
    
    Args:
        address: TON адрес в любом формате
        
    Returns:
        bool: True если адрес валидный
    """
    try:
        Address(address)
        return True
    except Exception:
        return False


def normalize_address(address: str, bounceable: bool = True) -> str:
    """
    Нормализация TON адреса к стандартному формату.
    
    Args:
        address: TON адрес в любом формате
        bounceable: Bounceable флаг
        
    Returns:
        str: Адрес в user-friendly формате
    """
    addr = Address(address)
    return addr.to_string(
        is_user_friendly=True,
        is_url_safe=True,
        is_bounceable=bounceable
    )