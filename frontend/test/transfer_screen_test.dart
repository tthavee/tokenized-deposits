import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:tokenized_deposits/main.dart';
import 'package:tokenized_deposits/screens/transfer_screen.dart';
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
      ];

  @override
  Future<Map<String, dynamic>> transfer({
    required String senderId,
    required String recipientId,
    required int amount,
    required String assetType,
    required String network,
  }) async =>
      {
        'sender_transaction_id': 'tx-sender-1',
        'recipient_transaction_id': 'tx-recipient-1',
        'status': 'confirmed',
        'on_chain_tx_hash': '0xabc',
      };
}

class _FailApiClient extends ApiClient {
  _FailApiClient() : super();

  @override
  Future<List<dynamic>> getBalances(String clientId) async => [
        {
          'asset_type': 'USD',
          'network': 'hardhat',
          'chain_address': '0x1234',
          'balance': 50,
        },
      ];

  @override
  Future<Map<String, dynamic>> transfer({
    required String senderId,
    required String recipientId,
    required int amount,
    required String assetType,
    required String network,
  }) async =>
      throw const ApiException(400, 'Insufficient sender balance');
}

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
              builder: (_) => const TransferScreen(),
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
  String recipientId = 'recipient-999',
  String amount = '100',
}) async {
  await tester.enterText(find.byKey(const Key('recipientIdField')), recipientId);
  await tester.enterText(find.byKey(const Key('amountField')), amount);

  await tester.tap(find.byKey(const Key('assetTypeField')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('USD').last);
  await tester.pumpAndSettle();

  await tester.tap(find.byKey(const Key('networkField')));
  await tester.pumpAndSettle();
  await tester.tap(find.text('hardhat').last);
  await tester.pumpAndSettle();
}

void main() {
// ---------------------------------------------------------------------------
// No client ID
// ---------------------------------------------------------------------------

group('TransferScreen — no client ID', () {
  testWidgets('shows fallback message when no client ID provided',
      (tester) async {
    await _openScreen(tester, null, _SuccessApiClient());
    expect(find.text('No client ID. Please complete KYC first.'), findsOneWidget);
  });

  testWidgets('still shows app bar title', (tester) async {
    await _openScreen(tester, null, _SuccessApiClient());
    expect(find.text('Transfer'), findsOneWidget);
  });
});

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

group('TransferScreen — rendering', () {
  testWidgets('shows all form fields and submit button', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    expect(find.byKey(const Key('recipientIdField')), findsOneWidget);
    expect(find.byKey(const Key('amountField')), findsOneWidget);
    expect(find.byKey(const Key('assetTypeField')), findsOneWidget);
    expect(find.byKey(const Key('networkField')), findsOneWidget);
    expect(find.byKey(const Key('submitButton')), findsOneWidget);
  });

  testWidgets('shows loaded balances', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    expect(find.text('USD (hardhat)'), findsOneWidget);
    expect(find.byKey(const Key('balance_USD_hardhat')), findsOneWidget);
  });

  testWidgets('shows "No balances found" when list is empty', (tester) async {
    await _openScreen(tester, 'client-1', _EmptyBalancesApiClient());
    expect(find.text('No balances found.'), findsOneWidget);
  });

  testWidgets('submit button label is Transfer', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    expect(
      find.descendant(
          of: find.byKey(const Key('submitButton')), matching: find.text('Transfer')),
      findsOneWidget,
    );
  });
});

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

group('TransferScreen — validation', () {
  testWidgets('shows required errors when submitted empty', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pump();
    expect(find.text('Required'), findsNWidgets(2));
  });

  testWidgets('shows error for non-numeric amount', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await tester.enterText(find.byKey(const Key('recipientIdField')), 'r-1');
    await tester.enterText(find.byKey(const Key('amountField')), 'abc');
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pump();
    expect(find.text('Enter a positive integer'), findsOneWidget);
  });

  testWidgets('shows error for zero amount', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await tester.enterText(find.byKey(const Key('recipientIdField')), 'r-1');
    await tester.enterText(find.byKey(const Key('amountField')), '0');
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pump();
    expect(find.text('Enter a positive integer'), findsOneWidget);
  });

  testWidgets('no validation errors when all fields are valid', (tester) async {
    await _openScreen(tester, 'client-1', _FailApiClient());
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pump();
    expect(find.text('Required'), findsNothing);
    expect(find.text('Enter a positive integer'), findsNothing);
  });
});

// ---------------------------------------------------------------------------
// Success
// ---------------------------------------------------------------------------

group('TransferScreen — success', () {
  testWidgets('shows confirmation dialog on success', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsOneWidget);
    expect(find.text('Transfer Confirmed'), findsOneWidget);
  });

  testWidgets('dialog contains sender transaction ID snippet', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.textContaining('tx-send'), findsOneWidget);
  });

  testWidgets('stays on transfer screen after dismissing dialog', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    expect(find.byType(TransferScreen), findsOneWidget);
  });

  testWidgets('submit button re-enabled after success', (tester) async {
    await _openScreen(tester, 'client-1', _SuccessApiClient());
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    final button =
        tester.widget<FilledButton>(find.byKey(const Key('submitButton')));
    expect(button.onPressed, isNotNull);
  });
});

// ---------------------------------------------------------------------------
// Failure
// ---------------------------------------------------------------------------

group('TransferScreen — failure', () {
  testWidgets('shows error snackbar on transfer failure', (tester) async {
    await _openScreen(tester, 'client-1', _FailApiClient());
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.byType(SnackBar), findsOneWidget);
    expect(find.textContaining('Insufficient sender balance'), findsOneWidget);
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
