import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:tokenized_deposits/main.dart';
import 'package:tokenized_deposits/screens/deposit_withdraw_screen.dart';
import 'package:tokenized_deposits/services/api_client.dart';

// ---------------------------------------------------------------------------
// Fakes
// ---------------------------------------------------------------------------

class _SuccessApiClient extends ApiClient {
  _SuccessApiClient() : super();

  @override
  Future<List<dynamic>> getBalances(String clientId) async => [
        {
          'asset_type': 'USD',
          'network': 'hardhat',
          'chain_address': '0x1234',
          'balance': 1000,
        },
        {
          'asset_type': 'EUR',
          'network': 'hardhat',
          'chain_address': '0x1234',
          'balance': 500,
        },
      ];

  @override
  Future<Map<String, dynamic>> deposit({
    required String clientId,
    required int amount,
    required String assetType,
    required String network,
  }) async =>
      {'transaction_id': 'tx-deposit-1', 'status': 'confirmed', 'on_chain_tx_hash': '0xabc'};

  @override
  Future<Map<String, dynamic>> withdraw({
    required String clientId,
    required int amount,
    required String assetType,
    required String network,
  }) async =>
      {'transaction_id': 'tx-withdraw-1', 'status': 'confirmed', 'on_chain_tx_hash': '0xdef'};
}

/// Balances load but transactions fail — tests deposit/withdraw failure paths.
class _FailApiClient extends ApiClient {
  _FailApiClient() : super();

  @override
  Future<List<dynamic>> getBalances(String clientId) async => [
        {
          'asset_type': 'USD',
          'network': 'hardhat',
          'chain_address': '0x1234',
          'balance': 0,
        },
      ];

  @override
  Future<Map<String, dynamic>> deposit({
    required String clientId,
    required int amount,
    required String assetType,
    required String network,
  }) async =>
      throw const ApiException(422, 'Insufficient funds');

  @override
  Future<Map<String, dynamic>> withdraw({
    required String clientId,
    required int amount,
    required String assetType,
    required String network,
  }) async =>
      throw const ApiException(422, 'Insufficient token balance');
}

/// Returns no balances — used to test the empty-balances display.
class _EmptyBalancesApiClient extends ApiClient {
  _EmptyBalancesApiClient() : super();

  @override
  Future<List<dynamic>> getBalances(String clientId) async => [];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

Widget _buildWithArgs(String? clientId, ApiClient api) {
  return ProviderScope(
    overrides: [apiClientProvider.overrideWithValue(api)],
    child: MaterialApp(
      home: Builder(
        builder: (context) => ElevatedButton(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(
              settings: RouteSettings(arguments: clientId),
              builder: (_) => const DepositWithdrawScreen(),
            ),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  );
}

Future<void> _openScreen(
  WidgetTester tester,
  String? clientId,
  ApiClient api,
) async {
  await tester.pumpWidget(_buildWithArgs(clientId, api));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

Future<void> _fillForm(
  WidgetTester tester, {
  String amount = '100',
  String assetType = 'USD',
  String network = 'hardhat',
}) async {
  await tester.enterText(find.byKey(const Key('amountField')), amount);

  // Open asset type dropdown and select.
  await tester.tap(find.byKey(const Key('assetTypeField')));
  await tester.pumpAndSettle();
  await tester.tap(find.text(assetType).last);
  await tester.pumpAndSettle();

  // Open network dropdown and select.
  await tester.tap(find.byKey(const Key('networkField')));
  await tester.pumpAndSettle();
  await tester.tap(find.text(network).last);
  await tester.pumpAndSettle();
}

void main() {
// ---------------------------------------------------------------------------
// No client ID
// ---------------------------------------------------------------------------

group('DepositWithdrawScreen — no client ID', () {
  testWidgets('shows fallback message when no client ID provided',
      (tester) async {
    await _openScreen(tester, null, _SuccessApiClient());
    expect(find.text('No client ID. Please complete KYC first.'),
        findsOneWidget);
  });

  testWidgets('still shows app bar', (tester) async {
    await _openScreen(tester, null, _SuccessApiClient());
    expect(find.text('Deposit / Withdraw'), findsOneWidget);
  });
});

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

group('DepositWithdrawScreen — rendering', () {
  testWidgets('shows all form fields and submit button', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    expect(find.byKey(const Key('amountField')), findsOneWidget);
    expect(find.byKey(const Key('assetTypeField')), findsOneWidget);
    expect(find.byKey(const Key('networkField')), findsOneWidget);
    expect(find.byKey(const Key('submitButton')), findsOneWidget);
  });

  testWidgets('shows tx type toggle with deposit selected by default',
      (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    expect(find.byKey(const Key('txTypeToggle')), findsOneWidget);
    expect(find.text('Deposit'), findsWidgets);
  });

  testWidgets('shows loaded balances', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    expect(find.text('USD (hardhat)'), findsOneWidget);
    expect(find.byKey(const Key('balance_USD_hardhat')), findsOneWidget);
    expect(find.byKey(const Key('balance_EUR_hardhat')), findsOneWidget);
  });

  testWidgets('shows "No balances found" when list is empty', (tester) async {
    await _openScreen(tester, 'client-1', _EmptyBalancesApiClient());
    expect(find.text('No balances found.'), findsOneWidget);
  });
});

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

group('DepositWithdrawScreen — validation', () {
  testWidgets('shows required errors when submitted empty', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pump();
    expect(find.text('Required'), findsNWidgets(3));
  });

  testWidgets('shows error for non-numeric amount', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await _fillForm(tester, amount: 'abc');
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pump();
    expect(find.text('Enter a positive integer'), findsOneWidget);
  });

  testWidgets('shows error for zero amount', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await _fillForm(tester, amount: '0');
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pump();
    expect(find.text('Enter a positive integer'), findsOneWidget);
  });

  testWidgets('no errors when all fields valid', (tester) async {
    await _openScreen(tester, 'client-1', _FailApiClient());
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pump();
    expect(find.text('Required'), findsNothing);
    expect(find.text('Enter a positive integer'), findsNothing);
  });
});

// ---------------------------------------------------------------------------
// Deposit success
// ---------------------------------------------------------------------------

group('DepositWithdrawScreen — deposit success', () {
  testWidgets('shows confirmation snackbar with transaction ID', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.byType(SnackBar), findsOneWidget);
    expect(find.textContaining('tx-deposit-1'), findsOneWidget);
  });

  testWidgets('stays on deposit/withdraw screen after success', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.byType(DepositWithdrawScreen), findsOneWidget);
  });

  testWidgets('submit button re-enabled after success', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    final button =
        tester.widget<FilledButton>(find.byKey(const Key('submitButton')));
    expect(button.onPressed, isNotNull);
  });
});

// ---------------------------------------------------------------------------
// Withdraw success
// ---------------------------------------------------------------------------

group('DepositWithdrawScreen — withdraw success', () {
  testWidgets('shows confirmation snackbar for withdrawal', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await tester.tap(find.text('Withdraw'));
    await tester.pump();
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.byType(SnackBar), findsOneWidget);
    expect(find.textContaining('tx-withdraw-1'), findsOneWidget);
  });
});

// ---------------------------------------------------------------------------
// Failure
// ---------------------------------------------------------------------------

group('DepositWithdrawScreen — failure', () {
  testWidgets('shows error snackbar on deposit failure', (tester) async {
    await _openScreen(tester, 'client-1', _FailApiClient());
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.byType(SnackBar), findsOneWidget);
    expect(find.textContaining('Insufficient funds'), findsOneWidget);
  });

  testWidgets('submit button re-enabled after failure', (tester) async {
    await _openScreen(tester, 'client-1', _FailApiClient());
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    final button =
        tester.widget<FilledButton>(find.byKey(const Key('submitButton')));
    expect(button.onPressed, isNotNull);
  });
});
}
