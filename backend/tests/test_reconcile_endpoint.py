"""
Tests for GET /admin/reconcile.

Firestore and Web3 are mocked — no real node or Firebase project needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

import main

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_KEY = "supersecretkey"
CONTRACT_ADDR = "0xDEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF"
CHAIN_ADDR = "0x" + "A" * 40

REGISTRY = {
    "USD_hardhat": {
        "asset_type": "USD",
        "network": "hardhat",
        "contract_address": CONTRACT_ADDR,
    }
}

CLIENT = {
    "id": "client-1",
    "kyc_status": "approved",
    "wallet": {"hardhat": CHAIN_ADDR},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc(data: dict) -> MagicMock:
    d = MagicMock()
    d.to_dict.return_value = data
    return d


def _tx(type_: str, amount: int, status: str = "confirmed") -> MagicMock:
    return _doc({"type": type_, "amount": amount, "status": status})


def _mock_w3(balance: int = 0) -> MagicMock:
    w3 = MagicMock()
    w3.eth.contract.return_value.functions.balanceOf.return_value.call.return_value = balance
    return w3


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    # Give each collection its own isolated mock so that chained .where()
    # and .stream() calls on different collections don't collide.
    clients_col = MagicMock()
    tx_col = MagicMock()

    def _get_collection(name):
        return {"clients": clients_col, "transactions": tx_col}.get(name, MagicMock())

    db.collection.side_effect = _get_collection
    db._clients_col = clients_col
    db._tx_col = tx_col
    return db


@pytest.fixture
def client(mock_db) -> TestClient:
    # Patch out the event listener so it doesn't overwrite app.state.token_registry
    # with an empty dict when the mock db's token_registry stream returns nothing.
    with (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value=REGISTRY),
        patch("main.run_event_listener", new=AsyncMock()),
    ):
        with TestClient(main.app) as c:
            yield c


def _get(client, *, api_key=VALID_KEY, w3=None, env_key=VALID_KEY):
    headers = {"X-API-Key": api_key} if api_key else {}
    w3 = w3 or _mock_w3()
    with (
        patch("routers.admin.Web3", return_value=w3) as MockWeb3,
        patch.dict("os.environ", {"ADMIN_API_KEY": env_key}),
    ):
        MockWeb3.HTTPProvider = MagicMock()
        MockWeb3.to_checksum_address = lambda x: x
        return client.get("/admin/reconcile", headers=headers)


def _setup_clients(mock_db, clients_list):
    mock_db._clients_col.where.return_value.stream.return_value = clients_list


def _setup_txs(mock_db, txs_list):
    (
        mock_db._tx_col
        .where.return_value
        .where.return_value
        .where.return_value
        .where.return_value
        .stream.return_value
    ) = txs_list


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestReconcileAuth:
    def test_401_missing_api_key(self, client, mock_db):
        _setup_clients(mock_db, [])
        resp = _get(client, api_key=None)
        assert resp.status_code == 401

    def test_401_wrong_api_key(self, client, mock_db):
        _setup_clients(mock_db, [])
        resp = _get(client, api_key="wrongkey")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Empty / no-discrepancy cases
# ---------------------------------------------------------------------------

class TestReconcileNoDiscrepancies:
    def test_returns_empty_list_when_no_clients(self, client, mock_db):
        _setup_clients(mock_db, [])
        resp = _get(client)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_empty_list_when_balances_agree(self, client, mock_db):
        _setup_clients(mock_db, [_doc(CLIENT)])
        _setup_txs(mock_db, [_tx("deposit", 500)])
        resp = _get(client, w3=_mock_w3(balance=500))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_empty_list_when_client_has_no_wallet(self, client, mock_db):
        _setup_clients(mock_db, [_doc({**CLIENT, "wallet": {}})])
        resp = _get(client)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_deposit_minus_withdrawal_matches_on_chain(self, client, mock_db):
        _setup_clients(mock_db, [_doc(CLIENT)])
        _setup_txs(mock_db, [_tx("deposit", 1000), _tx("withdrawal", 300)])
        resp = _get(client, w3=_mock_w3(balance=700))
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Discrepancy cases
# ---------------------------------------------------------------------------

class TestReconcileDiscrepancies:
    def test_returns_discrepancy_when_on_chain_higher(self, client, mock_db):
        _setup_clients(mock_db, [_doc(CLIENT)])
        _setup_txs(mock_db, [_tx("deposit", 500)])
        resp = _get(client, w3=_mock_w3(balance=1000))
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_returns_discrepancy_when_firestore_higher(self, client, mock_db):
        _setup_clients(mock_db, [_doc(CLIENT)])
        _setup_txs(mock_db, [_tx("deposit", 500)])
        resp = _get(client, w3=_mock_w3(balance=200))
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_discrepancy_entry_has_correct_fields(self, client, mock_db):
        _setup_clients(mock_db, [_doc(CLIENT)])
        _setup_txs(mock_db, [_tx("deposit", 500)])
        resp = _get(client, w3=_mock_w3(balance=1000))
        entry = resp.json()[0]
        assert entry["wallet"] == CHAIN_ADDR
        assert entry["asset_type"] == "USD"
        assert entry["network"] == "hardhat"
        assert entry["on_chain_balance"] == 1000
        assert entry["firestore_balance"] == 500

    def test_returns_one_entry_per_discrepant_triple(self, client, mock_db):
        client2 = {**CLIENT, "id": "client-2", "wallet": {"hardhat": "0x" + "B" * 40}}
        _setup_clients(mock_db, [_doc(CLIENT), _doc(client2)])
        _setup_txs(mock_db, [])
        resp = _get(client, w3=_mock_w3(balance=100))
        assert len(resp.json()) == 2

    def test_only_discrepant_triples_returned(self, client, mock_db):
        # Two registry entries; USD on-chain = 0 (in sync), EUR on-chain = 99 (discrepant).
        registry_two = {
            **REGISTRY,
            "EUR_hardhat": {
                "asset_type": "EUR",
                "network": "hardhat",
                "contract_address": "0x" + "2" * 40,
            },
        }
        _setup_clients(mock_db, [_doc(CLIENT)])
        _setup_txs(mock_db, [])  # Firestore balance = 0 for both

        call_count = [0]
        w3 = MagicMock()

        def balance_side_effect(addr):
            call_count[0] += 1
            m = MagicMock()
            m.call.return_value = 0 if call_count[0] == 1 else 99
            return m

        w3.eth.contract.return_value.functions.balanceOf.side_effect = balance_side_effect

        with (
            patch("main._load_token_registry", return_value=registry_two),
            patch("routers.admin.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"ADMIN_API_KEY": VALID_KEY}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            # Update app state directly so the live app uses the two-entry registry
            client.app.state.token_registry = registry_two
            resp = client.get("/admin/reconcile", headers={"X-API-Key": VALID_KEY})

        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["on_chain_balance"] == 99


# ---------------------------------------------------------------------------
# Firestore query behaviour
# ---------------------------------------------------------------------------

class TestReconcileFirestoreQueries:
    def test_queries_only_approved_clients(self, client, mock_db):
        _setup_clients(mock_db, [])
        _get(client)
        mock_db._clients_col.where.assert_called_with("kyc_status", "==", "approved")

    def test_queries_confirmed_transactions_only(self, client, mock_db):
        _setup_clients(mock_db, [_doc(CLIENT)])
        _setup_txs(mock_db, [])
        _get(client, w3=_mock_w3(balance=0))

        # The last .where() in the transaction chain filters by status == "confirmed"
        last_where = (
            mock_db._tx_col
            .where.return_value
            .where.return_value
            .where.return_value
            .where
        )
        last_where.assert_called_with("status", "==", "confirmed")
