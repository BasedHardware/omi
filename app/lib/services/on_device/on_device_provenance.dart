import 'package:flutter/foundation.dart';

/// Who wrote a conversation's summary, given its transcript was made on the phone.
enum OnDeviceSummaryOrigin {
  /// The phone's built-in model (iPhone 15 Pro or later).
  phone,

  /// Omi Cloud, from the transcript text only. Does not use live hours.
  cloud,

  /// No summary: the reader keeps everything on the phone.
  none,
}

/// Why the conversation was transcribed on the phone.
enum OnDeviceReason {
  /// The month's live hours ran out.
  liveHoursUsed,

  /// The reader chose on-device transcription to save live hours.
  savingLiveHours,
}

/// Where a conversation's transcript and summary were made, when the transcript was made on the
/// phone. Conversations transcribed live by Omi Cloud have none.
@immutable
class OnDeviceProvenance {
  const OnDeviceProvenance({required this.summary, required this.reason});

  final OnDeviceSummaryOrigin summary;
  final OnDeviceReason reason;

  @override
  bool operator ==(Object other) => other is OnDeviceProvenance && other.summary == summary && other.reason == reason;

  @override
  int get hashCode => Object.hash(summary, reason);
}
