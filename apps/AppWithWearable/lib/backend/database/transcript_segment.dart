import 'package:objectbox/objectbox.dart';

@Entity()
class TranscriptSegment {
  @Id()
  int id = 0;

  String text;
  String? speaker;
  late int speakerId;
  bool isUser;
  double start;
  double end;

  TranscriptSegment({
    required this.text,
    required this.speaker,
    required this.isUser,
    required this.start,
    required this.end,
  }) {
    speakerId = speaker != null ? int.parse(speaker!.split('_')[1]) : 0;
  }

  @override
  String toString() {
    return 'TranscriptSegment: {id: $id text: $text, speaker: $speakerId, isUser: $isUser, start: $start, end: $end}';
  }

  // Factory constructor to create a new Message instance from a map
  factory TranscriptSegment.fromJson(Map<String, dynamic> json) {
    return TranscriptSegment(
      text: json['text'] as String,
      speaker: (json['speaker'] ?? 'SPEAKER_00') as String,
      isUser: json['is_user'] as bool,
      start: json['start'] as double,
      end: json['end'] as double,
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

  static combineSegments(List<TranscriptSegment> segments, List<TranscriptSegment> data) {
    if (data.isEmpty) return;
    var joinedSimilarSegments = <TranscriptSegment>[];
    for (var value in data) {
      if (joinedSimilarSegments.isNotEmpty &&
          (joinedSimilarSegments.last.speaker == value.speaker ||
              (joinedSimilarSegments.last.isUser && value.isUser))) {
        joinedSimilarSegments.last.text += ' ${value.text}';
      } else {
        joinedSimilarSegments.add(value);
      }
    }

    if (segments.isNotEmpty &&
        (segments.last.speaker == joinedSimilarSegments[0].speaker ||
            (segments.last.isUser && joinedSimilarSegments[0].isUser)) &&
        segments.last.text.split(' ').length < 200) {
      // for better UI included last line segments.last.text.split(' ').length < 200
      // so even if speaker 0 then speaker 0 again (same thing), it will look better
      segments.last.text += ' ${joinedSimilarSegments[0].text}';
      joinedSimilarSegments.removeAt(0);
    }

    cleanSegments(segments);
    cleanSegments(joinedSimilarSegments);

    segments.addAll(joinedSimilarSegments);
  }

  static String buildDiarizedTranscriptMessage(List<TranscriptSegment> segments) {
    String transcript = '';
    for (var segment in segments) {
      if (segment.isUser) {
        transcript += 'You said: ${segment.text} ';
      } else {
        transcript += 'Speaker ${segment.speakerId}: ${segment.text} ';
      }
      transcript += '\n\n';
    }
    return transcript.trim();
  }
}
