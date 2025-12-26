/// Minimal schema for parsing STT responses into TranscriptSegments
/// Only contains fields required by backend: text, start, end, speaker
class SttResponseSchema {
  final String? segmentsPath;
  final String segmentsTextField;
  final String? segmentsStartField;
  final String? segmentsEndField;
  final String? segmentsSpeakerField;
  final String? textPath;
  final double defaultSegmentDuration;

  const SttResponseSchema({
    this.segmentsPath = 'segments',
    this.segmentsTextField = 'text',
    this.segmentsStartField = 'start',
    this.segmentsEndField = 'end',
    this.segmentsSpeakerField,
    this.textPath = 'text',
    this.defaultSegmentDuration = 5.0,
  });

  static const openAI = SttResponseSchema(
    segmentsPath: 'segments',
    segmentsTextField: 'text',
    segmentsStartField: 'start',
    segmentsEndField: 'end',
    textPath: 'text',
  );

  static const deepgram = SttResponseSchema(
    segmentsPath: 'results.channels[0].alternatives[0].words',
    segmentsTextField: 'word',
    segmentsStartField: 'start',
    segmentsEndField: 'end',
    segmentsSpeakerField: 'speaker',
    textPath: 'results.channels[0].alternatives[0].transcript',
  );

  static const googleCloud = SttResponseSchema(
    segmentsPath: 'results[0].alternatives[0].words',
    segmentsTextField: 'word',
    segmentsStartField: 'startTime',
    segmentsEndField: 'endTime',
    segmentsSpeakerField: 'speakerTag',
    textPath: 'results[0].alternatives[0].transcript',
  );

  static const azure = SttResponseSchema(
    segmentsPath: 'recognizedPhrases',
    segmentsTextField: 'nBest[0].display',
    segmentsStartField: 'offsetInTicks',
    segmentsEndField: 'durationInTicks',
    textPath: 'combinedRecognizedPhrases[0].display',
  );

  static const simpleText = SttResponseSchema(
    segmentsPath: null,
    segmentsTextField: 'text',
    textPath: 'text',
  );

  static const falAI = SttResponseSchema(
    segmentsPath: 'chunks',
    segmentsTextField: 'text',
    segmentsStartField: 'timestamp[0]',
    segmentsEndField: 'timestamp[1]',
    textPath: 'text',
  );

  static const gemini = SttResponseSchema(
    segmentsPath: null,
    segmentsTextField: 'text',
    textPath: 'candidates[0].content.parts[0].text',
  );

  /// Deepgram live WebSocket response format
  static const deepgramLive = SttResponseSchema(
    segmentsPath: 'channel.alternatives[0].words',
    segmentsTextField: 'punctuated_word',
    segmentsStartField: 'start',
    segmentsEndField: 'end',
    segmentsSpeakerField: 'speaker',
    textPath: 'channel.alternatives[0].transcript',
  );

  /// Gemini Live WebSocket response format
  static const geminiLive = SttResponseSchema(
    segmentsPath: null,
    segmentsTextField: 'text',
    textPath: 'serverContent.modelTurn.parts[0].text',
    defaultSegmentDuration: 3.0,
  );

  /// OpenAI GPT-4o Transcribe Diarize response format (diarized_json)
  static const openAIDiarize = SttResponseSchema(
    segmentsPath: 'segments',
    segmentsTextField: 'text',
    segmentsStartField: 'start',
    segmentsEndField: 'end',
    segmentsSpeakerField: 'speaker',
    textPath: 'text',
  );

  /// Template names that are live/streaming
  static const Set<String> liveTemplates = {'Deepgram', 'Google Gemini'};

  /// Available templates for custom STT configuration
  static const Map<String, SttResponseSchema> templates = {
    'OpenAI': openAI,
    'OpenAI Diarize': openAIDiarize,
    'Deepgram': deepgramLive,
    'Fal.AI': falAI,
    'Google Gemini': geminiLive,
    'Whisper': openAI,
  };

  factory SttResponseSchema.fromJson(Map<String, dynamic> json) {
    return SttResponseSchema(
      segmentsPath: json['segments_path'] as String?,
      segmentsTextField: json['segments_text_field'] as String? ?? 'text',
      segmentsStartField: json['segments_start_field'] as String?,
      segmentsEndField: json['segments_end_field'] as String?,
      segmentsSpeakerField: json['segments_speaker_field'] as String?,
      textPath: json['text_path'] as String?,
      defaultSegmentDuration: (json['default_segment_duration'] as num?)?.toDouble() ?? 5.0,
    );
  }

  Map<String, dynamic> toJson() => {
        'segments_path': segmentsPath,
        'segments_text_field': segmentsTextField,
        'segments_start_field': segmentsStartField,
        'segments_end_field': segmentsEndField,
        'segments_speaker_field': segmentsSpeakerField,
        'text_path': textPath,
        'default_segment_duration': defaultSegmentDuration,
      };
}

class JsonPathNavigator {
  static dynamic getValue(dynamic json, String? path) {
    if (path == null || path.isEmpty || json == null) return null;

    dynamic current = json;
    for (final segment in _parsePath(path)) {
      if (current == null) return null;

      if (segment.isArrayAccess) {
        if (segment.key.isNotEmpty && current is Map) {
          current = current[segment.key];
        }
        if (current is List && segment.index! < current.length) {
          current = current[segment.index!];
        } else {
          return null;
        }
      } else if (current is Map) {
        current = current[segment.key];
      } else {
        return null;
      }
    }
    return current;
  }

  static List<_PathSegment> _parsePath(String path) {
    final segments = <_PathSegment>[];
    final regex = RegExp(r'([^\.\[\]]+)|\[(\d+)\]');
    String? currentKey;

    for (final match in regex.allMatches(path)) {
      if (match.group(1) != null) {
        if (currentKey != null) segments.add(_PathSegment(currentKey));
        currentKey = match.group(1);
      } else if (match.group(2) != null) {
        segments.add(_PathSegment(currentKey ?? '', index: int.parse(match.group(2)!)));
        currentKey = null;
      }
    }
    if (currentKey != null) segments.add(_PathSegment(currentKey));
    return segments;
  }

  static String? getString(dynamic json, String? path) => getValue(json, path)?.toString();

  static double? getDouble(dynamic json, String? path) {
    final value = getValue(json, path);
    if (value is num) return value.toDouble();
    if (value is String) return double.tryParse(value.replaceAll('s', ''));
    return null;
  }

  static int? getInt(dynamic json, String? path) {
    final value = getValue(json, path);
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) return int.tryParse(value);
    return null;
  }

  static List? getList(dynamic json, String? path) {
    final value = getValue(json, path);
    return value is List ? value : null;
  }
}

class _PathSegment {
  final String key;
  final int? index;
  _PathSegment(this.key, {this.index});
  bool get isArrayAccess => index != null;
}
