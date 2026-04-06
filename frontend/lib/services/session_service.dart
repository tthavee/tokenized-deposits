import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/wallet.dart';

/// Persists the active client session to device storage so it survives
/// app restarts and browser refreshes.
class SessionService {
  static const _kClientId = 'session_client_id';
  static const _kWalletJson = 'session_wallet';

  /// Returns the saved client ID, or null if no session exists.
  static Future<String?> loadClientId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_kClientId);
  }

  /// Returns the saved wallet, or null if no session exists.
  static Future<Wallet?> loadWallet() async {
    final prefs = await SharedPreferences.getInstance();
    final json = prefs.getString(_kWalletJson);
    if (json == null) return null;
    return Wallet.fromJson(jsonDecode(json) as Map<String, dynamic>);
  }

  /// Persists the client ID and wallet after a successful KYC + wallet flow.
  static Future<void> save(String clientId, Wallet wallet) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kClientId, clientId);
    await prefs.setString(
      _kWalletJson,
      jsonEncode({'client_id': wallet.clientId, 'wallet': wallet.addresses}),
    );
  }

  /// Removes all session data.
  static Future<void> clear() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kClientId);
    await prefs.remove(_kWalletJson);
  }
}
