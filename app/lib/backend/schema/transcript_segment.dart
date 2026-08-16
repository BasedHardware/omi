import 'package:omi/backend/preferences.dart';
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
  }) {
    final parts = speaker?.split('_') ?? [];
    speakerId = parts.length > 1 ? (int.tryParse(parts[1]) ?? 0) : 0;
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

  // Factory constructor to create a new Message instance from a map
  factory TranscriptSegment.fromJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedTranscriptSegment.fromJson(json);
    return TranscriptSegment.fromGenerated(generated);
  }

  factory TranscriptSegment.fromGenerated(wire.GeneratedTranscriptSegment generated) {
    return TranscriptSegment(
      id: generated.id ?? '',
      text: generated.text,
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

  static String segmentsAsString(
    List<TranscriptSegment> segments, {
    bool includeTimestamps = false,
    String Function(String speakerId)? speakerLabelBuilder,
  }) {
    String transcript = '';
    var userName = SharedPreferencesUtil().givenName;
    var people = SharedPreferencesUtil().cachedPeople;
    var peopleMap = {for (var p in people) p.id: p.name};

    includeTimestamps = includeTimestamps && TranscriptSegment.canDisplaySeconds(segments);
    for (var segment in segments) {
      var segmentText = segment.text.trim();
      var timestampStr = includeTimestamps ? '[${segment.getTimestampString()}]' : '';
      if (segment.isUser) {
        transcript += '$timestampStr ${userName.isEmpty ? 'User' : userName}: $segmentText ';
      } else {
        String speakerName;
        if (segment.personId != null && peopleMap.containsKey(segment.personId)) {
          speakerName = peopleMap[segment.personId]!;
        } else {
          var displayId = '${getDisplaySpeakerId(segment.speakerId, segments)}';
          speakerName = speakerLabelBuilder != null ? speakerLabelBuilder(displayId) : 'Speaker $displayId';
        }
        transcript += '$timestampStr $speakerName: $segmentText ';
      }
      transcript += '\n\n';
    }
    return transcript.trim();
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

  /// Gets the display speaker ID (1-indexed) for a segment.
  /// Normalizes based on the minimum speaker ID in the conversation.
  ///
  /// Examples:
  /// - If conversation has speakers [0, 1, 2] -> displays as [1, 2, 3]
  /// - If conversation has speakers [1, 2, 3] -> displays as [1, 2, 3]
  /// - If conversation has speakers [5, 6] -> displays as [1, 2]
  static int getDisplaySpeakerId(int speakerId, List<TranscriptSegment> segments) {
    if (segments.isEmpty) return speakerId + 1;

    // Find minimum speaker ID among non-user segments
    int? minSpeakerId;
    for (var segment in segments) {
      if (!segment.isUser) {
        if (minSpeakerId == null || segment.speakerId < minSpeakerId) {
          minSpeakerId = segment.speakerId;
        }
      }
    }

    // If no non-user segments found, default to simple +1
    if (minSpeakerId == null) return speakerId + 1;

    // Normalize: subtract minimum and add 1 to make it 1-indexed
    return speakerId - minSpeakerId + 1;
  }
}
