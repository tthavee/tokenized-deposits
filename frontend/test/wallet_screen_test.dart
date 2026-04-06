import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:tokenized_deposits/main.dart';
import 'package:tokenized_deposits/models/wallet.dart';
import 'package:tokenized_deposits/screens/wallet_screen.dart';
import 'package:tokenized_deposits/services/api_client.dart';

// ---------------------------------------------------------------------------
// Fakes
// ---------------------------------------------------------------------------

class _SuccessApiClient extends ApiClient {
  _SuccessApiClient() : super();

  @override
  Future<Map<String, dynamic>> createWallet(String clientId) async => {
        'client_id': clientId,
        'wallet': {'hardhat': '0xNEW'},
      };
}

class _FailApiClient extends ApiClient {
  _FailApiClient() : super();

  @override
  Future<Map<String, dynamic>> createWallet(String clientId) async =>
      throw const ApiException(500, 'RPC error');
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Push WalletScreen with [wallet] as route arguments (existing wallet flow).
Widget _buildWithArgs(Wallet? wallet) {
  return ProviderScope(
    child: MaterialApp(
      home: Builder(
        builder: (context) => ElevatedButton(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(
              settings: RouteSettings(arguments: wallet),
              builder: (_) => const WalletScreen(),
            ),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  );
}

/// Push WalletScreen with no route args but with provider overrides.
Widget _buildWithProviders({
  String? clientId,
  Wallet? wallet,
  ApiClient? api,
}) {
  return ProviderScope(
    overrides: [
      if (api != null) apiClientProvider.overrideWithValue(api),
      currentClientIdProvider.overrideWith((ref) => clientId),
      currentWalletProvider.overrideWith((ref) => wallet),
    ],
    child: MaterialApp(
      home: Builder(
        builder: (context) => ElevatedButton(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute(builder: (_) => const WalletScreen()),
          ),
          child: const Text('open'),
        ),
      ),
    ),
  );
}

Future<void> _openWallet(WidgetTester tester, Wallet? wallet) async {
  await tester.pumpWidget(_buildWithArgs(wallet));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

Future<void> _openWithProviders(
  WidgetTester tester, {
  String? clientId,
  Wallet? wallet,
  ApiClient? api,
}) async {
  await tester.pumpWidget(
      _buildWithProviders(clientId: clientId, wallet: wallet, api: api));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

void main() {
// ---------------------------------------------------------------------------
// No wallet args, no session
// ---------------------------------------------------------------------------

group('WalletScreen — no args', () {
  testWidgets('shows fallback message when no wallet provided', (tester) async {
    await _openWallet(tester, null);
    expect(find.text('No wallet data. Please complete KYC first.'), findsOneWidget);
  });

  testWidgets('still shows app bar', (tester) async {
    await _openWallet(tester, null);
    expect(find.text('Wallet'), findsOneWidget);
  });
});

// ---------------------------------------------------------------------------
// Has clientId but no wallet yet — Create Wallet button
// ---------------------------------------------------------------------------

group('WalletScreen — create wallet', () {
  testWidgets('shows Create Wallet button when clientId known but no wallet',
      (tester) async {
    await _openWithProviders(tester,
        clientId: 'client-99', wallet: null, api: _SuccessApiClient());
    expect(find.byKey(const Key('createWalletButton')), findsOneWidget);
    expect(find.text('Create Wallet'), findsOneWidget);
  });

  testWidgets('shows wallet addresses after successful creation', (tester) async {
    await _openWithProviders(tester,
        clientId: 'client-99', wallet: null, api: _SuccessApiClient());
    await tester.tap(find.byKey(const Key('createWalletButton')));
    await tester.pumpAndSettle();
    expect(find.text('HARDHAT'), findsOneWidget);
    expect(find.text('0xNEW'), findsOneWidget);
  });

  testWidgets('shows error message on creation failure', (tester) async {
    await _openWithProviders(tester,
        clientId: 'client-99', wallet: null, api: _FailApiClient());
    await tester.tap(find.byKey(const Key('createWalletButton')));
    await tester.pumpAndSettle();
    expect(find.textContaining('RPC error'), findsOneWidget);
    expect(find.byKey(const Key('createWalletButton')), findsOneWidget);
  });

  testWidgets('button re-enabled after failure', (tester) async {
    await _openWithProviders(tester,
        clientId: 'client-99', wallet: null, api: _FailApiClient());
    await tester.tap(find.byKey(const Key('createWalletButton')));
    await tester.pumpAndSettle();
    final button = tester
        .widget<FilledButton>(find.byKey(const Key('createWalletButton')));
    expect(button.onPressed, isNotNull);
  });
});

// ---------------------------------------------------------------------------
// Single-network wallet
// ---------------------------------------------------------------------------

group('WalletScreen — single network', () {
  final wallet = Wallet(
    clientId: 'client-42',
    addresses: {'hardhat': '0x1234'},
  );

  testWidgets('shows client ID', (tester) async {
    await _openWallet(tester, wallet);
    expect(find.textContaining('client-42'), findsOneWidget);
  });

  testWidgets('shows network label in upper case', (tester) async {
    await _openWallet(tester, wallet);
    expect(find.text('HARDHAT'), findsOneWidget);
  });

  testWidgets('shows chain address', (tester) async {
    await _openWallet(tester, wallet);
    expect(find.text('0x1234'), findsOneWidget);
  });

  testWidgets('renders exactly one network card', (tester) async {
    await _openWallet(tester, wallet);
    expect(find.byType(Card), findsOneWidget);
  });
});

// ---------------------------------------------------------------------------
// Multi-network wallet
// ---------------------------------------------------------------------------

group('WalletScreen — multi-network', () {
  final wallet = Wallet(
    clientId: 'client-7',
    addresses: {
      'hardhat': '0xAAAA',
      'sepolia': '0xBBBB',
    },
  );

  testWidgets('shows one card per network', (tester) async {
    await _openWallet(tester, wallet);
    expect(find.byType(Card), findsNWidgets(2));
  });

  testWidgets('shows hardhat network label and address', (tester) async {
    await _openWallet(tester, wallet);
    expect(find.text('HARDHAT'), findsOneWidget);
    expect(find.text('0xAAAA'), findsOneWidget);
  });

  testWidgets('shows sepolia network label and address', (tester) async {
    await _openWallet(tester, wallet);
    expect(find.text('SEPOLIA'), findsOneWidget);
    expect(find.text('0xBBBB'), findsOneWidget);
  });

  testWidgets('address text is selectable', (tester) async {
    await _openWallet(tester, wallet);
    expect(find.byType(SelectableText), findsNWidgets(2));
  });
});
}
