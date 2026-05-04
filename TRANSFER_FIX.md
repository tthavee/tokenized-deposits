# Transfer Not Showing on Blockchain Fix

## Problem

Transfers were not showing up correctly on the Sepolia blockchain. The transactions were being executed, but they appeared as transfers from the operator's wallet rather than from the sender's wallet.

## Root Cause

The backend was using the standard ERC-20 `transfer()` function, which transfers tokens from the **caller's address** (the operator), not from the sender's address. 

```python
# OLD CODE - INCORRECT
tx = contract.functions.transfer(
    recipient_address,  # to
    amount,
).build_transaction({
    "from": operator.address,  # ← This transfers operator's tokens!
})
```

This meant:
1. The operator's balance was being reduced, not the sender's
2. On-chain, the transaction showed as: `operator → recipient`
3. The sender's balance remained unchanged
4. The transaction was technically successful but incorrect

## Solution

Added a new `operatorTransfer()` function to the smart contract that allows the owner (operator) to transfer tokens between two approved wallets on behalf of users.

### Changes Made

1. **`blockchain/contracts/DepositToken.sol`**
   - Added `operatorTransfer(from, to, amount)` function
   - Only callable by owner (operator)
   - Requires both `from` and `to` addresses to be KYC-approved
   - Respects the pause state

2. **`backend/routers/transfer.py`**
   - Updated ABI to include `operatorTransfer` and `paused` functions
   - Changed transfer call from `transfer(to, amount)` to `operatorTransfer(from, to, amount)`
   - Added pause state check before attempting transfer

### New Smart Contract Function

```solidity
/// @notice Transfer tokens between two approved wallets (owner only).
///         This allows the operator to facilitate transfers without requiring
///         users to hold private keys or sign transactions.
function operatorTransfer(
    address from,
    address to,
    uint256 amount
) external onlyOwner whenNotPaused {
    if (!_approved[from]) revert WalletNotApproved(from);
    if (!_approved[to]) revert WalletNotApproved(to);
    _transfer(from, to, amount);
}
```

## How to Deploy the Fix

### 1. Upgrade the Smart Contract

The contract uses UUPS proxy pattern, so you can upgrade without changing the contract address:

```bash
cd blockchain

# For Sepolia
npx hardhat run scripts/upgrade.ts --network sepolia

# For local Hardhat (if needed)
npx hardhat run scripts/upgrade.ts --network localhost
```

### 2. Deploy the Backend

```bash
./scripts/deploy.sh --backend-only
```

### 3. Verify the Fix

After deployment, test a transfer:

1. Go to the Transfer screen in the app
2. Select sender, recipient, asset type, network, and amount
3. Submit the transfer
4. Check the transaction on Sepolia Etherscan
5. Verify that the transaction shows: `sender_address → recipient_address` (not operator → recipient)

You can also verify the transaction hash in Etherscan:
```
https://sepolia.etherscan.io/tx/{transaction_hash}
```

## Architecture Note

This design follows the custodial model where:
- Users don't hold private keys
- The operator (backend) manages all on-chain transactions
- Users are identified by their KYC-approved wallet addresses
- The operator acts as a trusted intermediary for all token operations (mint, burn, transfer)

The `operatorTransfer` function maintains this model while ensuring that transfers correctly deduct from the sender's balance and credit the recipient's balance, with the transaction appearing on-chain as a transfer between the two user addresses.

## Testing

The existing tests will need to be updated to use the new `operatorTransfer` function. The test files that need updating:
- `backend/tests/test_transfer_endpoint.py`
- `backend/tests/test_properties.py` (if it tests transfers)

Run tests after updating:
```bash
cd backend
venv/bin/python -m pytest tests/test_transfer_endpoint.py -v
```
