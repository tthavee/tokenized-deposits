import 'package:flutter/material.dart';

/// Placeholder — transaction history screen (issue #16).
class HistoryScreen extends StatelessWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Transaction History')),
      body: const Center(
        child: Text(
          'Transaction history — coming in issue #16',
          style: TextStyle(fontSize: 16),
        ),
      ),
    );
  }
}
