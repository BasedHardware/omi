enum PhoneCallDirection { incoming, outgoing }

enum PhoneCallState { idle, connecting, ringing, active, ended, failed }

class VerifiedPhoneNumber {
  final String id;
  final String phoneNumber;
  final String? friendlyName;
  final String verifiedAt;
  final bool isPrimary;

  VerifiedPhoneNumber({
    required this.id,
    required this.phoneNumber,
    this.friendlyName,
    required this.verifiedAt,
    required this.isPrimary,
  });

  factory VerifiedPhoneNumber.fromJson(Map<String, dynamic> json) {
    return VerifiedPhoneNumber(
      id: json['id'] as String,
      phoneNumber: json['phone_number'] as String,
      friendlyName: json['friendly_name'] as String?,
      verifiedAt: json['verified_at'] as String,
      isPrimary: (json['is_primary'] ?? false) as bool,
    );
  }
}

class PhoneCallToken {
  final String accessToken;
  final int ttl;
  final String identity;

  PhoneCallToken({required this.accessToken, required this.ttl, required this.identity});

  factory PhoneCallToken.fromJson(Map<String, dynamic> json) {
    return PhoneCallToken(
      accessToken: json['access_token'] as String,
      ttl: json['ttl'] as int,
      identity: json['identity'] as String,
    );
  }
}
