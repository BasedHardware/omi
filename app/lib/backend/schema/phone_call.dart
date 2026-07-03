import 'package:omi/backend/schema/gen/phone_calls_wire.g.dart' as wire;

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
    return VerifiedPhoneNumber.fromGenerated(wire.GeneratedPhoneNumberResponse.fromJson(json));
  }

  factory VerifiedPhoneNumber.fromGenerated(wire.GeneratedPhoneNumberResponse generated) {
    return VerifiedPhoneNumber(
      id: generated.id,
      phoneNumber: generated.phoneNumber,
      friendlyName: generated.friendlyName,
      verifiedAt: generated.verifiedAt,
      isPrimary: generated.isPrimary,
    );
  }

  wire.GeneratedPhoneNumberResponse toGenerated() {
    return wire.GeneratedPhoneNumberResponse(
      id: id,
      phoneNumber: phoneNumber,
      friendlyName: friendlyName,
      verifiedAt: verifiedAt,
      isPrimary: isPrimary,
    );
  }
}

class PhoneCallToken {
  final String accessToken;
  final int ttl;
  final String identity;
  final DateTime expiresAt;

  PhoneCallToken({required this.accessToken, required this.ttl, required this.identity})
    : expiresAt = DateTime.now().add(Duration(seconds: ttl));

  factory PhoneCallToken.fromJson(Map<String, dynamic> json) {
    return PhoneCallToken.fromGenerated(wire.GeneratedTokenResponse.fromJson(json));
  }

  factory PhoneCallToken.fromGenerated(wire.GeneratedTokenResponse generated) {
    return PhoneCallToken(accessToken: generated.accessToken, ttl: generated.ttl, identity: generated.identity);
  }

  wire.GeneratedTokenResponse toGenerated() {
    return wire.GeneratedTokenResponse(accessToken: accessToken, ttl: ttl, identity: identity);
  }
}

class PhoneCallError {
  final String code;
  final String message;

  PhoneCallError({required this.code, required this.message});

  factory PhoneCallError.fromEvent(Map event) {
    return PhoneCallError(
      code: event['code'] as String? ?? 'UNKNOWN',
      message: event['message'] as String? ?? 'An unknown error occurred',
    );
  }

  @override
  String toString() => 'PhoneCallError($code: $message)';
}
