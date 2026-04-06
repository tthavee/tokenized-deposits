import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:tokenized_deposits/main.dart';
import 'package:tokenized_deposits/models/wallet.dart';
import 'package:tokenized_deposits/screens/kyc_screen.dart';
import 'package:tokenized_deposits/screens/wallet_screen.dart';
import 'package:tokenized_deposits/services/api_client.dart';

// ---------------------------------------------------------------------------
// Fakes
// ---------------------------------------------------------------------------

class _SuccessApiClient extends ApiClient {
  _SuccessApiClient() : super();

  @override
  Future<Map<String, dynamic>> createClient({
    required String firstName,
    required String lastName,
    required String dateOfBirth,
    required String nationalId,
  }) async =>
      {
        'id': 'client-1',
        'first_name': firstName,
        'last_name': lastName,
        'kyc_status': 'approved',
        'kyc_failure_reason': null,
      };

  @override
  Future<Map<String, dynamic>> createWallet(String clientId) async => {
        'client_id': clientId,
        'wallet': {'hardhat': '0xAAAA', 'sepolia': '0xBBBB'},
      };
}

class _KycFailApiClient extends ApiClient {
  _KycFailApiClient() : super();

  @override
  Future<Map<String, dynamic>> createClient({
    required String firstName,
    required String lastName,
    required String dateOfBirth,
    required String nationalId,
  }) async =>
      throw const ApiException(422, 'Document number is invalid');

  @override
  Future<Map<String, dynamic>> createWallet(String clientId) async =>
      throw UnimplementedError();
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

Widget _buildApp(ApiClient api) {
  return ProviderScope(
    overrides: [apiClientProvider.overrideWithValue(api)],
    child: MaterialApp(
      routes: {
        '/': (_) => const KycScreen(),
        '/wallet': (_) => const WalletScreen(),
      },
    ),
  );
}

Future<void> _fillForm(
  WidgetTester tester, {
  String firstName = 'Alice',
  String lastName = 'Smith',
  String dob = '1990-01-15',
  String nationalId = 'AB123456',
}) async {
  await tester.enterText(find.byKey(const Key('firstNameField')), firstName);
  await tester.enterText(find.byKey(const Key('lastNameField')), lastName);
  await tester.enterText(find.byKey(const Key('dobField')), dob);
  await tester.enterText(find.byKey(const Key('nationalIdField')), nationalId);
}

void main() {
// ---------------------------------------------------------------------------
// Form rendering
// ---------------------------------------------------------------------------

group('KycScreen — rendering', () {
  testWidgets('shows all four input fields', (tester) async {
    await tester.pumpWidget(_buildApp(_SuccessApiClient()));
    expect(find.byKey(const Key('firstNameField')), findsOneWidget);
    expect(find.byKey(const Key('lastNameField')), findsOneWidget);
    expect(find.byKey(const Key('dobField')), findsOneWidget);
    expect(find.byKey(const Key('nationalIdField')), findsOneWidget);
  });

  testWidgets('shows submit button', (tester) async {
    await tester.pumpWidget(_buildApp(_SuccessApiClient()));
    expect(find.byKey(const Key('submitButton')), findsOneWidget);
    expect(find.text('Submit KYC'), findsOneWidget);
  });
});

// ---------------------------------------------------------------------------
// Form validation
// ---------------------------------------------------------------------------

group('KycScreen — validation', () {
  testWidgets('shows required errors when form submitted empty', (tester) async {
    await tester.pumpWidget(_buildApp(_SuccessApiClient()));
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pump();
    expect(find.text('Required'), findsNWidgets(4));
  });

  testWidgets('shows date format error for bad DOB', (tester) async {
    await tester.pumpWidget(_buildApp(_SuccessApiClient()));
    await _fillForm(tester, dob: '15-01-1990');
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pump();
    expect(find.text('Use YYYY-MM-DD format'), findsOneWidget);
  });

  testWidgets('no errors when all fields valid', (tester) async {
    await tester.pumpWidget(_buildApp(_KycFailApiClient()));
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pump();
    expect(find.text('Required'), findsNothing);
    expect(find.text('Use YYYY-MM-DD format'), findsNothing);
  });
});

// ---------------------------------------------------------------------------
// Submission — success
// ---------------------------------------------------------------------------

group('KycScreen — success flow', () {
  testWidgets('navigates to wallet screen on approval', (tester) async {
    await tester.pumpWidget(_buildApp(_SuccessApiClient()));
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.byType(WalletScreen), findsOneWidget);
  });

  testWidgets('wallet screen shows correct client ID', (tester) async {
    await tester.pumpWidget(_buildApp(_SuccessApiClient()));
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.textContaining('client-1'), findsOneWidget);
  });

  testWidgets('wallet screen shows hardhat network card', (tester) async {
    await tester.pumpWidget(_buildApp(_SuccessApiClient()));
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.text('HARDHAT'), findsOneWidget);
    expect(find.text('0xAAAA'), findsOneWidget);
  });

  testWidgets('wallet screen shows sepolia network card', (tester) async {
    await tester.pumpWidget(_buildApp(_SuccessApiClient()));
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.text('SEPOLIA'), findsOneWidget);
    expect(find.text('0xBBBB'), findsOneWidget);
  });
});

// ---------------------------------------------------------------------------
// Submission — failure
// ---------------------------------------------------------------------------

group('KycScreen — failure flow', () {
  testWidgets('shows snackbar with failure message on KYC rejection',
      (tester) async {
    await tester.pumpWidget(_buildApp(_KycFailApiClient()));
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.byType(SnackBar), findsOneWidget);
    expect(find.textContaining('Document number is invalid'), findsOneWidget);
  });

  testWidgets('stays on KYC screen after failure', (tester) async {
    await tester.pumpWidget(_buildApp(_KycFailApiClient()));
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    expect(find.byType(KycScreen), findsOneWidget);
    expect(find.byType(WalletScreen), findsNothing);
  });

  testWidgets('submit button re-enabled after failure', (tester) async {
    await tester.pumpWidget(_buildApp(_KycFailApiClient()));
    await _fillForm(tester);
    await tester.tap(find.byKey(const Key('submitButton')));
    await tester.pumpAndSettle();
    final button =
        tester.widget<FilledButton>(find.byKey(const Key('submitButton')));
    expect(button.onPressed, isNotNull);
  });
});
}
