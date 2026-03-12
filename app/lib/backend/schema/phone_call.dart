enum PhoneCallDirection { incoming, outgoing }

enum PhoneCallState { idle, connecting, ringing, active, ended, failed }

class PhoneTranscriptSegment {
  final String id;
  final String text;
  final bool isUser;
  final String? personId;
  final double start;
  final double end;
  final bool isFinal;

  PhoneTranscriptSegment({
    required this.id,
    required this.text,
    required this.isUser,
    this.personId,
    required this.start,
    required this.end,
    this.isFinal = true,
  });

  factory PhoneTranscriptSegment.fromJson(Map<String, dynamic> json) {
    return PhoneTranscriptSegment(
      id: json['id'] as String,
      text: json['text'] as String,
      isUser: (json['is_user'] ?? false) as bool,
      personId: json['person_id'] as String?,
      start: double.tryParse(json['start'].toString()) ?? 0.0,
      end: double.tryParse(json['end'].toString()) ?? 0.0,
      isFinal: (json['is_final'] ?? true) as bool,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'text': text,
        'is_user': isUser,
        'person_id': personId,
        'start': start,
        'end': end,
        'is_final': isFinal,
      };

  String getSpeakerLabel(String? contactName, String phoneNumber) {
    if (isUser) return 'You';
    return contactName ?? phoneNumber;
  }
}

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

  PhoneCallToken({
    required this.accessToken,
    required this.ttl,
    required this.identity,
  });

  factory PhoneCallToken.fromJson(Map<String, dynamic> json) {
    return PhoneCallToken(
      accessToken: json['access_token'] as String,
      ttl: json['ttl'] as int,
      identity: json['identity'] as String,
    );
  }
}
