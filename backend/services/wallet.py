"""
Wallet service — generates blockchain addresses for clients.
"""

import os
from typing import Protocol

from eth_account import Account

SUPPORTED_NETWORKS: frozenset[str] = frozenset({"hardhat", "sepolia"})

# RPC endpoints used when registering wallets on-chain
RPC_URLS: dict[str, str] = {
    "hardhat": os.environ.get("HARDHAT_RPC_URL", "http://127.0.0.1:8545"),
    "sepolia": os.environ.get("SEPOLIA_RPC_URL", ""),
}


class WalletService(Protocol):
    def generate_address(self, network: str) -> str:
        """Return a new chain address for the given network."""
        ...


class EthereumWalletService:
    """Generates Ethereum-compatible addresses via web3.py Account.create()."""

    def generate_address(self, network: str) -> str:
        account = Account.create()
        return account.address
