import 'package:flutter/material.dart';

/// Placeholder — deposit/withdrawal forms and balance display (issue #15).
class DepositWithdrawScreen extends StatelessWidget {
  const DepositWithdrawScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Deposit / Withdraw')),
      body: const Center(
        child: Text(
          'Deposit & withdrawal forms — coming in issue #15',
          style: TextStyle(fontSize: 16),
        ),
      ),
    );
  }
}
