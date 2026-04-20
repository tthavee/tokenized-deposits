"""
Tests for services/event_listener.py

Firestore and Web3 are mocked — no real node or Firebase project needed.
"""

from unittest.mock import MagicMock, call, patch
import pytest

from services.event_listener import (
    BURN_TOPIC,
    MAX_RETRIES,
    MINT_TOPIC,
    _find_client_id,
    _poll_network,
    _process_log,
    _run_once,
    _write_with_retry,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONTRACT_ADDR = "0xDeAdBeEfDeAdBeEfDeAdBeEfDeAdBeEfDeAdBeEf"
CONTRACT_ADDR_LOWER = CONTRACT_ADDR.lower()
WALLET_ADDR = "0x" + "A" * 40
TX_HASH = "b" * 64  # no 0x — matches HexBytes.hex() output in this environment
CLIENT_ID = "client-abc"
NETWORK = "hardhat"
ASSET_TYPE = "USD"
AMOUNT = 500

REGISTRY_ENTRY = {
    "asset_type": ASSET_TYPE,
    "network": NETWORK,
    "contract_address": CONTRACT_ADDR,
}
CONTRACTS = {CONTRACT_ADDR_LOWER: REGISTRY_ENTRY}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _HexBytes(bytes):
    """Minimal HexBytes substitute matching web3.py's HexBytes behaviour.

    web3.py's hexbytes.HexBytes.hex() returns the hex string WITHOUT a '0x'
    prefix (i.e. same as built-in bytes.hex()).  Our helper must match this so
    that topic-hash and tx-hash comparisons in production code work correctly.
    """

    def hex(self):
        return super().hex()


def _make_log(
    topic0_hex: str,
    wallet: str = WALLET_ADDR,
    amount: int = AMOUNT,
    tx_hash: str = TX_HASH,
    contract: str = CONTRACT_ADDR,
) -> dict:
    """Construct a minimal eth_getLogs-style log dict.

    topic0_hex / tx_hash are plain hex strings (no '0x' prefix), matching the
    output of HexBytes.hex() in this environment.
    wallet is a checksummed address string (with '0x' prefix).
    """
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


def _mock_db(
    *,
    last_block: int = 0,
    cursor_exists: bool = True,
    existing_tx: bool = False,
    client_id: str | None = CLIENT_ID,
) -> MagicMock:
    """Return a pre-wired Firestore client mock with per-collection isolation."""
    db = MagicMock()

    # Give each logical collection its own isolated mock so that where(),
    # document(), set(), etc. on one collection don't bleed into another.
    tx_col = MagicMock()
    clients_col = MagicMock()
    system_col = MagicMock()
    token_registry_col = MagicMock()

    def _get_collection(name):
        return {
            "transactions": tx_col,
            "clients": clients_col,
            "system": system_col,
            "token_registry": token_registry_col,
        }.get(name, MagicMock())

    db.collection.side_effect = _get_collection

    # system/event_listener cursor document
    cursor_doc = MagicMock()
    cursor_doc.exists = cursor_exists
    cursor_doc.to_dict.return_value = {f"last_processed_block_{NETWORK}": last_block}
    system_col.document.return_value.get.return_value = cursor_doc

    # transactions idempotency check
    tx_col.where.return_value.limit.return_value.get.return_value = (
        [MagicMock()] if existing_tx else []
    )

    # clients lookup
    if client_id:
        client_doc = MagicMock()
        client_doc.to_dict.return_value = {"id": client_id}
        clients_col.where.return_value.limit.return_value.get.return_value = [client_doc]
    else:
        clients_col.where.return_value.limit.return_value.get.return_value = []

    return db


def _mock_w3(latest_block: int = 100, logs: list | None = None) -> MagicMock:
    w3 = MagicMock()
    w3.eth.block_number = latest_block
    w3.eth.get_logs.return_value = logs if logs is not None else []
    return w3


# ---------------------------------------------------------------------------
# _find_client_id
# ---------------------------------------------------------------------------

class TestFindClientId:
    def test_returns_client_id_when_found(self):
        db = MagicMock()
        doc = MagicMock()
        doc.to_dict.return_value = {"id": CLIENT_ID}
        db.collection("clients").where.return_value.limit.return_value.get.return_value = [doc]

        result = _find_client_id(db, NETWORK, WALLET_ADDR)

        assert result == CLIENT_ID

    def test_queries_correct_wallet_field(self):
        db = MagicMock()
        db.collection("clients").where.return_value.limit.return_value.get.return_value = []

        _find_client_id(db, "hardhat", WALLET_ADDR)

        db.collection("clients").where.assert_called_once_with(
            "wallet.hardhat", "==", WALLET_ADDR
        )

    def test_returns_none_when_no_match(self):
        db = MagicMock()
        db.collection("clients").where.return_value.limit.return_value.get.return_value = []

        assert _find_client_id(db, NETWORK, WALLET_ADDR) is None


# ---------------------------------------------------------------------------
# _write_with_retry
# ---------------------------------------------------------------------------

class TestWriteWithRetry:
    def test_writes_record_on_first_attempt(self):
        db = MagicMock()
        record = {"id": TX_HASH, "status": "confirmed"}

        _write_with_retry(db, TX_HASH, record)

        db.collection("transactions").document(TX_HASH).set.assert_called_once_with(record)

    def test_retries_up_to_max_on_failure(self):
        db = MagicMock()
        db.collection("transactions").document(TX_HASH).set.side_effect = Exception("firestore down")

        _write_with_retry(db, TX_HASH, {"id": TX_HASH})

        assert db.collection("transactions").document(TX_HASH).set.call_count == MAX_RETRIES

    def test_succeeds_on_second_attempt(self):
        db = MagicMock()
        db.collection("transactions").document(TX_HASH).set.side_effect = [
            Exception("transient"),
            None,
        ]

        _write_with_retry(db, TX_HASH, {"id": TX_HASH})

        assert db.collection("transactions").document(TX_HASH).set.call_count == 2

    def test_does_not_raise_after_max_retries(self):
        db = MagicMock()
        db.collection("transactions").document(TX_HASH).set.side_effect = Exception("persistent")

        # Should log and return without raising.
        _write_with_retry(db, TX_HASH, {"id": TX_HASH})


# ---------------------------------------------------------------------------
# _process_log — Mint
# ---------------------------------------------------------------------------

class TestProcessLogMint:
    def setup_method(self):
        self.log = _make_log(MINT_TOPIC)
        self.db = _mock_db(existing_tx=False)

    def _call(self, db=None):
        with patch(
            "services.event_listener.Web3.to_checksum_address",
            side_effect=lambda x: WALLET_ADDR,
        ):
            _process_log(db or self.db, self.log, CONTRACTS)

    def test_creates_deposit_record(self):
        self._call()
        record = self.db.collection("transactions").document(TX_HASH).set.call_args[0][0]
        assert record["type"] == "deposit"

    def test_record_has_correct_amount(self):
        self._call()
        record = self.db.collection("transactions").document(TX_HASH).set.call_args[0][0]
        assert record["amount"] == AMOUNT

    def test_record_has_asset_type_and_network(self):
        self._call()
        record = self.db.collection("transactions").document(TX_HASH).set.call_args[0][0]
        assert record["asset_type"] == ASSET_TYPE
        assert record["network"] == NETWORK

    def test_record_status_is_confirmed(self):
        self._call()
        record = self.db.collection("transactions").document(TX_HASH).set.call_args[0][0]
        assert record["status"] == "confirmed"

    def test_record_has_tx_hash(self):
        self._call()
        record = self.db.collection("transactions").document(TX_HASH).set.call_args[0][0]
        assert record["on_chain_tx_hash"] == TX_HASH

    def test_record_has_client_id(self):
        self._call()
        record = self.db.collection("transactions").document(TX_HASH).set.call_args[0][0]
        assert record["client_id"] == CLIENT_ID

    def test_record_client_id_empty_when_client_not_found(self):
        db = _mock_db(existing_tx=False, client_id=None)
        self._call(db=db)
        record = db.collection("transactions").document(TX_HASH).set.call_args[0][0]
        assert record["client_id"] == ""

    def test_document_keyed_on_tx_hash(self):
        self._call()
        self.db.collection("transactions").document.assert_called_with(TX_HASH)


# ---------------------------------------------------------------------------
# _process_log — Burn
# ---------------------------------------------------------------------------

class TestProcessLogBurn:
    def setup_method(self):
        self.log = _make_log(BURN_TOPIC)
        self.db = _mock_db(existing_tx=False)

    def _call(self):
        with patch(
            "services.event_listener.Web3.to_checksum_address",
            side_effect=lambda x: WALLET_ADDR,
        ):
            _process_log(self.db, self.log, CONTRACTS)

    def test_creates_withdrawal_record(self):
        self._call()
        record = self.db.collection("transactions").document(TX_HASH).set.call_args[0][0]
        assert record["type"] == "withdrawal"


# ---------------------------------------------------------------------------
# _process_log — Idempotency
# ---------------------------------------------------------------------------

class TestProcessLogIdempotency:
    def test_skips_when_record_already_exists(self):
        db = _mock_db(existing_tx=True)
        log = _make_log(MINT_TOPIC)

        with patch("services.event_listener.Web3.to_checksum_address", return_value=WALLET_ADDR):
            _process_log(db, log, CONTRACTS)

        db.collection("transactions").document(TX_HASH).set.assert_not_called()

    def test_checks_idempotency_by_tx_hash(self):
        db = _mock_db(existing_tx=False)
        log = _make_log(MINT_TOPIC)

        with patch("services.event_listener.Web3.to_checksum_address", return_value=WALLET_ADDR):
            _process_log(db, log, CONTRACTS)

        db.collection("transactions").where.assert_called_with(
            "on_chain_tx_hash", "==", TX_HASH
        )

    def test_skips_log_for_unknown_contract(self):
        db = _mock_db()
        log = _make_log(MINT_TOPIC, contract="0x" + "9" * 40)

        with patch("services.event_listener.Web3.to_checksum_address", return_value=WALLET_ADDR):
            _process_log(db, log, CONTRACTS)

        db.collection("transactions").document(TX_HASH).set.assert_not_called()


# ---------------------------------------------------------------------------
# _poll_network
# ---------------------------------------------------------------------------

class TestPollNetwork:
    RPC = "http://127.0.0.1:8545"

    def _call(self, db, w3):
        with patch("services.event_listener.Web3") as MockWeb3:
            MockWeb3.to_checksum_address = lambda x: (
                x if isinstance(x, str) else ("0x" + x.hex())
            )
            _poll_network(db, NETWORK, CONTRACTS, self.RPC, w3)

    def test_no_op_when_already_at_latest_block(self):
        db = _mock_db(last_block=100)
        w3 = _mock_w3(latest_block=100)

        self._call(db, w3)

        w3.eth.get_logs.assert_not_called()

    def test_fetches_logs_from_last_block_plus_one(self):
        db = _mock_db(last_block=50)
        w3 = _mock_w3(latest_block=100)

        self._call(db, w3)

        call_args = w3.eth.get_logs.call_args[0][0]
        assert call_args["fromBlock"] == 51
        assert call_args["toBlock"] == 100

    def test_fetches_from_block_zero_on_first_run(self):
        db = _mock_db(last_block=0, cursor_exists=False)
        w3 = _mock_w3(latest_block=100)

        self._call(db, w3)

        call_args = w3.eth.get_logs.call_args[0][0]
        assert call_args["fromBlock"] == 0

    def test_filters_by_contract_addresses(self):
        db = _mock_db(last_block=0)
        w3 = _mock_w3(latest_block=10)

        self._call(db, w3)

        call_args = w3.eth.get_logs.call_args[0][0]
        assert len(call_args["address"]) == 1

    def test_filters_by_mint_and_burn_topics(self):
        db = _mock_db(last_block=0)
        w3 = _mock_w3(latest_block=10)

        self._call(db, w3)

        call_args = w3.eth.get_logs.call_args[0][0]
        assert MINT_TOPIC in call_args["topics"][0]
        assert BURN_TOPIC in call_args["topics"][0]

    def test_advances_cursor_after_successful_batch(self):
        db = _mock_db(last_block=50)
        w3 = _mock_w3(latest_block=100)

        self._call(db, w3)

        db.collection("system").document("event_listener").set.assert_called_once_with(
            {f"last_processed_block_{NETWORK}": 100}, merge=True
        )

    def test_cursor_not_advanced_when_no_new_blocks(self):
        db = _mock_db(last_block=100)
        w3 = _mock_w3(latest_block=100)

        self._call(db, w3)

        db.collection("system").document("event_listener").set.assert_not_called()

    def test_processes_mint_log(self):
        db = _mock_db(last_block=0)
        log = _make_log(MINT_TOPIC)
        w3 = _mock_w3(latest_block=10, logs=[log])

        self._call(db, w3)

        record = db.collection("transactions").document(TX_HASH).set.call_args[0][0]
        assert record["type"] == "deposit"
        assert record["status"] == "confirmed"

    def test_processes_burn_log(self):
        db = _mock_db(last_block=0)
        log = _make_log(BURN_TOPIC)
        w3 = _mock_w3(latest_block=10, logs=[log])

        self._call(db, w3)

        record = db.collection("transactions").document(TX_HASH).set.call_args[0][0]
        assert record["type"] == "withdrawal"

    def test_cursor_defaults_to_zero_when_doc_missing(self):
        db = _mock_db(last_block=0, cursor_exists=False)
        w3 = _mock_w3(latest_block=5)

        self._call(db, w3)

        call_args = w3.eth.get_logs.call_args[0][0]
        assert call_args["fromBlock"] == 0

    def test_processes_multiple_logs_in_one_batch(self):
        db = _mock_db(last_block=0)
        tx2 = "c" * 64
        logs = [_make_log(MINT_TOPIC), _make_log(BURN_TOPIC, tx_hash=tx2)]
        w3 = _mock_w3(latest_block=10, logs=logs)

        self._call(db, w3)

        assert db.collection("transactions").document().set.call_count == 2


# ---------------------------------------------------------------------------
# _run_once
# ---------------------------------------------------------------------------

class TestRunOnce:
    def test_refreshes_token_registry(self):
        app_state = MagicMock()
        app_state.db = MagicMock()

        new_registry = {"USD_hardhat": REGISTRY_ENTRY}
        app_state.db.collection("token_registry").stream.return_value = [
            MagicMock(id="USD_hardhat", to_dict=lambda: REGISTRY_ENTRY)
        ]

        with patch("services.event_listener.RPC_URLS", {"hardhat": ""}):
            _run_once(app_state, {})

        assert app_state.token_registry == new_registry

    def test_skips_network_with_no_rpc_url(self):
        app_state = MagicMock()
        app_state.db = MagicMock()
        app_state.db.collection("token_registry").stream.return_value = [
            MagicMock(id="USD_hardhat", to_dict=lambda: REGISTRY_ENTRY)
        ]

        with patch("services.event_listener.RPC_URLS", {"hardhat": ""}):
            with patch("services.event_listener._poll_network") as mock_poll:
                _run_once(app_state, {})

        mock_poll.assert_not_called()

    def test_calls_poll_for_each_network(self):
        app_state = MagicMock()
        app_state.db = MagicMock()

        entries = [
            MagicMock(id="USD_hardhat", to_dict=lambda: {**REGISTRY_ENTRY, "network": "hardhat"}),
            MagicMock(id="EUR_hardhat", to_dict=lambda: {"asset_type": "EUR", "network": "hardhat", "contract_address": "0x" + "2" * 40}),
        ]
        app_state.db.collection("token_registry").stream.return_value = entries

        with patch("services.event_listener.RPC_URLS", {"hardhat": "http://localhost:8545"}):
            with patch("services.event_listener._poll_network") as mock_poll:
                _run_once(app_state, {})

        # Both USD and EUR are on hardhat — one poll call for that network.
        mock_poll.assert_called_once()
        _, kwargs_network = mock_poll.call_args[0][1], mock_poll.call_args[0][2]
        # Two contracts should be grouped under hardhat
        assert len(kwargs_network) == 2

    def test_continues_after_network_error(self):
        """An error on one network must not prevent other networks from being polled."""
        app_state = MagicMock()
        app_state.db = MagicMock()

        entries = [
            MagicMock(id="USD_hardhat", to_dict=lambda: {**REGISTRY_ENTRY, "network": "hardhat"}),
            MagicMock(id="USD_sepolia", to_dict=lambda: {"asset_type": "USD", "network": "sepolia", "contract_address": "0x" + "3" * 40}),
        ]
        app_state.db.collection("token_registry").stream.return_value = entries

        poll_calls = []

        def boom_then_ok(db, network, contracts, rpc_url, w3):
            poll_calls.append(network)
            if network == "hardhat":
                raise Exception("RPC down")

        with patch("services.event_listener.RPC_URLS", {
            "hardhat": "http://localhost:8545",
            "sepolia": "http://localhost:9545",
        }):
            with patch("services.event_listener._poll_network", side_effect=boom_then_ok):
                _run_once(app_state, {})

        assert "hardhat" in poll_calls
        assert "sepolia" in poll_calls
