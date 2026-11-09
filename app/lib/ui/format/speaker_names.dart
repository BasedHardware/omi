import 'dart:ui' show Locale;

import 'package:intl/intl.dart';

import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/ui/format/diarization_label.dart';

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
  static const maxUnnamedVoices = 8;

  // Display qualification only; voice linking still requires backend acoustic evidence.
  static const minLiveVoiceSeconds = 5.0;
  SpeakerNames._(this._ordinals, this._peopleById, this._ownerName, this._l10n, this._unresolved, this._collapsed,
      this._deferShortVoices);

  /// Resolver for [segments] (the whole conversation, so numbering matches every surface).
  ///
  /// [people] are the user's people (live list first; callers without one pass the cached list).
  /// [ownerName] replaces "You" for the owner — pass the user's given name for exports only.
  factory SpeakerNames.forSegments(
    List<TranscriptSegment> segments, {
    List<Person> people = const [],
    String? ownerName,
    bool unresolved = false,
    bool deferShortVoices = false,
    required AppLocalizations l10n,
  }) {
    return SpeakerNames._(
      {
        for (final entry in (deferShortVoices ? _qualifiedLiveOrdinals(segments) : denseOrdinals(segments)).entries)
          DiarizationLabel.fromRaw(entry.key): entry.value
      },
      {for (final person in people) person.id: person},
      ownerName == null || ownerName.trim().isEmpty ? null : ownerName.trim(),
      l10n,
      unresolved,
      _surplusVoices(segments, people),
      deferShortVoices,
    );
  }

  final Map<DiarizationLabel, int> _ordinals;
  final Set<DiarizationLabel> _collapsed;
  final Map<String, Person> _peopleById;
  final String? _ownerName;
  final AppLocalizations _l10n;
  final bool _unresolved;
  final bool _deferShortVoices;

  /// The name for [segment]'s speaker. [person] overrides the people lookup (callers that already
  /// resolved it).
  String forSegment(TranscriptSegment segment, {Person? person}) {
    if (segment.sttProvider?.startsWith('on_device:') == true) return '';
    if (segment.isUser) return _ownerName ?? _l10n.you;
    if (segment.speakerId == omiSpeakerId) return _l10n.omiAppName;
    final assigned = person ?? (segment.personId == null ? null : _peopleById[segment.personId]);
    if (assigned != null && assigned.name.trim().isNotEmpty) return assigned.name;
    return anonymousName(segment.speakerId);
  }

  /// Server-projected Review excerpts have resolved names, but no complete diarization map.
  /// Localize the owner and unnamed speaker through the same speaker naming authority.
  static String excerptLabel({required bool isUser, String? speakerLabel, required AppLocalizations l10n}) {
    if (isUser) return l10n.you;
    final label = speakerLabel?.trim() ?? '';
    if (label == 'You') return l10n.you;
    if (label == 'Others') return l10n.othersSpeakerLabel;
    final anonymous = RegExp(r'^Speaker ([A-Z]+)$').firstMatch(label);
    if (anonymous != null) {
      final ordinal = anonymous.group(1)!.codeUnits.fold<int>(0, (n, c) => n * 26 + c - 64);
      return l10n.speakerWithId('$ordinal');
    }
    if (label.isEmpty ||
        label == 'Speaker' ||
        label == 'Unknown speaker' ||
        RegExp(r'^(?:Speaker[ _]?|SPEAKER_)\d+$', caseSensitive: false).hasMatch(label)) {
      return l10n.unnamedSpeakerLabel;
    }
    return label;
  }

  /// "Speaker N" for a diarized [speakerId], with N from [ordinalFor].
  String anonymousName(int speakerId) {
    if (speakerId == omiSpeakerId) return _l10n.omiAppName;
    if (_unresolved || (_deferShortVoices && !_ordinals.containsKey(DiarizationLabel.fromRaw(speakerId)))) {
      return _l10n.unnamedSpeakerLabel;
    }
    if (_collapsed.contains(DiarizationLabel.fromRaw(speakerId))) return _l10n.othersSpeakerLabel;
    return _l10n.speakerWithId('${ordinalFor(speakerId)}');
  }

  /// The dense 1-based number shown for [speakerId]. An id this conversation has not seen yet
  /// (a speaker that joined after [forSegments] ran) is numbered after the known ones.
  int ordinalFor(int speakerId) =>
      _ordinals.putIfAbsent(DiarizationLabel.fromRaw(speakerId), () => _ordinals.length + 1);

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

  /// Allocate at the turn that completes five non-overlapping placed seconds.
  /// A short early voice qualifying later cannot renumber an already qualified voice.
  static Map<int, int> _qualifiedLiveOrdinals(List<TranscriptSegment> segments) {
    final ranges = <int, List<(double, double)>>{};
    for (final segment in segments) {
      if (segment.isUser || segment.speakerId == omiSpeakerId) continue;
      final start = segment.start, end = segment.end;
      if (!start.isFinite || !end.isFinite || start < 0 || end <= start) continue;
      ranges.putIfAbsent(segment.speakerId, () => []).add((start, end));
    }
    final qualifiedAt = <int, double>{};
    for (final entry in ranges.entries) {
      final voiceRanges = entry.value..sort((a, b) => a.$1.compareTo(b.$1));
      var coveredEnd = double.negativeInfinity, seconds = 0.0;
      for (final range in voiceRanges) {
        final uncoveredStart = range.$1 > coveredEnd ? range.$1 : coveredEnd;
        final fresh = range.$2 > uncoveredStart ? range.$2 - uncoveredStart : 0.0;
        if (seconds + fresh >= minLiveVoiceSeconds) {
          qualifiedAt[entry.key] = uncoveredStart + minLiveVoiceSeconds - seconds;
          break;
        }
        seconds += fresh;
        if (range.$2 > coveredEnd) coveredEnd = range.$2;
      }
    }
    final appearance = {for (final entry in ranges.keys.indexed) entry.$2: entry.$1};
    final qualified = qualifiedAt.keys.toList()
      ..sort((a, b) {
        final byTime = qualifiedAt[a]!.compareTo(qualifiedAt[b]!);
        return byTime != 0 ? byTime : appearance[a]!.compareTo(appearance[b]!);
      });
    final ordinals = {for (final entry in qualified.indexed) entry.$2: entry.$1 + 1};
    return ordinals;
  }

  /// Presentation mitigation only: keep at most seven substantial unknown voices plus Others.
  /// Known people and the owner are never merged. Raw identity remains available for correction.
  static Set<DiarizationLabel> _surplusVoices(List<TranscriptSegment> segments, List<Person> people) {
    final named = {
      for (final person in people)
        if (person.name.trim().isNotEmpty) person.id
    };
    final protected = <DiarizationLabel>{};
    final seconds = <DiarizationLabel, double>{};
    for (final segment in segments) {
      final key = DiarizationLabel.fromRaw(segment.speakerId);
      if (segment.isUser || segment.speakerId == omiSpeakerId || named.contains(segment.personId)) {
        protected.add(key);
      }
      final duration = segment.end - segment.start;
      seconds.update(key, (value) => value + (duration.isFinite && duration > 0 ? duration : 0),
          ifAbsent: () => duration.isFinite && duration > 0 ? duration : 0);
    }
    seconds.removeWhere((key, _) => protected.contains(key));
    if (seconds.length <= maxUnnamedVoices) return {};
    final ranked = seconds.keys.toList()..sort((a, b) => seconds[b]!.compareTo(seconds[a]!));
    final retained = ranked.where((key) => seconds[key]! >= 3).take(maxUnnamedVoices - 1).toSet();
    return seconds.keys.where((key) => !retained.contains(key)).toSet();
  }

  /// Strings for exports built without a `BuildContext`: the app's locale as intl knows it
  /// (`Intl.defaultLocale`, set from the app locale at startup), falling back to English.
  static AppLocalizations contextFreeL10n() {
    final name = Intl.defaultLocale ?? Intl.systemLocale;
    final parts = name.split(RegExp('[_-]'));
    for (final locale in [if (parts.length > 1) Locale(parts[0], parts[1]), Locale(parts[0]), const Locale('en')]) {
      try {
        return lookupAppLocalizations(locale);
      } catch (_) {
        continue;
      }
    }
    return lookupAppLocalizations(const Locale('en'));
  }
}
