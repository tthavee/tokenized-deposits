class TransactionEntry {
  const TransactionEntry({
    required this.id,
    required this.type,
    required this.amount,
    required this.assetType,
    required this.network,
    required this.status,
    required this.createdAt,
    this.onChainTxHash,
    this.contractAddress,
    this.direction,
    this.counterpartyId,
  });

  final String id;
  final String type;
  final int amount;
  final String assetType;
  final String network;
  final String status;
  final String createdAt;
  final String? onChainTxHash;
  final String? contractAddress;
  final String? direction;
  final String? counterpartyId;

  factory TransactionEntry.fromJson(Map<String, dynamic> json) =>
      TransactionEntry(
        id: json['id'] as String,
        type: json['type'] as String,
        amount: json['amount'] as int,
        assetType: json['asset_type'] as String,
        network: json['network'] as String,
        status: json['status'] as String,
        createdAt: json['created_at'] as String,
        onChainTxHash: json['on_chain_tx_hash'] as String?,
        contractAddress: json['contract_address'] as String?,
        direction: json['direction'] as String?,
        counterpartyId: json['counterparty_id'] as String?,
      );
}
