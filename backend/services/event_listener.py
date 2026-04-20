"""
Polling-based event listener for on-chain Mint and Burn events.

Started as an asyncio background task via the FastAPI lifespan context.  On
each poll cycle it:

  1. Refreshes the Token_Registry from Firestore (picks up new deployments).
  2. For each network, fetches eth_getLogs for Mint/Burn events since the last
     processed block.
  3. Upserts a Firestore transaction record for any event that does not already
     have one (keyed on on_chain_tx_hash, so the operation is idempotent).
  4. Advances the per-network block cursor only after all writes succeed.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

from firebase_admin import firestore
from web3 import Web3

from services.wallet import RPC_URLS

# Seconds between poll cycles.
POLL_INTERVAL = 3

# Maximum Firestore write attempts per event record.
MAX_RETRIES = 3

# keccak256 topic hashes for the custom events emitted by DepositToken.sol.
# Mint(address indexed recipient, uint256 amount)
MINT_TOPIC: str = Web3.keccak(text="Mint(address,uint256)").hex()
# Burn(address indexed source, uint256 amount)
BURN_TOPIC: str = Web3.keccak(text="Burn(address,uint256)").hex()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run_event_listener(app_state) -> None:
    """Async background task: poll every POLL_INTERVAL seconds."""
    print("[event_listener] started")
    # One persistent Web3 instance per network — never recreated between polls.
    w3_cache: dict[str, Web3] = {}
    while True:
        try:
            _run_once(app_state, w3_cache)
        except Exception as exc:
            print(f"[event_listener] unexpected error: {exc}")
        await asyncio.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Single poll cycle
# ---------------------------------------------------------------------------

def _run_once(app_state, w3_cache: dict[str, Web3]) -> None:
    db: firestore.Client = app_state.db

    # Refresh registry so newly deployed contracts are picked up automatically.
    registry = _load_token_registry(db)
    app_state.token_registry = registry

    # Group contracts by network: network -> {lowercase_address -> registry entry}
    by_network: dict[str, dict[str, Any]] = {}
    for entry in registry.values():
        network = entry.get("network", "")
        addr = (entry.get("contract_address") or "").lower()
        if network and addr:
            by_network.setdefault(network, {})[addr] = entry

    for network, contracts in by_network.items():
        rpc_url = RPC_URLS.get(network, "")
        if not rpc_url:
            continue
        try:
            if network not in w3_cache:
                w3_cache[network] = Web3(Web3.HTTPProvider(rpc_url))
            _poll_network(db, network, contracts, rpc_url, w3_cache[network])
        except Exception as exc:
            print(f"[event_listener] error polling {network}: {exc}")


# ---------------------------------------------------------------------------
# Per-network polling
# ---------------------------------------------------------------------------

def _poll_network(
    db: firestore.Client,
    network: str,
    contracts: dict[str, Any],
    rpc_url: str,
    w3: Web3,
) -> None:
    """Fetch new logs for *network* and upsert Firestore records."""
    # Read the per-network block cursor from Firestore.
    cursor_key = f"last_processed_block_{network}"
    cursor_doc = db.collection("system").document("event_listener").get()
    last_block: int = (
        cursor_doc.to_dict().get(cursor_key, 0) if cursor_doc.exists else 0
    )

    latest_block: int = w3.eth.block_number
    if last_block >= latest_block:
        return  # Nothing new.

    from_block = last_block + 1 if last_block > 0 else 0

    addresses = [Web3.to_checksum_address(a) for a in contracts]
    logs = w3.eth.get_logs(
        {
            "fromBlock": from_block,
            "toBlock": latest_block,
            "address": addresses,
            "topics": [[MINT_TOPIC, BURN_TOPIC]],
        }
    )

    for log in logs:
        try:
            _process_log(db, log, contracts)
        except Exception as exc:
            tx = log.get("transactionHash", b"").hex()
            print(f"[event_listener] failed to process log {tx}: {exc}")

    # Advance the cursor only after all events in this range are processed.
    db.collection("system").document("event_listener").set(
        {cursor_key: latest_block}, merge=True
    )
    print(
        f"[event_listener] {network}: processed blocks {from_block}→{latest_block}"
        f", {len(logs)} event(s)"
    )


# ---------------------------------------------------------------------------
# Single log processing
# ---------------------------------------------------------------------------

def _process_log(
    db: firestore.Client,
    log: dict,
    contracts: dict[str, Any],
) -> None:
    """Upsert a Firestore transaction record for one on-chain event."""
    contract_addr = log["address"].lower()
    entry = contracts.get(contract_addr)
    if not entry:
        return

    topic0: str = log["topics"][0].hex()
    is_mint = topic0 == MINT_TOPIC
    event_type = "deposit" if is_mint else "withdrawal"

    # topics[1] is a 32-byte ABI-encoded address (left-padded with zeros).
    wallet_address = Web3.to_checksum_address(log["topics"][1][-20:])

    # data is a 32-byte ABI-encoded uint256.
    amount = int.from_bytes(log["data"], "big")

    tx_hash: str = log["transactionHash"].hex()

    # Idempotency check: skip if any record already tracks this tx_hash.
    existing = (
        db.collection("transactions")
        .where("on_chain_tx_hash", "==", tx_hash)
        .limit(1)
        .get()
    )
    if existing:
        return

    client_id = _find_client_id(db, entry["network"], wallet_address) or ""

    record = {
        "id": tx_hash,
        "client_id": client_id,
        "type": event_type,
        "amount": amount,
        "asset_type": entry["asset_type"],
        "network": entry["network"],
        "status": "confirmed",
        "on_chain_tx_hash": tx_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    _write_with_retry(db, tx_hash, record)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_token_registry(db: firestore.Client) -> dict[str, Any]:
    return {doc.id: doc.to_dict() for doc in db.collection("token_registry").stream()}


def _find_client_id(db: firestore.Client, network: str, address: str) -> str | None:
    """Return the client_id whose wallet on *network* matches *address*, or None."""
    results = (
        db.collection("clients")
        .where(f"wallet.{network}", "==", address)
        .limit(1)
        .get()
    )
    return results[0].to_dict().get("id") if results else None


def _write_with_retry(db: firestore.Client, tx_hash: str, record: dict) -> None:
    """Write *record* to transactions/{tx_hash}, retrying up to MAX_RETRIES times."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            db.collection("transactions").document(tx_hash).set(record)
            return
        except Exception as exc:
            last_exc = exc
            print(
                f"[event_listener] Firestore write attempt {attempt}/{MAX_RETRIES}"
                f" failed for {tx_hash}: {exc}"
            )
    print(f"[event_listener] permanent Firestore failure for {tx_hash}: {last_exc}")
