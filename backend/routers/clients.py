"""
Client endpoints:

  POST /clients                    — KYC verification + client record creation
  POST /clients/{id}/wallet        — wallet address generation + on-chain registration
  POST /clients/{id}/deposit       — mint Deposit_Tokens for a fiat deposit
  POST /clients/{id}/withdraw      — burn Deposit_Tokens for a fiat withdrawal
  GET  /clients/{id}/balance       — on-chain balance for one (asset_type, network)
  GET  /clients/{id}/balances      — on-chain balances for all Token_Registry pairs
  GET  /clients/{id}/transactions  — Firestore transaction history for the client
"""

import os
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from web3 import Web3

from services.kyc import KYCRequest, KYCService
from services.wallet import SUPPORTED_NETWORKS, RPC_URLS, EthereumWalletService

router = APIRouter(prefix="/clients", tags=["clients"])

_kyc_service = KYCService()
_wallet_service = EthereumWalletService()

# Minimal ABI — only the functions we call
_REGISTER_WALLET_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "wallet", "type": "address"}],
        "name": "registerWallet",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

_DEPOSIT_TOKEN_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "burn",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "paused",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _db(request: Request):
    return request.app.state.db


def _token_registry(request: Request) -> dict[str, Any]:
    return request.app.state.token_registry


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ClientCreate(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    national_id: str


class ClientResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    kyc_status: str
    kyc_failure_reason: Optional[str] = None


class WalletResponse(BaseModel):
    client_id: str
    wallet: dict[str, str]


class DepositRequest(BaseModel):
    amount: int
    asset_type: str
    network: str


class DepositResponse(BaseModel):
    transaction_id: str
    status: str
    on_chain_tx_hash: Optional[str] = None
    gas_used: Optional[int] = None
    gas_price_gwei: Optional[float] = None
    fee_eth: Optional[float] = None


class WithdrawRequest(BaseModel):
    amount: int
    asset_type: str
    network: str


class WithdrawResponse(BaseModel):
    transaction_id: str
    status: str
    on_chain_tx_hash: Optional[str] = None
    gas_used: Optional[int] = None
    gas_price_gwei: Optional[float] = None
    fee_eth: Optional[float] = None


class BalanceEntry(BaseModel):
    asset_type: str
    network: str
    chain_address: str
    balance: int
    error: Optional[str] = None


class GasEstimate(BaseModel):
    network: str
    base_fee_gwei: float
    priority_fee_gwei: float
    gas_limit: int
    estimated_fee_eth: float


class TransactionRecord(BaseModel):
    id: str
    type: str
    amount: int
    asset_type: str
    network: str
    status: str
    on_chain_tx_hash: Optional[str] = None
    contract_address: Optional[str] = None
    created_at: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("", response_model=ClientResponse, status_code=201)
def create_client(body: ClientCreate, db=Depends(_db)):
    """Run KYC and create a client record in Firestore."""
    kyc_result = _kyc_service.verify(
        KYCRequest(
            first_name=body.first_name,
            last_name=body.last_name,
            date_of_birth=body.date_of_birth,
            national_id=body.national_id,
        )
    )

    client_id = str(uuid.uuid4())
    record: dict[str, Any] = {
        "id": client_id,
        "first_name": body.first_name,
        "last_name": body.last_name,
        "date_of_birth": body.date_of_birth.isoformat(),
        "national_id": body.national_id,
        "kyc_status": "approved" if kyc_result.approved else "failed",
    }
    if not kyc_result.approved:
        record["kyc_failure_reason"] = kyc_result.failure_reason

    db.collection("clients").document(client_id).set(record)

    if not kyc_result.approved:
        raise HTTPException(
            status_code=422,
            detail={
                "kyc_status": "failed",
                "kyc_failure_reason": kyc_result.failure_reason,
            },
        )

    return ClientResponse(**record)


@router.post("/{client_id}/wallet", response_model=WalletResponse)
def create_wallet(
    client_id: str,
    db=Depends(_db),
    token_registry: dict[str, Any] = Depends(_token_registry),
):
    """
    Generate one chain address per supported network and register each on the
    corresponding DepositToken contracts.  Returns existing wallet if already
    created (idempotent, 200).
    """
    doc = db.collection("clients").document(client_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Client not found")

    client: dict[str, Any] = doc.to_dict()

    if client.get("kyc_status") != "approved":
        raise HTTPException(status_code=403, detail="Client is not KYC-approved")

    # Idempotent: return existing wallet
    if existing := client.get("wallet"):
        return WalletResponse(client_id=client_id, wallet=existing)

    # Generate one address per network
    wallet: dict[str, str] = {
        network: _wallet_service.generate_address(network)
        for network in SUPPORTED_NETWORKS
    }

    db.collection("clients").document(client_id).update({"wallet": wallet})

    # Register addresses on-chain (best-effort; skip if RPC or key not configured)
    operator_key = os.environ.get("OPERATOR_PRIVATE_KEY", "")
    if operator_key:
        for network, address in wallet.items():
            rpc_url = RPC_URLS.get(network, "")
            if not rpc_url:
                continue
            try:
                _register_on_chain(token_registry, network, address, rpc_url, operator_key)
            except Exception as exc:
                print(f"[wallet] on-chain registration skipped for {network}: {exc}")

    return WalletResponse(client_id=client_id, wallet=wallet)


@router.get("/gas-estimate", response_model=GasEstimate)
def gas_estimate(network: str = Query(...)):
    """Return current gas price estimates for a mint/burn operation."""
    rpc_url = RPC_URLS.get(network, "")
    if not rpc_url:
        raise HTTPException(status_code=404, detail=f"Unknown network: {network}")
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        latest = w3.eth.get_block("latest")
        base_fee = latest.get("baseFeePerGas", 0)
        priority_fee = w3.eth.max_priority_fee
        gas_limit = 200_000
        estimated_fee_eth = (base_fee + priority_fee) * gas_limit / 1e18
        return GasEstimate(
            network=network,
            base_fee_gwei=base_fee / 1e9,
            priority_fee_gwei=priority_fee / 1e9,
            gas_limit=gas_limit,
            estimated_fee_eth=estimated_fee_eth,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not fetch gas estimate: {exc}") from exc


@router.post("/{client_id}/deposit", response_model=DepositResponse)
def create_deposit(
    client_id: str,
    body: DepositRequest,
    db=Depends(_db),
    token_registry: dict[str, Any] = Depends(_token_registry),
):
    """
    Mint Deposit_Tokens for a fiat deposit.

    1. Resolve the DepositToken contract from the Token_Registry.
    2. Create a pending transaction record in Firestore.
    3. Call mint() on-chain via the operator key.
    4. Update the transaction record to confirmed/failed.
    """
    # Validate client exists and has a wallet address for the requested network
    doc = db.collection("clients").document(client_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Client not found")

    client: dict[str, Any] = doc.to_dict()
    chain_address = client.get("wallet", {}).get(body.network)
    if not chain_address:
        raise HTTPException(
            status_code=404,
            detail=f"No wallet address for network {body.network!r}",
        )

    # Resolve contract from token registry
    registry_key = f"{body.asset_type}_{body.network}"
    entry = token_registry.get(registry_key)
    if not entry or not entry.get("contract_address"):
        raise HTTPException(
            status_code=404,
            detail=f"No contract found for {body.asset_type}/{body.network}",
        )
    contract_address = entry["contract_address"]

    # Create pending transaction record
    tx_id = str(uuid.uuid4())
    db.collection("transactions").document(tx_id).set(
        {
            "id": tx_id,
            "client_id": client_id,
            "type": "deposit",
            "amount": body.amount,
            "asset_type": body.asset_type,
            "network": body.network,
            "status": "pending",
            "on_chain_tx_hash": None,
            "contract_address": contract_address,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Connect to chain and check pause state
    operator_key = os.environ.get("OPERATOR_PRIVATE_KEY", "")
    rpc_url = RPC_URLS.get(body.network, "")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=_DEPOSIT_TOKEN_ABI,
    )

    if contract.functions.paused().call():
        raise HTTPException(
            status_code=503,
            detail=f"contract paused for {body.asset_type}/{body.network}",
        )

    # Mint tokens
    try:
        operator = w3.eth.account.from_key(operator_key)
        tx = contract.functions.mint(
            Web3.to_checksum_address(chain_address),
            body.amount * 10**18,
        ).build_transaction(
            {
                "from": operator.address,
                "nonce": w3.eth.get_transaction_count(operator.address),
                "gas": 200_000,
            }
        )
        signed = w3.eth.account.sign_transaction(tx, operator_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    except Exception as exc:
        db.collection("transactions").document(tx_id).update({"status": "failed"})
        raise HTTPException(status_code=502, detail=f"On-chain mint failed: {exc}") from exc

    gas_used, gas_price_gwei, fee_eth = _extract_gas(w3, tx_hash)
    db.collection("transactions").document(tx_id).update(
        {"status": "confirmed", "on_chain_tx_hash": tx_hash}
    )
    return DepositResponse(
        transaction_id=tx_id,
        status="confirmed",
        on_chain_tx_hash=tx_hash,
        gas_used=gas_used,
        gas_price_gwei=gas_price_gwei,
        fee_eth=fee_eth,
    )


@router.post("/{client_id}/withdraw", response_model=WithdrawResponse)
def create_withdrawal(
    client_id: str,
    body: WithdrawRequest,
    db=Depends(_db),
    token_registry: dict[str, Any] = Depends(_token_registry),
):
    """
    Burn Deposit_Tokens for a fiat withdrawal.

    1. Resolve the DepositToken contract from the Token_Registry.
    2. Verify the client's chain address holds enough tokens (422 if not).
    3. Create a pending transaction record in Firestore.
    4. Call burn() on-chain via the operator key.
    5. Update the transaction record to confirmed/failed.
    """
    # Validate client exists and has a wallet address for the requested network
    doc = db.collection("clients").document(client_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Client not found")

    client: dict[str, Any] = doc.to_dict()
    chain_address = client.get("wallet", {}).get(body.network)
    if not chain_address:
        raise HTTPException(
            status_code=404,
            detail=f"No wallet address for network {body.network!r}",
        )

    # Resolve contract from token registry
    registry_key = f"{body.asset_type}_{body.network}"
    entry = token_registry.get(registry_key)
    if not entry or not entry.get("contract_address"):
        raise HTTPException(
            status_code=404,
            detail=f"No contract found for {body.asset_type}/{body.network}",
        )
    contract_address = entry["contract_address"]

    # Connect to chain
    operator_key = os.environ.get("OPERATOR_PRIVATE_KEY", "")
    rpc_url = RPC_URLS.get(body.network, "")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=_DEPOSIT_TOKEN_ABI,
    )

    # Check pause state
    if contract.functions.paused().call():
        raise HTTPException(
            status_code=503,
            detail=f"contract paused for {body.asset_type}/{body.network}",
        )

    # Verify sufficient balance
    balance = contract.functions.balanceOf(
        Web3.to_checksum_address(chain_address)
    ).call()
    balance = balance // 10**18
    if balance < body.amount:
        raise HTTPException(
            status_code=422,
            detail={"message": "Insufficient token balance", "balance": balance},
        )

    # Create pending transaction record
    tx_id = str(uuid.uuid4())
    db.collection("transactions").document(tx_id).set(
        {
            "id": tx_id,
            "client_id": client_id,
            "type": "withdrawal",
            "amount": body.amount,
            "asset_type": body.asset_type,
            "network": body.network,
            "status": "pending",
            "on_chain_tx_hash": None,
            "contract_address": contract_address,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    # Burn tokens
    try:
        operator = w3.eth.account.from_key(operator_key)
        tx = contract.functions.burn(
            Web3.to_checksum_address(chain_address),
            body.amount * 10**18,
        ).build_transaction(
            {
                "from": operator.address,
                "nonce": w3.eth.get_transaction_count(operator.address),
                "gas": 200_000,
            }
        )
        signed = w3.eth.account.sign_transaction(tx, operator_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    except Exception as exc:
        db.collection("transactions").document(tx_id).update({"status": "failed"})
        raise HTTPException(status_code=502, detail=f"On-chain burn failed: {exc}") from exc

    gas_used, gas_price_gwei, fee_eth = _extract_gas(w3, tx_hash)
    db.collection("transactions").document(tx_id).update(
        {"status": "confirmed", "on_chain_tx_hash": tx_hash}
    )
    return WithdrawResponse(
        transaction_id=tx_id,
        status="confirmed",
        on_chain_tx_hash=tx_hash,
        gas_used=gas_used,
        gas_price_gwei=gas_price_gwei,
        fee_eth=fee_eth,
    )


@router.get("/{client_id}/balance", response_model=BalanceEntry)
def get_balance(
    client_id: str,
    asset_type: str = Query(...),
    network: str = Query(...),
    db=Depends(_db),
    token_registry: dict[str, Any] = Depends(_token_registry),
):
    """Return the on-chain token balance for one (asset_type, network) pair."""
    doc = db.collection("clients").document(client_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Client not found")

    client: dict[str, Any] = doc.to_dict()
    chain_address = client.get("wallet", {}).get(network)
    if not chain_address:
        raise HTTPException(
            status_code=404,
            detail=f"No wallet address for network {network!r}",
        )

    registry_key = f"{asset_type}_{network}"
    entry = token_registry.get(registry_key)
    if not entry or not entry.get("contract_address"):
        raise HTTPException(
            status_code=404,
            detail=f"No contract found for {asset_type}/{network}",
        )

    w3 = Web3(Web3.HTTPProvider(RPC_URLS.get(network, "")))
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(entry["contract_address"]),
        abi=_DEPOSIT_TOKEN_ABI,
    )
    balance = contract.functions.balanceOf(
        Web3.to_checksum_address(chain_address)
    ).call()

    return BalanceEntry(
        asset_type=asset_type,
        network=network,
        chain_address=chain_address,
        balance=balance,
    )


@router.get("/{client_id}/balances", response_model=list[BalanceEntry])
def get_balances(
    client_id: str,
    db=Depends(_db),
    token_registry: dict[str, Any] = Depends(_token_registry),
):
    """Return on-chain balances for every (asset_type, network) pair in the Token_Registry."""
    doc = db.collection("clients").document(client_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Client not found")

    wallet: dict[str, str] = doc.to_dict().get("wallet", {})
    results: list[BalanceEntry] = []

    for entry in token_registry.values():
        asset_type = entry["asset_type"]
        network = entry["network"]
        contract_address = entry.get("contract_address", "")
        chain_address = wallet.get(network, "")

        if not contract_address or not chain_address:
            results.append(
                BalanceEntry(
                    asset_type=asset_type,
                    network=network,
                    chain_address=chain_address,
                    balance=0,
                )
            )
            continue

        rpc_url = RPC_URLS.get(network, "")
        if not rpc_url:
            continue  # skip networks with no RPC configured (e.g. stale registry entries)

        w3 = Web3(Web3.HTTPProvider(rpc_url))
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=_DEPOSIT_TOKEN_ABI,
        )
        try:
            balance = contract.functions.balanceOf(
                Web3.to_checksum_address(chain_address)
            ).call()
            results.append(
                BalanceEntry(
                    asset_type=asset_type,
                    network=network,
                    chain_address=chain_address,
                    balance=balance // 10**18,
                )
            )
        except Exception:
            error_msg = "Hardhat node isn't running" if network == "hardhat" else f"{network.capitalize()} node unreachable"
            results.append(
                BalanceEntry(
                    asset_type=asset_type,
                    network=network,
                    chain_address=chain_address,
                    balance=0,
                    error=error_msg,
                )
            )

    return results


@router.get("/{client_id}/transactions", response_model=list[TransactionRecord])
def get_transactions(
    client_id: str,
    db=Depends(_db),
):
    """Return all Firestore transaction records for the client."""
    doc = db.collection("clients").document(client_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Client not found")

    docs = db.collection("transactions").where("client_id", "==", client_id).stream()
    return [TransactionRecord(**d.to_dict()) for d in docs]


# ---------------------------------------------------------------------------
# On-chain helpers
# ---------------------------------------------------------------------------

def _extract_gas(w3: Web3, tx_hash: str) -> tuple[Optional[int], Optional[float], Optional[float]]:
    """Wait for receipt and return (gas_used, gas_price_gwei, fee_eth). Returns Nones on timeout."""
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
        gas_used: int = receipt["gasUsed"]
        effective_gas_price: int = receipt.get("effectiveGasPrice", 0)
        fee_eth = gas_used * effective_gas_price / 1e18
        return gas_used, effective_gas_price / 1e9, fee_eth
    except Exception:
        return None, None, None


def _register_on_chain(
    token_registry: dict[str, Any],
    network: str,
    address: str,
    rpc_url: str,
    operator_key: str,
) -> None:
    """Call registerWallet on every DepositToken contract for *network*."""
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    operator = w3.eth.account.from_key(operator_key)

    for entry in token_registry.values():
        if entry.get("network") != network:
            continue
        contract_address = entry.get("contract_address", "")
        if not contract_address:
            continue

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=_REGISTER_WALLET_ABI,
        )
        tx = contract.functions.registerWallet(
            Web3.to_checksum_address(address)
        ).build_transaction(
            {
                "from": operator.address,
                "nonce": w3.eth.get_transaction_count(operator.address),
                "gas": 100_000,
            }
        )
        signed = w3.eth.account.sign_transaction(tx, operator_key)
        w3.eth.send_raw_transaction(signed.raw_transaction)
