"""
Tests for:
  GET /api/clients/{id}/balance
  GET /api/clients/{id}/balances
  GET /api/clients/{id}/transactions
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

import main

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLIENT_ID = "client-abc"
CONTRACT_ADDR = "0xDEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF"
HARDHAT_ADDR = "0x" + "A" * 40
SEPOLIA_ADDR = "0x" + "B" * 40

REGISTRY = {
    "USD_hardhat": {
        "asset_type": "USD",
        "network": "hardhat",
        "contract_address": CONTRACT_ADDR,
    },
    "USD_sepolia": {
        "asset_type": "USD",
        "network": "sepolia",
        "contract_address": "0x" + "E" * 40,
    },
}

APPROVED_CLIENT = {
    "id": CLIENT_ID,
    "first_name": "Alice",
    "last_name": "Smith",
    "kyc_status": "approved",
    "wallet": {"hardhat": HARDHAT_ADDR, "sepolia": SEPOLIA_ADDR},
}

TX_RECORD = {
    "id": "tx-1",
    "client_id": CLIENT_ID,
    "type": "deposit",
    "amount": 1000,
    "asset_type": "USD",
    "network": "hardhat",
    "status": "confirmed",
    "on_chain_tx_hash": "0x" + "c" * 64,
    "created_at": "2026-01-01T00:00:00+00:00",
}


def _doc(exists: bool, data: dict | None = None) -> MagicMock:
    d = MagicMock()
    d.exists = exists
    d.to_dict.return_value = data or {}
    return d


def _tx_doc(data: dict) -> MagicMock:
    d = MagicMock()
    d.to_dict.return_value = data
    return d


def _mock_w3(balance: int = 750) -> MagicMock:
    w3 = MagicMock()
    contract = MagicMock()
    contract.functions.balanceOf.return_value.call.return_value = balance
    w3.eth.contract.return_value = contract
    return w3


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(mock_db) -> TestClient:
    with (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value=REGISTRY),
        patch("main.run_event_listener", new=AsyncMock()),
    ):
        with TestClient(main.app) as c:
            yield c


# ---------------------------------------------------------------------------
# GET /api/clients/{id}/balance
# ---------------------------------------------------------------------------

class TestGetBalance:
    URL = f"/api/clients/{CLIENT_ID}/balance"

    def test_404_client_not_found(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(exists=False)
        resp = client.get(self.URL, params={"asset_type": "USD", "network": "hardhat"})
        assert resp.status_code == 404

    def test_404_no_wallet_for_network(self, client, mock_db):
        data = {**APPROVED_CLIENT, "wallet": {}}
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=data
        )
        resp = client.get(self.URL, params={"asset_type": "USD", "network": "hardhat"})
        assert resp.status_code == 404

    def test_404_unknown_asset_type(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        resp = client.get(self.URL, params={"asset_type": "EUR", "network": "hardhat"})
        assert resp.status_code == 404

    def test_404_unknown_network(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        resp = client.get(self.URL, params={"asset_type": "USD", "network": "mainnet"})
        assert resp.status_code == 404

    def test_returns_200_with_balance(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        w3 = _mock_w3(balance=750)
        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.get(self.URL, params={"asset_type": "USD", "network": "hardhat"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["balance"] == 750
        assert body["asset_type"] == "USD"
        assert body["network"] == "hardhat"
        assert body["chain_address"] == HARDHAT_ADDR

    def test_calls_balance_of_with_correct_address(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        w3 = _mock_w3(balance=0)
        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            client.get(self.URL, params={"asset_type": "USD", "network": "hardhat"})

        w3.eth.contract.return_value.functions.balanceOf.assert_called_once_with(HARDHAT_ADDR)


# ---------------------------------------------------------------------------
# GET /api/clients/{id}/balances
# ---------------------------------------------------------------------------

class TestGetBalances:
    URL = f"/api/clients/{CLIENT_ID}/balances"

    def test_404_client_not_found(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(exists=False)
        resp = client.get(self.URL)
        assert resp.status_code == 404

    def test_returns_one_entry_per_registry_pair(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        w3 = _mock_w3(balance=500)
        rpc_urls = {"hardhat": "http://localhost:8545", "sepolia": "http://localhost:9545"}
        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
            patch("routers.clients.RPC_URLS", rpc_urls),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.get(self.URL)

        assert resp.status_code == 200
        assert len(resp.json()) == 2  # USD_hardhat + USD_sepolia

    def test_each_entry_has_required_fields(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        w3 = _mock_w3(balance=100)
        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.get(self.URL)

        for entry in resp.json():
            assert "asset_type" in entry
            assert "network" in entry
            assert "chain_address" in entry
            assert "balance" in entry

    def test_zero_balance_returned_when_no_wallet_for_network(self, client, mock_db):
        data = {**APPROVED_CLIENT, "wallet": {}}  # no wallet at all
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=data
        )
        w3 = _mock_w3(balance=999)
        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.get(self.URL)

        assert resp.status_code == 200
        for entry in resp.json():
            assert entry["balance"] == 0


# ---------------------------------------------------------------------------
# GET /api/clients/{id}/transactions
# ---------------------------------------------------------------------------

class TestGetTransactions:
    URL = f"/api/clients/{CLIENT_ID}/transactions"

    def test_404_client_not_found(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(exists=False)
        resp = client.get(self.URL)
        assert resp.status_code == 404

    def test_returns_empty_list_when_no_transactions(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        mock_db.collection("transactions").where.return_value.stream.return_value = iter([])
        resp = client.get(self.URL)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_transaction_records(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        mock_db.collection("transactions").where.return_value.stream.return_value = iter(
            [_tx_doc(TX_RECORD)]
        )
        resp = client.get(self.URL)
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["id"] == "tx-1"

    def test_transaction_record_has_required_fields(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        mock_db.collection("transactions").where.return_value.stream.return_value = iter(
            [_tx_doc(TX_RECORD)]
        )
        resp = client.get(self.URL)
        record = resp.json()[0]
        for field in ("id", "type", "amount", "asset_type", "network", "status", "created_at"):
            assert field in record

    def test_queries_firestore_by_client_id(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        mock_db.collection("transactions").where.return_value.stream.return_value = iter([])
        client.get(self.URL)
        mock_db.collection("transactions").where.assert_called_once_with(
            "client_id", "==", CLIENT_ID
        )

    def test_returns_multiple_transactions(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        tx2 = {**TX_RECORD, "id": "tx-2", "type": "withdrawal", "amount": 200}
        mock_db.collection("transactions").where.return_value.stream.return_value = iter(
            [_tx_doc(TX_RECORD), _tx_doc(tx2)]
        )
        resp = client.get(self.URL)
        assert len(resp.json()) == 2
