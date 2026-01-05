"""
Fee Engine — расчёт комиссий.

Комиссия покрывает только стоимость газа в TON, конвертированную в USDT.
Формула: fee_usdt = gas_ton * ton_usdt_rate * (1 + buffer)

Buffer (15%) — запас на волатильность курса.
"""

from decimal import Decimal, ROUND_UP
import structlog

from app.services.price_service import PriceService, get_price_service
from app.core.constants import JETTON_TRANSFER_GAS

logger = structlog.get_logger()


class FeeEngine:
    """
    Расчёт комиссий за операции.
    
    Комиссия = стоимость газа в USDT + буфер на волатильность.
    
    Attributes:
        price_service: Сервис получения курсов
        gas_buffer: Буфер на волатильность (0.15 = 15%)
        min_fee_usdt: Минимальная комиссия (защита от микротранзакций)
    """
    
    def __init__(
        self,
        price_service: PriceService,
        gas_buffer: float = 0.15,
        min_fee_usdt: Decimal = Decimal("0.01")
    ):
        """
        Args:
            price_service: Сервис получения курсов
            gas_buffer: Буфер на волатильность (по умолчанию 15%)
            min_fee_usdt: Минимальная комиссия в USDT
        """
        self.price_service = price_service
        self.gas_buffer = Decimal(str(gas_buffer))
        self.min_fee_usdt = min_fee_usdt
    
    async def calculate_transfer_fee(
        self,
        amount: Decimal | None = None,  # Не используется, но оставлен для будущего
        gas_estimate_ton: Decimal | None = None
    ) -> dict:
        """
        Расчёт комиссии за перевод USDT.
        
        Args:
            amount: Сумма перевода (не влияет на комиссию в текущей модели)
            gas_estimate_ton: Оценка газа в TON (если None — используется стандартная)
            
        Returns:
            dict: {
                "fee_usdt": Decimal,      # Комиссия в USDT
                "gas_ton": Decimal,       # Газ в TON
                "ton_usdt_rate": Decimal, # Использованный курс
                "buffer": Decimal,        # Использованный буфер
            }
        """
        # Газ для jetton transfer
        if gas_estimate_ton is None:
            gas_ton = Decimal(str(JETTON_TRANSFER_GAS))
        else:
            gas_ton = gas_estimate_ton
        
        # Получаем курс TON/USDT
        ton_usdt_rate = await self.price_service.get_ton_usdt_price()
        
        # Рассчитываем комиссию
        # fee = gas_ton * rate * (1 + buffer)
        gas_cost_usdt = gas_ton * ton_usdt_rate
        fee_with_buffer = gas_cost_usdt * (Decimal("1") + self.gas_buffer)
        
        # Округляем вверх до 2 знаков
        fee_usdt = fee_with_buffer.quantize(Decimal("0.01"), rounding=ROUND_UP)
        
        # Применяем минимальную комиссию
        fee_usdt = max(fee_usdt, self.min_fee_usdt)
        
        logger.info(
            "Fee calculated",
            gas_ton=str(gas_ton),
            ton_usdt_rate=str(ton_usdt_rate),
            gas_cost_usdt=str(gas_cost_usdt),
            buffer=str(self.gas_buffer),
            fee_usdt=str(fee_usdt)
        )
        
        return {
            "fee_usdt": fee_usdt,
            "gas_ton": gas_ton,
            "ton_usdt_rate": ton_usdt_rate,
            "buffer": self.gas_buffer,
        }
    
    async def estimate_fee(self) -> Decimal:
        """
        Быстрая оценка комиссии (для UI).
        
        Returns:
            Decimal: Примерная комиссия в USDT
        """
        result = await self.calculate_transfer_fee()
        return result["fee_usdt"]
    
    def validate_sufficient_balance(
        self,
        user_balance: Decimal,
        amount: Decimal,
        fee: Decimal
    ) -> tuple[bool, str]:
        """
        Проверка достаточности баланса.
        
        Args:
            user_balance: Баланс пользователя в USDT
            amount: Сумма перевода
            fee: Комиссия
            
        Returns:
            tuple[bool, str]: (is_valid, error_message)
        """
        total_required = amount + fee
        
        if user_balance < total_required:
            deficit = total_required - user_balance
            return (
                False, 
                f"Insufficient balance. Need {total_required} USDT, have {user_balance} USDT. Short by {deficit} USDT"
            )
        
        return (True, "")


async def get_fee_engine() -> FeeEngine:
    """Получение FeeEngine с зависимостями."""
    from app.config import get_settings
    settings = get_settings()
    
    price_service = await get_price_service()
    
    return FeeEngine(
        price_service=price_service,
        gas_buffer=settings.gas_fee_buffer
    )