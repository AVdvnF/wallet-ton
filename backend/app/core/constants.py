"""
Константы для работы с TON.

Адреса контрактов, параметры сети и т.д.
"""

from enum import Enum


class Network(str, Enum):
    """TON Network."""
    MAINNET = "mainnet"
    TESTNET = "testnet"


# ============================================
# USDT Jetton Master Contract
# ============================================
# Mainnet USDT (официальный Tether)
USDT_MAINNET_MASTER = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"

# Testnet — нужно задеплоить свой тестовый jetton или использовать известный
# Можно использовать jUSDT от Dedust: 
USDT_TESTNET_MASTER = "kQD0GKBM8ZbryVk2aESmzfU6b9b_8era_IkvBSELujFZPsyy"


# ============================================
# TON Center API
# ============================================
TON_CENTER_MAINNET = "https://toncenter.com/api/v2"
TON_CENTER_TESTNET = "https://testnet.toncenter.com/api/v2"


# ============================================
# Gas Configuration
# ============================================
# Примерный gas для jetton transfer (в TON)
JETTON_TRANSFER_GAS = 0.05  # 0.05 TON

# Forward amount для jetton transfer (отправляется получателю для уведомления)
JETTON_FORWARD_AMOUNT = 0.001  # 0.001 TON

# Минимальный баланс TON на hot wallet
MIN_TON_BALANCE_CRITICAL = 2.0   # Блокировка операций
MIN_TON_BALANCE_WARNING = 10.0   # Алерт


# ============================================
# Wallet Configuration  
# ============================================
# Версия wallet контракта для subwallets
# v4r2 — современная версия с поддержкой plugins
WALLET_VERSION = "v4r2"

# Workchain (0 — основной, -1 — masterchain)
WORKCHAIN = 0