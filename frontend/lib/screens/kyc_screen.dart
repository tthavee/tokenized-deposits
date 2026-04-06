import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/kyc_provider.dart';

class KycScreen extends ConsumerStatefulWidget {
  const KycScreen({super.key});

  @override
  ConsumerState<KycScreen> createState() => _KycScreenState();
}

class _KycScreenState extends ConsumerState<KycScreen> {
  final _formKey = GlobalKey<FormState>();
  final _firstNameCtrl = TextEditingController();
  final _lastNameCtrl = TextEditingController();
  final _dobCtrl = TextEditingController();
  final _nationalIdCtrl = TextEditingController();

  @override
  void dispose() {
    _firstNameCtrl.dispose();
    _lastNameCtrl.dispose();
    _dobCtrl.dispose();
    _nationalIdCtrl.dispose();
    super.dispose();
  }

  void _submit() {
    if (!_formKey.currentState!.validate()) return;
    ref.read(kycProvider.notifier).submit(
          firstName: _firstNameCtrl.text.trim(),
          lastName: _lastNameCtrl.text.trim(),
          dateOfBirth: _dobCtrl.text.trim(),
          nationalId: _nationalIdCtrl.text.trim(),
        );
  }

  @override
  Widget build(BuildContext context) {
    final isLoading = ref.watch(kycProvider) is KycLoading;

    ref.listen<KycState>(kycProvider, (_, next) {
      switch (next) {
        case KycSuccess(:final wallet):
          Navigator.of(context).pushReplacementNamed(
            '/wallet',
            arguments: wallet,
          );
          ref.read(kycProvider.notifier).reset();
        case KycError(:final message):
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('KYC failed: $message'),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
          ref.read(kycProvider.notifier).reset();
        default:
          break;
      }
    });

    return Scaffold(
      appBar: AppBar(title: const Text('KYC Verification')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                key: const Key('firstNameField'),
                controller: _firstNameCtrl,
                decoration: const InputDecoration(labelText: 'First name'),
                textCapitalization: TextCapitalization.words,
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'Required' : null,
              ),
              const SizedBox(height: 16),
              TextFormField(
                key: const Key('lastNameField'),
                controller: _lastNameCtrl,
                decoration: const InputDecoration(labelText: 'Last name'),
                textCapitalization: TextCapitalization.words,
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'Required' : null,
              ),
              const SizedBox(height: 16),
              TextFormField(
                key: const Key('dobField'),
                controller: _dobCtrl,
                decoration: const InputDecoration(
                  labelText: 'Date of birth',
                  hintText: 'YYYY-MM-DD',
                ),
                keyboardType: TextInputType.datetime,
                validator: (v) {
                  if (v == null || v.trim().isEmpty) return 'Required';
                  if (!RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(v.trim())) {
                    return 'Use YYYY-MM-DD format';
                  }
                  return null;
                },
              ),
              const SizedBox(height: 16),
              TextFormField(
                key: const Key('nationalIdField'),
                controller: _nationalIdCtrl,
                decoration: const InputDecoration(labelText: 'National ID'),
                validator: (v) =>
                    (v == null || v.trim().isEmpty) ? 'Required' : null,
              ),
              const SizedBox(height: 32),
              FilledButton(
                key: const Key('submitButton'),
                onPressed: isLoading ? null : _submit,
                child: isLoading
                    ? const SizedBox.square(
                        dimension: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Submit KYC'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
