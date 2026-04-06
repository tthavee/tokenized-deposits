import 'package:flutter/material.dart';

import '../models/wallet.dart';

class WalletScreen extends StatelessWidget {
  const WalletScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final wallet = ModalRoute.of(context)?.settings.arguments as Wallet?;

    if (wallet == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Wallet')),
        body: const Center(
          child: Text('No wallet data. Please complete KYC first.'),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Wallet')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'Client ID: ${wallet.clientId}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 16),
          ...wallet.addresses.entries.map(
            (e) => _NetworkCard(network: e.key, address: e.value),
          ),
        ],
      ),
    );
  }
}

class _NetworkCard extends StatelessWidget {
  const _NetworkCard({required this.network, required this.address});

  final String network;
  final String address;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              network.toUpperCase(),
              style: Theme.of(context).textTheme.labelLarge,
            ),
            const SizedBox(height: 8),
            SelectableText(
              address,
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(fontFamily: 'monospace'),
            ),
          ],
        ),
      ),
    );
  }
}
