import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../models/transaction_entry.dart';
import '../providers/history_provider.dart';

class HistoryScreen extends ConsumerWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final clientId = (ModalRoute.of(context)?.settings.arguments as String?)
        ?? ref.watch(currentClientIdProvider);

    if (clientId == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Transaction History')),
        body: const Center(child: Text('No client ID. Please complete KYC first.')),
      );
    }

    final txAsync = ref.watch(transactionsProvider(clientId));

    return Scaffold(
      appBar: AppBar(title: const Text('Transaction History')),
      body: txAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Failed to load transactions: $e')),
        data: (txs) => RefreshIndicator(
          onRefresh: () => ref.refresh(transactionsProvider(clientId).future),
          child: txs.isEmpty
              ? const SingleChildScrollView(
                  physics: AlwaysScrollableScrollPhysics(),
                  child: SizedBox(
                    height: 300,
                    child: Center(
                      key: Key('emptyState'),
                      child: Text('No transactions yet.'),
                    ),
                  ),
                )
              : ListView.separated(
                  physics: const AlwaysScrollableScrollPhysics(),
                  itemCount: txs.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, i) => _TxTile(tx: txs[i]),
                ),
        ),
      ),
    );
  }
}

String _shortAddr(String addr) =>
    addr.length > 12 ? '${addr.substring(0, 6)}…${addr.substring(addr.length - 4)}' : addr;

class _TxTile extends StatelessWidget {
  const _TxTile({required this.tx});

  final TransactionEntry tx;

  @override
  Widget build(BuildContext context) {
    final isDeposit = tx.type == 'deposit';
    return ListTile(
      key: Key('tx_${tx.id}'),
      leading: Icon(
        isDeposit ? Icons.arrow_downward : Icons.arrow_upward,
        color: isDeposit ? Colors.green : Colors.red,
      ),
      title: Text(
        '${isDeposit ? 'Deposit' : 'Withdrawal'} — ${tx.assetType} (${tx.network})',
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(tx.createdAt.length > 10 ? tx.createdAt.substring(0, 10) : tx.createdAt),
          if (tx.contractAddress != null)
            Text(
              _shortAddr(tx.contractAddress!),
              style: const TextStyle(fontSize: 11, fontFamily: 'monospace'),
            ),
        ],
      ),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(
            '${tx.amount}',
            key: Key('amount_${tx.id}'),
            style: Theme.of(context).textTheme.bodyLarge,
          ),
          Text(
            tx.status,
            key: Key('status_${tx.id}'),
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
