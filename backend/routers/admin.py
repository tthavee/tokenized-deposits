"""
Admin endpoints (operator-only):

  POST /admin/pause    — pause a DepositToken contract for (asset_type, network)
  POST /admin/unpause  — unpause a DepositToken contract for (asset_type, network)

Authentication: X-API-Key header must match the ADMIN_API_KEY environment variable.
"""

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from web3 import Web3

from services.wallet import RPC_URLS


def _db(request: Request):
    return request.app.state.db

router = APIRouter(prefix="/admin", tags=["admin"])

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_BALANCE_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]

_PAUSE_ABI = [
    {
        "inputs": [],
        "name": "pause",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "unpause",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def _require_admin(api_key: str | None = Security(_api_key_header)) -> None:
    expected = os.environ.get("ADMIN_API_KEY", "")
    if not expected or api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _token_registry(request: Request) -> dict[str, Any]:
    return request.app.state.token_registry


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PauseRequest(BaseModel):
    asset_type: str
    network: str


class PauseResponse(BaseModel):
    asset_type: str
    network: str
    paused: bool
    tx_hash: str


class DiscrepancyEntry(BaseModel):
    wallet: str
    asset_type: str
    network: str
    on_chain_balance: int
    firestore_balance: int


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------

def _send_pause_tx(
    action: str,  # "pause" or "unpause"
    asset_type: str,
    network: str,
    token_registry: dict[str, Any],
) -> str:
    registry_key = f"{asset_type}_{network}"
    entry = token_registry.get(registry_key)
    if not entry or not entry.get("contract_address"):
        raise HTTPException(
            status_code=404,
            detail=f"No contract found for {asset_type}/{network}",
        )

    operator_key = os.environ.get("OPERATOR_PRIVATE_KEY", "")
    rpc_url = RPC_URLS.get(network, "")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    operator = w3.eth.account.from_key(operator_key)

    contract = w3.eth.contract(
        address=Web3.to_checksum_address(entry["contract_address"]),
        abi=_PAUSE_ABI,
    )
    fn = contract.functions.pause if action == "pause" else contract.functions.unpause
    tx = fn().build_transaction(
        {
            "from": operator.address,
            "nonce": w3.eth.get_transaction_count(operator.address),
            "gas": 100_000,
        }
    )
    signed = w3.eth.account.sign_transaction(tx, operator_key)
    return w3.eth.send_raw_transaction(signed.raw_transaction).hex()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/pause", response_model=PauseResponse, dependencies=[Depends(_require_admin)])
def pause_contract(
    body: PauseRequest,
    token_registry: dict[str, Any] = Depends(_token_registry),
):
    """Pause the DepositToken contract for the given (asset_type, network)."""
    tx_hash = _send_pause_tx("pause", body.asset_type, body.network, token_registry)
    return PauseResponse(
        asset_type=body.asset_type,
        network=body.network,
        paused=True,
        tx_hash=tx_hash,
    )


@router.post("/unpause", response_model=PauseResponse, dependencies=[Depends(_require_admin)])
def unpause_contract(
    body: PauseRequest,
    token_registry: dict[str, Any] = Depends(_token_registry),
):
    """Unpause the DepositToken contract for the given (asset_type, network)."""
    tx_hash = _send_pause_tx("unpause", body.asset_type, body.network, token_registry)
    return PauseResponse(
        asset_type=body.asset_type,
        network=body.network,
        paused=False,
        tx_hash=tx_hash,
    )


@router.get(
    "/reconcile",
    response_model=list[DiscrepancyEntry],
    dependencies=[Depends(_require_admin)],
)
def reconcile(
    db=Depends(_db),
    token_registry: dict[str, Any] = Depends(_token_registry),
):
    """
    Compare on-chain balances against Firestore-derived balances for every
    (client, asset_type, network) triple.  Returns only the triples where
    the two values differ.  An empty list means everything is in sync.

    Firestore balance = sum of confirmed deposits − sum of confirmed withdrawals.
    """
    discrepancies: list[DiscrepancyEntry] = []

    client_docs = (
        db.collection("clients").where("kyc_status", "==", "approved").stream()
    )

    for client_doc in client_docs:
        client: dict[str, Any] = client_doc.to_dict()
        wallet: dict[str, str] = client.get("wallet", {})
        client_id: str = client.get("id", "")

        for entry in token_registry.values():
            asset_type: str = entry["asset_type"]
            network: str = entry["network"]
            contract_address: str = entry.get("contract_address", "")
            chain_address: str = wallet.get(network, "")

            if not chain_address or not contract_address:
                continue

            rpc_url = RPC_URLS.get(network, "")
            if not rpc_url:
                continue

            # On-chain balance
            w3 = Web3(Web3.HTTPProvider(rpc_url))
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=_BALANCE_ABI,
            )
            on_chain_balance: int = contract.functions.balanceOf(
                Web3.to_checksum_address(chain_address)
            ).call()

            # Firestore-derived balance: sum confirmed deposits − withdrawals
            tx_docs = (
                db.collection("transactions")
                .where("client_id", "==", client_id)
                .where("asset_type", "==", asset_type)
                .where("network", "==", network)
                .where("status", "==", "confirmed")
                .stream()
            )
            firestore_balance = 0
            for tx in tx_docs:
                tx_data: dict[str, Any] = tx.to_dict()
                if tx_data.get("type") == "deposit":
                    firestore_balance += tx_data.get("amount", 0)
                else:
                    firestore_balance -= tx_data.get("amount", 0)

            if on_chain_balance != firestore_balance:
                discrepancies.append(
                    DiscrepancyEntry(
                        wallet=chain_address,
                        asset_type=asset_type,
                        network=network,
                        on_chain_balance=on_chain_balance,
                        firestore_balance=firestore_balance,
                    )
                )

    return discrepancies
