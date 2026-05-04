"""
Tests for POST /transfer.

Firestore and Web3 are mocked — no real node or Firebase project needed.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

import main

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SENDER_ID = "sender-111"
RECIPIENT_ID = "recipient-222"
CONTRACT_ADDR = "0xDEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF"
SENDER_ADDR = "0x" + "A" * 40
RECIPIENT_ADDR = "0x" + "B" * 40
TX_HASH = "0x" + "c" * 64

VALID_BODY = {
    "sender_id": SENDER_ID,
    "recipient_id": RECIPIENT_ID,
    "asset_type": "USD",
    "network": "hardhat",
    "amount": 50,
}

REGISTRY = {
    "USD_hardhat": {
        "asset_type": "USD",
        "network": "hardhat",
        "contract_address": CONTRACT_ADDR,
    }
}

SENDER_CLIENT = {
    "id": SENDER_ID,
    "kyc_status": "approved",
    "wallet": {"hardhat": SENDER_ADDR, "sepolia": "0x" + "D" * 40},
}

RECIPIENT_CLIENT = {
    "id": RECIPIENT_ID,
    "kyc_status": "approved",
    "wallet": {"hardhat": RECIPIENT_ADDR, "sepolia": "0x" + "E" * 40},
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


def _mock_w3(balance_wei: int = 100 * 10**18, tx_hash: bytes = bytes.fromhex(TX_HASH[2:]), paused: bool = False):
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

    contract = MagicMock()
    contract.functions.balanceOf.return_value.call.return_value = balance_wei
    contract.functions.paused.return_value.call.return_value = paused
    contract.functions.operatorTransfer.return_value.build_transaction.return_value = {}
    w3.eth.contract.return_value = contract
    return w3


def _setup_db(mock_db, sender=SENDER_CLIENT, recipient=RECIPIENT_CLIENT):
    """Wire mock_db so clients and transactions collections have independent mocks."""
    clients_col = MagicMock()
    transactions_col = MagicMock()

    def _get(doc_id):
        if doc_id == SENDER_ID:
            return _doc(exists=True, data=sender)
        if doc_id == RECIPIENT_ID:
            return _doc(exists=True, data=recipient)
        return _doc(exists=False)

    clients_col.document.side_effect = lambda doc_id: MagicMock(
        get=MagicMock(return_value=_get(doc_id))
    )

    mock_db.collection.side_effect = lambda name: (
        clients_col if name == "clients" else transactions_col
    )
    mock_db._transactions_col = transactions_col


# ---------------------------------------------------------------------------
# 400 — contract not in token registry
# ---------------------------------------------------------------------------

class TestTransferContractNotFound:
    def test_unknown_asset_type(self, client, mock_db):
        _setup_db(mock_db)
        body = {**VALID_BODY, "asset_type": "EUR"}
        resp = client.post("/api/transfer", json=body)
        assert resp.status_code == 400

    def test_unknown_network(self, client, mock_db):
        _setup_db(mock_db)
        body = {**VALID_BODY, "network": "mainnet"}
        resp = client.post("/api/transfer", json=body)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 400 — sender not found / no wallet
# ---------------------------------------------------------------------------

class TestTransferSenderInvalid:
    def test_sender_not_found(self, client, mock_db):
        mock_db.collection("clients").document.side_effect = lambda doc_id: MagicMock(
            get=MagicMock(return_value=_doc(exists=False))
        )
        resp = client.post("/api/transfer", json=VALID_BODY)
        assert resp.status_code == 400
        assert "Sender" in resp.json()["detail"]

    def test_sender_has_no_wallet_on_network(self, client, mock_db):
        sender_no_wallet = {**SENDER_CLIENT, "wallet": {"sepolia": "0x" + "D" * 40}}
        _setup_db(mock_db, sender=sender_no_wallet)
        resp = client.post("/api/transfer", json=VALID_BODY)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 400 — recipient not found / no wallet
# ---------------------------------------------------------------------------

class TestTransferRecipientInvalid:
    def test_recipient_not_found(self, client, mock_db):
        def _get(doc_id):
            if doc_id == SENDER_ID:
                return _doc(exists=True, data=SENDER_CLIENT)
            return _doc(exists=False)

        mock_db.collection("clients").document.side_effect = lambda doc_id: MagicMock(
            get=MagicMock(return_value=_get(doc_id))
        )
        resp = client.post("/api/transfer", json=VALID_BODY)
        assert resp.status_code == 400
        assert "Recipient" in resp.json()["detail"]

    def test_recipient_has_no_wallet_on_network(self, client, mock_db):
        recipient_no_wallet = {**RECIPIENT_CLIENT, "wallet": {"sepolia": "0x" + "E" * 40}}
        _setup_db(mock_db, recipient=recipient_no_wallet)
        w3 = _mock_w3(balance_wei=100 * 10**18)
        with (
            patch("routers.transfer.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.post("/api/transfer", json=VALID_BODY)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 400 — insufficient sender balance
# ---------------------------------------------------------------------------

class TestTransferInsufficientBalance:
    def test_returns_400_when_balance_too_low(self, client, mock_db):
        _setup_db(mock_db)
        w3 = _mock_w3(balance_wei=10 * 10**18)  # only 10 tokens, requesting 50
        with (
            patch("routers.transfer.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.post("/api/transfer", json=VALID_BODY)
        assert resp.status_code == 400
        assert resp.json()["detail"]["message"] == "Insufficient sender balance"

    def test_detail_includes_actual_balance(self, client, mock_db):
        _setup_db(mock_db)
        w3 = _mock_w3(balance_wei=10 * 10**18)
        with (
            patch("routers.transfer.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.post("/api/transfer", json=VALID_BODY)
        assert resp.json()["detail"]["balance"] == 10


# ---------------------------------------------------------------------------
# 202 — success
# ---------------------------------------------------------------------------

class TestTransferSuccess:
    @pytest.fixture(autouse=True)
    def setup(self, mock_db):
        _setup_db(mock_db)

    def _post(self, client):
        w3 = _mock_w3(balance_wei=100 * 10**18, tx_hash=bytes.fromhex(TX_HASH[2:]))
        with (
            patch("routers.transfer.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            return client.post("/api/transfer", json=VALID_BODY)

    def test_returns_202(self, client):
        assert self._post(client).status_code == 202

    def test_status_is_confirmed(self, client):
        assert self._post(client).json()["status"] == "confirmed"

    def test_response_has_tx_hash(self, client):
        assert self._post(client).json()["on_chain_tx_hash"] is not None

    def test_response_has_sender_and_recipient_tx_ids(self, client):
        data = self._post(client).json()
        assert "sender_transaction_id" in data
        assert "recipient_transaction_id" in data
        assert data["sender_transaction_id"] != data["recipient_transaction_id"]

    def test_calls_operatorTransfer_on_contract(self, client, mock_db):
        w3 = _mock_w3(balance_wei=100 * 10**18, tx_hash=bytes.fromhex(TX_HASH[2:]))
        with (
            patch("routers.transfer.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            client.post("/api/transfer", json=VALID_BODY)
        w3.eth.contract.return_value.functions.operatorTransfer.assert_called_once()

    def test_creates_two_firestore_records(self, client, mock_db):
        self._post(client)
        set_calls = mock_db._transactions_col.document.return_value.set.call_args_list
        assert len(set_calls) == 2

    def test_sender_record_has_direction_sent(self, client, mock_db):
        self._post(client)
        records = [c[0][0] for c in mock_db._transactions_col.document.return_value.set.call_args_list]
        sent_records = [r for r in records if r.get("direction") == "sent"]
        assert len(sent_records) == 1
        assert sent_records[0]["client_id"] == SENDER_ID

    def test_recipient_record_has_direction_received(self, client, mock_db):
        self._post(client)
        records = [c[0][0] for c in mock_db._transactions_col.document.return_value.set.call_args_list]
        received_records = [r for r in records if r.get("direction") == "received"]
        assert len(received_records) == 1
        assert received_records[0]["client_id"] == RECIPIENT_ID

    def test_both_records_updated_to_confirmed(self, client, mock_db):
        self._post(client)
        update_calls = mock_db._transactions_col.document.return_value.update.call_args_list
        confirmed = [c[0][0] for c in update_calls if c[0][0].get("status") == "confirmed"]
        assert len(confirmed) == 2
        assert all("on_chain_tx_hash" in c for c in confirmed)


# ---------------------------------------------------------------------------
# Firestore retry on confirmed-update failure
# ---------------------------------------------------------------------------

class TestTransferFirestoreRetry:
    def test_retries_confirmed_update_up_to_3_times(self, client, mock_db):
        _setup_db(mock_db)
        # First two update calls raise, third succeeds
        mock_db._transactions_col.document.return_value.update.side_effect = [
            Exception("transient"), Exception("transient"), None, None,
        ]
        w3 = _mock_w3(balance_wei=100 * 10**18, tx_hash=bytes.fromhex(TX_HASH[2:]))
        with (
            patch("routers.transfer.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.post("/api/transfer", json=VALID_BODY)
        assert resp.status_code == 202


# ---------------------------------------------------------------------------
# 502 — on-chain failure
# ---------------------------------------------------------------------------

class TestTransferOnChainFailure:
    def test_returns_502_on_transfer_exception(self, client, mock_db):
        _setup_db(mock_db)
        w3 = _mock_w3(balance_wei=100 * 10**18)
        w3.eth.send_raw_transaction.side_effect = Exception("revert: Recipient not KYC-approved")
        with (
            patch("routers.transfer.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            resp = client.post("/api/transfer", json=VALID_BODY)
        assert resp.status_code == 502

    def test_marks_both_records_failed_on_exception(self, client, mock_db):
        _setup_db(mock_db)
        w3 = _mock_w3(balance_wei=100 * 10**18)
        w3.eth.send_raw_transaction.side_effect = Exception("revert")
        with (
            patch("routers.transfer.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            client.post("/api/transfer", json=VALID_BODY)
        update_calls = mock_db._transactions_col.document.return_value.update.call_args_list
        assert len(update_calls) == 2
        for call in update_calls:
            assert call[0][0]["status"] == "failed"
