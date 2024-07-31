class TranscriptSegment {
  final String text;
  final String? speaker;
  final int? speakerId;
  final bool isUser;
  final double start;
  final double end;

  TranscriptSegment({
    required this.text,
    this.speaker,
    this.speakerId,
    required this.isUser,
    required this.start,
    required this.end,
  });

  factory TranscriptSegment.fromJson(Map<String, dynamic> json) {
    return TranscriptSegment(
      text: json['text'],
      speaker: json['speaker'],
      speakerId: json['speakerId'],
      isUser: json['is_user'],
      start: json['start'].toDouble(),
      end: json['end'].toDouble(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'text': text,
      'speaker': speaker,
      'speakerId': speakerId,
      'is_user': isUser,
      'start': start,
      'end': end,
    };
  }
}
