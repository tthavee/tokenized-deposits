class BalanceEntry {
  const BalanceEntry({
    required this.assetType,
    required this.network,
    required this.chainAddress,
    required this.balance,
    this.error,
    this.contractAddress,
  });

  final String assetType;
  final String network;
  final String chainAddress;
  final int balance;
  final String? error;
  final String? contractAddress;

  factory BalanceEntry.fromJson(Map<String, dynamic> json) => BalanceEntry(
        assetType: json['asset_type'] as String,
        network: json['network'] as String,
        chainAddress: json['chain_address'] as String,
        balance: json['balance'] as int,
        error: json['error'] as String?,
        contractAddress: json['contract_address'] as String?,
      );
}
