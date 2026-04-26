import 'dart:convert';
import 'package:http/http.dart' as http;
import '../config/app_config.dart';

/// Thin HTTP wrapper around the Tokenized Deposits backend API.
class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  final String _base = AppConfig.baseApiUrl;

  // -------------------------------------------------------------------------
  // Clients / KYC
  // -------------------------------------------------------------------------

  Future<Map<String, dynamic>> createClient({
    required String firstName,
    required String lastName,
    required String dateOfBirth,
    required String nationalId,
  }) async =>
      (await _post('/clients', {
        'first_name': firstName,
        'last_name': lastName,
        'date_of_birth': dateOfBirth,
        'national_id': nationalId,
      })) as Map<String, dynamic>;

  // -------------------------------------------------------------------------
  // Wallet
  // -------------------------------------------------------------------------

  Future<Map<String, dynamic>> createWallet(String clientId) async =>
      (await _post('/clients/$clientId/wallet', {})) as Map<String, dynamic>;

  // -------------------------------------------------------------------------
  // Deposit / Withdrawal
  // -------------------------------------------------------------------------

  Future<Map<String, dynamic>> deposit({
    required String clientId,
    required int amount,
    required String assetType,
    required String network,
  }) async =>
      (await _post('/clients/$clientId/deposit', {
        'amount': amount,
        'asset_type': assetType,
        'network': network,
      })) as Map<String, dynamic>;

  Future<Map<String, dynamic>> withdraw({
    required String clientId,
    required int amount,
    required String assetType,
    required String network,
  }) async =>
      (await _post('/clients/$clientId/withdraw', {
        'amount': amount,
        'asset_type': assetType,
        'network': network,
      })) as Map<String, dynamic>;

  // -------------------------------------------------------------------------
  // Balance
  // -------------------------------------------------------------------------

  Future<Map<String, dynamic>> getBalance({
    required String clientId,
    required String assetType,
    required String network,
  }) async =>
      (await _get(
        '/clients/$clientId/balance?asset_type=$assetType&network=$network',
      )) as Map<String, dynamic>;

  Future<List<dynamic>> getBalances(String clientId) async {
    final data = await _get('/clients/$clientId/balances');
    return data as List<dynamic>;
  }

  // -------------------------------------------------------------------------
  // Transactions
  // -------------------------------------------------------------------------

  Future<List<dynamic>> getTransactions(String clientId) async {
    final data = await _get('/clients/$clientId/transactions');
    return data as List<dynamic>;
  }

  Future<Map<String, dynamic>> getGasEstimate(String network) async =>
      (await _get('/clients/gas-estimate?network=$network')) as Map<String, dynamic>;

  // -------------------------------------------------------------------------
  // Admin
  // -------------------------------------------------------------------------

  Future<Map<String, dynamic>> registerWallets({
    required String apiKey,
    required String network,
  }) async =>
      (await _adminPost('/admin/register-wallets', {'network': network}, apiKey))
          as Map<String, dynamic>;

  Future<Map<String, dynamic>> pauseContract({
    required String apiKey,
    required String assetType,
    required String network,
  }) async =>
      (await _adminPost('/admin/pause', {'asset_type': assetType, 'network': network}, apiKey))
          as Map<String, dynamic>;

  Future<Map<String, dynamic>> unpauseContract({
    required String apiKey,
    required String assetType,
    required String network,
  }) async =>
      (await _adminPost('/admin/unpause', {'asset_type': assetType, 'network': network}, apiKey))
          as Map<String, dynamic>;

  Future<List<dynamic>> reconcile({required String apiKey}) async =>
      (await _adminGet('/admin/reconcile', apiKey)) as List<dynamic>;

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  Future<dynamic> _get(String path) async {
    final response = await _client.get(Uri.parse('$_base$path'));
    return _decode(response);
  }

  Future<dynamic> _post(String path, Map<String, dynamic> body) async {
    final response = await _client.post(
      Uri.parse('$_base$path'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    return _decode(response);
  }

  Future<dynamic> _adminGet(String path, String apiKey) async {
    final response = await _client.get(
      Uri.parse('$_base$path'),
      headers: {'X-API-Key': apiKey},
    );
    return _decode(response);
  }

  Future<dynamic> _adminPost(String path, Map<String, dynamic> body, String apiKey) async {
    final response = await _client.post(
      Uri.parse('$_base$path'),
      headers: {'Content-Type': 'application/json', 'X-API-Key': apiKey},
      body: jsonEncode(body),
    );
    return _decode(response);
  }

  dynamic _decode(http.Response response) {
    final body = jsonDecode(response.body);
    if (response.statusCode >= 400) {
      final detail = body is Map ? body['detail'] ?? body : body;
      throw ApiException(response.statusCode, detail.toString());
    }
    return body;
  }
}

class ApiException implements Exception {
  const ApiException(this.statusCode, this.detail);

  final int statusCode;
  final String detail;

  @override
  String toString() => 'ApiException($statusCode): $detail';
}
