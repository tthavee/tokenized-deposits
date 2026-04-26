import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../models/balance_entry.dart';
import '../services/api_client.dart';

// ---------------------------------------------------------------------------
// Transaction action state
// ---------------------------------------------------------------------------

sealed class TxState {
  const TxState();
}

class TxIdle extends TxState {
  const TxIdle();
}

class TxLoading extends TxState {
  const TxLoading();
}

class TxSuccess extends TxState {
  const TxSuccess(this.transactionId, {this.gasUsed, this.gasPriceGwei, this.feeEth});
  final String transactionId;
  final int? gasUsed;
  final double? gasPriceGwei;
  final double? feeEth;
}

class TxError extends TxState {
  const TxError(this.message);
  final String message;
}

// ---------------------------------------------------------------------------
// Notifier
// ---------------------------------------------------------------------------

class TxNotifier extends StateNotifier<TxState> {
  TxNotifier(this._api) : super(const TxIdle());

  final ApiClient _api;

  Future<void> deposit({
    required String clientId,
    required int amount,
    required String assetType,
    required String network,
  }) async {
    state = const TxLoading();
    try {
      final result = await _api.deposit(
        clientId: clientId,
        amount: amount,
        assetType: assetType,
        network: network,
      );
      state = TxSuccess(
        result['transaction_id'] as String,
        gasUsed: result['gas_used'] as int?,
        gasPriceGwei: (result['gas_price_gwei'] as num?)?.toDouble(),
        feeEth: (result['fee_eth'] as num?)?.toDouble(),
      );
    } on ApiException catch (e) {
      state = TxError(e.detail);
    } catch (e) {
      state = TxError(e.toString());
    }
  }

  Future<void> withdraw({
    required String clientId,
    required int amount,
    required String assetType,
    required String network,
  }) async {
    state = const TxLoading();
    try {
      final result = await _api.withdraw(
        clientId: clientId,
        amount: amount,
        assetType: assetType,
        network: network,
      );
      state = TxSuccess(
        result['transaction_id'] as String,
        gasUsed: result['gas_used'] as int?,
        gasPriceGwei: (result['gas_price_gwei'] as num?)?.toDouble(),
        feeEth: (result['fee_eth'] as num?)?.toDouble(),
      );
    } on ApiException catch (e) {
      state = TxError(e.detail);
    } catch (e) {
      state = TxError(e.toString());
    }
  }

  void reset() => state = const TxIdle();
}

// ---------------------------------------------------------------------------
// Providers
// ---------------------------------------------------------------------------

final txProvider = StateNotifierProvider<TxNotifier, TxState>(
  (ref) => TxNotifier(ref.watch(apiClientProvider)),
);

final balancesProvider =
    FutureProvider.family<List<BalanceEntry>, String>((ref, clientId) async {
  final list = await ref.watch(apiClientProvider).getBalances(clientId);
  return list
      .map((e) => BalanceEntry.fromJson(e as Map<String, dynamic>))
      .toList();
});
