import 'package:flutter/material.dart';

/// Placeholder — KYC form and wallet display (issue #14).
class KycScreen extends StatelessWidget {
  const KycScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('KYC Verification')),
      body: const Center(
        child: Text(
          'KYC form — coming in issue #14',
          style: TextStyle(fontSize: 16),
        ),
      ),
    );
  }
}
