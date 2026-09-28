import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;

/// What a conversation's `speaker_id` values mean. Server-authored.
///
/// Capture restarts its speaker numbering on every reconnect, provider
/// failover and uploaded audio chunk, so the raw ids of a long recording can
/// number in the thousands for a handful of people. Only a resolved or single
/// capture diarization makes ids countable as people; everything else is not.
class ConversationSpeakers {
  /// `resolved` (re-diarized from stored audio), `capture` (one uninterrupted
  /// diarization) or `unavailable`. Kept raw so a future status round-trips.
  final String status;
  final int version;

  /// Voices that spoke enough to count as participants.
  final List<int> participantSpeakerIds;

  const ConversationSpeakers({required this.status, this.version = 1, this.participantSpeakerIds = const []});

  /// Whether [participantSpeakerIds] may be counted as people.
  bool get countable => status == 'resolved' || status == 'capture';

  factory ConversationSpeakers.fromGenerated(wire.GeneratedConversationSpeakers generated) {
    return ConversationSpeakers(
      status: generated.status,
      version: generated.version,
      participantSpeakerIds: generated.participantSpeakerIds,
    );
  }

  wire.GeneratedConversationSpeakers toGenerated() {
    return wire.GeneratedConversationSpeakers(
      status: status,
      version: version,
      participantSpeakerIds: participantSpeakerIds,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}
