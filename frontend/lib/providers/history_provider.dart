import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../models/transaction_entry.dart';

final transactionsProvider =
    FutureProvider.autoDispose.family<List<TransactionEntry>, String>(
        (ref, clientId) async {
  final list = await ref.watch(apiClientProvider).getTransactions(clientId);
  return list
      .map((e) => TransactionEntry.fromJson(e as Map<String, dynamic>))
      .toList()
    ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
});
