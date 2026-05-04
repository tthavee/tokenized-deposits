"""
Transfer endpoint:

  POST /transfer  — validate and submit an on-chain token transfer between two clients
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from web3 import Web3

from services.wallet import RPC_URLS

log = logging.getLogger(__name__)

router = APIRouter(tags=["transfer"])

_TRANSFER_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "operatorTransfer",
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

_MAX_RETRIES = 3


def _db(request: Request):
    return request.app.state.db


def _token_registry(request: Request) -> dict[str, Any]:
    return request.app.state.token_registry


def _write_with_retry(db, tx_id: str, data: dict) -> None:
    """Update a transaction document, retrying up to _MAX_RETRIES times."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            db.collection("transactions").document(tx_id).update(data)
            return
        except Exception as exc:
            last_exc = exc
            log.warning("Firestore update attempt %d/%d failed for %s: %s", attempt, _MAX_RETRIES, tx_id, exc)
    log.error("permanent Firestore failure for %s after %d attempts: %s", tx_id, _MAX_RETRIES, last_exc)


class TransferRequest(BaseModel):
    sender_id: str
    recipient_id: str
    asset_type: str
    network: str
    amount: int


class TransferResponse(BaseModel):
    sender_transaction_id: str
    recipient_transaction_id: str
    status: str
    on_chain_tx_hash: str


@router.post("/transfer", response_model=TransferResponse, status_code=202)
def transfer_tokens(
    body: TransferRequest,
    db=Depends(_db),
    token_registry: dict[str, Any] = Depends(_token_registry),
):
    """
    Validate and submit a KYC-gated token transfer from one client to another.

    Validation order:
    1. Token_Registry must have a contract for (asset_type, network)
    2. Sender must have a chain address on the network
    3. Recipient must have a chain address on the network
    4. Sender's on-chain balance must be >= amount
    """
    # 1. Resolve contract
    registry_key = f"{body.asset_type}_{body.network}"
    entry = token_registry.get(registry_key)
    if not entry or not entry.get("contract_address"):
        raise HTTPException(
            status_code=400,
            detail=f"No contract found for {body.asset_type}/{body.network}",
        )
    contract_address = entry["contract_address"]

    # 2. Sender's chain address
    sender_doc = db.collection("clients").document(body.sender_id).get()
    if not sender_doc.exists:
        raise HTTPException(status_code=400, detail="Sender not found")
    sender_chain_address = sender_doc.to_dict().get("wallet", {}).get(body.network)
    if not sender_chain_address:
        raise HTTPException(
            status_code=400,
            detail=f"Sender has no wallet on network {body.network!r}",
        )

    # 3. Recipient's chain address
    recipient_doc = db.collection("clients").document(body.recipient_id).get()
    if not recipient_doc.exists:
        raise HTTPException(status_code=400, detail="Recipient not found")
    recipient_chain_address = recipient_doc.to_dict().get("wallet", {}).get(body.network)
    if not recipient_chain_address:
        raise HTTPException(
            status_code=400,
            detail=f"Recipient has no wallet on network {body.network!r}",
        )

    # 4. Check sender balance
    rpc_url = RPC_URLS.get(body.network, "")
    operator_key = os.environ.get("OPERATOR_PRIVATE_KEY", "")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=_TRANSFER_ABI,
    )
    on_chain_balance = contract.functions.balanceOf(
        Web3.to_checksum_address(sender_chain_address)
    ).call()
    balance_units = on_chain_balance // 10**18
    if balance_units < body.amount:
        raise HTTPException(
            status_code=400,
            detail={"message": "Insufficient sender balance", "balance": balance_units},
        )

    # Check if contract is paused
    if contract.functions.paused().call():
        raise HTTPException(
            status_code=503,
            detail=f"Contract paused for {body.asset_type}/{body.network}",
        )

    # Create pending Firestore records for both sides of the transfer
    sender_tx_id = str(uuid.uuid4())
    recipient_tx_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    for tx_id, client_id, direction, counterparty in [
        (sender_tx_id, body.sender_id, "sent", body.recipient_id),
        (recipient_tx_id, body.recipient_id, "received", body.sender_id),
    ]:
        db.collection("transactions").document(tx_id).set({
            "id": tx_id,
            "client_id": client_id,
            "type": "transfer",
            "direction": direction,
            "counterparty_id": counterparty,
            "amount": body.amount,
            "asset_type": body.asset_type,
            "network": body.network,
            "status": "pending",
            "on_chain_tx_hash": None,
            "contract_address": contract_address,
            "created_at": now,
        })

    # Submit on-chain transfer via operator wallet using operatorTransfer
    try:
        operator = w3.eth.account.from_key(operator_key)
        tx = contract.functions.operatorTransfer(
            Web3.to_checksum_address(sender_chain_address),
            Web3.to_checksum_address(recipient_chain_address),
            body.amount * 10**18,
        ).build_transaction({
            "from": operator.address,
            "nonce": w3.eth.get_transaction_count(operator.address),
            "gas": 200_000,
        })
        signed = w3.eth.account.sign_transaction(tx, operator_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    except Exception as exc:
        for tx_id in [sender_tx_id, recipient_tx_id]:
            _write_with_retry(db, tx_id, {"status": "failed"})
        raise HTTPException(status_code=502, detail=f"On-chain transfer failed: {exc}") from exc

    # Wait for receipt and update both records to confirmed
    try:
        w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
    except Exception:
        log.warning("receipt timeout for tx=%s — records remain pending", tx_hash)
        return TransferResponse(
            sender_transaction_id=sender_tx_id,
            recipient_transaction_id=recipient_tx_id,
            status="pending",
            on_chain_tx_hash=tx_hash,
        )

    for tx_id in [sender_tx_id, recipient_tx_id]:
        _write_with_retry(db, tx_id, {"status": "confirmed", "on_chain_tx_hash": tx_hash})

    return TransferResponse(
        sender_transaction_id=sender_tx_id,
        recipient_transaction_id=recipient_tx_id,
        status="confirmed",
        on_chain_tx_hash=tx_hash,
    )
