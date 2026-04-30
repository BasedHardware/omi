/// Signals collected from the user during onboarding.
///
/// Mirrors `desktop-v2/src/stores/onboardingCompanionStore.ts` — these are the
/// facts the assistant uses to ground its openers and follow-up turns.
class CompanionSignals {
  final String? preferredName;
  final String? language; // e.g. "en", "pt-BR"
  final bool? hasDevice;
  final bool? speechProfileCaptured;

  const CompanionSignals({
    this.preferredName,
    this.language,
    this.hasDevice,
    this.speechProfileCaptured,
  });

  CompanionSignals copyWith({
    String? preferredName,
    String? language,
    bool? hasDevice,
    bool? speechProfileCaptured,
  }) {
    return CompanionSignals(
      preferredName: preferredName ?? this.preferredName,
      language: language ?? this.language,
      hasDevice: hasDevice ?? this.hasDevice,
      speechProfileCaptured: speechProfileCaptured ?? this.speechProfileCaptured,
    );
  }

  Map<String, dynamic> toJson() => {
        'preferredName': preferredName,
        'language': language,
        'hasDevice': hasDevice,
        'speechProfileCaptured': speechProfileCaptured,
      };

  factory CompanionSignals.fromJson(Map<String, dynamic> json) {
    return CompanionSignals(
      preferredName: json['preferredName'] as String?,
      language: json['language'] as String?,
      hasDevice: json['hasDevice'] as bool?,
      speechProfileCaptured: json['speechProfileCaptured'] as bool?,
    );
  }
}
