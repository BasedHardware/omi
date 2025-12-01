import 'package:omi/models/stt_response_schema.dart';

/// Helper to extract numeric speaker ID from various string formats
int? _extractSpeakerIdFromValue(dynamic value) {
  if (value == null) return null;
  
  // Already an int
  if (value is int) return value;
  
  // Numeric value
  if (value is num) return value.toInt();
  
  // String handling
  if (value is String) {
    // Try direct int parse (Deepgram returns 0, 1, 2 as integers or "0", "1", "2")
    final directParse = int.tryParse(value);
    if (directParse != null) return directParse;
    
    // Try extracting number from "SPEAKER_0", "speaker_1", "Speaker 2" formats
    final match = RegExp(r'(\d+)').firstMatch(value);
    return match != null ? int.tryParse(match.group(1)!) : null;
  }
  
  return null;
}

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

          // Extract speaker info - try dedicated speakerId field first, then derive from speaker field
          final speakerValue = schema.speakerField != null 
              ? JsonPathNavigator.getValue(seg, schema.speakerField) 
              : null;
          final speakerIdFromField = schema.speakerIdField != null 
              ? JsonPathNavigator.getInt(seg, schema.speakerIdField) 
              : null;
          
          // Use explicit speakerId field if available, otherwise extract from speaker value
          final speakerId = speakerIdFromField ?? _extractSpeakerIdFromValue(speakerValue);
          
          segments.add(SttSegment(
            text: text,
            start: start,
            end: end,
            speaker: speakerValue?.toString(),
            speakerId: speakerId,
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
