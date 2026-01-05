"""
Работа с Jettons (токенами на TON).

USDT на TON — это Jetton (TEP-74 стандарт).
Каждый пользователь имеет свой Jetton Wallet для каждого токена.

Структура:
- Jetton Master — контракт токена (один на весь токен)
- Jetton Wallet — кошелёк пользователя для этого токена (у каждого свой)

Для перевода USDT:
1. Находим Jetton Wallet отправителя
2. Отправляем transfer message на этот wallet
3. Jetton Wallet отправителя → Jetton Wallet получателя
"""

from decimal import Decimal
from tonsdk.boc import Cell, begin_cell
from tonsdk.utils import Address, to_nano

from app.core.constants import JETTON_FORWARD_AMOUNT


# Jetton Transfer op code (TEP-74)
JETTON_TRANSFER_OP = 0xf8a7ea5


def build_jetton_transfer_body(
    destination: str,
    amount: int,
    response_destination: str | None = None,
    forward_amount: int = 0,
    forward_payload: Cell | None = None,
    query_id: int = 0
) -> Cell:
    """
    Создание тела сообщения для Jetton Transfer.
    
    TEP-74 Transfer message structure:
    - op: uint32 = 0xf8a7ea5
    - query_id: uint64
    - amount: Coins (количество jettons)
    - destination: Address (получатель jettons)
    - response_destination: Address (куда отправить excess)
    - custom_payload: Maybe Cell
    - forward_ton_amount: Coins (сколько TON отправить вместе)
    - forward_payload: Maybe Cell (данные для получателя)
    
    Args:
        destination: Адрес получателя (его основной TON адрес, не jetton wallet!)
        amount: Количество jettons в минимальных единицах (для USDT: 6 decimals)
        response_destination: Куда вернуть excess TON (обычно отправитель)
        forward_amount: Сколько TON отправить получателю (для уведомления)
        forward_payload: Дополнительные данные для получателя
        query_id: Уникальный ID запроса
        
    Returns:
        Cell: Тело сообщения для отправки на Jetton Wallet
    """
    # Парсим адреса
    dest_addr = Address(destination)
    
    # Response destination — куда вернуть остаток TON
    if response_destination:
        resp_addr = Address(response_destination)
    else:
        resp_addr = dest_addr  # По умолчанию — получателю
    
    # Строим Cell
    body = (
        begin_cell()
        .store_uint(JETTON_TRANSFER_OP, 32)  # op code
        .store_uint(query_id, 64)             # query_id
        .store_coins(amount)                  # amount of jettons
        .store_address(dest_addr)             # destination
        .store_address(resp_addr)             # response_destination
        .store_bit(0)                         # custom_payload (empty)
        .store_coins(forward_amount)          # forward_ton_amount
    )
    
    # Forward payload
    if forward_payload:
        body = body.store_bit(1).store_ref(forward_payload)
    else:
        body = body.store_bit(0)
    
    return body.end_cell()


def build_jetton_transfer_message(
    jetton_wallet_address: str,
    destination: str,
    jetton_amount: int,
    response_destination: str,
    ton_amount: int = 50000000,  # 0.05 TON для газа
    forward_amount: int = 1000000,  # 0.001 TON для уведомления
    query_id: int = 0
) -> dict:
    """
    Создание полного сообщения для Jetton Transfer.
    
    Это сообщение отправляется с основного кошелька на Jetton Wallet.
    
    Args:
        jetton_wallet_address: Адрес Jetton Wallet отправителя
        destination: Адрес получателя (основной TON адрес)
        jetton_amount: Количество jettons (в минимальных единицах)
        response_destination: Куда вернуть excess TON
        ton_amount: Сколько TON приложить к сообщению (для газа)
        forward_amount: Сколько TON отправить получателю
        query_id: Уникальный ID
        
    Returns:
        dict: Параметры для отправки через wallet.create_transfer_message()
    """
    body = build_jetton_transfer_body(
        destination=destination,
        amount=jetton_amount,
        response_destination=response_destination,
        forward_amount=forward_amount,
        query_id=query_id
    )
    
    return {
        "to_addr": jetton_wallet_address,
        "amount": ton_amount,
        "payload": body,
    }


def usdt_to_nano(amount: Decimal | float | str) -> int:
    """
    Конвертация USDT в минимальные единицы.
    
    USDT имеет 6 decimals (как и оригинальный Tether).
    1 USDT = 1_000_000 nano USDT
    
    Args:
        amount: Сумма в USDT (например, 10.5)
        
    Returns:
        int: Сумма в минимальных единицах (10500000)
    """
    if isinstance(amount, str):
        amount = Decimal(amount)
    elif isinstance(amount, float):
        amount = Decimal(str(amount))
    
    return int(amount * Decimal("1000000"))


def nano_to_usdt(amount: int) -> Decimal:
    """
    Конвертация из минимальных единиц в USDT.
    
    Args:
        amount: Сумма в минимальных единицах
        
    Returns:
        Decimal: Сумма в USDT
    """
    return Decimal(amount) / Decimal("1000000")


def ton_to_nano(amount: Decimal | float | str) -> int:
    """
    Конвертация TON в nanoTON.
    
    1 TON = 1_000_000_000 nanoTON (9 decimals)
    
    Args:
        amount: Сумма в TON
        
    Returns:
        int: Сумма в nanoTON
    """
    if isinstance(amount, str):
        amount = Decimal(amount)
    elif isinstance(amount, float):
        amount = Decimal(str(amount))
    
    return int(amount * Decimal("1000000000"))


def nano_to_ton(amount: int) -> Decimal:
    """
    Конвертация из nanoTON в TON.
    
    Args:
        amount: Сумма в nanoTON
        
    Returns:
        Decimal: Сумма в TON
    """
    return Decimal(amount) / Decimal("1000000000")