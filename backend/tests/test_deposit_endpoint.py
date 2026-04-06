"""
Tests for POST /clients/{id}/deposit.

Firestore and Web3 are mocked — no real node or Firebase project needed.
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
CHAIN_ADDR = "0x" + "A" * 40
TX_HASH = "0x" + "b" * 64

VALID_BODY = {"amount": 1000, "asset_type": "USD", "network": "hardhat"}

REGISTRY = {
    "USD_hardhat": {
        "asset_type": "USD",
        "network": "hardhat",
        "contract_address": CONTRACT_ADDR,
    }
}

APPROVED_CLIENT = {
    "id": CLIENT_ID,
    "first_name": "Alice",
    "last_name": "Smith",
    "kyc_status": "approved",
    "wallet": {"hardhat": CHAIN_ADDR, "sepolia": "0x" + "C" * 40},
}


def _doc(exists: bool, data: dict | None = None) -> MagicMock:
    d = MagicMock()
    d.exists = exists
    d.to_dict.return_value = data or {}
    return d


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


def _mock_w3(paused: bool = False, tx_hash: bytes = bytes.fromhex(TX_HASH[2:])):
    """Return a pre-wired Web3 mock."""
    w3 = MagicMock()
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.account.from_key.return_value = MagicMock(
        address="0x1234567890123456789012345678901234567890"
    )
    signed = MagicMock()
    signed.raw_transaction = b"raw"
    w3.eth.account.sign_transaction.return_value = signed
    w3.eth.send_raw_transaction.return_value = tx_hash

    # contract mock
    contract = MagicMock()
    contract.functions.paused.return_value.call.return_value = paused
    w3.eth.contract.return_value = contract
    return w3


# ---------------------------------------------------------------------------
# 404 — client not found
# ---------------------------------------------------------------------------

class TestDepositClientNotFound:
    def test_returns_404(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(exists=False)
        resp = client.post(f"/clients/{CLIENT_ID}/deposit", json=VALID_BODY)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 404 — no wallet for requested network
# ---------------------------------------------------------------------------

class TestDepositNoWallet:
    def test_returns_404_when_wallet_missing_for_network(self, client, mock_db):
        client_no_wallet = {**APPROVED_CLIENT, "wallet": {}}
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=client_no_wallet
        )
        resp = client.post(f"/clients/{CLIENT_ID}/deposit", json=VALID_BODY)
        assert resp.status_code == 404

    def test_returns_404_when_network_not_in_wallet(self, client, mock_db):
        client_partial = {**APPROVED_CLIENT, "wallet": {"sepolia": "0x" + "C" * 40}}
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=client_partial
        )
        resp = client.post(f"/clients/{CLIENT_ID}/deposit", json=VALID_BODY)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 404 — contract not in token registry
# ---------------------------------------------------------------------------

class TestDepositContractNotFound:
    def test_returns_404_for_unknown_asset_type(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        body = {**VALID_BODY, "asset_type": "EUR"}
        resp = client.post(f"/clients/{CLIENT_ID}/deposit", json=body)
        assert resp.status_code == 404

    def test_returns_404_for_unknown_network(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        body = {**VALID_BODY, "network": "mainnet"}
        resp = client.post(f"/clients/{CLIENT_ID}/deposit", json=body)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 503 — contract paused
# ---------------------------------------------------------------------------

class TestDepositContractPaused:
    def test_returns_503(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        w3 = _mock_w3(paused=True)
        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.post(f"/clients/{CLIENT_ID}/deposit", json=VALID_BODY)
        assert resp.status_code == 503

    def test_503_detail_contains_asset_and_network(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        w3 = _mock_w3(paused=True)
        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.post(f"/clients/{CLIENT_ID}/deposit", json=VALID_BODY)
        assert "USD" in resp.json()["detail"]
        assert "hardhat" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 200 — success
# ---------------------------------------------------------------------------

class TestDepositSuccess:
    @pytest.fixture(autouse=True)
    def setup(self, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )

    def _post(self, client):
        w3 = _mock_w3(paused=False, tx_hash=bytes.fromhex(TX_HASH[2:]))
        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            return client.post(f"/clients/{CLIENT_ID}/deposit", json=VALID_BODY)

    def test_returns_200(self, client):
        assert self._post(client).status_code == 200

    def test_response_status_is_confirmed(self, client):
        assert self._post(client).json()["status"] == "confirmed"

    def test_response_has_transaction_id(self, client):
        assert "transaction_id" in self._post(client).json()

    def test_response_has_tx_hash(self, client):
        resp = self._post(client)
        assert resp.json()["on_chain_tx_hash"] is not None

    def test_creates_pending_record_in_firestore(self, client, mock_db):
        self._post(client)
        set_call = mock_db.collection("transactions").document().set.call_args[0][0]
        assert set_call["status"] == "pending"
        assert set_call["asset_type"] == "USD"
        assert set_call["network"] == "hardhat"
        assert set_call["amount"] == 1000

    def test_updates_record_to_confirmed(self, client, mock_db):
        self._post(client)
        update_call = mock_db.collection("transactions").document().update.call_args[0][0]
        assert update_call["status"] == "confirmed"
        assert "on_chain_tx_hash" in update_call

    def test_calls_mint_on_contract(self, client, mock_db):
        w3 = _mock_w3(paused=False, tx_hash=bytes.fromhex(TX_HASH[2:]))
        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            client.post(f"/clients/{CLIENT_ID}/deposit", json=VALID_BODY)
        w3.eth.contract.return_value.functions.mint.assert_called_once()


# ---------------------------------------------------------------------------
# 502 — on-chain failure
# ---------------------------------------------------------------------------

class TestDepositOnChainFailure:
    def test_returns_502_on_mint_exception(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        w3 = _mock_w3(paused=False)
        w3.eth.send_raw_transaction.side_effect = Exception("revert: wallet not approved")

        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.post(f"/clients/{CLIENT_ID}/deposit", json=VALID_BODY)

        assert resp.status_code == 502

    def test_updates_record_to_failed_on_mint_exception(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        w3 = _mock_w3(paused=False)
        w3.eth.send_raw_transaction.side_effect = Exception("revert")

        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            client.post(f"/clients/{CLIENT_ID}/deposit", json=VALID_BODY)

        update_call = mock_db.collection("transactions").document().update.call_args[0][0]
        assert update_call["status"] == "failed"
