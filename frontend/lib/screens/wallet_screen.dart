import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../models/wallet.dart';
import '../services/api_client.dart';
import '../services/session_service.dart';

class WalletScreen extends ConsumerStatefulWidget {
  const WalletScreen({super.key});

  @override
  ConsumerState<WalletScreen> createState() => _WalletScreenState();
}

class _WalletScreenState extends ConsumerState<WalletScreen> {
  bool _isCreating = false;
  String? _error;

  Future<void> _createWallet(String clientId) async {
    setState(() {
      _isCreating = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final json = await api.createWallet(clientId);
      final wallet = Wallet.fromJson(json);
      ref.read(currentWalletProvider.notifier).state = wallet;
      SessionService.save(clientId, wallet);
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _isCreating = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    // Route args take precedence (direct navigation from KYC); fall back to
    // global session provider (navigated from home after KYC was done).
    final wallet = (ModalRoute.of(context)?.settings.arguments as Wallet?)
        ?? ref.watch(currentWalletProvider);
    final clientId = ref.watch(currentClientIdProvider);

    if (wallet == null && clientId == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Wallet')),
        body: const Center(
          child: Text('No wallet data. Please complete KYC first.'),
        ),
      );
    }

    // Have a clientId but no wallet yet — offer to create one.
    if (wallet == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Wallet')),
        body: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'No wallet has been created yet for this account.',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(
                  _error!,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 32),
              FilledButton(
                key: const Key('createWalletButton'),
                onPressed: _isCreating ? null : () => _createWallet(clientId!),
                child: _isCreating
                    ? const SizedBox.square(
                        dimension: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Create Wallet'),
              ),
            ],
          ),
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
