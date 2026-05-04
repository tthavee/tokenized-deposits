"""
Tests for POST /clients/{id}/withdraw.

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

VALID_BODY = {"amount": 500, "asset_type": "USD", "network": "hardhat"}

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


def _mock_w3(
    paused: bool = False,
    balance: int = 1000,
    tx_hash: bytes = bytes.fromhex(TX_HASH[2:]),
) -> MagicMock:
    w3 = MagicMock()
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.account.from_key.return_value = MagicMock(
        address="0x1234567890123456789012345678901234567890"
    )
    signed = MagicMock()
    signed.raw_transaction = b"raw"
    w3.eth.account.sign_transaction.return_value = signed
    w3.eth.send_raw_transaction.return_value = tx_hash

    contract = MagicMock()
    contract.functions.paused.return_value.call.return_value = paused
    contract.functions.balanceOf.return_value.call.return_value = balance
    w3.eth.contract.return_value = contract
    return w3


def _patched_post(client, mock_db, body=None, *, paused=False, balance=1000):
    mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
        exists=True, data=APPROVED_CLIENT
    )
    w3 = _mock_w3(paused=paused, balance=balance)
    with (
        patch("routers.clients.Web3", return_value=w3) as MockWeb3,
        patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
    ):
        MockWeb3.HTTPProvider = MagicMock()
        MockWeb3.to_checksum_address = lambda x: x
        return client.post(f"/api/clients/{CLIENT_ID}/withdraw", json=body or VALID_BODY), w3


# ---------------------------------------------------------------------------
# 404 — client not found
# ---------------------------------------------------------------------------

class TestWithdrawClientNotFound:
    def test_returns_404(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(exists=False)
        resp = client.post(f"/api/clients/{CLIENT_ID}/withdraw", json=VALID_BODY)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 404 — no wallet for network
# ---------------------------------------------------------------------------

class TestWithdrawNoWallet:
    def test_returns_404_when_wallet_missing(self, client, mock_db):
        data = {**APPROVED_CLIENT, "wallet": {}}
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=data
        )
        resp = client.post(f"/api/clients/{CLIENT_ID}/withdraw", json=VALID_BODY)
        assert resp.status_code == 404

    def test_returns_404_when_network_absent(self, client, mock_db):
        data = {**APPROVED_CLIENT, "wallet": {"sepolia": "0x" + "C" * 40}}
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=data
        )
        resp = client.post(f"/api/clients/{CLIENT_ID}/withdraw", json=VALID_BODY)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 404 — contract not in registry
# ---------------------------------------------------------------------------

class TestWithdrawContractNotFound:
    def test_returns_404_for_unknown_asset_type(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        resp = client.post(f"/api/clients/{CLIENT_ID}/withdraw", json={**VALID_BODY, "asset_type": "EUR"})
        assert resp.status_code == 404

    def test_returns_404_for_unknown_network(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        resp = client.post(f"/api/clients/{CLIENT_ID}/withdraw", json={**VALID_BODY, "network": "mainnet"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 503 — contract paused
# ---------------------------------------------------------------------------

class TestWithdrawContractPaused:
    def test_returns_503(self, client, mock_db):
        resp, _ = _patched_post(client, mock_db, paused=True)
        assert resp.status_code == 503

    def test_detail_names_asset_and_network(self, client, mock_db):
        resp, _ = _patched_post(client, mock_db, paused=True)
        assert "USD" in resp.json()["detail"]
        assert "hardhat" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 422 — insufficient balance
# ---------------------------------------------------------------------------

class TestWithdrawInsufficientBalance:
    def test_returns_422_when_balance_too_low(self, client, mock_db):
        resp, _ = _patched_post(client, mock_db, balance=100)  # amount=500 > balance=100
        assert resp.status_code == 422

    def test_detail_includes_current_balance(self, client, mock_db):
        resp, _ = _patched_post(client, mock_db, balance=100)
        assert resp.json()["detail"]["balance"] == 100

    def test_exact_balance_is_allowed(self, client, mock_db):
        resp, _ = _patched_post(client, mock_db, balance=500)  # balance == amount
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 200 — success
# ---------------------------------------------------------------------------

class TestWithdrawSuccess:
    def test_returns_200(self, client, mock_db):
        resp, _ = _patched_post(client, mock_db)
        assert resp.status_code == 200

    def test_response_status_confirmed(self, client, mock_db):
        resp, _ = _patched_post(client, mock_db)
        assert resp.json()["status"] == "confirmed"

    def test_response_has_transaction_id(self, client, mock_db):
        resp, _ = _patched_post(client, mock_db)
        assert "transaction_id" in resp.json()

    def test_response_has_tx_hash(self, client, mock_db):
        resp, _ = _patched_post(client, mock_db)
        assert resp.json()["on_chain_tx_hash"] is not None

    def test_creates_pending_record_in_firestore(self, client, mock_db):
        _patched_post(client, mock_db)
        record = mock_db.collection("transactions").document().set.call_args[0][0]
        assert record["status"] == "pending"
        assert record["type"] == "withdrawal"
        assert record["asset_type"] == "USD"
        assert record["network"] == "hardhat"
        assert record["amount"] == 500

    def test_updates_record_to_confirmed(self, client, mock_db):
        _patched_post(client, mock_db)
        update = mock_db.collection("transactions").document().update.call_args[0][0]
        assert update["status"] == "confirmed"
        assert "on_chain_tx_hash" in update

    def test_calls_burn_on_contract(self, client, mock_db):
        _, w3 = _patched_post(client, mock_db)
        w3.eth.contract.return_value.functions.burn.assert_called_once()


# ---------------------------------------------------------------------------
# 502 — on-chain failure
# ---------------------------------------------------------------------------

class TestWithdrawOnChainFailure:
    def test_returns_502_on_burn_exception(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        w3 = _mock_w3(balance=1000)
        w3.eth.send_raw_transaction.side_effect = Exception("revert: wallet not approved")

        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.post(f"/api/clients/{CLIENT_ID}/withdraw", json=VALID_BODY)

        assert resp.status_code == 502

    def test_updates_record_to_failed_on_burn_exception(self, client, mock_db):
        mock_db.collection("clients").document(CLIENT_ID).get.return_value = _doc(
            exists=True, data=APPROVED_CLIENT
        )
        w3 = _mock_w3(balance=1000)
        w3.eth.send_raw_transaction.side_effect = Exception("revert")

        with (
            patch("routers.clients.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            client.post(f"/api/clients/{CLIENT_ID}/withdraw", json=VALID_BODY)

        update = mock_db.collection("transactions").document().update.call_args[0][0]
        assert update["status"] == "failed"
