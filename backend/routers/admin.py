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

router = APIRouter(prefix="/admin", tags=["admin"])

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

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
