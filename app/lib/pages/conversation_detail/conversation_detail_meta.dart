import 'package:omi/backend/schema/conversation_speakers.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/ui/format/speaker_names.dart';
import 'package:omi/utils/constants.dart';

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
    final named = EpisodePresentation.participants(segments, const [], SpeakerNames.contextFreeL10n(),
        ownerLabel: you, personName: personName);
    final unnamedIds = <int>{};
    for (final segment in segments) {
      if (segment.isUser || segment.speakerId == omiSpeakerId) continue;
      final personId = segment.personId;
      final name = personId == null ? null : personName?.call(personId)?.trim();
      if (name == null || name.isEmpty) {
        unnamedIds.add(segment.speakerId);
      }
    }
    if (speakers == null || !speakers.countable || unnamedIds.length > SpeakerNames.maxUnnamedVoices) {
      return (named: named, unnamed: 0, uncounted: unnamedIds.isNotEmpty);
    }
    final participants = speakers.participantSpeakerIds.toSet();
    return (named: named, unnamed: unnamedIds.where(participants.contains).length, uncounted: false);
  }

  /// The people chip's avatars: the first two named people's initials, then one circle counting
  /// everyone else ("1" for one more voice), or "+" when other voices spoke but cannot be counted.
  static List<String> avatars(List<String> named, int unnamed, {bool uncounted = false}) {
    final shown = [for (final name in named.take(2)) _initial(name)];
    if (uncounted) return [...shown, '+'];
    final rest = named.length - shown.length + unnamed;
    return rest > 0 ? [...shown, '$rest'] : shown;
  }

  static String _initial(String name) {
    final trimmed = name.trim();
    return trimmed.isEmpty ? '?' : String.fromCharCode(trimmed.runes.first).toUpperCase();
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
