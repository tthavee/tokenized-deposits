import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:tokenized_deposits/main.dart';

void main() {
  testWidgets('Home screen shows all navigation tiles', (WidgetTester tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: TokenizedDepositsApp()),
    );

    expect(find.text('KYC Verification'), findsOneWidget);
    expect(find.text('Wallet'), findsOneWidget);
    expect(find.text('Deposit / Withdraw'), findsOneWidget);
    expect(find.text('Transaction History'), findsOneWidget);
  });
}
