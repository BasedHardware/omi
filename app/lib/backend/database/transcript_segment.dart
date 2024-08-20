import 'dart:convert';

import 'package:friend_private/backend/preferences.dart';
import 'package:objectbox/objectbox.dart';

@Entity()
class TranscriptSegment {
  @Id()
  int id = 0;

  String text;
  String? speaker;
  late int speakerId;
  bool isUser;

  // @Property(type: PropertyType.date)
  // DateTime? createdAt;
  double start;
  double end;

  TranscriptSegment({
    required this.text,
    required this.speaker,
    required this.isUser,
    required this.start,
    required this.end,
    // this.createdAt,
  }) {
    speakerId = speaker != null ? int.parse(speaker!.split('_')[1]) : 0;
    // createdAt ??= DateTime.now(); // TODO: -30 seconds + start time ? max(now, (now-30)
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
      text: json['text'] as String,
      speaker: (json['speaker'] ?? 'SPEAKER_00') as String,
      isUser: (json['is_user'] ?? false) as bool,
      start: json['start'] as double,
      end: json['end'] as double,
      // createdAt: json['created_at'] != null ? DateTime.parse(json['created_at']) : null,
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

  static cleanSegments(List<TranscriptSegment> segments) {
    var hallucinations = ['Thank you.', 'I don\'t know what to do,', 'I\'m', 'It was the worst case.', 'and,'];
    // TODO: do this with any words that gets repeated twice
    // - Replicate apparently has much more hallucinations
    for (var i = 0; i < segments.length; i++) {
      for (var hallucination in hallucinations) {
        segments[i].text = segments[i]
            .text
            .replaceAll('$hallucination $hallucination $hallucination', '')
            .replaceAll('$hallucination $hallucination', '')
            .replaceAll('  ', ' ')
            .trim();
      }
    }
    // remove empty segments
    segments.removeWhere((element) => element.text.isEmpty);
  }

  static combineSegments(
    List<TranscriptSegment> segments,
    List<TranscriptSegment> newSegments, {
    int toAddSeconds = 0,
    double toRemoveSeconds = 0,
  }) {
    if (newSegments.isEmpty) return;
    // print('toAddSeconds: $toAddSeconds toRemoveSeconds: $toRemoveSeconds');

    for (var segment in newSegments) {
      segment.start -= toRemoveSeconds;
      segment.end -= toRemoveSeconds;

      segment.start += toAddSeconds;
      segment.end += toAddSeconds;
    }

    var joinedSimilarSegments = <TranscriptSegment>[];
    for (var newSegment in newSegments) {
      if (joinedSimilarSegments.isNotEmpty &&
          (joinedSimilarSegments.last.speaker == newSegment.speaker ||
              (joinedSimilarSegments.last.isUser && newSegment.isUser))) {
        joinedSimilarSegments.last.text += ' ${newSegment.text}';
        joinedSimilarSegments.last.end = newSegment.end;
      } else {
        joinedSimilarSegments.add(newSegment);
      }
    }
    // segments is not empty
    // prev segment speaker is same as first new segment speaker || prev segment is user and first new segment is user
    // and the difference between the end of the last segment and the start of the first new segment is less than 30 seconds

    if (segments.isNotEmpty &&
        (segments.last.speaker == joinedSimilarSegments[0].speaker ||
            (segments.last.isUser && joinedSimilarSegments[0].isUser)) &&
        (joinedSimilarSegments[0].start - segments.last.end < 30)) {
      segments.last.text += ' ${joinedSimilarSegments[0].text}';
      segments.last.end = joinedSimilarSegments[0].end;
      // let's not switch to user, if the 1st segment is not, it will be always the user basically.
      // if (joinedSimilarSegments[0].isUser) segments.last.isUser = true;
      joinedSimilarSegments.removeAt(0);
    }

    cleanSegments(segments);
    cleanSegments(joinedSimilarSegments);

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
