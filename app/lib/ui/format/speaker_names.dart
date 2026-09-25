import 'dart:ui' show Locale;

import 'package:intl/intl.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/utils/constants.dart';

/// The one source of speaker names for a conversation (docs/ux-contract.md §9): transcript
/// bubbles, the edit-segment and tag-speaker sheets, participant lists, filters, and every copied,
/// shared or exported transcript.
///
/// * the owner → "You" in the app; in exports the owner's given name when set, else "You"
/// * a speaker assigned to a person → that person's name (the live people list first)
/// * Omi's own speaker → "Omi"
/// * anyone else → "Speaker N", where N counts the conversation's anonymous-or-named speakers
///   1, 2, 3… in order of first appearance. Never a raw diarization id, never a gap: a
///   conversation whose owner is `SPEAKER_00` reads "You, Speaker 1, Speaker 2", not "Speaker 2,
///   Speaker 3". Assigning a person to a speaker does not renumber the others.
///
/// ```dart
/// final names = SpeakerNames.forSegments(conversation.transcriptSegments, people: people, l10n: context.l10n);
/// Text(names.forSegment(segment));
/// ```
class SpeakerNames {
  SpeakerNames._(this._ordinals, this._peopleById, this._ownerName, this._l10n);

  /// Resolver for [segments] (the whole conversation, so numbering matches every surface).
  ///
  /// [people] are the user's people (live list first; callers without one pass the cached list).
  /// [ownerName] replaces "You" for the owner — pass the user's given name for exports only.
  factory SpeakerNames.forSegments(
    List<TranscriptSegment> segments, {
    List<Person> people = const [],
    String? ownerName,
    required AppLocalizations l10n,
  }) {
    return SpeakerNames._(
      denseOrdinals(segments),
      {for (final person in people) person.id: person},
      ownerName == null || ownerName.trim().isEmpty ? null : ownerName.trim(),
      l10n,
    );
  }

  final Map<int, int> _ordinals;
  final Map<String, Person> _peopleById;
  final String? _ownerName;
  final AppLocalizations _l10n;

  /// The name for [segment]'s speaker. [person] overrides the people lookup (callers that already
  /// resolved it).
  String forSegment(TranscriptSegment segment, {Person? person}) {
    if (segment.isUser) return _ownerName ?? _l10n.you;
    if (segment.speakerId == omiSpeakerId) return _l10n.omiAppName;
    final assigned = person ?? (segment.personId == null ? null : _peopleById[segment.personId]);
    if (assigned != null && assigned.name.trim().isNotEmpty) return assigned.name;
    return anonymousName(segment.speakerId);
  }

  /// "Speaker N" for a diarized [speakerId], with N from [ordinalFor].
  String anonymousName(int speakerId) {
    if (speakerId == omiSpeakerId) return _l10n.omiAppName;
    return _l10n.speakerWithId('${ordinalFor(speakerId)}');
  }

  /// The dense 1-based number shown for [speakerId]. An id this conversation has not seen yet
  /// (a speaker that joined after [forSegments] ran) is numbered after the known ones.
  int ordinalFor(int speakerId) => _ordinals.putIfAbsent(speakerId, () => _ordinals.length + 1);

  /// Speaker id → dense 1-based number, in order of first appearance, skipping the owner's
  /// segments and Omi.
  static Map<int, int> denseOrdinals(List<TranscriptSegment> segments) {
    final ordinals = <int, int>{};
    for (final segment in segments) {
      if (segment.isUser || segment.speakerId == omiSpeakerId) continue;
      ordinals.putIfAbsent(segment.speakerId, () => ordinals.length + 1);
    }
    return ordinals;
  }

  /// Strings for exports built without a `BuildContext`: the app's locale as intl knows it
  /// (`Intl.defaultLocale`, set from the app locale at startup), falling back to English.
  static AppLocalizations contextFreeL10n() {
    final name = Intl.defaultLocale ?? Intl.systemLocale;
    final parts = name.split(RegExp('[_-]'));
    for (final locale in [
      if (parts.length > 1) Locale(parts[0], parts[1]),
      Locale(parts[0]),
      const Locale('en'),
    ]) {
      try {
        return lookupAppLocalizations(locale);
      } catch (_) {
        continue;
      }
    }
    return lookupAppLocalizations(const Locale('en'));
  }
}
