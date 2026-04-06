# Tokenized Deposits — Architecture & Technical Flow

## Overview

Tokenized Deposits is a system that represents fiat currency deposits as ERC-20 tokens on a blockchain. When a user deposits USD, tokens are minted to their wallet. When they withdraw, tokens are burned. The token balance is always a 1:1 mirror of their fiat position.

### System Architecture

```mermaid
graph TD
    User["👤 User (Browser / Mobile)"]
    Flutter["Flutter App\nlib/screens, lib/providers, lib/services"]
    Backend["FastAPI Backend\nrouters/, services/"]
    Firestore["🔥 Firestore\nclients, transactions,\ntoken_registry, system"]
    Chain["⛓️ Blockchain\nHardhat / Sepolia"]
    Contract["DepositToken.sol\nERC-20 + Ownable + Pausable"]
    EventListener["Event Listener\nasyncio background task"]

    User -->|"interacts with"| Flutter
    Flutter -->|"HTTP REST"| Backend
    Backend -->|"Firebase Admin SDK"| Firestore
    Backend -->|"web3.py / JSON-RPC"| Chain
    Chain --> Contract
    EventListener -->|"eth_getLogs every 3s"| Chain
    EventListener -->|"upsert transaction records"| Firestore
    Backend -->|"spawns on startup"| EventListener
```

---

## Directory Structure

```
tokenized-deposits/
├── backend/                    # Python FastAPI service
│   ├── main.py                 # App entry point, lifespan, middleware
│   ├── routers/
│   │   ├── clients.py          # All client-facing endpoints
│   │   └── admin.py            # Operator-only endpoints
│   ├── services/
│   │   ├── kyc.py              # KYC verification stub
│   │   ├── wallet.py           # Ethereum address generation
│   │   └── event_listener.py   # Background on-chain event poller
│   └── tests/                  # pytest test suites
│
├── blockchain/                 # Hardhat project
│   ├── contracts/
│   │   └── DepositToken.sol    # The ERC-20 token contract
│   ├── scripts/
│   │   └── deploy.ts           # Deploy script (writes to Firestore)
│   └── test/
│       └── DepositToken.test.ts
│
├── frontend/                   # Flutter app
│   ├── lib/
│   │   ├── main.dart           # App entry, global providers, session restore
│   │   ├── config/app_config.dart
│   │   ├── models/             # Plain Dart data classes
│   │   ├── providers/          # Riverpod state notifiers
│   │   ├── screens/            # UI screens
│   │   └── services/           # ApiClient, SessionService
│   └── test/                   # Flutter widget tests
│
├── firestore.rules             # Deny all client-side access (backend-only via Admin SDK)
└── firestore.indexes.json      # Composite index definitions
```

---

## The Smart Contract — `DepositToken.sol`

**File:** `blockchain/contracts/DepositToken.sol`

Each `(asset_type, network)` pair gets its own deployed instance of this contract. E.g. USD on hardhat is one contract, EUR on Sepolia is another.

```solidity
contract DepositToken is ERC20, Ownable, Pausable {
    string public assetType;      // e.g. "USD"
    string public networkLabel;   // e.g. "hardhat"
    mapping(address => bool) private _approved;  // KYC allowlist
```

### Contract Inheritance

```mermaid
classDiagram
    class ERC20 {
        +balanceOf(address) uint256
        +transfer(address, uint256) bool
        +_mint(address, uint256)
        +_burn(address, uint256)
    }
    class Ownable {
        +owner() address
        +onlyOwner modifier
        +transferOwnership(address)
    }
    class Pausable {
        +paused() bool
        +whenNotPaused modifier
        +_pause()
        +_unpause()
    }
    class DepositToken {
        +assetType string
        +networkLabel string
        -_approved mapping
        +registerWallet(address)
        +revokeWallet(address)
        +isApproved(address) bool
        +mint(address, uint256)
        +burn(address, uint256)
        +pause()
        +unpause()
    }
    DepositToken --|> ERC20
    DepositToken --|> Ownable
    DepositToken --|> Pausable
```

**Key design decisions:**

| Feature | How it works |
|---|---|
| Access control | `onlyOwner` — only the operator wallet (backend) can mint/burn |
| KYC allowlist | `registerWallet(address)` adds a wallet; mint/burn revert with `WalletNotApproved` if not in the list |
| Pause circuit breaker | `pause()` / `unpause()` block all mint/burn operations; useful for incident response |
| Events | `Mint(address indexed recipient, uint256 amount)` and `Burn(address indexed source, uint256 amount)` are emitted and used by the event listener |

**Deployment:** `blockchain/scripts/deploy.ts` deploys a contract, saves the address to a local JSON file, and writes a record to the Firestore `token_registry` collection so the backend can discover it at startup.

---

## Firestore Collections

All Firestore access is via the Firebase Admin SDK (backend only). Client-side access is denied in `firestore.rules`.

### Collection Schema

```mermaid
erDiagram
    clients {
        string id PK
        string first_name
        string last_name
        string date_of_birth
        string national_id
        string kyc_status
        string kyc_failure_reason
        map wallet
    }
    transactions {
        string id PK
        string client_id FK
        string type
        int amount
        string asset_type
        string network
        string status
        string on_chain_tx_hash
        string created_at
    }
    token_registry {
        string id PK
        string contract_address
        string asset_type
        string network
        string deployed_at
        string deployer_address
    }
    system {
        string id PK
        int last_processed_block_hardhat
        int last_processed_block_sepolia
    }
    clients ||--o{ transactions : "client_id"
```

### `clients/{client_id}`
```json
{
  "id": "uuid",
  "first_name": "Alice",
  "last_name": "Smith",
  "date_of_birth": "1990-01-15",
  "national_id": "AB1234",
  "kyc_status": "approved",
  "kyc_failure_reason": null,
  "wallet": {
    "hardhat": "0xABC...",
    "sepolia": "0xDEF..."
  }
}
```

### `transactions/{tx_id}`
```json
{
  "id": "uuid-or-tx-hash",
  "client_id": "uuid",
  "type": "deposit",
  "amount": 100,
  "asset_type": "USD",
  "network": "hardhat",
  "status": "confirmed",
  "on_chain_tx_hash": "0x...",
  "created_at": "2026-04-05T10:00:00Z"
}
```

### `token_registry/{asset_type}_{network}`
```json
{
  "contract_address": "0x...",
  "asset_type": "USD",
  "network": "hardhat",
  "deployed_at": "2026-04-05T09:00:00Z",
  "deployer_address": "0x..."
}
```

### `system/event_listener`
```json
{
  "last_processed_block_hardhat": 42,
  "last_processed_block_sepolia": 17000000
}
```
Used as a cursor so the event listener knows which blocks have already been processed.

---

## Backend Startup Sequence

**File:** `backend/main.py`

```mermaid
sequenceDiagram
    participant UV as uvicorn
    participant App as FastAPI app
    participant FB as Firebase / Firestore
    participant EL as Event Listener (asyncio task)

    UV->>App: startup (lifespan)
    App->>FB: initialize_app(credentials)
    FB-->>App: Firestore client
    App->>FB: token_registry.stream()
    FB-->>App: registry docs → app.state.token_registry
    App->>EL: asyncio.create_task(run_event_listener)
    Note over EL: runs in background every 3s
    App-->>UV: yield — HTTP server ready

    UV->>App: shutdown signal
    App->>EL: listener_task.cancel()
    EL-->>App: CancelledError (suppressed)
```

The `token_registry` dict is kept in `app.state` and shared across all requests. The event listener refreshes it on every poll cycle so newly deployed contracts are picked up without a restart.

---

## User Flows

### 1. App Launch & Session Restore

```mermaid
flowchart TD
    A([App Launch]) --> B[WidgetsFlutterBinding.ensureInitialized]
    B --> C[SessionService.loadClientId]
    C --> D{Saved session\nexists?}
    D -- Yes --> E[Seed currentClientIdProvider\n+ currentWalletProvider]
    D -- No --> F[Providers start as null]
    E --> G[runApp with ProviderScope overrides]
    F --> G
    G --> H{clientId\nin provider?}
    H -- Yes --> I[Home shows\nSigned in as clientId\n+ Clear session tile]
    H -- No --> J[Home shows nav\nto KYC]
    I --> K[Deposit/Withdraw and Wallet\nscreens work immediately]
```

---

### 2. KYC + Wallet Creation

```mermaid
sequenceDiagram
    actor User
    participant UI as Flutter KycScreen
    participant KN as KycNotifier
    participant API as FastAPI /clients
    participant KYC as KYCService
    participant FS as Firestore
    participant Chain as Blockchain

    User->>UI: Fill form + Submit
    UI->>KN: submit(firstName, lastName, dob, nationalId)
    KN->>KN: state = KycLoading
    KN->>API: POST /clients
    API->>KYC: verify(KYCRequest)
    KYC-->>API: KYCResult(approved=true)
    API->>FS: clients/{id}.set(record)
    API-->>KN: 201 ClientResponse

    KN->>API: POST /clients/{id}/wallet
    API->>API: generate address per network\n(eth_account.Account.create)
    API->>FS: clients/{id}.update(wallet)
    API->>Chain: registerWallet(address)\nper DepositToken contract
    Chain-->>API: tx receipt
    API-->>KN: 200 WalletResponse

    KN->>KN: state = KycSuccess(client, wallet)
    KN->>UI: ref.listen triggers
    UI->>UI: set currentClientIdProvider\nset currentWalletProvider
    UI->>UI: SessionService.save(clientId, wallet)
    UI->>UI: Navigator.pushReplacementNamed /wallet
```

**KYC failure path:**
```mermaid
sequenceDiagram
    actor User
    participant UI as Flutter KycScreen
    participant KN as KycNotifier
    participant API as FastAPI /clients

    User->>UI: Submit with invalid national_id
    UI->>KN: submit(...)
    KN->>API: POST /clients
    API-->>KN: 422 {kyc_failure_reason: "..."}
    KN->>KN: state = KycError(message)
    KN->>UI: ref.listen triggers
    UI->>UI: ScaffoldMessenger.showSnackBar
    UI->>UI: stays on KycScreen\nbutton re-enabled
```

---

### 3. Deposit (Fiat → Tokens)

```mermaid
sequenceDiagram
    actor User
    participant UI as Flutter DepositWithdrawScreen
    participant TN as TxNotifier
    participant API as FastAPI /deposit
    participant FS as Firestore
    participant Chain as Blockchain
    participant CT as DepositToken contract

    User->>UI: Enter amount, asset_type, network → Deposit
    UI->>TN: deposit(clientId, amount, assetType, network)
    TN->>TN: state = TxLoading
    TN->>API: POST /clients/{id}/deposit

    API->>FS: clients/{id}.get() → chain_address
    API->>API: token_registry lookup → contract_address
    API->>FS: transactions/{txId}.set(status=pending)
    API->>Chain: contract.paused().call()
    Chain-->>API: false

    API->>Chain: contract.mint(chain_address, amount)\nsigned with OPERATOR_PRIVATE_KEY
    Chain->>CT: mint()
    CT->>CT: _approved[wallet] check
    CT->>CT: _mint(address, amount)
    CT-->>Chain: emit Mint(recipient, amount)
    Chain-->>API: tx_hash

    API->>FS: transactions/{txId}.update(confirmed, tx_hash)
    API-->>TN: {transaction_id, status: confirmed}

    TN->>TN: state = TxSuccess(transactionId)
    TN->>UI: ref.listen triggers
    UI->>UI: showSnackBar "Transaction confirmed"
    UI->>UI: ref.invalidate(balancesProvider)\n→ refreshes balance display
```

---

### 4. Withdrawal (Tokens → Fiat)

```mermaid
sequenceDiagram
    actor User
    participant UI as Flutter DepositWithdrawScreen
    participant TN as TxNotifier
    participant API as FastAPI /withdraw
    participant FS as Firestore
    participant Chain as Blockchain
    participant CT as DepositToken contract

    User->>UI: Enter amount → Withdraw
    UI->>TN: withdraw(clientId, amount, assetType, network)
    TN->>API: POST /clients/{id}/withdraw

    API->>FS: clients/{id}.get() → chain_address
    API->>Chain: contract.balanceOf(chain_address)
    Chain-->>API: current_balance

    alt balance < amount
        API-->>TN: 422 Insufficient token balance
        TN->>TN: state = TxError
        TN->>UI: showSnackBar error
    else balance >= amount
        API->>FS: transactions/{txId}.set(pending)
        API->>Chain: contract.burn(chain_address, amount)\nsigned with OPERATOR_PRIVATE_KEY
        Chain->>CT: burn()
        CT->>CT: _burn(address, amount)
        CT-->>Chain: emit Burn(source, amount)
        Chain-->>API: tx_hash
        API->>FS: transactions/{txId}.update(confirmed)
        API-->>TN: {transaction_id, status: confirmed}
        TN->>UI: showSnackBar confirmed
    end
```

---

### 5. Event Listener (Background Sync)

**File:** `backend/services/event_listener.py`

```mermaid
flowchart TD
    Start([asyncio task starts]) --> Loop[/Every 3 seconds/]
    Loop --> Refresh[Refresh token_registry\nfrom Firestore]
    Refresh --> Group[Group contracts by network]
    Group --> ForNet[For each network]

    ForNet --> ReadCursor[Read cursor:\nsystem/event_listener\n.last_processed_block_network]
    ReadCursor --> GetLatest[eth.block_number]
    GetLatest --> Check{cursor >= latest?}
    Check -- Yes --> Sleep[sleep 3s → Loop]
    Check -- No --> GetLogs["eth_getLogs(\n  fromBlock=cursor+1,\n  toBlock=latest,\n  address=contracts,\n  topics=[MINT, BURN]\n)"]

    GetLogs --> ForLog[For each log]
    ForLog --> Decode["Decode log:\n• topics[1][-20:] → wallet\n• data → amount (uint256)\n• transactionHash → tx_hash"]
    Decode --> IdCheck{transactions where\non_chain_tx_hash == tx_hash\nexists?}
    IdCheck -- Yes → skip --> ForLog
    IdCheck -- No --> FindClient["_find_client_id:\nclients.where(wallet.network == address)"]
    FindClient --> Write["_write_with_retry:\ntransactions/tx_hash .set(record)\n(up to 3 attempts)"]
    Write --> ForLog
    ForLog --> AdvanceCursor[Advance cursor\nto latest_block]
    AdvanceCursor --> ForNet
    ForNet --> Sleep
```

**Topic computation:**
```python
MINT_TOPIC = Web3.keccak(text="Mint(address,uint256)").hex()
BURN_TOPIC  = Web3.keccak(text="Burn(address,uint256)").hex()
```
These match the `event Mint(address indexed recipient, uint256 amount)` signature in the Solidity contract.

---

### 6. Admin — Reconciliation

**Endpoint:** `GET /admin/reconcile` (requires `X-API-Key` header)

```mermaid
flowchart TD
    Start([GET /admin/reconcile]) --> Auth{X-API-Key\nvalid?}
    Auth -- No --> 401[401 Unauthorized]
    Auth -- Yes --> Clients["Query Firestore:\nclients where kyc_status == approved"]
    Clients --> ForClient[For each client]
    ForClient --> ForToken[For each token_registry entry]
    ForToken --> Resolve[Resolve chain_address\nfrom client.wallet.network]
    Resolve --> Skip{chain_address\nor contract_address\nmissing?}
    Skip -- Yes --> ForToken
    Skip -- No --> OnChain["contract.balanceOf(chain_address)\n→ on_chain_balance"]
    OnChain --> FSBalance["Firestore balance:\nΣ confirmed deposits\n− Σ confirmed withdrawals\nfor this client + asset + network"]
    FSBalance --> Compare{on_chain\n==\nfirestore?}
    Compare -- Yes → in sync --> ForToken
    Compare -- No --> Append[Append DiscrepancyEntry]
    Append --> ForToken
    ForToken --> ForClient
    ForClient --> Return["Return list of discrepancies\n(empty = all in sync)"]
```

---

## Frontend State Management

**Library:** Riverpod 2.x (`flutter_riverpod`)

### Provider Dependency Graph

```mermaid
graph TD
    ACP["apiClientProvider\nProvider&lt;ApiClient&gt;"]
    CCI["currentClientIdProvider\nStateProvider&lt;String?&gt;"]
    CWP["currentWalletProvider\nStateProvider&lt;Wallet?&gt;"]
    KYC["kycProvider\nStateNotifierProvider&lt;KycNotifier, KycState&gt;"]
    TX["txProvider\nStateNotifierProvider&lt;TxNotifier, TxState&gt;"]
    BAL["balancesProvider\nFutureProvider.family&lt;List&lt;BalanceEntry&gt;, String&gt;"]

    ACP --> KYC
    ACP --> TX
    ACP --> BAL

    KYC -->|"on success: sets"| CCI
    KYC -->|"on success: sets"| CWP

    CCI -->|"read by"| DepositWithdrawScreen
    CWP -->|"read by"| WalletScreen
    BAL -->|"watched by"| DepositWithdrawScreen
    TX -->|"watched by"| DepositWithdrawScreen
    KYC -->|"watched by"| KycScreen
```

### Sealed State Classes

```mermaid
stateDiagram-v2
    direction LR
    [*] --> KycIdle
    KycIdle --> KycLoading: submit()
    KycLoading --> KycSuccess: API ok
    KycLoading --> KycError: API error
    KycSuccess --> KycIdle: reset()
    KycError --> KycIdle: reset()

    note right of KycSuccess
        Triggers navigation to /wallet
        Sets currentClientIdProvider
        Sets currentWalletProvider
        Calls SessionService.save()
    end note

    note right of KycError
        Shows SnackBar with message
        Re-enables submit button
    end note
```

```mermaid
stateDiagram-v2
    direction LR
    [*] --> TxIdle
    TxIdle --> TxLoading: deposit() / withdraw()
    TxLoading --> TxSuccess: API ok
    TxLoading --> TxError: API error
    TxSuccess --> TxIdle: reset()
    TxError --> TxIdle: reset()

    note right of TxSuccess
        Shows confirmation SnackBar
        Invalidates balancesProvider
        → triggers balance refresh
    end note
```

### Session persistence (`lib/services/session_service.dart`)

Uses `shared_preferences` to persist the `clientId` and wallet JSON to device/browser storage. On startup, `main()` reads these before `runApp()` and seeds the providers via `ProviderScope` overrides, so the user's session survives page refreshes and app restarts.

```dart
// main() startup sequence
WidgetsFlutterBinding.ensureInitialized();
final savedClientId = await SessionService.loadClientId();
final savedWallet   = await SessionService.loadWallet();
runApp(ProviderScope(
  overrides: [
    currentClientIdProvider.overrideWith((ref) => savedClientId),
    currentWalletProvider.overrideWith((ref) => savedWallet),
  ],
  child: const TokenizedDepositsApp(),
));
```

---

## API Reference

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/clients` | — | KYC verification + client creation |
| POST | `/clients/{id}/wallet` | — | Generate chain addresses + on-chain registration |
| POST | `/clients/{id}/deposit` | — | Mint tokens for a fiat deposit |
| POST | `/clients/{id}/withdraw` | — | Burn tokens for a fiat withdrawal |
| GET | `/clients/{id}/balance` | — | On-chain balance for one `(asset_type, network)` |
| GET | `/clients/{id}/balances` | — | On-chain balances for all token registry pairs |
| GET | `/clients/{id}/transactions` | — | Firestore transaction history |
| POST | `/admin/pause` | `X-API-Key` | Pause a DepositToken contract |
| POST | `/admin/unpause` | `X-API-Key` | Unpause a DepositToken contract |
| GET | `/admin/reconcile` | `X-API-Key` | Compare on-chain vs. Firestore balances |
| GET | `/health` | — | Liveness check |

---

## Running Locally

**Prerequisites:** Python 3.11+, Node 18+, Flutter 3.x, Firebase project with Firestore.

```bash
# 1. Start the local blockchain
cd blockchain
npm install
npm run node                          # keeps running in terminal 1

# 2. Deploy a token contract (terminal 2)
npx hardhat run scripts/deploy.ts --network localhost \
  -- --asset-type USD --network-label hardhat

# 3. Start the backend (terminal 3)
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp secrets/firebase-credentials.json ...   # populate from Firebase Console
uvicorn main:app --reload

# 4. Start the Flutter app (terminal 4)
cd frontend
flutter run -d chrome \
  --dart-define=BASE_API_URL=http://localhost:8000
```

**Environment variables (backend `.env`):**

| Variable | Purpose |
|---|---|
| `OPERATOR_PRIVATE_KEY` | Hardhat/Sepolia account that owns the contracts |
| `HARDHAT_RPC_URL` | Defaults to `http://127.0.0.1:8545` |
| `SEPOLIA_RPC_URL` | Alchemy/Infura URL for Sepolia testnet |
| `ADMIN_API_KEY` | Secret for `/admin/*` endpoints |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Firebase service account JSON |

---

## Key Design Patterns

**Dual-write consistency:** Every deposit/withdrawal creates a Firestore record *and* submits an on-chain transaction. The event listener provides a safety net by independently reading on-chain events and creating Firestore records if they are missing, keeping the two stores in sync.

**Operator key model:** The backend operator wallet is the sole `owner` of all DepositToken contracts. Clients never hold private keys that can mint or burn — they only hold addresses where tokens are credited. This means the backend controls all token operations.

**Idempotency:** The event listener keys transaction records on `on_chain_tx_hash`, so replaying events (e.g. after a restart) never creates duplicates.

**Test overrides:** `apiClientProvider` is a plain `Provider` that tests replace via `ProviderScope(overrides: [...])`. Backend tests patch `main.run_event_listener` with `AsyncMock` to prevent the background task from running during test setup.
