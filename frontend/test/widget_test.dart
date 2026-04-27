import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:tokenized_deposits/main.dart';

void main() {
  testWidgets('Unauthenticated app shows Sign In screen', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: TokenizedDepositsApp()),
    );
    await tester.pumpAndSettle();

    // With no session, the dashboard redirects to login.
    expect(find.text('Sign In'), findsAtLeastNWidgets(1));
  });

  testWidgets('Menu screen shows all navigation tiles when signed in',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          currentClientIdProvider.overrideWith((ref) => 'test-client-id'),
        ],
        child: const TokenizedDepositsApp(),
      ),
    );

    // Navigate to the menu screen.
    await tester.pumpAndSettle();
    final NavigatorState navigator =
        tester.state<NavigatorState>(find.byType(Navigator).first);
    navigator.pushNamed('/menu');
    await tester.pumpAndSettle();

    expect(find.text('New Wallet & KYC'), findsOneWidget);
    expect(find.text('Wallet'), findsOneWidget);
    expect(find.text('Deposit / Withdraw'), findsOneWidget);
    expect(find.text('Transaction History'), findsOneWidget);
  });
}
