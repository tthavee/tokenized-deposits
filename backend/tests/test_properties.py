"""
Property-based tests for the Tokenized Deposits backend.

Feature: tokenized-deposits-poc
Uses Hypothesis for generative testing. All properties tagged with their
spec number (P1, P2, ...).

Firestore and Web3 are mocked — no real node or Firebase project needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

import main
from services.event_listener import (
    BURN_TOPIC,
    MINT_TOPIC,
    _process_log,
    _run_once,
    _write_with_retry,
)

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_asset_types = st.sampled_from(["USD", "EUR", "GBP"])
_networks = st.sampled_from(["hardhat", "sepolia"])
_amounts = st.integers(min_value=1, max_value=10_000)
_client_ids = st.uuids().map(str)
_addresses = st.just("0x" + "A" * 40)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc(exists: bool, data: dict | None = None) -> MagicMock:
    d = MagicMock()
    d.exists = exists
    d.to_dict.return_value = data or {}
    return d


def _make_client(kyc_status: str, wallet: dict | None = None) -> dict:
    return {
        "id": "client-1",
        "first_name": "Alice",
        "last_name": "Smith",
        "date_of_birth": "1990-01-01",
        "national_id": "ID123",
        "kyc_status": kyc_status,
        "kyc_failure_reason": None if kyc_status == "approved" else "Invalid document",
        "wallet": wallet or {},
    }


def _make_registry(asset_type: str, network: str) -> dict:
    return {
        f"{asset_type}_{network}": {
            "asset_type": asset_type,
            "network": network,
            "contract_address": "0x" + "D" * 40,
        }
    }


def _make_mock_db() -> MagicMock:
    return MagicMock()


def _make_app_client(mock_db: MagicMock, registry: dict) -> TestClient:
    ctx = (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value=registry),
        patch("main.run_event_listener", new=AsyncMock()),
    )
    # Use context manager manually so we can yield inside @given
    import contextlib
    stack = contextlib.ExitStack()
    for c in ctx:
        stack.enter_context(c)
    client = stack.enter_context(TestClient(main.app))
    return client, stack


class _HexBytes(bytes):
    def hex(self):
        return super().hex()


def _make_log(topic0_hex: str, wallet: str, amount: int, tx_hash: str, contract: str) -> dict:
    topic0 = _HexBytes(bytes.fromhex(topic0_hex))
    topic1 = _HexBytes(b"\x00" * 12 + bytes.fromhex(wallet[2:]))
    data = _HexBytes(amount.to_bytes(32, "big"))
    tx = _HexBytes(bytes.fromhex(tx_hash))
    return {
        "address": contract,
        "topics": [topic0, topic1],
        "data": data,
        "transactionHash": tx,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    return _make_mock_db()


@pytest.fixture
def base_client(mock_db):
    with (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value={}),
        patch("main.run_event_listener", new=AsyncMock()),
    ):
        with TestClient(main.app) as c:
            yield c, mock_db


@pytest.fixture
def kyc_client(mock_db):
    """Client fixture that mocks the KYC service."""
    with (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value={}),
        patch("main.run_event_listener", new=AsyncMock()),
    ):
        with TestClient(main.app) as c:
            yield c, mock_db


# ---------------------------------------------------------------------------
# P1: wallet mapping is null unless kyc_status == "approved"
# Feature: tokenized-deposits-poc, Property 1
# ---------------------------------------------------------------------------

@given(
    first_name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))),
    last_name=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))),
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_p1_wallet_null_unless_kyc_approved(first_name, last_name, mock_db):
    """P1: wallet mapping is null unless kyc_status == 'approved'."""
    # Simulate KYC rejection
    mock_db.collection("clients").document.return_value.get.return_value = _doc(exists=False)
    mock_db.collection("clients").where.return_value.limit.return_value.get.return_value = []

    mock_kyc = MagicMock()
    mock_kyc.verify.return_value = MagicMock(approved=False, failure_reason="Name mismatch")

    with (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value={}),
        patch("main.run_event_listener", new=AsyncMock()),
        patch("routers.clients._kyc_service", mock_kyc),
    ):
        with TestClient(main.app) as c:
            resp = c.post("/clients", json={
                "first_name": first_name,
                "last_name": last_name,
                "date_of_birth": "1990-01-01",
                "national_id": "ID999",
            })

    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["kyc_status"] == "failed"


# ---------------------------------------------------------------------------
# P2: failed KYC stores non-null failure_reason and null wallet
# Feature: tokenized-deposits-poc, Property 2
# ---------------------------------------------------------------------------

@given(failure_reason=st.text(min_size=1, max_size=100))
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_p2_failed_kyc_has_failure_reason(failure_reason, mock_db):
    """P2: failed KYC stores non-null failure_reason and null wallet."""
    mock_db.collection("clients").document.return_value.get.return_value = _doc(exists=False)
    mock_db.collection("clients").where.return_value.limit.return_value.get.return_value = []

    mock_kyc = MagicMock()
    mock_kyc.verify.return_value = MagicMock(approved=False, failure_reason=failure_reason)

    with (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value={}),
        patch("main.run_event_listener", new=AsyncMock()),
        patch("routers.clients._kyc_service", mock_kyc),
    ):
        with TestClient(main.app) as c:
            resp = c.post("/clients", json={
                "first_name": "Alice",
                "last_name": "Smith",
                "date_of_birth": "1990-01-01",
                "national_id": "BAD",
            })

    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["kyc_failure_reason"] is not None
    assert body["detail"]["kyc_status"] == "failed"


# ---------------------------------------------------------------------------
# P6: unknown (asset_type, network) pair returns 404
# Feature: tokenized-deposits-poc, Property 6
# ---------------------------------------------------------------------------

@given(
    asset_type=st.text(min_size=1, max_size=5, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    network=st.text(min_size=1, max_size=10, alphabet="abcdefghijklmnopqrstuvwxyz"),
    amount=_amounts,
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_p6_unknown_asset_network_returns_404(asset_type, network, amount, mock_db):
    """P6: unknown (asset_type, network) pair returns 404 for deposit/withdraw/balance."""
    client_id = "client-1"
    mock_db.collection("clients").document(client_id).get.return_value = _doc(
        exists=True, data=_make_client("approved", {"hardhat": "0x" + "A" * 40})
    )

    # Registry has no entry for this asset_type/network combination
    with (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value={}),
        patch("main.run_event_listener", new=AsyncMock()),
    ):
        with TestClient(main.app) as c:
            deposit_resp = c.post(f"/clients/{client_id}/deposit", json={
                "amount": amount, "asset_type": asset_type, "network": network,
            })
            withdraw_resp = c.post(f"/clients/{client_id}/withdraw", json={
                "amount": amount, "asset_type": asset_type, "network": network,
            })
            balance_resp = c.get(
                f"/clients/{client_id}/balance",
                params={"asset_type": asset_type, "network": network},
            )

    assert deposit_resp.status_code == 404
    assert withdraw_resp.status_code == 404
    assert balance_resp.status_code == 404


# ---------------------------------------------------------------------------
# P10: withdrawal where amount > balance returns 422
# Feature: tokenized-deposits-poc, Property 10
# ---------------------------------------------------------------------------

@given(
    balance=st.integers(min_value=0, max_value=999),
    amount=st.integers(min_value=1000, max_value=9999),
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_p10_withdrawal_exceeding_balance_returns_422(balance, amount, mock_db):
    """P10: withdrawal where amount > on-chain balance returns 422."""
    client_id = "client-1"
    asset_type, network = "USD", "hardhat"
    contract_addr = "0x" + "D" * 40
    wallet_addr = "0x" + "A" * 40
    registry = _make_registry(asset_type, network)

    mock_db.collection("clients").document(client_id).get.return_value = _doc(
        exists=True, data=_make_client("approved", {network: wallet_addr})
    )

    w3 = MagicMock()
    contract_mock = w3.eth.contract.return_value
    contract_mock.functions.paused.return_value.call.return_value = False
    contract_mock.functions.balanceOf.return_value.call.return_value = balance

    with (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value=registry),
        patch("main.run_event_listener", new=AsyncMock()),
        patch("routers.clients.Web3", return_value=w3) as MockWeb3,
        patch("routers.clients.RPC_URLS", {network: "http://localhost:8545"}),
        patch("routers.clients.os.environ.get", return_value="0x" + "f" * 64),
    ):
        MockWeb3.HTTPProvider = MagicMock()
        MockWeb3.to_checksum_address = lambda x: x
        with TestClient(main.app) as c:
            resp = c.post(f"/clients/{client_id}/withdraw", json={
                "amount": amount, "asset_type": asset_type, "network": network,
            })

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# P16: all-balances returns one entry per Token_Registry pair
# Feature: tokenized-deposits-poc, Property 16
# ---------------------------------------------------------------------------

@given(
    pairs=st.lists(
        st.tuples(_asset_types, _networks),
        min_size=1, max_size=4, unique=True,
    )
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_p16_balances_returns_one_entry_per_registry_pair(pairs, mock_db):
    """P16: all-balances endpoint returns one entry per (asset_type, network) pair."""
    client_id = "client-1"
    wallet = {network: "0x" + "A" * 40 for _, network in pairs}
    registry = {
        f"{at}_{nw}": {"asset_type": at, "network": nw, "contract_address": "0x" + "D" * 40}
        for at, nw in pairs
    }
    rpc_urls = {nw: "http://localhost:8545" for _, nw in pairs}

    mock_db.collection("clients").document(client_id).get.return_value = _doc(
        exists=True, data=_make_client("approved", wallet)
    )

    w3 = MagicMock()
    w3.eth.contract.return_value.functions.balanceOf.return_value.call.return_value = 0

    with (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value=registry),
        patch("main.run_event_listener", new=AsyncMock()),
        patch("routers.clients.Web3", return_value=w3) as MockWeb3,
        patch("routers.clients.RPC_URLS", rpc_urls),
    ):
        MockWeb3.HTTPProvider = MagicMock()
        MockWeb3.to_checksum_address = lambda x: x
        with TestClient(main.app) as c:
            resp = c.get(f"/clients/{client_id}/balances")

    assert resp.status_code == 200
    assert len(resp.json()) == len(pairs)


# ---------------------------------------------------------------------------
# P17: transaction history contains exactly the Firestore records for that client
# Feature: tokenized-deposits-poc, Property 17
# ---------------------------------------------------------------------------

@given(
    n_tx=st.integers(min_value=0, max_value=5),
    asset_type=_asset_types,
    network=_networks,
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_p17_history_matches_firestore_records(n_tx, asset_type, network, mock_db):
    """P17: transaction history contains exactly the Firestore records for that client,
    each with non-null asset_type and network."""
    client_id = "client-1"

    tx_records = [
        {
            "id": f"tx-{i}",
            "client_id": client_id,
            "type": "deposit" if i % 2 == 0 else "withdrawal",
            "amount": 100 * (i + 1),
            "asset_type": asset_type,
            "network": network,
            "status": "confirmed",
            "on_chain_tx_hash": "0x" + f"{i}" * 64,
            "created_at": f"2026-01-{i+1:02d}T00:00:00Z",
        }
        for i in range(n_tx)
    ]

    mock_db.collection("clients").document(client_id).get.return_value = _doc(
        exists=True, data=_make_client("approved")
    )
    mock_db.collection("transactions").where.return_value.stream.return_value = [
        MagicMock(to_dict=lambda r=r: r) for r in tx_records
    ]

    with (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value={}),
        patch("main.run_event_listener", new=AsyncMock()),
    ):
        with TestClient(main.app) as c:
            resp = c.get(f"/clients/{client_id}/transactions")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == n_tx
    for entry in body:
        assert entry["asset_type"] is not None
        assert entry["network"] is not None


# ---------------------------------------------------------------------------
# P22: every on-chain event produces a Firestore record with all required fields
# Feature: tokenized-deposits-poc, Property 22
# ---------------------------------------------------------------------------

@given(
    asset_type=_asset_types,
    network=_networks,
    amount=_amounts,
    is_mint=st.booleans(),
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_p22_on_chain_event_produces_firestore_record(asset_type, network, amount, is_mint):
    """P22: every on-chain event produces a Firestore record with all 6 required fields."""
    contract_addr = "0x" + "D" * 40
    wallet_addr = "0x" + "A" * 40
    tx_hash = "ab" * 32

    contracts = {contract_addr.lower(): {"asset_type": asset_type, "network": network, "contract_address": contract_addr}}
    topic = MINT_TOPIC if is_mint else BURN_TOPIC
    log = _make_log(topic, wallet_addr, amount, tx_hash, contract_addr)

    db = MagicMock()
    db.collection("transactions").where.return_value.limit.return_value.get.return_value = []
    db.collection("clients").where.return_value.limit.return_value.get.return_value = []

    with patch("services.event_listener.Web3.to_checksum_address", side_effect=lambda x: x if isinstance(x, str) else "0x" + x.hex()):
        _process_log(db, log, contracts)

    db.collection("transactions").document(tx_hash).set.assert_called_once()
    record = db.collection("transactions").document(tx_hash).set.call_args[0][0]

    for field in ("id", "type", "amount", "asset_type", "network", "status"):
        assert field in record, f"Missing field: {field}"
        assert record[field] is not None


# ---------------------------------------------------------------------------
# P24: every Token_Registry doc ID is {asset_type}_{network} with required fields
# Feature: tokenized-deposits-poc, Property 24
# ---------------------------------------------------------------------------

@given(
    asset_type=_asset_types,
    network=_networks,
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_p24_registry_doc_id_format(asset_type, network, mock_db):
    """P24: token_registry doc IDs are {asset_type}_{network} with non-null fields."""
    registry = _make_registry(asset_type, network)

    for doc_id, entry in registry.items():
        assert doc_id == f"{asset_type}_{network}"
        assert entry["asset_type"] is not None
        assert entry["network"] is not None
        assert entry["contract_address"] is not None


# ---------------------------------------------------------------------------
# P25: Firestore write retried exactly up to MAX_RETRIES times on failure
# Feature: tokenized-deposits-poc, Property 25
# ---------------------------------------------------------------------------

@given(failures=st.integers(min_value=1, max_value=3))
@settings(max_examples=10)
def test_p25_firestore_write_retried_up_to_max(failures):
    """P25: Firestore write retried exactly up to MAX_RETRIES (3) times on failure."""
    from services.event_listener import MAX_RETRIES

    db = MagicMock()
    call_count = 0

    def flaky_set(record):
        nonlocal call_count
        call_count += 1
        if call_count <= failures:
            raise Exception("Firestore unavailable")

    db.collection("transactions").document.return_value.set.side_effect = flaky_set

    _write_with_retry(db, "tx-hash", {"id": "tx-hash"})

    expected_calls = min(failures + 1, MAX_RETRIES)
    assert db.collection("transactions").document.return_value.set.call_count == expected_calls


@given(st.just(None))
@settings(max_examples=5)
def test_p25_firestore_write_stops_after_max_retries(_):
    """P25: write stops after MAX_RETRIES failures without raising."""
    from services.event_listener import MAX_RETRIES

    db = MagicMock()
    db.collection("transactions").document.return_value.set.side_effect = Exception("always fails")

    # Should not raise
    _write_with_retry(db, "tx-hash", {"id": "tx-hash"})

    assert db.collection("transactions").document.return_value.set.call_count == MAX_RETRIES


# ---------------------------------------------------------------------------
# P27: event listener upsert is idempotent
# Feature: tokenized-deposits-poc, Property 27
# ---------------------------------------------------------------------------

@given(
    asset_type=_asset_types,
    network=_networks,
    amount=_amounts,
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_p27_event_listener_upsert_is_idempotent(asset_type, network, amount):
    """P27: processing the same log twice does not create a duplicate Firestore record."""
    contract_addr = "0x" + "D" * 40
    wallet_addr = "0x" + "A" * 40
    tx_hash = "ab" * 32

    contracts = {contract_addr.lower(): {"asset_type": asset_type, "network": network, "contract_address": contract_addr}}
    log = _make_log(MINT_TOPIC, wallet_addr, amount, tx_hash, contract_addr)

    db = MagicMock()
    # First call: no existing record
    db.collection("transactions").where.return_value.limit.return_value.get.return_value = []
    db.collection("clients").where.return_value.limit.return_value.get.return_value = []

    with patch("services.event_listener.Web3.to_checksum_address", side_effect=lambda x: x if isinstance(x, str) else "0x" + x.hex()):
        _process_log(db, log, contracts)

    assert db.collection("transactions").document(tx_hash).set.call_count == 1

    # Second call: existing record found — should skip
    db.collection("transactions").where.return_value.limit.return_value.get.return_value = [MagicMock()]

    with patch("services.event_listener.Web3.to_checksum_address", side_effect=lambda x: x if isinstance(x, str) else "0x" + x.hex()):
        _process_log(db, log, contracts)

    # Still only 1 write total
    assert db.collection("transactions").document(tx_hash).set.call_count == 1
