# Requirements Document

## Introduction

This document defines the requirements for a Proof of Concept (POC) of Tokenized Deposits for T-Bank.
The POC demonstrates how traditional bank deposits can be represented as ERC-20 tokens on an Ethereum
blockchain. Clients go through a KYC check, receive a blockchain wallet, and can deposit or withdraw
funds — with the corresponding tokens being minted or burned on-chain. Off-chain state is persisted in
Google Firestore. The system is exposed via a Python backend API and a Flutter mobile/web frontend.
The primary deployment target is a local Hardhat network for development and POC demonstration.
Sepolia testnet is supported as an optional network for stakeholder access.

---

## Glossary

- **T-Bank**: The issuing bank operating the tokenized deposit system.
- **Deposit_Token**: An ERC-20 token issued by T-Bank representing 1 unit of fiat currency held on deposit.
- **Smart_Contract**: The Solidity contract deployed on Ethereum that governs minting, burning, and transfers of Deposit_Tokens.
- **Wallet**: An Ethereum externally-owned account (EOA) created for and assigned to a verified client.
- **Client**: A bank customer who has passed KYC verification and holds a Wallet.
- **KYC_Service**: The component responsible for verifying client identity before wallet creation.
- **Backend_API**: The Python service that orchestrates business logic, interacts with Firestore, and submits transactions to the blockchain.
- **Firestore**: Google Firestore database used as the off-chain source of truth for client records, wallet mappings, and transaction history.
- **Frontend**: The Flutter application used by clients and bank operators to interact with the system.
- **Bank_Operator**: A T-Bank employee with administrative privileges to manage the system.
- **Minting**: The act of creating new Deposit_Tokens in response to a confirmed fiat deposit.
- **Burning**: The act of destroying Deposit_Tokens in response to a withdrawal request.

---

## Requirements

### Requirement 1: KYC Verification Before Wallet Creation

**User Story:** As a Bank_Operator, I want clients to pass KYC verification before receiving a wallet, so that T-Bank complies with identity regulations and only verified individuals hold Deposit_Tokens.

#### Acceptance Criteria

1. WHEN a client submits identity information, THE KYC_Service SHALL verify the client's identity before a Wallet is created.
2. WHEN KYC verification succeeds, THE Backend_API SHALL mark the client record in Firestore as KYC-approved.
3. IF KYC verification fails, THEN THE Backend_API SHALL reject the wallet creation request and store the failure reason in Firestore.
4. THE Smart_Contract SHALL restrict Deposit_Token minting to Wallets that are registered as KYC-approved on-chain.
5. WHEN a client's KYC status is revoked by a Bank_Operator, THE Backend_API SHALL update the client record in Firestore and THE Smart_Contract SHALL prevent further minting to that Wallet.

---

### Requirement 2: Client Wallet Creation

**User Story:** As a Client, I want a blockchain wallet created for me after KYC approval, so that I can hold and transact with Deposit_Tokens.

#### Acceptance Criteria

1. WHEN a client's KYC status is approved, THE Backend_API SHALL generate a new Ethereum Wallet for the client.
2. THE Backend_API SHALL store the Wallet address and the association to the client record in Firestore.
3. THE Smart_Contract SHALL register the Wallet address as an approved holder.
4. IF a Wallet already exists for a client, THEN THE Backend_API SHALL return the existing Wallet address without creating a duplicate.
5. THE Frontend SHALL display the client's Wallet address after successful wallet creation.

---

### Requirement 3: Deposit and Token Minting

**User Story:** As a Client, I want to deposit fiat currency and receive an equivalent amount of Deposit_Tokens in my Wallet, so that my deposit is represented on-chain.

#### Acceptance Criteria

1. WHEN a Client initiates a deposit of amount N, THE Backend_API SHALL record a pending deposit transaction in Firestore.
2. WHEN the fiat deposit is confirmed, THE Backend_API SHALL instruct THE Smart_Contract to mint N Deposit_Tokens to the Client's Wallet.
3. WHEN minting succeeds, THE Backend_API SHALL update the transaction record in Firestore to a confirmed status and record the on-chain transaction hash.
4. IF the minting transaction fails on-chain, THEN THE Backend_API SHALL update the transaction record in Firestore to a failed status and SHALL NOT credit the Client's Wallet.
5. THE Frontend SHALL display the updated Deposit_Token balance in the Client's Wallet after a successful deposit.
6. THE Smart_Contract SHALL emit a Mint event containing the recipient Wallet address and the minted amount for every successful minting operation.

---

### Requirement 4: Withdrawal and Token Burning

**User Story:** As a Client, I want to withdraw my deposit and have the corresponding Deposit_Tokens burned, so that the on-chain supply accurately reflects actual deposits held by T-Bank.

#### Acceptance Criteria

1. WHEN a Client initiates a withdrawal of amount N, THE Backend_API SHALL verify that the Client's Wallet holds at least N Deposit_Tokens.
2. IF the Client's Wallet holds fewer than N Deposit_Tokens, THEN THE Backend_API SHALL reject the withdrawal request and return a descriptive error to the Frontend.
3. WHEN the withdrawal is approved, THE Backend_API SHALL instruct THE Smart_Contract to burn N Deposit_Tokens from the Client's Wallet.
4. WHEN burning succeeds, THE Backend_API SHALL record the withdrawal as completed in Firestore and record the on-chain transaction hash.
5. IF the burning transaction fails on-chain, THEN THE Backend_API SHALL update the transaction record in Firestore to a failed status and SHALL NOT debit the Client's Wallet.
6. THE Smart_Contract SHALL emit a Burn event containing the source Wallet address and the burned amount for every successful burning operation.

---

### Requirement 5: Token Balance and Transaction History

**User Story:** As a Client, I want to view my current Deposit_Token balance and transaction history, so that I can track my deposits and withdrawals.

#### Acceptance Criteria

1. THE Backend_API SHALL expose an endpoint that returns the current Deposit_Token balance for a given Wallet address by querying THE Smart_Contract.
2. THE Backend_API SHALL expose an endpoint that returns the transaction history for a Client by reading records from Firestore.
3. THE Frontend SHALL display the Client's current Deposit_Token balance and a list of past deposit and withdrawal transactions.
4. WHEN a new deposit or withdrawal transaction is completed, THE Backend_API SHALL update Firestore so that the transaction appears in the Client's history within 5 seconds of on-chain confirmation.

---

### Requirement 6: Smart Contract Integrity and Admin Controls

**User Story:** As a Bank_Operator, I want administrative controls over the Smart_Contract, so that T-Bank can respond to incidents and maintain system integrity.

#### Acceptance Criteria

1. THE Smart_Contract SHALL designate a single owner address controlled by T-Bank with exclusive rights to mint, burn, register wallets, and pause the contract.
2. WHEN a Bank_Operator triggers a pause, THE Smart_Contract SHALL halt all minting and burning operations until unpaused.
3. WHILE the Smart_Contract is paused, THE Backend_API SHALL reject deposit and withdrawal requests and return a descriptive error to the Frontend.
4. THE Smart_Contract SHALL follow the ERC-20 standard so that token balances are queryable by standard Ethereum tooling.
5. THE Smart_Contract SHALL be deployable to a local Hardhat network for POC demonstration purposes. Deployment to the Ethereum Sepolia testnet is supported as an optional configuration.

---

### Requirement 7: Off-Chain Data Consistency (Firestore)

**User Story:** As a Bank_Operator, I want all on-chain events to be reflected in Firestore, so that T-Bank has an auditable off-chain record of all tokenized deposit activity.

#### Acceptance Criteria

1. WHEN a Mint or Burn event is emitted by THE Smart_Contract, THE Backend_API SHALL write a corresponding record to Firestore containing the Wallet address, amount, transaction hash, and timestamp.
2. THE Backend_API SHALL store each Client record in Firestore with fields for: client identifier, KYC status, Wallet address, and creation timestamp.
3. IF a Firestore write fails after an on-chain event, THEN THE Backend_API SHALL retry the write up to 3 times before logging a permanent failure.
4. THE Backend_API SHALL expose a reconciliation endpoint that compares on-chain token balances with Firestore records and returns any discrepancies.

---

### Requirement 8: Optional Testnet Deployment (Sepolia)

**User Story:** As a Bank_Operator, I want the option to deploy the smart contract to Sepolia testnet, so that stakeholders can inspect and interact with the contract publicly if needed.

#### Acceptance Criteria

1. THE deployment script SHALL support both local Hardhat and Sepolia networks via a network flag.
2. WHEN deploying to Sepolia, THE Backend_API SHALL connect via an RPC provider (Alchemy or Infura) configured via environment variable.
3. WHEN deploying to Sepolia, THE Smart_Contract SHOULD be verified on Sepolia Etherscan so that the source code is publicly readable.
4. Sepolia deployment is OPTIONAL and not required for the core POC demonstration.
