"""
Tests for POST /admin/pause and POST /admin/unpause.
"""

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

import main

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTRACT_ADDR = "0xDEADBEEFDEADBEEFDEADBEEFDEADBEEFDEADBEEF"
TX_HASH = "0x" + "a" * 64
VALID_KEY = "supersecretkey"

REGISTRY = {
    "USD_hardhat": {
        "asset_type": "USD",
        "network": "hardhat",
        "contract_address": CONTRACT_ADDR,
    }
}

VALID_BODY = {"asset_type": "USD", "network": "hardhat"}


def _mock_w3() -> MagicMock:
    w3 = MagicMock()
    w3.eth.get_transaction_count.return_value = 0
    w3.eth.account.from_key.return_value = MagicMock(
        address="0x1234567890123456789012345678901234567890"
    )
    signed = MagicMock()
    signed.raw_transaction = b"raw"
    w3.eth.account.sign_transaction.return_value = signed
    w3.eth.send_raw_transaction.return_value = bytes.fromhex(TX_HASH[2:])
    w3.eth.contract.return_value = MagicMock()
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
    ):
        with TestClient(main.app) as c:
            yield c


def _post(client, url, body=None, *, api_key=VALID_KEY, env_key=VALID_KEY):
    headers = {"X-API-Key": api_key} if api_key else {}
    with (
        patch("routers.admin.Web3", return_value=_mock_w3()) as MockWeb3,
        patch.dict("os.environ", {
            "ADMIN_API_KEY": env_key,
            "OPERATOR_PRIVATE_KEY": "0x" + "a" * 64,
        }),
    ):
        MockWeb3.HTTPProvider = MagicMock()
        MockWeb3.to_checksum_address = lambda x: x
        return client.post(url, json=body or VALID_BODY, headers=headers)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class TestAdminAuth:
    @pytest.mark.parametrize("url", ["/admin/pause", "/admin/unpause"])
    def test_401_missing_api_key(self, client, url):
        resp = _post(client, url, api_key=None)
        assert resp.status_code == 401

    @pytest.mark.parametrize("url", ["/admin/pause", "/admin/unpause"])
    def test_401_wrong_api_key(self, client, url):
        resp = _post(client, url, api_key="wrongkey")
        assert resp.status_code == 401

    @pytest.mark.parametrize("url", ["/admin/pause", "/admin/unpause"])
    def test_200_correct_api_key(self, client, url):
        resp = _post(client, url)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /admin/pause
# ---------------------------------------------------------------------------

class TestPause:
    def test_returns_paused_true(self, client):
        resp = _post(client, "/admin/pause")
        assert resp.json()["paused"] is True

    def test_response_has_asset_and_network(self, client):
        resp = _post(client, "/admin/pause")
        assert resp.json()["asset_type"] == "USD"
        assert resp.json()["network"] == "hardhat"

    def test_response_has_tx_hash(self, client):
        resp = _post(client, "/admin/pause")
        assert resp.json()["tx_hash"] is not None

    def test_404_unknown_pair(self, client):
        resp = _post(client, "/admin/pause", body={"asset_type": "EUR", "network": "hardhat"})
        assert resp.status_code == 404

    def test_calls_pause_on_contract(self, client):
        w3 = _mock_w3()
        with (
            patch("routers.admin.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {
                "ADMIN_API_KEY": VALID_KEY,
                "OPERATOR_PRIVATE_KEY": "0x" + "a" * 64,
            }),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            client.post(
                "/admin/pause",
                json=VALID_BODY,
                headers={"X-API-Key": VALID_KEY},
            )
        w3.eth.contract.return_value.functions.pause.assert_called_once()


# ---------------------------------------------------------------------------
# POST /admin/unpause
# ---------------------------------------------------------------------------

class TestUnpause:
    def test_returns_paused_false(self, client):
        resp = _post(client, "/admin/unpause")
        assert resp.json()["paused"] is False

    def test_response_has_asset_and_network(self, client):
        resp = _post(client, "/admin/unpause")
        assert resp.json()["asset_type"] == "USD"
        assert resp.json()["network"] == "hardhat"

    def test_response_has_tx_hash(self, client):
        resp = _post(client, "/admin/unpause")
        assert resp.json()["tx_hash"] is not None

    def test_404_unknown_pair(self, client):
        resp = _post(client, "/admin/unpause", body={"asset_type": "USD", "network": "mainnet"})
        assert resp.status_code == 404

    def test_calls_unpause_on_contract(self, client):
        w3 = _mock_w3()
        with (
            patch("routers.admin.Web3", return_value=w3) as MockWeb3,
            patch.dict("os.environ", {
                "ADMIN_API_KEY": VALID_KEY,
                "OPERATOR_PRIVATE_KEY": "0x" + "a" * 64,
            }),
        ):
            MockWeb3.HTTPProvider = MagicMock()
            MockWeb3.to_checksum_address = lambda x: x
            client.post(
                "/admin/unpause",
                json=VALID_BODY,
                headers={"X-API-Key": VALID_KEY},
            )
        w3.eth.contract.return_value.functions.unpause.assert_called_once()


# ---------------------------------------------------------------------------
# Isolation — pausing one pair doesn't affect others
# ---------------------------------------------------------------------------

class TestPauseIsolation:
    def test_pause_one_does_not_affect_other_pair(self, client):
        # Pause USD/hardhat — USD/sepolia (not in registry) should 404 independently
        _post(client, "/admin/pause")
        resp = _post(client, "/admin/pause", body={"asset_type": "USD", "network": "sepolia"})
        assert resp.status_code == 404
