import 'dart:js_interop';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../models/balance_entry.dart';
import '../providers/deposit_withdraw_provider.dart';
import '../services/session_service.dart';

@JS('window.open')
external void _windowOpen(String url, String target);

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final clientId = ref.watch(currentClientIdProvider);
    final wallet = ref.watch(currentWalletProvider);

    if (clientId == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        Navigator.of(context).pushReplacementNamed('/login');
      });
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final balancesAsync = ref.watch(balancesProvider(clientId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Dashboard'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Refresh',
            onPressed: () => ref.invalidate(balancesProvider(clientId)),
          ),
          IconButton(
            icon: const Icon(Icons.menu),
            tooltip: 'More options',
            onPressed: () => Navigator.of(context).pushNamed('/menu'),
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
            onPressed: () async {
              await SessionService.clear();
              ref.read(currentClientIdProvider.notifier).state = null;
              ref.read(currentWalletProvider.notifier).state = null;
              if (context.mounted) {
                Navigator.of(context).pushReplacementNamed('/login');
              }
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(balancesProvider(clientId)),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // ----------------------------------------------------------------
            // Wallets
            // ----------------------------------------------------------------
            const _SectionHeader(icon: Icons.account_balance_wallet, title: 'My Wallets'),
            if (wallet == null || wallet.addresses.isEmpty)
              const _EmptyCard(message: 'No wallet found. Use New Wallet & KYC from the menu.')
            else
              ...wallet.addresses.entries.map(
                (e) => _WalletCard(network: e.key, address: e.value),
              ),

            const SizedBox(height: 24),

            // ----------------------------------------------------------------
            // Token balances
            // ----------------------------------------------------------------
            const _SectionHeader(icon: Icons.token, title: 'Token Balances'),
            balancesAsync.when(
              data: (balances) {
                if (balances.isEmpty) {
                  return const _EmptyCard(message: 'No token balances found.');
                }
                return Column(
                  children: balances.map((b) => _BalanceCard(entry: b)).toList(),
                );
              },
              loading: () => const Padding(
                padding: EdgeInsets.symmetric(vertical: 24),
                child: Center(child: CircularProgressIndicator()),
              ),
              error: (e, _) => _EmptyCard(message: 'Could not load balances: $e'),
            ),

            const SizedBox(height: 24),

            // ----------------------------------------------------------------
            // Quick actions
            // ----------------------------------------------------------------
            const _SectionHeader(icon: Icons.flash_on, title: 'Quick Actions'),
            Row(
              children: [
                Expanded(
                  child: _ActionCard(
                    icon: Icons.swap_horiz,
                    label: 'Deposit / Withdraw',
                    onTap: () => Navigator.of(context).pushNamed('/deposit-withdraw'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _ActionCard(
                    icon: Icons.history,
                    label: 'Transaction History',
                    onTap: () => Navigator.of(context).pushNamed('/history'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Section header
// ---------------------------------------------------------------------------

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.icon, required this.title});

  final IconData icon;
  final String title;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(width: 8),
          Text(
            title,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text(message),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Wallet address card
// ---------------------------------------------------------------------------

class _WalletCard extends StatelessWidget {
  const _WalletCard({required this.network, required this.address});

  final String network;
  final String address;

  String get _label {
    switch (network) {
      case 'sepolia':
        return 'Sepolia Testnet';
      case 'hardhat':
        return 'Hardhat (Local)';
      default:
        return '${network[0].toUpperCase()}${network.substring(1)}';
    }
  }

  Color _networkColor(BuildContext context) {
    switch (network) {
      case 'sepolia':
        return Colors.blue;
      case 'hardhat':
        return Colors.grey;
      default:
        return Theme.of(context).colorScheme.primary;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.circle, size: 10, color: _networkColor(context)),
                const SizedBox(width: 8),
                Text(
                  _label,
                  style: Theme.of(context)
                      .textTheme
                      .titleSmall
                      ?.copyWith(fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  child: SelectableText(
                    address,
                    style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.copy, size: 16),
                  tooltip: 'Copy address',
                  onPressed: () {
                    Clipboard.setData(ClipboardData(text: address));
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('Address copied to clipboard'),
                        duration: Duration(seconds: 1),
                      ),
                    );
                  },
                ),
              ],
            ),
            if (network == 'sepolia-xxxx') ...[
              const SizedBox(height: 4),
              _EtherscanLink(
                label: 'View wallet on Etherscan',
                url: 'https://sepolia.etherscan.io/address/$address#tokentxns',
                icon: Icons.open_in_new,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Balance card
// ---------------------------------------------------------------------------

class _BalanceCard extends StatelessWidget {
  const _BalanceCard({required this.entry});

  final BalanceEntry entry;

  bool get _hasSepolia => entry.network == 'sepolia';

  String get _networkLabel =>
      '${entry.network[0].toUpperCase()}${entry.network.substring(1)}';

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final hasContract = _hasSepolia && entry.contractAddress != null;

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Asset + network label
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      entry.assetType,
                      style: Theme.of(context)
                          .textTheme
                          .titleSmall
                          ?.copyWith(fontWeight: FontWeight.bold),
                    ),
                    Text(
                      _networkLabel,
                      style: Theme.of(context)
                          .textTheme
                          .bodySmall
                          ?.copyWith(color: colorScheme.secondary),
                    ),
                  ],
                ),
                // Balance or error chip
                if (entry.error != null)
                  Chip(
                    label: Text(
                      'Unavailable',
                      style: TextStyle(color: colorScheme.error, fontSize: 11),
                    ),
                    backgroundColor: colorScheme.errorContainer,
                    padding: EdgeInsets.zero,
                    visualDensity: VisualDensity.compact,
                  )
                else
                  Text(
                    '${entry.balance}',
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: colorScheme.primary,
                        ),
                  ),
              ],
            ),

            if (entry.error != null) ...[
              const SizedBox(height: 4),
              Text(
                entry.error!,
                style: TextStyle(color: colorScheme.error, fontSize: 12),
              ),
            ],

            if (hasContract) ...[
              const Divider(height: 20),
              Wrap(
                spacing: 20,
                runSpacing: 8,
                children: [
                  _EtherscanLink(
                    label: 'My Wallet',
                    url:
                        'https://sepolia.etherscan.io/token/${entry.contractAddress}?a=${entry.chainAddress}',
                    icon: Icons.person_search,
                  ),
                  _EtherscanLink(
                    label: 'All wallets',
                    url:
                        'https://sepolia.etherscan.io/token/${entry.contractAddress}#balances',
                    icon: Icons.description,
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Etherscan link widget
// ---------------------------------------------------------------------------

class _EtherscanLink extends StatelessWidget {
  const _EtherscanLink({
    required this.label,
    required this.url,
    this.icon,
  });

  final String label;
  final String url;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return InkWell(
      onTap: () => _windowOpen(url, '_blank'),
      borderRadius: BorderRadius.circular(4),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[
              Icon(icon, size: 14, color: color),
              const SizedBox(width: 4),
            ],
            Text(
              label,
              style: TextStyle(
                color: color,
                decoration: TextDecoration.underline,
                decorationColor: color,
                fontSize: 13,
              ),
            ),
            const SizedBox(width: 3),
            Icon(Icons.open_in_new, size: 12, color: color),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Quick action card
// ---------------------------------------------------------------------------

class _ActionCard extends StatelessWidget {
  const _ActionCard({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.hardEdge,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 12),
          child: Column(
            children: [
              Icon(icon, size: 30, color: Theme.of(context).colorScheme.primary),
              const SizedBox(height: 8),
              Text(
                label,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
