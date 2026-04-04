"""
Integration tests for POST /clients and POST /clients/{id}/wallet.

Firestore is mocked so tests run without a Firebase project.
On-chain calls are skipped unless OPERATOR_PRIVATE_KEY is set (tested separately
by asserting the Web3 mock is/isn't called).
"""

from unittest.mock import MagicMock, patch, call
import pytest
from fastapi.testclient import TestClient

import main  # imported so we can set app.state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_CLIENT_BODY = {
    "first_name": "Alice",
    "last_name": "Smith",
    "date_of_birth": "1990-01-15",
    "national_id": "AB1234",
}

APPROVED_CLIENT_DOC = {
    "id": "client-123",
    "first_name": "Alice",
    "last_name": "Smith",
    "date_of_birth": "1990-01-15",
    "national_id": "AB1234",
    "kyc_status": "approved",
}


def _make_firestore_doc(exists: bool, data: dict | None = None) -> MagicMock:
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = data or {}
    return doc


@pytest.fixture
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(mock_db) -> TestClient:
    """TestClient with Firestore replaced by a MagicMock."""
    with (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value={}),
    ):
        with TestClient(main.app) as c:
            yield c


@pytest.fixture
def client_with_registry(mock_db) -> TestClient:
    """TestClient with a non-empty token_registry (one hardhat contract)."""
    registry = {
        "USD_hardhat": {
            "asset_type": "USD",
            "network": "hardhat",
            "contract_address": "0xDEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF",
        }
    }
    with (
        patch("main._init_firebase", return_value=mock_db),
        patch("main._load_token_registry", return_value=registry),
    ):
        with TestClient(main.app) as c:
            yield c


# ---------------------------------------------------------------------------
# POST /clients — success
# ---------------------------------------------------------------------------

class TestCreateClientApproved:
    def test_returns_201(self, client, mock_db):
        resp = client.post("/clients", json=VALID_CLIENT_BODY)
        assert resp.status_code == 201

    def test_response_has_kyc_approved(self, client, mock_db):
        resp = client.post("/clients", json=VALID_CLIENT_BODY)
        assert resp.json()["kyc_status"] == "approved"

    def test_response_has_client_id(self, client, mock_db):
        resp = client.post("/clients", json=VALID_CLIENT_BODY)
        assert "id" in resp.json()

    def test_response_has_no_failure_reason(self, client, mock_db):
        resp = client.post("/clients", json=VALID_CLIENT_BODY)
        assert resp.json().get("kyc_failure_reason") is None

    def test_writes_to_firestore(self, client, mock_db):
        resp = client.post("/clients", json=VALID_CLIENT_BODY)
        client_id = resp.json()["id"]
        mock_db.collection("clients").document(client_id).set.assert_called_once()

    def test_firestore_record_has_approved_status(self, client, mock_db):
        resp = client.post("/clients", json=VALID_CLIENT_BODY)
        client_id = resp.json()["id"]
        saved = mock_db.collection("clients").document(client_id).set.call_args[0][0]
        assert saved["kyc_status"] == "approved"


# ---------------------------------------------------------------------------
# POST /clients — KYC failure
# ---------------------------------------------------------------------------

class TestCreateClientRejected:
    INVALID_BODY = {**VALID_CLIENT_BODY, "national_id": "bad id!"}

    def test_returns_422(self, client, mock_db):
        resp = client.post("/clients", json=self.INVALID_BODY)
        assert resp.status_code == 422

    def test_response_has_failure_reason(self, client, mock_db):
        resp = client.post("/clients", json=self.INVALID_BODY)
        detail = resp.json()["detail"]
        assert detail["kyc_status"] == "failed"
        assert detail["kyc_failure_reason"]

    def test_still_writes_failed_record_to_firestore(self, client, mock_db):
        resp = client.post("/clients", json=self.INVALID_BODY)
        # Even on failure the record must be persisted
        assert mock_db.collection("clients").document().set.called

    def test_firestore_record_has_failed_status(self, client, mock_db):
        client.post("/clients", json=self.INVALID_BODY)
        set_call = mock_db.collection("clients").document().set.call_args[0][0]
        assert set_call["kyc_status"] == "failed"
        assert set_call["kyc_failure_reason"]


# ---------------------------------------------------------------------------
# POST /clients/{id}/wallet — 404
# ---------------------------------------------------------------------------

class TestCreateWalletNotFound:
    def test_returns_404_when_client_missing(self, client, mock_db):
        mock_db.collection("clients").document("unknown").get.return_value = (
            _make_firestore_doc(exists=False)
        )
        resp = client.post("/clients/unknown/wallet")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /clients/{id}/wallet — 403 (not KYC-approved)
# ---------------------------------------------------------------------------

class TestCreateWalletNotApproved:
    def test_returns_403_for_failed_kyc(self, client, mock_db):
        doc = _make_firestore_doc(
            exists=True,
            data={**APPROVED_CLIENT_DOC, "kyc_status": "failed"},
        )
        mock_db.collection("clients").document("client-123").get.return_value = doc
        resp = client.post("/clients/client-123/wallet")
        assert resp.status_code == 403

    def test_returns_403_for_pending_kyc(self, client, mock_db):
        doc = _make_firestore_doc(
            exists=True,
            data={**APPROVED_CLIENT_DOC, "kyc_status": "pending"},
        )
        mock_db.collection("clients").document("client-123").get.return_value = doc
        resp = client.post("/clients/client-123/wallet")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /clients/{id}/wallet — success (first creation)
# ---------------------------------------------------------------------------

class TestCreateWalletSuccess:
    @pytest.fixture(autouse=True)
    def setup(self, mock_db):
        doc = _make_firestore_doc(exists=True, data=APPROVED_CLIENT_DOC)
        mock_db.collection("clients").document("client-123").get.return_value = doc

    def test_returns_200(self, client):
        resp = client.post("/clients/client-123/wallet")
        assert resp.status_code == 200

    def test_response_contains_client_id(self, client):
        resp = client.post("/clients/client-123/wallet")
        assert resp.json()["client_id"] == "client-123"

    def test_response_contains_wallet_map(self, client):
        resp = client.post("/clients/client-123/wallet")
        wallet = resp.json()["wallet"]
        assert "hardhat" in wallet
        assert "sepolia" in wallet

    def test_wallet_addresses_are_valid_ethereum(self, client):
        resp = client.post("/clients/client-123/wallet")
        wallet = resp.json()["wallet"]
        for address in wallet.values():
            assert address.startswith("0x"), f"Expected 0x-prefixed address, got {address}"
            assert len(address) == 42

    def test_persists_wallet_to_firestore(self, client, mock_db):
        resp = client.post("/clients/client-123/wallet")
        wallet = resp.json()["wallet"]
        mock_db.collection("clients").document("client-123").update.assert_called_once_with(
            {"wallet": wallet}
        )

    def test_no_onchain_call_without_operator_key(self, client):
        with (
            patch("routers.clients.Web3") as mock_web3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": ""}),
        ):
            client.post("/clients/client-123/wallet")
            mock_web3.assert_not_called()


# ---------------------------------------------------------------------------
# POST /clients/{id}/wallet — idempotent (already exists)
# ---------------------------------------------------------------------------

class TestCreateWalletIdempotent:
    EXISTING_WALLET = {"hardhat": "0xAAAA" + "0" * 36, "sepolia": "0xBBBB" + "0" * 36}

    @pytest.fixture(autouse=True)
    def setup(self, mock_db):
        doc = _make_firestore_doc(
            exists=True,
            data={**APPROVED_CLIENT_DOC, "wallet": self.EXISTING_WALLET},
        )
        mock_db.collection("clients").document("client-123").get.return_value = doc

    def test_returns_200(self, client):
        resp = client.post("/clients/client-123/wallet")
        assert resp.status_code == 200

    def test_returns_existing_wallet(self, client):
        resp = client.post("/clients/client-123/wallet")
        assert resp.json()["wallet"] == self.EXISTING_WALLET

    def test_does_not_update_firestore(self, client, mock_db):
        client.post("/clients/client-123/wallet")
        mock_db.collection("clients").document("client-123").update.assert_not_called()


# ---------------------------------------------------------------------------
# On-chain registration (with operator key set)
# ---------------------------------------------------------------------------

class TestOnChainRegistration:
    CONTRACT_ADDR = "0xDEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF"

    @pytest.fixture(autouse=True)
    def setup(self, mock_db):
        doc = _make_firestore_doc(exists=True, data=APPROVED_CLIENT_DOC)
        mock_db.collection("clients").document("client-123").get.return_value = doc

    def test_calls_register_wallet_on_contract(self, client_with_registry, mock_db):
        mock_w3_instance = MagicMock()
        mock_w3_instance.eth.get_transaction_count.return_value = 0
        signed = MagicMock()
        signed.raw_transaction = b"signed-tx"
        mock_w3_instance.eth.account.sign_transaction.return_value = signed
        mock_w3_instance.eth.account.from_key.return_value = MagicMock(
            address="0x1234567890123456789012345678901234567890"
        )

        with (
            patch("routers.clients.Web3", return_value=mock_w3_instance) as MockWeb3,
            patch.dict("os.environ", {"OPERATOR_PRIVATE_KEY": "0x" + "a" * 64}),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x

            resp = client_with_registry.post("/clients/client-123/wallet")

        assert resp.status_code == 200
        mock_w3_instance.eth.send_raw_transaction.assert_called_once()
