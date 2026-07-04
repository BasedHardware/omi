import 'package:omi/backend/schema/gen/phone_calls_wire.g.dart' as wire;

enum PhoneCallDirection { incoming, outgoing }

enum PhoneCallState { idle, connecting, ringing, active, ended, failed }

// Phase 4 SSOT: VerifiedPhoneNumber was a pure 1:1 field-mapping wrapper around
// GeneratedPhoneNumberResponse (identical fields + fromJson + toJson). Replaced
// with a typedef. PhoneCallToken and PhoneCallError stay hand-written: PhoneCallToken
// derives a computed expiresAt, PhoneCallError parses a Twilio event map — neither is
// a thin wrapper.
typedef VerifiedPhoneNumber = wire.GeneratedPhoneNumberResponse;

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
