import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:tokenized_deposits/main.dart';
import 'package:tokenized_deposits/screens/history_screen.dart';
import 'package:tokenized_deposits/services/api_client.dart';

// ---------------------------------------------------------------------------
// Fakes
// ---------------------------------------------------------------------------

class _TwoTxApiClient extends ApiClient {
  _TwoTxApiClient() : super();

  @override
  Future<List<dynamic>> getTransactions(String clientId) async => [
        {
          'id': 'tx-1',
          'type': 'deposit',
          'amount': 500,
          'asset_type': 'USD',
          'network': 'hardhat',
          'status': 'confirmed',
          'on_chain_tx_hash': '0xabc',
          'created_at': '2024-01-15T10:00:00Z',
        },
        {
          'id': 'tx-2',
          'type': 'withdrawal',
          'amount': 100,
          'asset_type': 'EUR',
          'network': 'sepolia',
          'status': 'pending',
          'on_chain_tx_hash': null,
          'created_at': '2024-01-10T08:00:00Z',
        },
      ];
}

class _EmptyTxApiClient extends ApiClient {
  _EmptyTxApiClient() : super();

  @override
  Future<List<dynamic>> getTransactions(String clientId) async => [];
}

class _TransferTxApiClient extends ApiClient {
  _TransferTxApiClient() : super();

  @override
  Future<List<dynamic>> getTransactions(String clientId) async => [
        {
          'id': 'tx-1',
          'type': 'deposit',
          'amount': 500,
          'asset_type': 'USD',
          'network': 'hardhat',
          'status': 'confirmed',
          'on_chain_tx_hash': '0xabc',
          'created_at': '2024-01-15T10:00:00Z',
        },
        {
          'id': 'tx-sent',
          'type': 'transfer',
          'direction': 'sent',
          'amount': 200,
          'asset_type': 'USD',
          'network': 'hardhat',
          'status': 'confirmed',
          'counterparty_id': 'recipient-999',
          'on_chain_tx_hash': '0xdef',
          'created_at': '2024-01-14T09:00:00Z',
        },
        {
          'id': 'tx-recv',
          'type': 'transfer',
          'direction': 'received',
          'amount': 75,
          'asset_type': 'USD',
          'network': 'hardhat',
          'status': 'confirmed',
          'counterparty_id': 'sender-111',
          'on_chain_tx_hash': '0xfed',
          'created_at': '2024-01-13T07:00:00Z',
        },
      ];
}

class _FailTxApiClient extends ApiClient {
  _FailTxApiClient() : super();

  @override
  Future<List<dynamic>> getTransactions(String clientId) async =>
      throw const ApiException(500, 'Server error');
}

// ---------------------------------------------------------------------------
// Helper
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
              builder: (_) => const HistoryScreen(),
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

void main() {
  group('HistoryScreen — no client ID', () {
    testWidgets('shows fallback message', (tester) async {
      await _openScreen(tester, null, _TwoTxApiClient());
      expect(
        find.text('No client ID. Please complete KYC first.'),
        findsOneWidget,
      );
    });
  });

  group('HistoryScreen — empty state', () {
    testWidgets('shows empty state message', (tester) async {
      await _openScreen(tester, 'client-1', _EmptyTxApiClient());
      expect(find.byKey(const Key('emptyState')), findsOneWidget);
      expect(find.text('No transactions yet.'), findsOneWidget);
    });
  });

  group('HistoryScreen — transaction list', () {
    testWidgets('renders one tile per transaction', (tester) async {
      await _openScreen(tester, 'client-1', _TwoTxApiClient());
      expect(find.byKey(const Key('tx_tx-1')), findsOneWidget);
      expect(find.byKey(const Key('tx_tx-2')), findsOneWidget);
    });

    testWidgets('shows asset type and network labels', (tester) async {
      await _openScreen(tester, 'client-1', _TwoTxApiClient());
      expect(find.text('Deposit — USD (hardhat)'), findsOneWidget);
      expect(find.text('Withdrawal — EUR (sepolia)'), findsOneWidget);
    });

    testWidgets('shows amount for each transaction', (tester) async {
      await _openScreen(tester, 'client-1', _TwoTxApiClient());
      expect(find.byKey(const Key('amount_tx-1')), findsOneWidget);
      expect(find.byKey(const Key('amount_tx-2')), findsOneWidget);
    });

    testWidgets('shows status for each transaction', (tester) async {
      await _openScreen(tester, 'client-1', _TwoTxApiClient());
      expect(find.byKey(const Key('status_tx-1')), findsOneWidget);
      expect(find.byKey(const Key('status_tx-2')), findsOneWidget);
      expect(find.text('confirmed'), findsOneWidget);
      expect(find.text('pending'), findsOneWidget);
    });

    testWidgets('shows date substring from created_at', (tester) async {
      await _openScreen(tester, 'client-1', _TwoTxApiClient());
      expect(find.text('2024-01-15'), findsOneWidget);
      expect(find.text('2024-01-10'), findsOneWidget);
    });
  });

  group('HistoryScreen — error state', () {
    testWidgets('shows error message on API failure', (tester) async {
      await _openScreen(tester, 'client-1', _FailTxApiClient());
      expect(find.textContaining('Failed to load transactions'), findsOneWidget);
    });
  });

  group('HistoryScreen — transfer rows', () {
    testWidgets('renders transfer tiles alongside deposit tiles', (tester) async {
      await _openScreen(tester, 'client-1', _TransferTxApiClient());
      expect(find.byKey(const Key('tx_tx-1')), findsOneWidget);
      expect(find.byKey(const Key('tx_tx-sent')), findsOneWidget);
      expect(find.byKey(const Key('tx_tx-recv')), findsOneWidget);
    });

    testWidgets('sent transfer shows direction and asset label', (tester) async {
      await _openScreen(tester, 'client-1', _TransferTxApiClient());
      expect(find.text('Transfer — Sent — USD (hardhat)'), findsOneWidget);
    });

    testWidgets('received transfer shows direction and asset label', (tester) async {
      await _openScreen(tester, 'client-1', _TransferTxApiClient());
      expect(find.text('Transfer — Received — USD (hardhat)'), findsOneWidget);
    });

    testWidgets('transfer row shows counterparty ID', (tester) async {
      await _openScreen(tester, 'client-1', _TransferTxApiClient());
      expect(find.byKey(const Key('counterparty_tx-sent')), findsOneWidget);
      expect(find.text('recipient-999'), findsOneWidget);
    });

    testWidgets('transfer row shows amount and status', (tester) async {
      await _openScreen(tester, 'client-1', _TransferTxApiClient());
      expect(find.byKey(const Key('amount_tx-sent')), findsOneWidget);
      expect(find.byKey(const Key('status_tx-sent')), findsOneWidget);
    });

    testWidgets('existing deposit row is unaffected', (tester) async {
      await _openScreen(tester, 'client-1', _TransferTxApiClient());
      expect(find.text('Deposit — USD (hardhat)'), findsOneWidget);
    });
  });
}
