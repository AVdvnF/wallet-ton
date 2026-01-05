"""
Gas Manager — управление балансом TON для газа.

Отвечает за:
- Мониторинг TON баланса hot wallet
- Блокировку операций при низком балансе
- Алерты при достижении thresholds
"""

from decimal import Decimal
import structlog

from app.core.ton_client import TonClient
from app.core.constants import MIN_TON_BALANCE_CRITICAL, MIN_TON_BALANCE_WARNING

logger = structlog.get_logger()


class GasManager:
    """
    Менеджер газа (TON).
    
    Контролирует баланс TON на hot wallet.
    Блокирует операции если баланс ниже критического уровня.
    
    Attributes:
        ton_client: Клиент для работы с TON
        hot_wallet_address: Адрес hot wallet
        warning_threshold: Порог для warning алерта
        critical_threshold: Порог для блокировки операций
    """
    
    def __init__(
        self,
        ton_client: TonClient,
        hot_wallet_address: str,
        warning_threshold: Decimal = Decimal(str(MIN_TON_BALANCE_WARNING)),
        critical_threshold: Decimal = Decimal(str(MIN_TON_BALANCE_CRITICAL))
    ):
        """
        Args:
            ton_client: TON клиент
            hot_wallet_address: Адрес hot wallet
            warning_threshold: Порог warning (по умолчанию 10 TON)
            critical_threshold: Порог critical (по умолчанию 2 TON)
        """
        self.ton_client = ton_client
        self.hot_wallet_address = hot_wallet_address
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
    
    async def get_ton_balance(self) -> Decimal:
        """
        Получение текущего баланса TON на hot wallet.
        
        Returns:
            Decimal: Баланс в TON
        """
        balance = await self.ton_client.get_balance(self.hot_wallet_address)
        logger.debug("Hot wallet TON balance", balance=str(balance))
        return balance
    
    async def check_gas_availability(
        self, 
        required_gas: Decimal = Decimal("0.05")
    ) -> dict:
        """
        Проверка доступности газа для операции.
        
        Args:
            required_gas: Требуемое количество TON для операции
            
        Returns:
            dict: {
                "available": bool,       # Можно ли выполнить операцию
                "balance": Decimal,      # Текущий баланс
                "status": str,           # "ok", "warning", "critical"
                "message": str,          # Сообщение
            }
        """
        balance = await self.get_ton_balance()
        
        # Определяем статус
        if balance < self.critical_threshold:
            status = "critical"
            available = False
            message = f"CRITICAL: TON balance ({balance}) below critical threshold ({self.critical_threshold}). Operations blocked."
            logger.error(message, balance=str(balance), threshold=str(self.critical_threshold))
            
        elif balance < required_gas:
            status = "critical"
            available = False
            message = f"Insufficient TON for gas. Have {balance}, need {required_gas}"
            logger.error(message)
            
        elif balance < self.warning_threshold:
            status = "warning"
            available = True
            message = f"WARNING: TON balance ({balance}) below warning threshold ({self.warning_threshold}). Please top up."
            logger.warning(message, balance=str(balance), threshold=str(self.warning_threshold))
            
        else:
            status = "ok"
            available = True
            message = f"TON balance OK: {balance}"
            logger.debug(message)
        
        return {
            "available": available,
            "balance": balance,
            "status": status,
            "message": message,
        }
    
    async def can_process_transfer(self) -> tuple[bool, str]:
        """
        Проверка возможности обработки перевода.
        
        Returns:
            tuple[bool, str]: (can_process, reason)
        """
        result = await self.check_gas_availability()
        return (result["available"], result["message"])
    
    async def get_status(self) -> dict:
        """
        Получение полного статуса Gas Manager.
        
        Returns:
            dict: Полная информация о состоянии
        """
        balance = await self.get_ton_balance()
        
        return {
            "hot_wallet_address": self.hot_wallet_address,
            "ton_balance": str(balance),
            "warning_threshold": str(self.warning_threshold),
            "critical_threshold": str(self.critical_threshold),
            "status": "critical" if balance < self.critical_threshold else 
                      "warning" if balance < self.warning_threshold else "ok",
            "operations_allowed": balance >= self.critical_threshold,
        }