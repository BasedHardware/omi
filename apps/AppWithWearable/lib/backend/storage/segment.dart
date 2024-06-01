//  {
//         "start": 78.328,
//         "end": 79.009,
//         "text": " That's cool.",
//         "speaker": "SPEAKER_00",
//         "is_user": false
//     },
class TranscriptSegment {
  String text;
  String speaker;
  bool isUser;
  double start;
  double end;

  TranscriptSegment({
    required this.text,
    required this.speaker,
    required this.isUser,
    required this.start,
    required this.end,
  });

  @override
  String toString() {
    return 'TranscriptSegment: {text: $text, speaker: $speaker, isUser: $isUser, start: $start, end: $end}';
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
      'is_user': isUser,
      'start': start,
      'end': end,
    };
  }

  static List<TranscriptSegment> fromJsonList(List<dynamic> jsonList) {
    return jsonList.map((e) => TranscriptSegment.fromJson(e)).toList();
  }
}
