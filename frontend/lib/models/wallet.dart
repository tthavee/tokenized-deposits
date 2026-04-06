/// Represents a wallet returned by POST /clients/{id}/wallet.
class Wallet {
  const Wallet({required this.clientId, required this.addresses});

  final String clientId;

  /// Network label → chain address, e.g. {'hardhat': '0x...', 'sepolia': '0x...'}.
  final Map<String, String> addresses;

  factory Wallet.fromJson(Map<String, dynamic> json) => Wallet(
        clientId: json['client_id'] as String,
        addresses: Map<String, String>.from(json['wallet'] as Map),
      );
}
