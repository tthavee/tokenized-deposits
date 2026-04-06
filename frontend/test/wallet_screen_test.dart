import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:tokenized_deposits/models/wallet.dart';
import 'package:tokenized_deposits/screens/wallet_screen.dart';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Push WalletScreen onto a navigator with [wallet] as route arguments.
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

Future<void> _openWallet(WidgetTester tester, Wallet? wallet) async {
  await tester.pumpWidget(_buildWithArgs(wallet));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
}

void main() {
// ---------------------------------------------------------------------------
// No wallet args
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
