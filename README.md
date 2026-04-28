# Blockchain — Hardhat and Sepolia Project

Local Ethereum development environment for the Tokenized Deposits POC.

## About This Project

T-Bank's Tokenized Deposits POC demonstrates how traditional fiat bank deposits can be represented as ERC-20 tokens (`DepositToken`) on a blockchain. KYC-verified clients receive a chain-agnostic wallet and can deposit, withdraw, or transfer funds across multiple asset types (e.g., USD, EUR) on one or more networks. A Python backend API orchestrates all business logic, Solidity smart contracts govern on-chain token operations (one per `(Asset_Type, Network)` pair), Google Firestore persists off-chain state, and a Flutter frontend provides the client-facing interface.

Key design decisions:
- One `DepositToken.sol` contract is deployed per `(Asset_Type, Network)` pair (e.g., `USD/hardhat`, `EUR/hardhat`)
- The backend API is the sole transaction signer — clients never hold private keys
- A `Token_Registry` in Firestore maps each `(Asset_Type, Network)` pair to its deployed contract address
- An Event Listener Worker polls on-chain events and keeps Firestore in sync
- Token transfers are restricted at the contract level — the `_update` hook rejects any transfer to a non-KYC-approved address, enforcing compliance even for direct on-chain calls

### Spec Documents

- [Requirements](.specs/requirements.md) — functional requirements, user stories, and acceptance criteria
- [Design](.specs/design.md) — architecture, data models, sequence diagrams, activity diagrams, and correctness properties

---

## Prerequisites

- Node.js >= 18
- npm

## Setup

```bash
cd blockchain
npm install
```

## Usage

Start a local Hardhat node (port 8545):

```bash
# First run — fresh chain, state saved on exit
npm run node

# Subsequent runs — resume from saved state
npm run node:resume

# Intentional reset — wipe state and start fresh (requires redeployment)
npm run node:reset
```

Compile contracts:

```bash
npm run compile
```

Run tests:

```bash
npm test
```

Deploy to local network (requires node running in another terminal):

```bash
npm run deploy:local
```

## Optional: Sepolia Testnet

To deploy to Sepolia, create a `.env` file in the `blockchain/` directory:

```env
SEPOLIA_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY
OPERATOR_PRIVATE_KEY=0xYOUR_PRIVATE_KEY
ETHERSCAN_API_KEY=YOUR_ETHERSCAN_KEY   # optional, for contract verification
```

Then run:

```bash
# Deploy to Sepolia
npx hardhat run scripts/deploy.ts --network sepolia

# Verify on Etherscan (optional)
npx hardhat verify --network sepolia <CONTRACT_ADDRESS>
```

Get free Sepolia ETH from [sepoliafaucet.com](https://sepoliafaucet.com).

## Upgrading the Smart Contract

The contract is deployed behind a UUPS proxy — the proxy address (and all stored balances) never changes when you upgrade the logic.

```bash
# After editing DepositToken.sol, run tests first
cd blockchain
npx hardhat test

# Then upgrade the implementation on Sepolia (proxy address stays the same)
npx hardhat run scripts/upgrade.ts --network sepolia

# Or upgrade on local hardhat
npx hardhat run scripts/upgrade.ts --network localhost
```

---

## Event Listener

The event listener watches the blockchain for `Mint`, `Burn`, and `Transfer` events and mirrors them into Firestore as transaction records. It is **not** started automatically with the backend — run it separately when you need on-chain sync.

```bash
cd backend
venv/bin/python scripts/run_event_listener.py
```

Stop it with `Ctrl+C`.

**When to run it:**
- After a deposit, withdrawal, or transfer to confirm the Firestore record was written
- To catch any on-chain activity done outside the app (Etherscan, scripts)
- During active testing sessions

**What it does each cycle (every 30s):**
1. Reads the last processed block cursor from Firestore per network
2. Fetches `Mint`, `Burn`, and `Transfer` logs from the chain (up to 2,000 blocks at a time)
3. Writes any new events to Firestore as transaction records (idempotent)
4. Advances the block cursor

> **Note:** The token registry is reloaded from Firestore every 10 cycles (~5 min) rather than every poll to stay within Firestore's free-tier read quota.

---

## Project Structure

```
blockchain/
├── contracts/
│   └── DepositToken.sol   # UUPS-upgradeable ERC-20 deposit token
├── scripts/
│   ├── deploy.ts           # First-time deployment via UUPS proxy
│   └── upgrade.ts          # Upgrade implementation behind existing proxy
├── test/                   # Hardhat + Chai + fast-check tests
├── hardhat.config.ts
└── package.json

backend/
├── routers/
│   ├── clients.py          # KYC, wallet, deposit, withdraw, transfer, balance endpoints
│   └── admin.py            # Pause/unpause, register-wallets, reconcile endpoints
├── services/
│   ├── event_listener.py   # On-chain Mint/Burn/Transfer event → Firestore sync logic
│   ├── kyc.py
│   └── wallet.py
├── scripts/
│   └── run_event_listener.py  # Standalone event listener entrypoint
└── main.py                 # FastAPI app

frontend/
├── lib/
│   ├── screens/            # KYC, Wallet, Deposit/Withdraw, Transfer, History, Admin screens
│   ├── providers/          # Riverpod state providers
│   ├── models/             # BalanceEntry, TransactionEntry, etc.
│   └── services/           # ApiClient HTTP wrapper
└── pubspec.yaml
```

## Network

- Local node: `http://127.0.0.1:8545`
- Chain ID: `31337`
- The deployment script writes `deployment-{asset}-{network}.json` with the proxy address and ABI, which the Python backend reads at startup.
