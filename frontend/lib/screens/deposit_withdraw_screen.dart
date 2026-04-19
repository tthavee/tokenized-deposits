import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../models/balance_entry.dart';
import '../providers/deposit_withdraw_provider.dart';

class DepositWithdrawScreen extends ConsumerStatefulWidget {
  const DepositWithdrawScreen({super.key});

  @override
  ConsumerState<DepositWithdrawScreen> createState() =>
      _DepositWithdrawScreenState();
}

class _DepositWithdrawScreenState
    extends ConsumerState<DepositWithdrawScreen> {
  final _formKey = GlobalKey<FormState>();
  final _amountCtrl = TextEditingController();
  String? _selectedAssetType;
  String? _selectedNetwork;
  String _txType = 'deposit';

  @override
  void dispose() {
    _amountCtrl.dispose();
    super.dispose();
  }

  void _submit(String clientId) {
    if (!_formKey.currentState!.validate()) return;
    final amount = int.parse(_amountCtrl.text.trim());
    final assetType = _selectedAssetType!;
    final network = _selectedNetwork!;
    if (_txType == 'deposit') {
      ref.read(txProvider.notifier).deposit(
            clientId: clientId,
            amount: amount,
            assetType: assetType,
            network: network,
          );
    } else {
      ref.read(txProvider.notifier).withdraw(
            clientId: clientId,
            amount: amount,
            assetType: assetType,
            network: network,
          );
    }
  }

  @override
  Widget build(BuildContext context) {
    // Route args take precedence (tests); fall back to global session provider.
    final clientId = (ModalRoute.of(context)?.settings.arguments as String?)
        ?? ref.watch(currentClientIdProvider);

    if (clientId == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Deposit / Withdraw')),
        body: const Center(
          child: Text('No client ID. Please complete KYC first.'),
        ),
      );
    }

    final isLoading = ref.watch(txProvider) is TxLoading;
    final balancesAsync = ref.watch(balancesProvider(clientId));

    // Derive selector options from loaded balances (preserved across reloads via
    // Riverpod's AsyncLoading.valueOrNull returning previous data).
    final balances = balancesAsync.valueOrNull ?? [];
    final assetTypes = balances.map((b) => b.assetType).toSet().toList()
      ..sort();
    final networks = balances
        .where((b) =>
            _selectedAssetType == null || b.assetType == _selectedAssetType)
        .map((b) => b.network)
        .toSet()
        .toList()
      ..sort();

    ref.listen<TxState>(txProvider, (_, next) {
      switch (next) {
        case TxSuccess(:final transactionId):
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Transaction confirmed: $transactionId')),
          );
          ref.read(txProvider.notifier).reset();
          ref.invalidate(balancesProvider(clientId));
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
      appBar: AppBar(title: const Text('Deposit / Withdraw')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Balances', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            balancesAsync.when(
              data: (balances) => balances.isEmpty
                  ? const Text('No balances found.')
                  : Column(
                      children:
                          balances.map((b) => _BalanceRow(entry: b)).toList(),
                    ),
              loading: () =>
                  const Center(child: CircularProgressIndicator()),
              error: (e, _) => Text('Failed to load balances: $e'),
            ),
            const Divider(height: 40),
            SegmentedButton<String>(
              key: const Key('txTypeToggle'),
              segments: const [
                ButtonSegment(value: 'deposit', label: Text('Deposit')),
                ButtonSegment(value: 'withdraw', label: Text('Withdraw')),
              ],
              selected: {_txType},
              onSelectionChanged: (v) =>
                  setState(() => _txType = v.first),
            ),
            const SizedBox(height: 16),
            Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
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
                        .map((t) =>
                            DropdownMenuItem(value: t, child: Text(t)))
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
                        .map((n) =>
                            DropdownMenuItem(value: n, child: Text(n)))
                        .toList(),
                    onChanged: _selectedAssetType == null
                        ? null
                        : (v) => setState(() => _selectedNetwork = v),
                    validator: (v) => v == null ? 'Required' : null,
                  ),
                  const SizedBox(height: 32),
                  FilledButton(
                    key: const Key('submitButton'),
                    onPressed: isLoading ? null : () => _submit(clientId),
                    child: isLoading
                        ? const SizedBox.square(
                            dimension: 20,
                            child:
                                CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(_txType == 'deposit' ? 'Deposit' : 'Withdraw'),
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
