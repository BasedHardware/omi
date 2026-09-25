import 'package:omi/backend/schema/conversation_speakers.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

/// The facts the conversation header states, computed apart from the widgets
/// so the rules stay testable.
abstract final class ConversationDetailMeta {
  /// Who spoke, counting only people with a name (David, 2026-09-24: never label "Speaker 1"):
  /// [named] holds [you] for the owner, then named people in first-appearance order; [unnamed] is
  /// how many unnamed voices took part.
  ///
  /// A speaker id is a person only when the server says so ([speakers] is countable): capture
  /// restarts its numbering per reconnect and uploaded chunk, so a long recording's raw ids can
  /// run into the thousands. Otherwise unnamed voices are not counted, and [uncounted] says some
  /// spoke.
  static ({List<String> named, int unnamed, bool uncounted}) participants(
    List<TranscriptSegment> segments, {
    required String you,
    String? Function(String personId)? personName,
    ConversationSpeakers? speakers,
  }) {
    final named = <String>[];
    final unnamedIds = <int>{};
    if (segments.any((segment) => segment.isUser)) named.add(you);
    for (final segment in segments) {
      if (segment.isUser) continue;
      final personId = segment.personId;
      final name = personId == null ? null : personName?.call(personId)?.trim();
      if (name == null || name.isEmpty) {
        unnamedIds.add(segment.speakerId);
      } else if (!named.contains(name)) {
        named.add(name);
      }
    }
    if (speakers == null || !speakers.countable) {
      return (named: named, unnamed: 0, uncounted: unnamedIds.isNotEmpty);
    }
    final participants = speakers.participantSpeakerIds.toSet();
    return (named: named, unnamed: unnamedIds.where(participants.contains).length, uncounted: false);
  }

  /// "David", "David + 3 others" through [summary], or "David + others" through [uncountedSummary]
  /// when other voices spoke but cannot be counted; null when nobody is named, so the people chip
  /// hides rather than listing anonymous speakers.
  static String? peopleLabel(
    List<String> named,
    int unnamed, {
    bool uncounted = false,
    required String Function(String first, int others) summary,
    required String Function(String first) uncountedSummary,
  }) {
    if (named.isEmpty) return null;
    if (uncounted) return uncountedSummary(named.first);
    final others = named.length - 1 + unnamed;
    return others == 0 ? named.first : summary(named.first, others);
  }
}
