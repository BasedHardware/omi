import 'package:flutter/foundation.dart';
import 'package:omi/backend/schema/conversation.dart';

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
  const OnDeviceProvenance({required this.summary, required this.reason, this.engine});

  static OnDeviceProvenance? fromConversation(ServerConversation conversation) {
    final raw = conversation.onDeviceProvenance;
    final local = conversation.transcriptSegments.any((s) => s.sttProvider?.startsWith('on_device:') == true);
    if (raw == null && !local) return null;
    final summary = raw?['summary'] is String ? raw!['summary'] as String : null;
    String? engine = raw?['engine'] is String ? raw!['engine'] as String : null;
    if (engine == null) {
      for (final segment in conversation.transcriptSegments) {
        if (segment.sttProvider?.startsWith('on_device:') == true) {
          engine = segment.sttProvider!.substring(10);
          break;
        }
      }
    }
    return OnDeviceProvenance(
        engine: engine,
        summary: OnDeviceSummaryOrigin.values.firstWhere((s) => s.name == summary,
            orElse: () => conversation.clientProcessing?['provenance'] is Map &&
                    conversation.clientProcessing!['provenance']['runtime'] == 'local'
                ? OnDeviceSummaryOrigin.phone
                : OnDeviceSummaryOrigin.cloud),
        reason: raw?['reason'] == OnDeviceReason.savingLiveHours.name
            ? OnDeviceReason.savingLiveHours
            : OnDeviceReason.liveHoursUsed);
  }

  final String? engine;
  final OnDeviceSummaryOrigin summary;
  final OnDeviceReason reason;

  @override
  bool operator ==(Object other) =>
      other is OnDeviceProvenance && other.summary == summary && other.reason == reason && other.engine == engine;

  @override
  int get hashCode => Object.hash(summary, reason, engine);
}
