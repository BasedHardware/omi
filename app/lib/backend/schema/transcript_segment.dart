import 'package:omi/backend/preferences.dart';

class TranscriptSegment {
  String id;

  String text;
  String? speaker;
  late int speakerId;
  bool isUser;
  String? personId;
  double start;
  double end;

  TranscriptSegment({
    required this.id,
    required this.text,
    required this.speaker,
    required this.isUser,
    required this.personId,
    required this.start,
    required this.end,
  }) {
    speakerId = speaker != null ? int.parse(speaker!.split('_')[1]) : 0;
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
    return TranscriptSegment(
      id: json['id'] as String,
      text: json['text'] as String,
      speaker: (json['speaker'] ?? 'SPEAKER_00') as String,
      isUser: (json['is_user'] ?? false) as bool,
      personId: json['person_id'],
      start: double.tryParse(json['start'].toString()) ?? 0.0,
      end: double.tryParse(json['end'].toString()) ?? 0.0,
    );
  }

  // Method to convert a Message instance into a map
  Map<String, dynamic> toJson() {
    return {
      'text': text,
      'speaker': speaker,
      'speaker_id': speakerId,
      'is_user': isUser,
      'start': start,
      'end': end,
    };
  }

  static List<TranscriptSegment> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => TranscriptSegment.fromJson(e)).toList();
  }

  static List<TranscriptSegment> updateSegments(
      List<TranscriptSegment> segments, List<TranscriptSegment> updateSegments) {
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
  }) {
    String transcript = '';
    var userName = SharedPreferencesUtil().givenName;
    includeTimestamps = includeTimestamps && TranscriptSegment.canDisplaySeconds(segments);
    for (var segment in segments) {
      var segmentText = segment.text.trim();
      var timestampStr = includeTimestamps ? '[${segment.getTimestampString()}]' : '';
      if (segment.isUser) {
        transcript += '$timestampStr ${userName.isEmpty ? 'User' : userName}: $segmentText ';
      } else {
        transcript += '$timestampStr Speaker ${segment.speakerId}: $segmentText ';
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
}
