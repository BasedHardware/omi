import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/format/speaker_names.dart';
import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;

// Phase 4.1 — pure 1:1 thin wrapper: both fields (String lang, String text) match
// GeneratedTranslation exactly with no behavior, so it is a typedef.
// GeneratedTranslation provides fromJson/toJson; the deleted hand-written
// fromJsonList/toGenerated had no callers.
typedef Translation = wire.GeneratedTranslation;

class TranscriptSegment {
  String id;
  late int idx;

  String text;
  String? speaker;
  late int speakerId;
  bool isUser;
  String? personId;
  double start;
  double end;
  List<Translation> translations = [];
  bool speechProfileProcessed;
  String? sttProvider;

  TranscriptSegment({
    required this.id,
    required this.text,
    required this.speaker,
    required this.isUser,
    required this.personId,
    required this.start,
    required this.end,
    required this.translations,
    this.speechProfileProcessed = true,
    this.sttProvider,
    int? speakerId,
  }) {
    final parts = speaker?.split('_') ?? [];
    this.speakerId = speakerId ?? (parts.length > 1 ? (int.tryParse(parts[1]) ?? 0) : 0);
  }

  @override
  String toString() {
    return 'TranscriptSegment: {id: $id text: $text, speaker: $speakerId, isUser: $isUser, start: $start, end: $end}';
  }

  String getTimestampString() {
    var start = Duration(seconds: this.start.toInt());
    var end = Duration(seconds: this.end.toInt());
    return '${start.inHours.toString().padLeft(2, '0')}:${(start.inMinutes % 60).toString().padLeft(2, '0')}:${(start.inSeconds % 60).toString().padLeft(2, '0')} - ${end.inHours.toString().padLeft(2, '0')}:${(end.inMinutes % 60).toString().padLeft(2, '0')}:${(end.inSeconds % 60).toString().padLeft(2, '0')}';
  }

  /// Whitespace-delimited word count. Shared with [ServerConversation.isFailedTitleRecoverable]
  /// so the ≥5-word "real content" heuristic has one source of truth.
  int get wordCount => text.split(RegExp(r'\s+')).where((word) => word.isNotEmpty).length;

  // Factory constructor to create a new Message instance from a map
  factory TranscriptSegment.fromJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedTranscriptSegment.fromJson(json);
    return TranscriptSegment.fromGenerated(generated);
  }

  factory TranscriptSegment.fromGenerated(wire.GeneratedTranscriptSegment generated) {
    return TranscriptSegment(
      id: generated.id ?? '',
      text: generated.text,
      speakerId: generated.speakerId,
      speaker: generated.speaker ?? 'SPEAKER_00',
      isUser: generated.isUser,
      personId: generated.personId,
      start: generated.start,
      end: generated.end,
      translations: generated.translations ?? const [],
      speechProfileProcessed: generated.speechProfileProcessed,
      sttProvider: generated.sttProvider,
    );
  }

  wire.GeneratedTranscriptSegment toGenerated() {
    return wire.GeneratedTranscriptSegment(
      id: id,
      text: text,
      speaker: speaker,
      speakerId: speakerId,
      isUser: isUser,
      personId: personId,
      start: start,
      end: end,
      translations: translations,
      speechProfileProcessed: speechProfileProcessed,
      sttProvider: sttProvider,
    );
  }

  // Method to convert a Message instance into a map
  Map<String, dynamic> toJson() {
    return toGenerated().toJson();
  }

  static List<TranscriptSegment> updateSegments(
    List<TranscriptSegment> segments,
    List<TranscriptSegment> updateSegments,
  ) {
    if (updateSegments.isEmpty) return [];

    if (segments.isEmpty) return updateSegments;

    // Replace existing segments with the same ID
    Map<String, TranscriptSegment> updateSegmentMap = {};
    for (var segment in updateSegments) {
      updateSegmentMap[segment.id] = segment;
    }
    for (int i = 0; i < segments.length; i++) {
      String segmentId = segments[i].id;
      if (updateSegmentMap.containsKey(segmentId)) {
        segments[i] = updateSegmentMap[segmentId]!;
        updateSegmentMap.remove(segmentId);
      }
    }

    // remaining
    return updateSegments.where((segment) => updateSegmentMap.containsKey(segment.id)).toList();
  }

  static combineSegments(
    List<TranscriptSegment> segments,
    List<TranscriptSegment> newSegments, {
    int toAddSeconds = 0,
    double toRemoveSeconds = 0,
  }) {
    if (newSegments.isEmpty) return;

    for (var segment in newSegments) {
      segment.start -= toRemoveSeconds;
      segment.end -= toRemoveSeconds;

      segment.start += toAddSeconds;
      segment.end += toAddSeconds;
    }

    var joinedSimilarSegments = <TranscriptSegment>[];
    for (var newSegment in newSegments) {
      // TODO: bad edge case because of using deepgram
      // - previous segments before ws2 is switched on the backend, (duration of speech profile) will not be assigned.
      bool isNotEmpty = joinedSimilarSegments.isNotEmpty;
      bool isSameUser = isNotEmpty && joinedSimilarSegments.last.isUser == newSegment.isUser;
      bool isSameSpeaker = isNotEmpty && joinedSimilarSegments.last.speaker == newSegment.speaker;

      if (isNotEmpty && isSameSpeaker && isSameUser) {
        joinedSimilarSegments.last.text += ' ${newSegment.text}';
        joinedSimilarSegments.last.end = newSegment.end;
      } else {
        joinedSimilarSegments.add(newSegment);
      }
    }

    if (joinedSimilarSegments.isEmpty) return;

    bool isNotEmpty = segments.isNotEmpty;
    bool isSameUser = isNotEmpty && segments.last.isUser == joinedSimilarSegments[0].isUser;
    bool isSameSpeaker = isNotEmpty && segments.last.speaker == joinedSimilarSegments[0].speaker;
    bool withinThreshold = isNotEmpty && (joinedSimilarSegments[0].start - segments.last.end < 30);

    if (isNotEmpty && isSameSpeaker && isSameUser && withinThreshold) {
      segments.last.text += ' ${joinedSimilarSegments[0].text}';
      segments.last.end = joinedSimilarSegments[0].end;
      joinedSimilarSegments.removeAt(0);
    }

    segments.addAll(joinedSimilarSegments);
  }

  /// Plain-text transcript for copy, share and export, one "[time] Name: text" block per segment.
  ///
  /// Names come from [SpeakerNames] so they match the screen: the owner is [ownerName] (default:
  /// the user's given name, else the localized "You"), assigned people by name ([people], default
  /// the cached list), Omi as "Omi", everyone else "Speaker N" in the conversation's dense
  /// numbering, localized with [l10n] (default: the app locale via [SpeakerNames.contextFreeL10n]).
  /// Pass [numberingSegments] (the whole conversation) when [segments] is only a slice of it.
  static String segmentsAsString(
    List<TranscriptSegment> segments, {
    bool includeTimestamps = false,
    AppLocalizations? l10n,
    List<Person>? people,
    String? ownerName,
    List<TranscriptSegment>? numberingSegments,
  }) {
    final names = SpeakerNames.forSegments(
      numberingSegments ?? segments,
      people: people ?? SharedPreferencesUtil().cachedPeople,
      ownerName: ownerName ?? SharedPreferencesUtil().givenName,
      l10n: l10n ?? SpeakerNames.contextFreeL10n(),
    );
    final buffer = StringBuffer();
    includeTimestamps = includeTimestamps && TranscriptSegment.canDisplaySeconds(segments);
    for (final segment in segments) {
      final timestampStr = includeTimestamps ? '[${segment.getTimestampString()}]' : '';
      buffer.write('$timestampStr ${names.forSegment(segment)}: ${segment.text.trim()} ');
      buffer.write('\n\n');
    }
    return buffer.toString().trim();
  }

  static bool canDisplaySeconds(List<TranscriptSegment> segments) {
    for (var i = 0; i < segments.length; i++) {
      for (var j = i + 1; j < segments.length; j++) {
        if (segments[i].start > segments[j].end || segments[i].end > segments[j].start) {
          return false;
        }
      }
    }
    return true;
  }

  /// The "Speaker N" number shown for [speakerId] in the conversation made of [segments].
  ///
  /// Dense and 1-based in order of first appearance, skipping the owner and Omi (see
  /// [SpeakerNames]): canonical ids keep their gaps (provider restarts allocate new identities),
  /// the display does not. Assigning a person keeps everyone's number; tagging a speaker as the
  /// owner removes them from the count.
  static int getDisplaySpeakerId(int speakerId, List<TranscriptSegment> segments) {
    final ordinals = SpeakerNames.denseOrdinals(segments);
    return ordinals[speakerId] ?? ordinals.length + 1;
  }
}
