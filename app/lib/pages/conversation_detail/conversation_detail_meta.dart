import 'package:omi/backend/schema/transcript_segment.dart';

/// The facts the conversation header states, computed apart from the widgets
/// so the rules stay testable.
abstract final class ConversationDetailMeta {
  /// "You, Dana +2": the first [limit] names, then how many more.
  static String peopleSummary(List<String> names, {int limit = 2}) {
    if (names.length <= limit) return names.join(', ');
    return '${names.take(limit).join(', ')} +${names.length - limit}';
  }

  /// Who spoke, by the names the transcript shows: [you] for the owner, a named
  /// person, or "Speaker N". First-appearance order, with the owner first.
  static List<String> participants(
    List<TranscriptSegment> segments, {
    required String you,
    required String Function(int speakerId) speaker,
    String? Function(String personId)? personName,
  }) {
    final seen = <String>{};
    final result = <String>[];
    if (segments.any((segment) => segment.isUser)) {
      seen.add(you);
      result.add(you);
    }
    for (final segment in segments) {
      if (segment.isUser) continue;
      final personId = segment.personId;
      final named = personId == null ? null : personName?.call(personId);
      final name = (named != null && named.trim().isNotEmpty) ? named : speaker(segment.speakerId);
      if (seen.add(name)) result.add(name);
    }
    return result;
  }
}
