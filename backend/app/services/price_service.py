"""
Сервис получения курсов валют.

Получает актуальный курс TON/USDT с Binance API.
Используется для расчёта комиссии за газ в USDT.
"""

import asyncio
from decimal import Decimal
from typing import Optional
import httpx
import structlog
from datetime import datetime, timedelta

logger = structlog.get_logger()


class PriceService:
    """
    Сервис получения цен.
    
    Кэширует курс на 60 секунд для снижения нагрузки на API.
    
    Attributes:
        _cache: Кэш курса {symbol: (price, timestamp)}
        _cache_ttl: Время жизни кэша в секундах
    """
    
    BINANCE_API = "https://api.binance.com/api/v3"
    
    def __init__(self, cache_ttl: int = 60):
        """
        Args:
            cache_ttl: Время жизни кэша в секундах (по умолчанию 60)
        """
        self._cache: dict[str, tuple[Decimal, datetime]] = {}
        self._cache_ttl = cache_ttl
        self._http_client = httpx.AsyncClient(timeout=10.0)
    
    async def close(self):
        """Закрытие HTTP клиента."""
        await self._http_client.aclose()
    
    async def get_ton_usdt_price(self) -> Decimal:
        """
        Получение курса TON/USDT.
        
        Returns:
            Decimal: Текущая цена TON в USDT
            
        Raises:
            Exception: При ошибке получения курса
        """
        return await self._get_price("TONUSDT")
    
    async def _get_price(self, symbol: str) -> Decimal:
        """
        Получение цены с кэшированием.
        
        Args:
            symbol: Торговая пара (например, TONUSDT)
            
        Returns:
            Decimal: Цена
        """
        # Проверяем кэш
        if symbol in self._cache:
            price, cached_at = self._cache[symbol]
            if datetime.utcnow() - cached_at < timedelta(seconds=self._cache_ttl):
                logger.debug("Price from cache", symbol=symbol, price=str(price))
                return price
        
        # Запрашиваем с Binance
        try:
            response = await self._http_client.get(
                f"{self.BINANCE_API}/ticker/price",
                params={"symbol": symbol}
            )
            response.raise_for_status()
            data = response.json()
            
            price = Decimal(data["price"])
            
            # Кэшируем
            self._cache[symbol] = (price, datetime.utcnow())
            
            logger.info("Price fetched", symbol=symbol, price=str(price))
            return price
            
        except Exception as e:
            logger.error("Failed to get price", symbol=symbol, error=str(e))
            
            # Если есть старый кэш — используем его
            if symbol in self._cache:
                price, _ = self._cache[symbol]
                logger.warning("Using stale cache", symbol=symbol, price=str(price))
                return price
            
            raise Exception(f"Cannot get price for {symbol}: {e}")
    
    def get_cached_price(self, symbol: str = "TONUSDT") -> Optional[Decimal]:
        """
        Получение кэшированной цены (без запроса).
        
        Returns:
            Decimal | None: Цена или None если кэш пуст
        """
        if symbol in self._cache:
            price, _ = self._cache[symbol]
            return price
        return None


# Глобальный instance (singleton pattern)
_price_service: Optional[PriceService] = None


async def get_price_service() -> PriceService:
    """Получение singleton instance PriceService."""
    global _price_service
    if _price_service is None:
        _price_service = PriceService()
    return _price_service