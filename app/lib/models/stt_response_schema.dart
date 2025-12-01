class SttResponseSchema {
  final String? segmentsPath;
  final String textField;
  final String? startField;
  final String? endField;
  final String? speakerField;
  final String? speakerIdField;
  final String? confidenceField;
  final String? rawTextPath;
  final String? durationPath;
  final String? languagePath;
  final double defaultSegmentDuration;

  const SttResponseSchema({
    this.segmentsPath = 'segments',
    this.textField = 'text',
    this.startField = 'start',
    this.endField = 'end',
    this.speakerField,
    this.speakerIdField,
    this.confidenceField,
    this.rawTextPath = 'text',
    this.durationPath = 'duration',
    this.languagePath = 'language',
    this.defaultSegmentDuration = 5.0,
  });

  static const openAI = SttResponseSchema(
    segmentsPath: 'segments',
    textField: 'text',
    startField: 'start',
    endField: 'end',
    confidenceField: 'avg_logprob',
    rawTextPath: 'text',
    durationPath: 'duration',
    languagePath: 'language',
  );

  static const deepgram = SttResponseSchema(
    segmentsPath: 'results.channels[0].alternatives[0].words',
    textField: 'word',
    startField: 'start',
    endField: 'end',
    confidenceField: 'confidence',
    speakerField: 'speaker',
    rawTextPath: 'results.channels[0].alternatives[0].transcript',
    durationPath: 'metadata.duration',
    languagePath: 'metadata.language_code',
  );

  static const googleCloud = SttResponseSchema(
    segmentsPath: 'results[0].alternatives[0].words',
    textField: 'word',
    startField: 'startTime',
    endField: 'endTime',
    speakerField: 'speakerTag',
    confidenceField: 'confidence',
    rawTextPath: 'results[0].alternatives[0].transcript',
  );

  static const azure = SttResponseSchema(
    segmentsPath: 'recognizedPhrases',
    textField: 'nBest[0].display',
    startField: 'offsetInTicks',
    endField: 'durationInTicks',
    confidenceField: 'nBest[0].confidence',
    rawTextPath: 'combinedRecognizedPhrases[0].display',
    durationPath: 'duration',
  );

  static const simpleText = SttResponseSchema(
    segmentsPath: null,
    textField: 'text',
    rawTextPath: 'text',
  );

  static const falAI = SttResponseSchema(
    segmentsPath: 'chunks',
    textField: 'text',
    startField: 'timestamp[0]',
    endField: 'timestamp[1]',
    rawTextPath: 'text',
  );

  static const gemini = SttResponseSchema(
    segmentsPath: null,
    textField: 'text',
    rawTextPath: 'candidates[0].content.parts[0].text',
  );

  factory SttResponseSchema.fromJson(Map<String, dynamic> json) {
    return SttResponseSchema(
      segmentsPath: json['segments_path'] as String?,
      textField: json['text_field'] as String? ?? 'text',
      startField: json['start_field'] as String?,
      endField: json['end_field'] as String?,
      speakerField: json['speaker_field'] as String?,
      speakerIdField: json['speaker_id_field'] as String?,
      confidenceField: json['confidence_field'] as String?,
      rawTextPath: json['raw_text_path'] as String?,
      durationPath: json['duration_path'] as String?,
      languagePath: json['language_path'] as String?,
      defaultSegmentDuration: (json['default_segment_duration'] as num?)?.toDouble() ?? 5.0,
    );
  }

  Map<String, dynamic> toJson() => {
        'segments_path': segmentsPath,
        'text_field': textField,
        'start_field': startField,
        'end_field': endField,
        'speaker_field': speakerField,
        'speaker_id_field': speakerIdField,
        'confidence_field': confidenceField,
        'raw_text_path': rawTextPath,
        'duration_path': durationPath,
        'language_path': languagePath,
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
