# Blockchain — Hardhat Project

Local Ethereum development environment for the Tokenized Deposits POC.

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
npm run node
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

## Project Structure

```
blockchain/
├── contracts/       # Solidity contracts (DepositToken.sol — issue #5)
├── scripts/
│   └── deploy.ts    # Deployment script — saves deployment.json for backend
├── test/            # Hardhat + Chai + fast-check tests (issue #17)
├── hardhat.config.ts
├── tsconfig.json
└── package.json
```

## Network

- Local node: `http://127.0.0.1:8545`
- Chain ID: `31337`
- The deployment script writes `deployment.json` with the contract address and ABI,
  which the Python backend reads at startup.
