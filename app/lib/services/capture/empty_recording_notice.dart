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

const int shortPhoneRecordingSeconds = 30;

RecordingSurface recordingSurfaceForSource(String? raw) {
  final value = (raw ?? '').toLowerCase();
  if (value.contains('watch')) return RecordingSurface.watch;
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

/// A missing process body. A 404 and a 200 without a conversation are the
/// empty-delete path. A missing HTTP response is [EmptyRecordingReason.nullResult].
EmptyRecordingReason? reasonForMissingConversation({
  required bool hasResponse,
  required bool hasConversation,
  ProcessAbsence? absence,
}) {
  if (hasConversation) return null;
  if (hasResponse) return EmptyRecordingReason.emptyDeleted;
  if (absence == ProcessAbsence.notFound || absence == ProcessAbsence.emptyBody) {
    return EmptyRecordingReason.emptyDeleted;
  }
  return EmptyRecordingReason.nullResult;
}

/// Immediate explanation for a phone stop that never observed speech and
/// stayed under 30 seconds. Pendant and watch stops wait for a process result
/// so a late transcript is not described as "too short".
bool shouldExplainShortPhoneStop({
  required RecordingSurface surface,
  required int durationSeconds,
  required bool transcriptObserved,
  required bool conversationDelivered,
}) {
  if (conversationDelivered || transcriptObserved) return false;
  if (surface != RecordingSurface.phone) return false;
  return durationSeconds < shortPhoneRecordingSeconds;
}

/// True when every known conversation was discarded, so Home would otherwise
/// show the new-user empty state.
bool onlyDiscardedConversations(Iterable<bool> discardedFlags) {
  final flags = discardedFlags.toList();
  return flags.isNotEmpty && flags.every((discarded) => discarded);
}
