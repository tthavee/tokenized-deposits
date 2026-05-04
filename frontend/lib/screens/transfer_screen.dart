import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../models/balance_entry.dart';
import '../providers/deposit_withdraw_provider.dart';

class TransferScreen extends ConsumerStatefulWidget {
  const TransferScreen({super.key});

  @override
  ConsumerState<TransferScreen> createState() => _TransferScreenState();
}

class _TransferScreenState extends ConsumerState<TransferScreen> {
  final _formKey = GlobalKey<FormState>();
  final _recipientCtrl = TextEditingController();
  final _amountCtrl = TextEditingController();
  String? _selectedAssetType;
  String? _selectedNetwork;

  @override
  void dispose() {
    _recipientCtrl.dispose();
    _amountCtrl.dispose();
    super.dispose();
  }

  void _submit(String clientId) {
    if (!_formKey.currentState!.validate()) return;
    ref.read(txProvider.notifier).transfer(
          senderId: clientId,
          recipientId: _recipientCtrl.text.trim(),
          amount: int.parse(_amountCtrl.text.trim()),
          assetType: _selectedAssetType!,
          network: _selectedNetwork!,
        );
  }

  @override
  Widget build(BuildContext context) {
    final clientId = (ModalRoute.of(context)?.settings.arguments as String?)
        ?? ref.watch(currentClientIdProvider);

    if (clientId == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Transfer')),
        body: const Center(
          child: Text('No client ID. Please complete KYC first.'),
        ),
      );
    }

    final isLoading = ref.watch(txProvider) is TxLoading;
    final balancesAsync = ref.watch(balancesProvider(clientId));

    final balances = balancesAsync.valueOrNull ?? [];
    final assetTypes = balances.map((b) => b.assetType).toSet().toList()..sort();
    final networks = balances
        .where((b) => _selectedAssetType == null || b.assetType == _selectedAssetType)
        .map((b) => b.network)
        .toSet()
        .toList()
      ..sort();

    ref.listen<AsyncValue<List<BalanceEntry>>>(balancesProvider(clientId), (_, next) {
      if (_selectedAssetType != null) return;
      final loaded = next.valueOrNull;
      if (loaded == null || loaded.isEmpty) return;
      final availableAssets = loaded.map((b) => b.assetType).toSet();
      final defaultAsset =
          availableAssets.contains('USDD') ? 'USDD' : availableAssets.first;
      final availableNetworks = loaded
          .where((b) => b.assetType == defaultAsset)
          .map((b) => b.network)
          .toSet();
      final defaultNetwork = availableNetworks.contains('sepolia')
          ? 'sepolia'
          : availableNetworks.first;
      setState(() {
        _selectedAssetType = defaultAsset;
        _selectedNetwork = defaultNetwork;
      });
    });

    ref.listen<TxState>(txProvider, (_, next) {
      switch (next) {
        case TxSuccess(:final transactionId):
          ref.read(txProvider.notifier).reset();
          ref.invalidate(balancesProvider(clientId));
          showDialog(
            context: context,
            builder: (_) => _TransferSuccessDialog(transactionId: transactionId),
          );
        case TxError(:final message):
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Error: $message'),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
          ref.read(txProvider.notifier).reset();
        default:
          break;
      }
    });

    return Scaffold(
      appBar: AppBar(title: const Text('Transfer')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Your Balances', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            balancesAsync.when(
              data: (bs) => bs.isEmpty
                  ? const Text('No balances found.')
                  : Column(children: bs.map((b) => _BalanceRow(entry: b)).toList()),
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Text('Failed to load balances: $e'),
            ),
            const Divider(height: 40),
            Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextFormField(
                    key: const Key('recipientIdField'),
                    controller: _recipientCtrl,
                    decoration: const InputDecoration(labelText: 'Recipient ID'),
                    validator: (v) =>
                        (v == null || v.trim().isEmpty) ? 'Required' : null,
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    key: const Key('amountField'),
                    controller: _amountCtrl,
                    decoration: const InputDecoration(labelText: 'Amount'),
                    keyboardType: TextInputType.number,
                    validator: (v) {
                      if (v == null || v.trim().isEmpty) return 'Required';
                      final parsed = int.tryParse(v.trim());
                      if (parsed == null || parsed <= 0) {
                        return 'Enter a positive integer';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    key: const Key('assetTypeField'),
                    decoration: const InputDecoration(labelText: 'Asset type'),
                    initialValue: _selectedAssetType,
                    hint: const Text('Select asset type'),
                    items: assetTypes
                        .map((t) => DropdownMenuItem(value: t, child: Text(t)))
                        .toList(),
                    onChanged: (v) => setState(() {
                      _selectedAssetType = v;
                      _selectedNetwork = null;
                    }),
                    validator: (v) => v == null ? 'Required' : null,
                  ),
                  const SizedBox(height: 16),
                  DropdownButtonFormField<String>(
                    key: const Key('networkField'),
                    decoration: const InputDecoration(labelText: 'Network'),
                    initialValue: _selectedNetwork,
                    hint: const Text('Select network'),
                    items: networks
                        .map((n) => DropdownMenuItem(value: n, child: Text(n)))
                        .toList(),
                    onChanged: _selectedAssetType == null
                        ? null
                        : (v) => setState(() => _selectedNetwork = v),
                    validator: (v) => v == null ? 'Required' : null,
                  ),
                  const SizedBox(height: 24),
                  FilledButton(
                    key: const Key('submitButton'),
                    onPressed: isLoading ? null : () => _submit(clientId),
                    child: isLoading
                        ? const SizedBox.square(
                            dimension: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Transfer'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TransferSuccessDialog extends StatelessWidget {
  const _TransferSuccessDialog({required this.transactionId});

  final String transactionId;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Transfer Confirmed'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Your transfer was submitted successfully.'),
          const SizedBox(height: 12),
          Text(
            'TX ID: ${transactionId.length > 8 ? '${transactionId.substring(0, 8)}…' : transactionId}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('OK'),
        ),
      ],
    );
  }
}

class _BalanceRow extends StatelessWidget {
  const _BalanceRow({required this.entry});

  final BalanceEntry entry;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text('${entry.assetType} (${entry.network})'),
          if (entry.error != null)
            Text(
              entry.error!,
              style: TextStyle(
                color: Theme.of(context).colorScheme.error,
                fontStyle: FontStyle.italic,
                fontSize: 12,
              ),
            )
          else
            Text(
              entry.balance.toString(),
              key: Key('balance_${entry.assetType}_${entry.network}'),
              style: Theme.of(context).textTheme.bodyLarge,
            ),
        ],
      ),
    );
  }
}
