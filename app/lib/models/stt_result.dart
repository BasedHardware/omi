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

String _extractSpeakerLabel(dynamic value, int speakerId) {
  if (value is String && value.trim().isNotEmpty) {
    return value.trim();
  }
  return 'SPEAKER_$speakerId';
}

bool _extractBool(dynamic value) {
  if (value is bool) return value;
  if (value is num) return value != 0;
  if (value is String) {
    final normalized = value.trim().toLowerCase();
    if (normalized == 'true' || normalized == '1' || normalized == 'yes') return true;
    if (normalized == 'false' || normalized == '0' || normalized == 'no') return false;
  }
  return false;
}

String? _extractNullableString(dynamic value) {
  if (value == null) return null;
  final text = value.toString().trim();
  return text.isEmpty ? null : text;
}

List<dynamic>? _extractTranslations(dynamic value) {
  if (value is List) return value;
  return null;
}

dynamic _schemaValue(dynamic json, String? configuredPath, String fallbackPath) {
  if (configuredPath != null) {
    return JsonPathNavigator.getValue(json, configuredPath);
  }
  return JsonPathNavigator.getValue(json, fallbackPath);
}

/// A single segment of transcribed text with timing - matches backend TranscriptSegment
class SttSegment {
  final String text;
  final double start;
  final double end;
  final String speaker;
  final int speakerId;
  final bool isUser;
  final String? personId;
  final List<dynamic>? translations;

  SttSegment({
    required this.text,
    required this.start,
    required this.end,
    String? speaker,
    this.speakerId = 0,
    this.isUser = false,
    this.personId,
    this.translations,
  }) : speaker = speaker ?? 'SPEAKER_$speakerId';

  Map<String, dynamic> toTranscriptSegmentJson() {
    return {
      'text': text.trim(),
      'speaker': speaker,
      'speaker_id': speakerId,
      'is_user': isUser,
      'start': start,
      'end': end,
      'person_id': personId,
      if (translations != null) 'translations': translations,
    };
  }
}

class SttTranscriptionResult {
  final List<SttSegment> segments;
  final String? rawText;

  SttTranscriptionResult({this.segments = const [], this.rawText});

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

          final speakerValue = _schemaValue(seg, schema.segmentsSpeakerField, 'speaker');
          final speakerIdValue = _schemaValue(seg, schema.segmentsSpeakerIdField, 'speaker_id');
          final speakerId = speakerIdValue != null
              ? _extractSpeakerId(speakerIdValue)
              : _extractSpeakerId(speakerValue);
          final speaker = _extractSpeakerLabel(speakerValue, speakerId);
          final isUser = _extractBool(_schemaValue(seg, schema.segmentsIsUserField, 'is_user'));
          final personId = _extractNullableString(_schemaValue(seg, schema.segmentsPersonIdField, 'person_id'));
          final translations = _extractTranslations(
            _schemaValue(seg, schema.segmentsTranslationsField, 'translations'),
          );

          segments.add(
            SttSegment(
              text: text,
              start: start,
              end: end,
              speaker: speaker,
              speakerId: speakerId,
              isUser: isUser,
              personId: personId,
              translations: translations,
            ),
          );
        }
      }
    }

    String? rawText = JsonPathNavigator.getString(json, schema.textPath);

    // Fallback: create single segment from raw text
    if (segments.isEmpty && rawText != null && rawText.trim().isNotEmpty) {
      segments.add(
        SttSegment(
          text: rawText.trim(),
          start: audioOffsetSeconds,
          end: audioOffsetSeconds + schema.defaultSegmentDuration,
        ),
      );
    }

    return SttTranscriptionResult(segments: segments, rawText: rawText);
  }
}

List<Map<String, dynamic>> mergeTranscriptSegmentsBySpeaker(Iterable<SttSegment> sourceSegments) {
  final segments = <Map<String, dynamic>>[];

  for (final segment in sourceSegments) {
    if (segment.text.trim().isEmpty) continue;

    final segmentJson = segment.toTranscriptSegmentJson();
    final hasTranslations = segment.translations != null && segment.translations!.isNotEmpty;
    final lastTranslations = segments.isNotEmpty ? segments.last['translations'] : null;
    final lastHasTranslations = lastTranslations is List && lastTranslations.isNotEmpty;

    if (segments.isEmpty ||
        segments.last['speaker'] != segmentJson['speaker'] ||
        segments.last['speaker_id'] != segmentJson['speaker_id'] ||
        segments.last['is_user'] != segmentJson['is_user'] ||
        segments.last['person_id'] != segmentJson['person_id'] ||
        lastHasTranslations ||
        hasTranslations) {
      segments.add(segmentJson);
    } else {
      final last = segments.last;
      last['text'] = '${last['text']} ${segment.text.trim()}';
      last['end'] = segment.end;
    }
  }

  return segments;
}
