"""
Клиент для взаимодействия с TON блокчейном.

Использует TON Center API для:
- Получения балансов
- Отправки транзакций
- Получения информации о jetton wallets
"""

import asyncio
from decimal import Decimal
from typing import Optional
import httpx
import structlog
from tonsdk.boc import Cell
from tonsdk.utils import Address, bytes_to_b64str

from app.config import get_settings
from app.core.constants import (
    TON_CENTER_MAINNET, 
    TON_CENTER_TESTNET,
    USDT_MAINNET_MASTER,
    USDT_TESTNET_MASTER,
)
from app.core.jetton import nano_to_ton, nano_to_usdt

logger = structlog.get_logger()


class TonClient:
    """
    Клиент для работы с TON через TON Center API.
    
    TON Center — публичный API для взаимодействия с TON блокчейном.
    Бесплатный tier: 10 req/sec, достаточно для старта.
    
    Attributes:
        base_url: URL TON Center API
        api_key: API ключ (опционально, увеличивает лимиты)
        http_client: Async HTTP клиент
    """
    
    def __init__(self, network: str = "testnet", api_key: str = ""):
        """
        Инициализация клиента.
        
        Args:
            network: "mainnet" или "testnet"
            api_key: TON Center API key
        """
        self.network = network
        self.is_mainnet = network.lower() == "mainnet"
        
        self.base_url = TON_CENTER_MAINNET if self.is_mainnet else TON_CENTER_TESTNET
        self.api_key = api_key
        
        # USDT Master адрес зависит от сети
        self.usdt_master = USDT_MAINNET_MASTER if self.is_mainnet else USDT_TESTNET_MASTER
        
        self.http_client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Закрытие HTTP клиента."""
        await self.http_client.aclose()
    
    def _get_headers(self) -> dict:
        """Получение заголовков для запроса."""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers
    
    async def _request(self, method: str, params: dict) -> dict:
        """
        Выполнение запроса к TON Center API.
        
        Args:
            method: Метод API (getAddressBalance, sendBoc, etc.)
            params: Параметры запроса
            
        Returns:
            dict: Ответ API
            
        Raises:
            Exception: При ошибке API
        """
        url = f"{self.base_url}/{method}"
        
        try:
            response = await self.http_client.get(
                url,
                params=params,
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            
            if not data.get("ok"):
                error = data.get("error", "Unknown error")
                logger.error("TON Center API error", method=method, error=error)
                raise Exception(f"TON Center API error: {error}")
            
            return data.get("result")
            
        except httpx.HTTPError as e:
            logger.error("HTTP error", method=method, error=str(e))
            raise
    
    async def get_balance(self, address: str) -> Decimal:
        """
        Получение баланса TON.
        
        Args:
            address: TON адрес
            
        Returns:
            Decimal: Баланс в TON
        """
        result = await self._request("getAddressBalance", {"address": address})
        balance_nano = int(result)
        return nano_to_ton(balance_nano)
    
    async def get_address_info(self, address: str) -> dict:
        """
        Получение информации об адресе.
        
        Args:
            address: TON адрес
            
        Returns:
            dict: Информация (баланс, статус, код и т.д.)
        """
        return await self._request("getAddressInformation", {"address": address})
    
    async def get_jetton_wallet_address(
        self, 
        owner_address: str, 
        jetton_master: str | None = None
    ) -> str:
        """
        Получение адреса Jetton Wallet для владельца.
        
        Каждый пользователь имеет свой Jetton Wallet для каждого токена.
        Этот метод возвращает адрес Jetton Wallet по адресу владельца.
        
        Args:
            owner_address: Адрес владельца (основной TON кошелёк)
            jetton_master: Адрес Jetton Master (по умолчанию USDT)
            
        Returns:
            str: Адрес Jetton Wallet
        """
        if jetton_master is None:
            jetton_master = self.usdt_master
        
        result = await self._request(
            "runGetMethod",
            {
                "address": jetton_master,
                "method": "get_wallet_address",
                "stack": [
                    ["tvm.Slice", f"te6cccgBAQEAJAAAQ4A{self._address_to_cell_base64(owner_address)}"]
                ]
            }
        )
        
        # Парсим результат
        if result.get("exit_code") != 0:
            raise Exception(f"get_wallet_address failed: exit_code={result.get('exit_code')}")
        
        stack = result.get("stack", [])
        if not stack:
            raise Exception("Empty stack returned")
        
        # Первый элемент стека — адрес jetton wallet
        cell_data = stack[0][1].get("bytes")
        return self._parse_address_from_cell(cell_data)
    
    async def get_jetton_balance(
        self, 
        owner_address: str, 
        jetton_master: str | None = None
    ) -> Decimal:
        """
        Получение баланса Jetton (USDT).
        
        Args:
            owner_address: Адрес владельца
            jetton_master: Адрес Jetton Master (по умолчанию USDT)
            
        Returns:
            Decimal: Баланс в USDT
        """
        try:
            jetton_wallet = await self.get_jetton_wallet_address(owner_address, jetton_master)
            
            result = await self._request(
                "runGetMethod",
                {
                    "address": jetton_wallet,
                    "method": "get_wallet_data",
                    "stack": []
                }
            )
            
            if result.get("exit_code") != 0:
                # Jetton wallet не существует — баланс 0
                return Decimal("0")
            
            stack = result.get("stack", [])
            if not stack:
                return Decimal("0")
            
            # Первый элемент — баланс в nano
            balance_nano = int(stack[0][1], 16) if isinstance(stack[0][1], str) else int(stack[0][1])
            return nano_to_usdt(balance_nano)
            
        except Exception as e:
            logger.warning("Failed to get jetton balance", address=owner_address, error=str(e))
            return Decimal("0")
    
    async def send_boc(self, boc: str) -> dict:
        """
        Отправка подписанной транзакции в блокчейн.
        
        Args:
            boc: Base64-encoded BOC (Bag of Cells)
            
        Returns:
            dict: Результат отправки
        """
        result = await self._request("sendBoc", {"boc": boc})
        logger.info("Transaction sent", result=result)
        return result
    
    async def get_transactions(
        self, 
        address: str, 
        limit: int = 10,
        lt: int | None = None,
        hash: str | None = None
    ) -> list:
        """
        Получение транзакций адреса.
        
        Args:
            address: TON адрес
            limit: Максимальное количество
            lt: Logical time (для пагинации)
            hash: Hash транзакции (для пагинации)
            
        Returns:
            list: Список транзакций
        """
        params = {"address": address, "limit": limit}
        if lt:
            params["lt"] = lt
        if hash:
            params["hash"] = hash
        
        return await self._request("getTransactions", params)
    
    def _address_to_cell_base64(self, address: str) -> str:
        """Конвертация адреса в base64 для TVM."""
        addr = Address(address)
        # Создаём cell с адресом
        from tonsdk.boc import begin_cell
        cell = begin_cell().store_address(addr).end_cell()
        return bytes_to_b64str(cell.to_boc(False))
    
    def _parse_address_from_cell(self, cell_base64: str) -> str:
        """Парсинг адреса из base64 cell."""
        import base64
        from tonsdk.boc import Cell
        
        cell_bytes = base64.b64decode(cell_base64)
        cell = Cell.one_from_boc(cell_bytes)
        
        # Читаем адрес из cell
        slice_data = cell.begin_parse()
        addr = slice_data.read_msg_addr()
        
        return addr.to_string(is_user_friendly=True, is_url_safe=True, is_bounceable=True)


async def get_ton_client() -> TonClient:
    """
    Получение настроенного TON клиента.
    
    Использует настройки из .env
    """
    settings = get_settings()
    return TonClient(
        network=settings.ton_network,
        api_key=settings.ton_center_api_key
    )