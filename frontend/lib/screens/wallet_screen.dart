import 'package:flutter/material.dart';

/// Placeholder — wallet address display (issue #14).
class WalletScreen extends StatelessWidget {
  const WalletScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Wallet')),
      body: const Center(
        child: Text(
          'Wallet display — coming in issue #14',
          style: TextStyle(fontSize: 16),
        ),
      ),
    );
  }
}
