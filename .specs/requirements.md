# Requirements Document

## Introduction

This document defines the requirements for a Proof of Concept (POC) of Tokenized Deposits for T-Bank.
The POC demonstrates how traditional bank deposits can be represented as ERC-20 tokens on a blockchain.
Clients go through a KYC check, receive a chain-agnostic Wallet, and can deposit, withdraw, or transfer funds across
multiple fiat-backed digital asset types (e.g., USD, EUR) on one or more Networks — with the corresponding
tokens being minted, burned, or transferred on-chain. Off-chain state is persisted in Google Firestore. The system is
exposed via a Python backend API and a Flutter mobile/web frontend.

The Wallet model is designed to be chain-agnostic: a single logical Wallet is identified by the client's
identifier and stores a mapping of Network → Chain_Address. This allows future Networks (e.g., Stellar,
Polygon) to be added without changing the Wallet data model or existing client records. For this POC,
Ethereum is the only implemented Network, with the primary deployment target being a local Hardhat network.
Sepolia testnet is supported as an optional Ethereum Network for stakeholder access.

**Known Limitation — Off-Chain Assets:** The current Wallet model is chain-agnostic across blockchain
networks but does not support assets that exist outside of a blockchain (e.g., traditional securities,
commodities, fiat balances in a core banking system, loyalty points). All assets are assumed to be
represented by a Smart_Contract on a Network. Supporting off-chain asset types would require a broader
abstraction where `Network` is replaced by a generic `AssetPlatform` (which could be a blockchain, a
custodian API, or an internal ledger) and `Chain_Address` is replaced by a generic `AccountReference`.
This is out of scope for the current POC but should be considered if the Wallet is intended to serve as
a universal digital asset holder in future iterations.

---

## Glossary

- **T-Bank**: The issuing bank operating the tokenized deposit system.
- **Network**: A blockchain network supported by the system, identified by a string key (e.g., "hardhat", "sepolia"). Ethereum is the only Network implemented in this POC.
- **Asset_Type**: A named category of fiat-backed digital asset supported by the system (e.g., "USD", "EUR"), together with the Network on which it is deployed. Each (Asset_Type, Network) pair has exactly one associated Smart_Contract.
- **Deposit_Token**: An ERC-20 token issued by T-Bank for a specific Asset_Type on a specific Network, representing 1 unit of the corresponding fiat currency held on deposit.
- **Smart_Contract**: A Solidity contract deployed on a Network that governs minting, burning, and transfers of Deposit_Tokens for a single Asset_Type. One Smart_Contract is deployed per (Asset_Type, Network) pair.
- **Token_Registry**: The off-chain configuration (stored in Firestore and loaded by the Backend_API) that maps each (Asset_Type, Network) pair to its deployed Smart_Contract address.
- **Wallet**: A chain-agnostic logical construct assigned to a verified client, identified by the client's identifier. A Wallet stores a mapping of Network → Chain_Address and can hold Deposit_Tokens of multiple Asset_Types across one or more Networks.
- **Chain_Address**: A network-specific address associated with a client's Wallet for a given Network (e.g., an Ethereum EOA address for the "hardhat" or "sepolia" Network).
- **Client**: A bank customer who has passed KYC verification and holds a Wallet.
- **KYC_Service**: The component responsible for verifying client identity before wallet creation.
- **Backend_API**: The Python service that orchestrates business logic, interacts with Firestore, and submits transactions to the blockchain.
- **Firestore**: Google Firestore database used as the off-chain source of truth for client records, wallet mappings, token registry, and transaction history.
- **Frontend**: The Flutter application used by clients and bank operators to interact with the system.
- **Bank_Operator**: A T-Bank employee with administrative privileges to manage the system.
- **Minting**: The act of creating new Deposit_Tokens of a specific Asset_Type on a specific Network in response to a confirmed fiat deposit.
- **Burning**: The act of destroying Deposit_Tokens of a specific Asset_Type on a specific Network in response to a withdrawal request.
- **Transfer**: The act of moving a specified amount of Deposit_Tokens of a given Asset_Type from one Client's Chain_Address to another KYC-approved Client's Chain_Address on the same Network, without any fiat conversion.

---

## Requirements

### Requirement 1: KYC Verification Before Wallet Creation

**User Story:** As a Bank_Operator, I want clients to pass KYC verification before receiving a wallet, so that T-Bank complies with identity regulations and only verified individuals hold Deposit_Tokens.

#### Acceptance Criteria

1. WHEN a client submits identity information, THE KYC_Service SHALL verify the client's identity before a Wallet is created.
2. WHEN KYC verification succeeds, THE Backend_API SHALL mark the client record in Firestore as KYC-approved.
3. IF KYC verification fails, THEN THE Backend_API SHALL reject the wallet creation request and store the failure reason in Firestore.
4. THE Smart_Contract SHALL restrict Deposit_Token minting to Wallets that are registered as KYC-approved on-chain.
5. WHEN a client's KYC status is revoked by a Bank_Operator, THE Backend_API SHALL update the client record in Firestore and THE Smart_Contract SHALL prevent further minting to that Wallet for all Asset_Types.

---

### Requirement 2: Client Wallet Creation

**User Story:** As a Client, I want a blockchain wallet created for me after KYC approval, so that I can hold and transact with Deposit_Tokens across multiple Asset_Types and Networks.

#### Acceptance Criteria

1. WHEN a client's KYC status is approved, THE Backend_API SHALL create a logical Wallet identified by the client's identifier, independent of any specific blockchain.
2. WHEN a Wallet is created, THE Backend_API SHALL generate a Chain_Address for each supported Network (currently only Ethereum) and store the Network → Chain_Address mapping in Firestore under the client's Wallet record.
3. THE Backend_API SHALL store the Wallet record and its Network → Chain_Address mapping in Firestore associated with the client identifier.
4. THE Smart_Contract for each (Asset_Type, Network) pair SHALL register the corresponding Chain_Address as an approved holder at the time of Wallet creation.
5. IF a Wallet already exists for a client, THEN THE Backend_API SHALL return the existing Wallet record without creating a duplicate.
6. THE Frontend SHALL display the client's Chain_Address for each Network after successful wallet creation.
7. THE Backend_API SHALL register the Chain_Address for each Network on all Smart_Contracts listed in the Token_Registry for that Network at the time of wallet creation.

---

### Requirement 3: Deposit and Token Minting

**User Story:** As a Client, I want to deposit fiat currency of a specific Asset_Type on a specific Network and receive an equivalent amount of Deposit_Tokens in my Wallet's Chain_Address for that Network, so that my deposit is represented on-chain.

#### Acceptance Criteria

1. WHEN a Client initiates a deposit of amount N for a given Asset_Type and Network, THE Backend_API SHALL record a pending deposit transaction in Firestore including the Asset_Type and Network.
2. WHEN the fiat deposit is confirmed, THE Backend_API SHALL resolve the Smart_Contract address from the Token_Registry using the (Asset_Type, Network) pair and instruct that Smart_Contract to mint N Deposit_Tokens to the Client's Chain_Address for that Network.
3. IF the specified (Asset_Type, Network) pair is not present in the Token_Registry, THEN THE Backend_API SHALL reject the deposit request and return a descriptive error to the Frontend.
4. WHEN minting succeeds, THE Backend_API SHALL update the transaction record in Firestore to a confirmed status and record the on-chain transaction hash.
5. IF the minting transaction fails on-chain, THEN THE Backend_API SHALL update the transaction record in Firestore to a failed status and SHALL NOT credit the Client's Chain_Address.
6. THE Frontend SHALL display the updated Deposit_Token balance for the relevant (Asset_Type, Network) in the Client's Wallet after a successful deposit.
7. THE Smart_Contract SHALL emit a Mint event containing the recipient Chain_Address and the minted amount for every successful minting operation.

---

### Requirement 4: Withdrawal and Token Burning

**User Story:** As a Client, I want to withdraw my deposit of a specific Asset_Type on a specific Network and have the corresponding Deposit_Tokens burned, so that the on-chain supply for each (Asset_Type, Network) accurately reflects actual deposits held by T-Bank.

#### Acceptance Criteria

1. WHEN a Client initiates a withdrawal of amount N for a given Asset_Type and Network, THE Backend_API SHALL verify that the Client's Chain_Address for that Network holds at least N Deposit_Tokens of that Asset_Type.
2. IF the Client's Chain_Address holds fewer than N Deposit_Tokens of the specified (Asset_Type, Network), THEN THE Backend_API SHALL reject the withdrawal request and return a descriptive error to the Frontend.
3. IF the specified (Asset_Type, Network) pair is not present in the Token_Registry, THEN THE Backend_API SHALL reject the withdrawal request and return a descriptive error to the Frontend.
4. WHEN the withdrawal is approved, THE Backend_API SHALL resolve the Smart_Contract address from the Token_Registry using the (Asset_Type, Network) pair and instruct that Smart_Contract to burn N Deposit_Tokens from the Client's Chain_Address for that Network.
5. WHEN burning succeeds, THE Backend_API SHALL record the withdrawal as completed in Firestore including the Asset_Type, Network, and on-chain transaction hash.
6. IF the burning transaction fails on-chain, THEN THE Backend_API SHALL update the transaction record in Firestore to a failed status and SHALL NOT debit the Client's Chain_Address.
7. THE Smart_Contract SHALL emit a Burn event containing the source Chain_Address and the burned amount for every successful burning operation.

---

### Requirement 5: Token Transfer between Client Wallets

**User Story:** As a Client, I want to transfer Deposit_Tokens of a specific Asset_Type on a specific Network directly to another Client's Wallet, so that value can move between verified participants without involving fiat conversion or bank intermediation.

#### Acceptance Criteria

1. WHEN a Client initiates a transfer of amount N of a given Asset_Type and Network to a recipient identified by their client identifier, THE Backend_API SHALL verify that the sender's Chain_Address for that Network holds at least N Deposit_Tokens of that Asset_Type.
2. IF the sender's Chain_Address holds fewer than N Deposit_Tokens of the specified (Asset_Type, Network), THEN THE Backend_API SHALL reject the transfer request and return a descriptive error to the Frontend.
3. IF the specified (Asset_Type, Network) pair is not present in the Token_Registry, THEN THE Backend_API SHALL reject the transfer request and return a descriptive error to the Frontend.
4. IF the recipient does not have a registered Wallet with a Chain_Address for the specified Network, THEN THE Backend_API SHALL reject the transfer request and return a descriptive error to the Frontend.
5. THE Smart_Contract SHALL restrict token transfers so that only Chain_Addresses registered as KYC-approved holders may receive Deposit_Tokens, enforcing this check on every transfer via an override of the internal ERC-20 transfer hook.
6. WHEN the transfer is approved, THE Backend_API SHALL resolve the Smart_Contract address from the Token_Registry using the (Asset_Type, Network) pair and instruct that Smart_Contract to transfer N Deposit_Tokens from the sender's Chain_Address to the recipient's Chain_Address for that Network.
7. WHEN the transfer succeeds on-chain, THE Backend_API SHALL record the transfer in Firestore for both the sender and the recipient, with each record including the Asset_Type, Network, amount, counterparty client identifier, transaction direction (sent/received), and on-chain transaction hash.
8. IF the transfer transaction fails on-chain, THEN THE Backend_API SHALL update the transaction record in Firestore to a failed status and SHALL NOT debit the sender's Chain_Address or credit the recipient's Chain_Address.
9. THE Smart_Contract SHALL emit an ERC-20 Transfer event containing the sender Chain_Address, recipient Chain_Address, and amount for every successful transfer operation.
10. THE Frontend SHALL display the updated Deposit_Token balance for the relevant (Asset_Type, Network) in the Client's Wallet after a successful transfer, and the transfer SHALL appear in the transaction history for both the sender and the recipient.

---

### Requirement 6: Token Balance and Transaction History

**User Story:** As a Client, I want to view my current Deposit_Token balance per (Asset_Type, Network) and my full transaction history, so that I can track my deposits, withdrawals, and transfers across all asset types and networks.

#### Acceptance Criteria

1. THE Backend_API SHALL expose an endpoint that returns the current Deposit_Token balance for a given Wallet and (Asset_Type, Network) pair by querying the corresponding Smart_Contract.
2. THE Backend_API SHALL expose an endpoint that returns the Deposit_Token balances for a given Wallet across all (Asset_Type, Network) pairs listed in the Token_Registry.
3. THE Backend_API SHALL expose an endpoint that returns the transaction history for a Client by reading records from Firestore, with each record including the transaction type (deposit, withdrawal, or transfer), Asset_Type, Network, amount, counterparty (where applicable), and timestamp.
4. THE Frontend SHALL display the Client's current Deposit_Token balance per (Asset_Type, Network) and a list of past deposit, withdrawal, and transfer transactions, each labelled with its type, Asset_Type, and Network.
5. WHEN a new deposit, withdrawal, or transfer transaction is completed, THE Backend_API SHALL update Firestore so that the transaction appears in the Client's history within 5 seconds of on-chain confirmation.

---

### Requirement 7: Smart Contract Integrity and Admin Controls

**User Story:** As a Bank_Operator, I want administrative controls over each Smart_Contract, so that T-Bank can respond to incidents and maintain system integrity across all (Asset_Type, Network) pairs.

#### Acceptance Criteria

1. THE Smart_Contract for each (Asset_Type, Network) pair SHALL designate a single owner address controlled by T-Bank with exclusive rights to mint, burn, register wallets, and pause the contract.
2. WHEN a Bank_Operator triggers a pause on a Smart_Contract for a given (Asset_Type, Network) pair, THE Smart_Contract SHALL halt all minting, burning, and transfer operations for that (Asset_Type, Network) until unpaused.
3. WHILE a Smart_Contract is paused, THE Backend_API SHALL reject deposit, withdrawal, and transfer requests for the corresponding (Asset_Type, Network) pair and return a descriptive error to the Frontend.
4. THE Smart_Contract for each (Asset_Type, Network) pair SHALL follow the ERC-20 standard so that token balances are queryable by standard Ethereum tooling.
5. WHEN a Bank_Operator adds a new Network, THE Backend_API SHALL support deploying Smart_Contracts for existing Asset_Types on that Network and registering the (Asset_Type, Network) → contract address entries in the Token_Registry without requiring changes to existing Smart_Contracts or existing Wallet records.
6. THE Smart_Contract SHALL be deployable to a local Hardhat network for POC demonstration purposes. Deployment to the Ethereum Sepolia testnet is supported as an optional Network configuration.

---

### Requirement 8: Off-Chain Data Consistency (Firestore)

**User Story:** As a Bank_Operator, I want all on-chain events to be reflected in Firestore, so that T-Bank has an auditable off-chain record of all tokenized deposit activity across all (Asset_Type, Network) pairs.

#### Acceptance Criteria

1. WHEN a Mint, Burn, or Transfer event is emitted by THE Smart_Contract for any (Asset_Type, Network) pair, THE Backend_API SHALL write a corresponding record to Firestore containing the Chain_Address(es) involved, Asset_Type, Network, amount, transaction hash, and timestamp.
2. THE Backend_API SHALL store each Client record in Firestore with fields for: client identifier, KYC status, Wallet record (including the Network → Chain_Address mapping), and creation timestamp.
3. THE Token_Registry SHALL be stored in Firestore as a collection mapping each (Asset_Type, Network) pair to its deployed Smart_Contract address and deployment metadata.
4. IF a Firestore write fails after an on-chain event, THEN THE Backend_API SHALL retry the write up to 3 times before logging a permanent failure.
5. THE Backend_API SHALL expose a reconciliation endpoint that compares on-chain token balances with Firestore records for each (Asset_Type, Network) pair and returns any discrepancies.

---

### Requirement 9: Optional Testnet Deployment (Sepolia)

**User Story:** As a Bank_Operator, I want the option to deploy smart contracts to Sepolia testnet, so that stakeholders can inspect and interact with the contracts publicly if needed.

#### Acceptance Criteria

1. THE deployment script SHALL support both local Hardhat and Sepolia Networks via a network flag, and SHALL accept an Asset_Type parameter to deploy the corresponding Smart_Contract.
2. WHEN deploying to Sepolia, THE Backend_API SHALL connect via an RPC provider (Alchemy or Infura) configured via environment variable.
3. WHEN deploying to Sepolia, THE Smart_Contract SHOULD be verified on Sepolia Etherscan so that the source code is publicly readable.
4. Sepolia deployment is OPTIONAL and not required for the core POC demonstration.

