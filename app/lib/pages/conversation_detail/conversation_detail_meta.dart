import 'package:omi/backend/schema/transcript_segment.dart';

/// The facts the conversation header states, computed apart from the widgets
/// so the rules stay testable.
abstract final class ConversationDetailMeta {
  /// Who spoke, counting only people with a name (David, 2026-09-24: never label "Speaker 1"):
  /// [named] holds [you] for the owner, then named people in first-appearance order; [unnamed] is
  /// how many distinct speakers have no name.
  static ({List<String> named, int unnamed}) participants(
    List<TranscriptSegment> segments, {
    required String you,
    String? Function(String personId)? personName,
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
    return (named: named, unnamed: unnamedIds.length);
  }

  /// "David", or "David + 3 others" through [summary]; null when nobody is named, so the people
  /// chip hides rather than listing anonymous speakers.
  static String? peopleLabel(
    List<String> named,
    int unnamed, {
    required String Function(String first, int others) summary,
  }) {
    if (named.isEmpty) return null;
    final others = named.length - 1 + unnamed;
    return others == 0 ? named.first : summary(named.first, others);
  }
}
