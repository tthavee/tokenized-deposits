import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'screens/deposit_withdraw_screen.dart';
import 'screens/history_screen.dart';
import 'screens/kyc_screen.dart';
import 'screens/wallet_screen.dart';
import 'services/api_client.dart';

/// Global provider for the API client.
final apiClientProvider = Provider<ApiClient>((_) => ApiClient());

void main() {
  runApp(const ProviderScope(child: TokenizedDepositsApp()));
}

class TokenizedDepositsApp extends StatelessWidget {
  const TokenizedDepositsApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Tokenized Deposits',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
        useMaterial3: true,
      ),
      initialRoute: '/',
      routes: {
        '/': (_) => const HomeScreen(),
        '/kyc': (_) => const KycScreen(),
        '/wallet': (_) => const WalletScreen(),
        '/deposit-withdraw': (_) => const DepositWithdrawScreen(),
        '/history': (_) => const HistoryScreen(),
      },
    );
  }
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Tokenized Deposits')),
      body: ListView(
        children: const [
          _NavTile(
            icon: Icons.verified_user,
            label: 'KYC Verification',
            route: '/kyc',
          ),
          _NavTile(
            icon: Icons.account_balance_wallet,
            label: 'Wallet',
            route: '/wallet',
          ),
          _NavTile(
            icon: Icons.swap_horiz,
            label: 'Deposit / Withdraw',
            route: '/deposit-withdraw',
          ),
          _NavTile(
            icon: Icons.history,
            label: 'Transaction History',
            route: '/history',
          ),
        ],
      ),
    );
  }
}

class _NavTile extends StatelessWidget {
  const _NavTile({
    required this.icon,
    required this.label,
    required this.route,
  });

  final IconData icon;
  final String label;
  final String route;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Icon(icon),
      title: Text(label),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => Navigator.pushNamed(context, route),
    );
  }
}
