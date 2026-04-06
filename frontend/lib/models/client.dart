/// Represents a client record returned by POST /clients.
class Client {
  const Client({
    required this.id,
    required this.kycStatus,
    this.kycFailureReason,
  });

  final String id;
  final String kycStatus;
  final String? kycFailureReason;

  factory Client.fromJson(Map<String, dynamic> json) => Client(
        id: json['id'] as String,
        kycStatus: json['kyc_status'] as String,
        kycFailureReason: json['kyc_failure_reason'] as String?,
      );
}
