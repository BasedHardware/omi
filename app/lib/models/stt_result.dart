import 'package:omi/models/stt_response_schema.dart';

/// A single segment of transcribed text with timing information
class SttSegment {
  final String text;
  final double start;
  final double end;
  final String? speaker;
  final int? speakerId;
  final double? confidence;

  SttSegment({
    required this.text,
    required this.start,
    required this.end,
    this.speaker,
    this.speakerId,
    this.confidence,
  });
}

class SttTranscriptionResult {
  final List<SttSegment> segments;
  final String? rawText;
  final String? language;
  final double? duration;
  final Map<String, dynamic>? metadata;

  SttTranscriptionResult({
    this.segments = const [],
    this.rawText,
    this.language,
    this.duration,
    this.metadata,
  });

  bool get isEmpty => segments.isEmpty && (rawText == null || rawText!.trim().isEmpty);
  bool get isNotEmpty => !isEmpty;

  factory SttTranscriptionResult.fromJsonWithSchema(
    Map<String, dynamic> json,
    SttResponseSchema schema, {
    double audioOffsetSeconds = 0,
  }) {
    final segments = <SttSegment>[];

    if (schema.segmentsPath != null) {
      final segmentsList = JsonPathNavigator.getList(json, schema.segmentsPath);
      if (segmentsList != null) {
        for (var seg in segmentsList) {
          final text = JsonPathNavigator.getString(seg, schema.textField)?.trim() ?? '';
          if (text.isEmpty) continue;

          double start = audioOffsetSeconds;
          double end = audioOffsetSeconds + schema.defaultSegmentDuration;

          if (schema.startField != null) {
            final startValue = JsonPathNavigator.getDouble(seg, schema.startField);
            if (startValue != null) {
              if (schema.startField!.contains('Ticks')) {
                start = audioOffsetSeconds + (startValue / 10000000.0);
              } else {
                start = audioOffsetSeconds + startValue;
              }
            }
          }

          if (schema.endField != null) {
            final endValue = JsonPathNavigator.getDouble(seg, schema.endField);
            if (endValue != null) {
              if (schema.endField!.contains('Ticks')) {
                end = audioOffsetSeconds + (endValue / 10000000.0);
              } else {
                end = audioOffsetSeconds + endValue;
              }
            }
          }

          segments.add(SttSegment(
            text: text,
            start: start,
            end: end,
            speaker: schema.speakerField != null ? JsonPathNavigator.getString(seg, schema.speakerField) : null,
            speakerId: schema.speakerIdField != null ? JsonPathNavigator.getInt(seg, schema.speakerIdField) : null,
            confidence:
                schema.confidenceField != null ? JsonPathNavigator.getDouble(seg, schema.confidenceField) : null,
          ));
        }
      }
    }

    String? rawText = JsonPathNavigator.getString(json, schema.rawTextPath);

    if (segments.isEmpty && rawText != null && rawText.trim().isNotEmpty) {
      final duration = JsonPathNavigator.getDouble(json, schema.durationPath) ?? schema.defaultSegmentDuration;
      segments.add(SttSegment(
        text: rawText.trim(),
        start: audioOffsetSeconds,
        end: audioOffsetSeconds + duration,
      ));
    }

    return SttTranscriptionResult(
      segments: segments,
      rawText: rawText,
      language: JsonPathNavigator.getString(json, schema.languagePath),
      duration: JsonPathNavigator.getDouble(json, schema.durationPath),
    );
  }
}
