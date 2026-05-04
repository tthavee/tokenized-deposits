// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/token/ERC20/ERC20Upgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/PausableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";

/// @title DepositToken
/// @notice ERC-20 token representing fiat deposits for a specific (assetType, network) pair.
///         Deployed behind a UUPS proxy so the logic can be upgraded without changing the
///         contract address or losing any stored balances.
contract DepositToken is
    Initializable,
    ERC20Upgradeable,
    OwnableUpgradeable,
    PausableUpgradeable,
    UUPSUpgradeable
{
    string public assetType;
    string public networkLabel;

    mapping(address => bool) private _approved;

    event Mint(address indexed recipient, uint256 amount);
    event Burn(address indexed source, uint256 amount);
    event WalletRegistered(address indexed wallet);
    event WalletRevoked(address indexed wallet);

    error WalletNotApproved(address wallet);

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /// @notice Replaces the constructor — called once by the proxy on first deployment.
    function initialize(
        string memory _assetType,
        string memory _networkLabel,
        address _owner
    ) public initializer {
        __ERC20_init(
            string.concat(_assetType, " Deposit Token"),
            string.concat(_assetType, "D")
        );
        __Ownable_init(_owner);
        __Pausable_init();
        assetType = _assetType;
        networkLabel = _networkLabel;
    }

    /// @notice Required by UUPS — restricts upgrades to the owner.
    function _authorizeUpgrade(address) internal override onlyOwner {}

    /// @notice Add a wallet to the KYC allowlist.
    function registerWallet(address wallet) external onlyOwner {
        _approved[wallet] = true;
        emit WalletRegistered(wallet);
    }

    /// @notice Remove a wallet from the KYC allowlist.
    function revokeWallet(address wallet) external onlyOwner {
        _approved[wallet] = false;
        emit WalletRevoked(wallet);
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

    /// @dev Blocks transfers to addresses not in the KYC allowlist.
    ///      Burns (to == address(0)) and mints (from == address(0)) are unaffected.
    function _update(address from, address to, uint256 value) internal override {
        require(to == address(0) || _approved[to], "Recipient not KYC-approved");
        super._update(from, to, value);
    }
}
