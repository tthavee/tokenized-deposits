import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'models/wallet.dart';
import 'screens/admin_screen.dart';
import 'screens/deposit_withdraw_screen.dart';
import 'screens/history_screen.dart';
import 'screens/kyc_screen.dart';
import 'screens/login_screen.dart';
import 'screens/wallet_screen.dart';
import 'services/api_client.dart';
import 'services/session_service.dart';

/// Global provider for the API client.
final apiClientProvider = Provider<ApiClient>((_) => ApiClient());

/// Holds the client ID of the currently authenticated user.
/// Seeded from SharedPreferences on startup; updated after KYC.
final currentClientIdProvider = StateProvider<String?>((ref) => null);

/// Holds the wallet of the currently authenticated user.
/// Seeded from SharedPreferences on startup; updated after KYC.
final currentWalletProvider = StateProvider<Wallet?>((ref) => null);

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Restore previous session so users don't have to re-do KYC on every launch.
  final savedClientId = await SessionService.loadClientId();
  final savedWallet = await SessionService.loadWallet();

  runApp(
    ProviderScope(
      overrides: [
        currentClientIdProvider.overrideWith((ref) => savedClientId),
        currentWalletProvider.overrideWith((ref) => savedWallet),
      ],
      child: const TokenizedDepositsApp(),
    ),
  );
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
        '/login': (_) => const LoginScreen(),
        '/kyc': (_) => const KycScreen(),
        '/wallet': (_) => const WalletScreen(),
        '/deposit-withdraw': (_) => const DepositWithdrawScreen(),
        '/history': (_) => const HistoryScreen(),
        '/admin': (_) => const AdminScreen(),
      },
    );
  }
}

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final clientId = ref.watch(currentClientIdProvider);

    if (clientId == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        Navigator.of(context).pushReplacementNamed('/login');
      });
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Tokenized Deposits')),
      body: ListView(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
            child: Text(
              'Signed in as $clientId',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
          ListTile(
            leading: const Icon(Icons.logout),
            title: const Text('Sign out'),
            onTap: () async {
              await SessionService.clear();
              ref.read(currentClientIdProvider.notifier).state = null;
              ref.read(currentWalletProvider.notifier).state = null;
            },
          ),
          const Divider(),
          const _NavTile(
            icon: Icons.verified_user,
            label: 'KYC Verification',
            route: '/kyc',
          ),
          const _NavTile(
            icon: Icons.account_balance_wallet,
            label: 'Wallet',
            route: '/wallet',
          ),
          const _NavTile(
            icon: Icons.swap_horiz,
            label: 'Deposit / Withdraw',
            route: '/deposit-withdraw',
          ),
          const _NavTile(
            icon: Icons.history,
            label: 'Transaction History',
            route: '/history',
          ),
          const Divider(),
          const _NavTile(
            icon: Icons.admin_panel_settings,
            label: 'Admin',
            route: '/admin',
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
