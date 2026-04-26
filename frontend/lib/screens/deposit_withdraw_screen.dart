import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../models/balance_entry.dart';
import '../providers/deposit_withdraw_provider.dart';
import '../services/api_client.dart';

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
  Map<String, dynamic>? _gasEstimate;
  bool _gasLoading = false;

  @override
  void dispose() {
    _amountCtrl.dispose();
    super.dispose();
  }

  Future<void> _fetchGasEstimate(String network) async {
    setState(() { _gasLoading = true; _gasEstimate = null; });
    try {
      final estimate = await ApiClient().getGasEstimate(network);
      if (mounted) setState(() => _gasEstimate = estimate);
    } catch (_) {
      if (mounted) setState(() => _gasEstimate = null);
    } finally {
      if (mounted) setState(() => _gasLoading = false);
    }
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

    // Auto-select defaults when balances first arrive.
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
      _fetchGasEstimate(defaultNetwork);
    });

    ref.listen<TxState>(txProvider, (_, next) {
      switch (next) {
        case TxSuccess(:final transactionId, :final gasUsed, :final gasPriceGwei, :final feeEth):
          ref.read(txProvider.notifier).reset();
          ref.invalidate(balancesProvider(clientId));
          showDialog(
            context: context,
            builder: (_) => _TxReceiptDialog(
              transactionId: transactionId,
              gasUsed: gasUsed,
              gasPriceGwei: gasPriceGwei,
              feeEth: feeEth,
            ),
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
                    key: ValueKey('assetTypeField_$_selectedAssetType'),
                    decoration: const InputDecoration(labelText: 'Asset type'),
                    initialValue: _selectedAssetType,
                    hint: const Text('Select asset type'),
                    items: assetTypes
                        .map((t) => DropdownMenuItem(
                              value: t,
                              child: Text(t),
                            ))
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
                        : (v) {
                            setState(() => _selectedNetwork = v);
                            if (v != null) _fetchGasEstimate(v);
                          },
                    validator: (v) => v == null ? 'Required' : null,
                  ),
                  const SizedBox(height: 16),
                  if (_gasLoading)
                    const Center(child: CircularProgressIndicator(strokeWidth: 2))
                  else if (_gasEstimate != null)
                    _GasEstimateCard(estimate: _gasEstimate!),
                  const SizedBox(height: 16),
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

class _TxReceiptDialog extends StatelessWidget {
  const _TxReceiptDialog({
    required this.transactionId,
    this.gasUsed,
    this.gasPriceGwei,
    this.feeEth,
  });

  final String transactionId;
  final int? gasUsed;
  final double? gasPriceGwei;
  final double? feeEth;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Transaction Confirmed'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _GasRow('TX ID', '${transactionId.substring(0, 8)}…'),
          const Divider(height: 16),
          if (gasUsed != null) _GasRow('Gas used', '$gasUsed'),
          if (gasPriceGwei != null)
            _GasRow('Gas price', '${gasPriceGwei!.toStringAsFixed(2)} Gwei'),
          if (feeEth != null)
            _GasRow('Fee paid', '${feeEth!.toStringAsFixed(8)} ETH', bold: true),
          if (gasUsed == null)
            const Text('Gas info unavailable (tx still pending)'),
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

class _GasEstimateCard extends StatelessWidget {
  const _GasEstimateCard({required this.estimate});

  final Map<String, dynamic> estimate;

  @override
  Widget build(BuildContext context) {
    final baseFee = (estimate['base_fee_gwei'] as num).toStringAsFixed(2);
    final priorityFee = (estimate['priority_fee_gwei'] as num).toStringAsFixed(2);
    final feeEth = (estimate['estimated_fee_eth'] as num).toStringAsFixed(8);
    final gasLimit = estimate['gas_limit'];

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Estimated Gas Fee', style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: 8),
            _GasRow('Base fee', '$baseFee Gwei'),
            _GasRow('Priority fee', '$priorityFee Gwei'),
            _GasRow('Gas limit', '$gasLimit'),
            const Divider(height: 12),
            _GasRow('Estimated fee', '$feeEth ETH', bold: true),
          ],
        ),
      ),
    );
  }
}

class _GasRow extends StatelessWidget {
  const _GasRow(this.label, this.value, {this.bold = false});

  final String label;
  final String value;
  final bool bold;

  @override
  Widget build(BuildContext context) {
    final style = bold ? const TextStyle(fontWeight: FontWeight.bold) : null;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: style),
          Text(value, style: style),
        ],
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
