// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/// @title DepositToken
/// @notice ERC-20 token representing fiat deposits for a specific (assetType, network) pair.
///         T-Bank can mint and burn tokens for KYC-approved wallets only.
contract DepositToken is ERC20, Ownable, Pausable {
    string public assetType;
    string public networkLabel;

    mapping(address => bool) private _approved;

    event Mint(address indexed recipient, uint256 amount);
    event Burn(address indexed source, uint256 amount);

    error WalletNotApproved(address wallet);

    constructor(
        string memory _assetType,
        string memory _networkLabel
    )
        ERC20(
            string.concat(_assetType, " Deposit Token"),
            string.concat(_assetType, "D")
        )
        Ownable(msg.sender)
    {
        assetType = _assetType;
        networkLabel = _networkLabel;
    }

    /// @notice Add a wallet to the KYC allowlist.
    function registerWallet(address wallet) external onlyOwner {
        _approved[wallet] = true;
    }

    /// @notice Remove a wallet from the KYC allowlist.
    function revokeWallet(address wallet) external onlyOwner {
        _approved[wallet] = false;
    }

    /// @notice Returns true if the wallet is in the KYC allowlist.
    function isApproved(address wallet) external view returns (bool) {
        return _approved[wallet];
    }

    /// @notice Pause the contract (owner only). Blocks mint and burn.
    function pause() external onlyOwner {
        _pause();
    }

    /// @notice Unpause the contract (owner only).
    function unpause() external onlyOwner {
        _unpause();
    }

    /// @notice Mint tokens to an approved wallet. Reverts if paused or wallet not approved.
    function mint(address to, uint256 amount) external onlyOwner whenNotPaused {
        if (!_approved[to]) revert WalletNotApproved(to);
        _mint(to, amount);
        emit Mint(to, amount);
    }

    /// @notice Burn tokens from an approved wallet. Reverts if paused or wallet not approved.
    function burn(address from, uint256 amount) external onlyOwner whenNotPaused {
        if (!_approved[from]) revert WalletNotApproved(from);
        _burn(from, amount);
        emit Burn(from, amount);
    }
}
