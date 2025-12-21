import 'package:omi/models/stt_response_schema.dart';

/// Helper to extract numeric speaker ID from various formats
int _extractSpeakerId(dynamic value) {
  if (value == null) return 0;
  if (value is int) return value;
  if (value is num) return value.toInt();
  if (value is String) {
    // Pattern 1: Direct numeric string
    final directParse = int.tryParse(value);
    if (directParse != null) return directParse;

    // Pattern 2: "SPEAKER_1" or "speaker_1" format - extract number
    final match = RegExp(r'(\d+)').firstMatch(value);
    if (match != null) return int.tryParse(match.group(1)!) ?? 0;

    // Pattern 3: "A", "B", "C" format (OpenAI diarize) -> 0, 1, 2
    if (value.length == 1) {
      final code = value.toUpperCase().codeUnitAt(0);
      if (code >= 65 && code <= 90) {
        // A-Z
        return code - 65; // A=0, B=1, C=2, ...
      }
    }
  }
  return 0;
}

/// A single segment of transcribed text with timing - matches backend TranscriptSegment
class SttSegment {
  final String text;
  final double start;
  final double end;
  final int speakerId;

  SttSegment({
    required this.text,
    required this.start,
    required this.end,
    this.speakerId = 0,
  });
}

class SttTranscriptionResult {
  final List<SttSegment> segments;
  final String? rawText;

  SttTranscriptionResult({
    this.segments = const [],
    this.rawText,
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
          final text = JsonPathNavigator.getString(seg, schema.segmentsTextField)?.trim() ?? '';
          if (text.isEmpty) continue;

          double start = audioOffsetSeconds;
          double end = audioOffsetSeconds + schema.defaultSegmentDuration;

          if (schema.segmentsStartField != null) {
            final startValue = JsonPathNavigator.getDouble(seg, schema.segmentsStartField);
            if (startValue != null) {
              // Handle Azure's tick format (100 nanoseconds per tick)
              if (schema.segmentsStartField!.contains('Ticks')) {
                start = audioOffsetSeconds + (startValue / 10000000.0);
              } else {
                start = audioOffsetSeconds + startValue;
              }
            }
          }

          if (schema.segmentsEndField != null) {
            final endValue = JsonPathNavigator.getDouble(seg, schema.segmentsEndField);
            if (endValue != null) {
              if (schema.segmentsEndField!.contains('Ticks')) {
                end = audioOffsetSeconds + (endValue / 10000000.0);
              } else {
                end = audioOffsetSeconds + endValue;
              }
            }
          }

          // Extract speaker ID from speaker field
          final speakerValue =
              schema.segmentsSpeakerField != null ? JsonPathNavigator.getValue(seg, schema.segmentsSpeakerField) : null;

          segments.add(SttSegment(
            text: text,
            start: start,
            end: end,
            speakerId: _extractSpeakerId(speakerValue),
          ));
        }
      }
    }

    String? rawText = JsonPathNavigator.getString(json, schema.textPath);

    // Fallback: create single segment from raw text
    if (segments.isEmpty && rawText != null && rawText.trim().isNotEmpty) {
      segments.add(SttSegment(
        text: rawText.trim(),
        start: audioOffsetSeconds,
        end: audioOffsetSeconds + schema.defaultSegmentDuration,
      ));
    }

    return SttTranscriptionResult(
      segments: segments,
      rawText: rawText,
    );
  }
}
