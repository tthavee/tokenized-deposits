import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../models/client.dart';
import '../models/wallet.dart';
import '../services/api_client.dart';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

sealed class KycState {
  const KycState();
}

class KycIdle extends KycState {
  const KycIdle();
}

class KycLoading extends KycState {
  const KycLoading();
}

class KycSuccess extends KycState {
  const KycSuccess(this.client, this.wallet);
  final Client client;
  final Wallet wallet;
}

class KycError extends KycState {
  const KycError(this.message);
  final String message;
}

// ---------------------------------------------------------------------------
// Notifier
// ---------------------------------------------------------------------------

class KycNotifier extends StateNotifier<KycState> {
  KycNotifier(this._api) : super(const KycIdle());

  final ApiClient _api;

  /// Run KYC and, on approval, immediately create the client wallet.
  Future<void> submit({
    required String firstName,
    required String lastName,
    required String dateOfBirth,
    required String nationalId,
    required String password,
  }) async {
    state = const KycLoading();
    try {
      final clientJson = await _api.createClient(
        firstName: firstName,
        lastName: lastName,
        dateOfBirth: dateOfBirth,
        nationalId: nationalId,
        password: password,
      );
      final client = Client.fromJson(clientJson);

      final walletJson = await _api.createWallet(client.id);
      final wallet = Wallet.fromJson(walletJson);

      state = KycSuccess(client, wallet);
    } on ApiException catch (e) {
      state = KycError(e.detail);
    } catch (e) {
      state = KycError(e.toString());
    }
  }

  void reset() => state = const KycIdle();
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

final kycProvider = StateNotifierProvider<KycNotifier, KycState>(
  (ref) => KycNotifier(ref.watch(apiClientProvider)),
);
