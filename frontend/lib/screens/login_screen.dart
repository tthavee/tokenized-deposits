import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';
import '../models/wallet.dart';
import '../services/api_client.dart';
import '../services/session_service.dart';

class _ClientOption {
  const _ClientOption({
    required this.id,
    required this.firstName,
    required this.lastName,
  });

  final String id;
  final String firstName;
  final String lastName;

  String get displayName => '$firstName $lastName';
}

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _passwordCtrl = TextEditingController();

  List<_ClientOption> _clients = [];
  _ClientOption? _selected;
  bool _loading = true;
  bool _submitting = false;
  bool _obscure = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _fetchClients();
  }

  @override
  void dispose() {
    _passwordCtrl.dispose();
    super.dispose();
  }

  Future<void> _fetchClients() async {
    try {
      final api = ref.read(apiClientProvider);
      final data = await api.listClients();
      setState(() {
        _clients = data
            .map((e) => _ClientOption(
                  id: e['id'] as String,
                  firstName: e['first_name'] as String,
                  lastName: e['last_name'] as String,
                ))
            .toList()
          ..sort((a, b) => a.displayName.compareTo(b.displayName));
        _loading = false;
      });
    } catch (_) {
      setState(() {
        _error = 'Could not load clients. Is the backend running?';
        _loading = false;
      });
    }
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final api = ref.read(apiClientProvider);
      final result = await api.login(
        clientId: _selected!.id,
        password: _passwordCtrl.text,
      );
      final clientId = result['client_id'] as String;
      ref.read(currentClientIdProvider.notifier).state = clientId;

      final rawWallet = result['wallet'] as Map?;
      if (rawWallet != null) {
        final wallet = Wallet.fromJson({
          'client_id': clientId,
          'wallet': rawWallet,
        });
        ref.read(currentWalletProvider.notifier).state = wallet;
        await SessionService.save(clientId, wallet);
      }

      if (mounted) Navigator.of(context).pushReplacementNamed('/');
    } on ApiException catch (e) {
      setState(() => _error = e.statusCode == 401
          ? 'Incorrect password.'
          : 'Login failed: ${e.detail}');
    } catch (_) {
      setState(() => _error = 'Login failed. Check your connection.');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Sign In')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const SizedBox(height: 16),
                    DropdownButtonFormField<_ClientOption>(
                      initialValue: _selected,
                      decoration: const InputDecoration(
                        labelText: 'Client',
                        border: OutlineInputBorder(),
                      ),
                      items: _clients
                          .map((c) => DropdownMenuItem(
                                value: c,
                                child: Text(c.displayName),
                              ))
                          .toList(),
                      onChanged: (v) => setState(() => _selected = v),
                      validator: (v) => v == null ? 'Select a client' : null,
                    ),
                    const SizedBox(height: 20),
                    TextFormField(
                      controller: _passwordCtrl,
                      obscureText: _obscure,
                      decoration: InputDecoration(
                        labelText: 'Password',
                        border: const OutlineInputBorder(),
                        suffixIcon: IconButton(
                          icon: Icon(
                            _obscure ? Icons.visibility : Icons.visibility_off,
                          ),
                          onPressed: () =>
                              setState(() => _obscure = !_obscure),
                        ),
                      ),
                      validator: (v) =>
                          (v == null || v.isEmpty) ? 'Required' : null,
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        _error!,
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ],
                    const SizedBox(height: 28),
                    FilledButton(
                      onPressed: _submitting ? null : _submit,
                      child: _submitting
                          ? const SizedBox.square(
                              dimension: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          : const Text('Sign In'),
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}
