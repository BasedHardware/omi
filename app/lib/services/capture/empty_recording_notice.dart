import 'package:omi/backend/schema/conversation.dart';

/// Capture surface for `Recording Produced No Conversation`.
///
/// Phone mic is [phone]. Pendant and other hardware that is not an Apple Watch
/// is [omi]. The watch app is [watch].
enum RecordingSurface { phone, omi, watch }

enum EmptyRecordingReason { emptyDeleted, discarded, nullResult }

/// Why POST /v1/conversations did not return a conversation row.
enum ProcessAbsence { notFound, transport, emptyBody }

class InProgressProcessOutcome {
  const InProgressProcessOutcome({this.response, this.absence});

  final CreateConversationResponse? response;
  final ProcessAbsence? absence;
}

class RecordingCompletionFacts {
  const RecordingCompletionFacts({
    required this.source,
    required this.durationSeconds,
    required this.transcriptObserved,
  });

  final String source;
  final int durationSeconds;
  final bool transcriptObserved;
}

/// What Home should say when the visible list is empty because a recording
/// never became a conversation the user can open.
enum HomeEmptyExplanation { none, tooShort, discardedOnly }

/// First announcement, a later capture of the same discarded-only list, or
/// a list that is not discarded-only.
enum DiscardedOnlyClaim { shown, alreadyShown, notDiscardedOnly }

/// Telemetry sources are `phone_mic_*` and `pendant_*`. Watch is not one of
/// those strings; [recordingSurfaceForSession] reads it from the device.
RecordingSurface recordingSurfaceForTelemetry(String? raw) {
  final value = (raw ?? '').toLowerCase();
  if (value == 'phone' || value.startsWith('phone')) return RecordingSurface.phone;
  return RecordingSurface.omi;
}

RecordingSurface recordingSurfaceForConversation(ConversationSource? source) {
  return switch (source) {
    ConversationSource.phone => RecordingSurface.phone,
    ConversationSource.apple_watch => RecordingSurface.watch,
    _ => RecordingSurface.omi,
  };
}

/// Prefer the conversation or the session device. The telemetry string is only
/// the phone-versus-pendant fallback when neither source is known.
RecordingSurface recordingSurfaceForSession({
  ConversationSource? conversationSource,
  ConversationSource? deviceSource,
  String? telemetrySource,
}) {
  final classified = conversationSource ?? deviceSource;
  if (classified != null) return recordingSurfaceForConversation(classified);
  return recordingSurfaceForTelemetry(telemetrySource);
}

/// True when every known conversation was discarded, so Home would otherwise
/// show the new-user empty state.
bool onlyDiscardedConversations(Iterable<bool> discardedFlags) {
  final flags = discardedFlags.toList();
  return flags.isNotEmpty && flags.every((discarded) => discarded);
}
