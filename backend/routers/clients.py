"""
Client endpoints:

  POST /clients                — KYC verification + client record creation
  POST /clients/{id}/wallet   — wallet address generation + on-chain registration
  POST /clients/{id}/deposit  — mint Deposit_Tokens for a fiat deposit
"""

import os
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
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
            _register_on_chain(token_registry, network, address, rpc_url, operator_key)

    return WalletResponse(client_id=client_id, wallet=wallet)


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
            body.amount,
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

    db.collection("transactions").document(tx_id).update(
        {"status": "confirmed", "on_chain_tx_hash": tx_hash}
    )
    return DepositResponse(transaction_id=tx_id, status="confirmed", on_chain_tx_hash=tx_hash)


# ---------------------------------------------------------------------------
# On-chain helper
# ---------------------------------------------------------------------------

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
