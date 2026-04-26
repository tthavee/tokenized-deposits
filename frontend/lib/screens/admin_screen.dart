import 'package:flutter/material.dart';

import '../services/api_client.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  String? _apiKey;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _promptApiKey());
  }

  Future<void> _promptApiKey() async {
    final key = await showDialog<String>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const _ApiKeyDialog(),
    );
    if (!mounted) return;
    if (key == null) {
      Navigator.of(context).pop();
    } else {
      setState(() => _apiKey = key);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Admin')),
      body: _apiKey == null
          ? const SizedBox.shrink()
          : _AdminPanel(apiKey: _apiKey!),
    );
  }
}

// ---------------------------------------------------------------------------
// API key prompt dialog
// ---------------------------------------------------------------------------

class _ApiKeyDialog extends StatefulWidget {
  const _ApiKeyDialog();

  @override
  State<_ApiKeyDialog> createState() => _ApiKeyDialogState();
}

class _ApiKeyDialogState extends State<_ApiKeyDialog> {
  final _ctrl = TextEditingController();
  bool _obscure = true;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Admin access'),
      content: TextField(
        controller: _ctrl,
        obscureText: _obscure,
        autofocus: true,
        decoration: InputDecoration(
          labelText: 'API Key',
          suffixIcon: IconButton(
            icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
            onPressed: () => setState(() => _obscure = !_obscure),
          ),
        ),
        onSubmitted: (_) => Navigator.of(context).pop(_ctrl.text.trim()),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(null),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(_ctrl.text.trim()),
          child: const Text('Enter'),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Admin panel (shown after key is accepted)
// ---------------------------------------------------------------------------

class _AdminPanel extends StatelessWidget {
  const _AdminPanel({required this.apiKey});

  final String apiKey;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        _RegisterWalletsCard(apiKey: apiKey),
        const SizedBox(height: 16),
        _PauseUnpauseCard(apiKey: apiKey),
        const SizedBox(height: 16),
        _ReconcileCard(apiKey: apiKey),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Register Wallets card
// ---------------------------------------------------------------------------

class _RegisterWalletsCard extends StatefulWidget {
  const _RegisterWalletsCard({required this.apiKey});

  final String apiKey;

  @override
  State<_RegisterWalletsCard> createState() => _RegisterWalletsCardState();
}

class _RegisterWalletsCardState extends State<_RegisterWalletsCard> {
  String _network = 'sepolia';
  bool _loading = false;
  Map<String, dynamic>? _result;
  String? _error;

  Future<void> _run() async {
    setState(() { _loading = true; _result = null; _error = null; });
    try {
      final result = await ApiClient().registerWallets(
        apiKey: widget.apiKey,
        network: _network,
      );
      if (mounted) setState(() => _result = result);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Register Wallets', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              'Registers any KYC-approved client wallets that are missing from the on-chain allowlist.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              initialValue: _network,
              decoration: const InputDecoration(labelText: 'Network', isDense: true),
              items: const [
                DropdownMenuItem(value: 'sepolia', child: Text('sepolia')),
                DropdownMenuItem(value: 'hardhat', child: Text('hardhat')),
              ],
              onChanged: (v) => setState(() { _network = v!; _result = null; _error = null; }),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: _loading ? null : _run,
              child: _loading
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Text('Register wallets'),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error, fontSize: 13),
              ),
            ],
            if (_result != null) ...[
              const SizedBox(height: 12),
              _ResultRow('Registered', _result!['registered'] as List, Colors.green),
              _ResultRow('Skipped (already approved)', _result!['skipped'] as List, Colors.grey),
              _ResultRow('Failed', _result!['failed'] as List, Colors.red),
            ],
          ],
        ),
      ),
    );
  }
}

class _ResultRow extends StatelessWidget {
  const _ResultRow(this.label, this.items, this.color);

  final String label;
  final List items;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          Text('$label: ', style: const TextStyle(fontWeight: FontWeight.w600)),
          Text(
            items.isEmpty ? 'none' : '${items.length}',
            style: TextStyle(color: color, fontWeight: FontWeight.bold),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Pause / Unpause card
// ---------------------------------------------------------------------------

class _PauseUnpauseCard extends StatefulWidget {
  const _PauseUnpauseCard({required this.apiKey});

  final String apiKey;

  @override
  State<_PauseUnpauseCard> createState() => _PauseUnpauseCardState();
}

class _PauseUnpauseCardState extends State<_PauseUnpauseCard> {
  String _network = 'sepolia';
  String _assetType = 'USD';
  bool _loading = false;
  String? _lastAction;
  String? _error;

  Future<void> _send(String action) async {
    setState(() { _loading = true; _lastAction = null; _error = null; });
    try {
      final fn = action == 'pause'
          ? ApiClient().pauseContract(
              apiKey: widget.apiKey, assetType: _assetType, network: _network)
          : ApiClient().unpauseContract(
              apiKey: widget.apiKey, assetType: _assetType, network: _network);
      await fn;
      if (mounted) setState(() => _lastAction = action);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Pause / Unpause Contract', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: _assetType,
                    decoration: const InputDecoration(labelText: 'Asset', isDense: true),
                    items: const [
                      DropdownMenuItem(value: 'USD', child: Text('USD')),
                    ],
                    onChanged: (v) => setState(() => _assetType = v!),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: _network,
                    decoration: const InputDecoration(labelText: 'Network', isDense: true),
                    items: const [
                      DropdownMenuItem(value: 'sepolia', child: Text('sepolia')),
                      DropdownMenuItem(value: 'hardhat', child: Text('hardhat')),
                    ],
                    onChanged: (v) => setState(() => _network = v!),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _loading ? null : () => _send('pause'),
                    child: const Text('Pause'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    onPressed: _loading ? null : () => _send('unpause'),
                    child: const Text('Unpause'),
                  ),
                ),
              ],
            ),
            if (_loading) ...[
              const SizedBox(height: 8),
              const LinearProgressIndicator(),
            ],
            if (_lastAction != null) ...[
              const SizedBox(height: 8),
              Text(
                'Contract ${_lastAction}d successfully.',
                style: const TextStyle(color: Colors.green, fontSize: 13),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error, fontSize: 13),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Reconcile card
// ---------------------------------------------------------------------------

class _ReconcileCard extends StatefulWidget {
  const _ReconcileCard({required this.apiKey});

  final String apiKey;

  @override
  State<_ReconcileCard> createState() => _ReconcileCardState();
}

class _ReconcileCardState extends State<_ReconcileCard> {
  bool _loading = false;
  List<dynamic>? _discrepancies;
  String? _error;

  Future<void> _run() async {
    setState(() { _loading = true; _discrepancies = null; _error = null; });
    try {
      final result = await ApiClient().reconcile(apiKey: widget.apiKey);
      if (mounted) setState(() => _discrepancies = result);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Reconcile Balances', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 4),
            Text(
              'Compares on-chain balances against Firestore records and lists discrepancies.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 12),
            OutlinedButton(
              onPressed: _loading ? null : _run,
              child: _loading
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Run reconciliation'),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error, fontSize: 13),
              ),
            ],
            if (_discrepancies != null) ...[
              const SizedBox(height: 12),
              if (_discrepancies!.isEmpty)
                const Text('All balances match.', style: TextStyle(color: Colors.green))
              else
                ..._discrepancies!.map((d) => _DiscrepancyTile(d as Map<String, dynamic>)),
            ],
          ],
        ),
      ),
    );
  }
}

class _DiscrepancyTile extends StatelessWidget {
  const _DiscrepancyTile(this.data);

  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      title: Text('${data['asset_type']} (${data['network']})'),
      subtitle: Text(
        'Wallet: ${(data['wallet'] as String).substring(0, 10)}…\n'
        'On-chain: ${data['on_chain_balance']}  |  Firestore: ${data['firestore_balance']}',
      ),
      leading: Icon(Icons.warning_amber, color: Theme.of(context).colorScheme.error),
    );
  }
}
