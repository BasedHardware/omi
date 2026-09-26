import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

/// Client copy of `omi:backend/utils/conversations/transcript_hash.py` encoding v5.
///
/// The digest is a wire contract. Bump [transcriptHashEncodingVersion] when
/// the framing changes. The version is not mixed into the digest bytes.
const int transcriptHashEncodingVersion = 5;

const String defaultSpeaker = 'SPEAKER_00';
const int defaultSpeakerId = 0;
const String isUserToken = 'Y';
const String notUserToken = 'N';

class CanonicalTranscriptSegment {
  const CanonicalTranscriptSegment({
    required this.speaker,
    required this.speakerId,
    required this.isUser,
    required this.personId,
    required this.text,
  });

  final String speaker;
  final int speakerId;
  final bool isUser;
  final String? personId;
  final String text;
}

String _stripOrDefault(String? raw, [String defaultValue = '']) {
  if (raw == null) return defaultValue;
  final stripped = raw.trim();
  if (stripped.isEmpty) return defaultValue;
  return stripped;
}

int derivedSpeakerId(String canonicalSpeaker) {
  final parts = canonicalSpeaker.split('_');
  if (parts.length < 2) return defaultSpeakerId;
  return int.tryParse(parts[1]) ?? defaultSpeakerId;
}

CanonicalTranscriptSegment canonicalizeSegment({
  String? speaker,
  int? speakerId,
  bool? isUser,
  String? personId,
  String? text,
}) {
  final canonicalSpeaker = _stripOrDefault(speaker, defaultSpeaker);
  final canonicalPerson = _stripOrDefault(personId);
  return CanonicalTranscriptSegment(
    speaker: canonicalSpeaker,
    speakerId: speakerId ?? derivedSpeakerId(canonicalSpeaker),
    isUser: isUser == true,
    personId: canonicalPerson.isEmpty ? null : canonicalPerson,
    text: _stripOrDefault(text),
  );
}

CanonicalTranscriptSegment canonicalizeTranscriptSegment(TranscriptSegment segment) {
  return canonicalizeSegment(
    speaker: segment.speaker,
    speakerId: segment.speakerId,
    isUser: segment.isUser,
    personId: segment.personId,
    text: segment.text,
  );
}

List<int> _frame(String value) {
  final encoded = utf8.encode(value);
  return [...ascii.encode('${encoded.length}\n'), ...encoded];
}

List<int> canonicalTranscriptBytes(Iterable<CanonicalTranscriptSegment> parts) {
  final out = <int>[];
  for (final part in parts) {
    out
      ..addAll(_frame(part.speaker))
      ..addAll(_frame('${part.speakerId}'))
      ..addAll(_frame(part.isUser ? isUserToken : notUserToken))
      ..addAll(_frame(part.personId ?? ''))
      ..addAll(_frame(part.text));
  }
  return out;
}

String transcriptSha256FromCanonical(Iterable<CanonicalTranscriptSegment> parts) {
  return sha256.convert(canonicalTranscriptBytes(parts)).toString();
}

String transcriptSha256(Iterable<TranscriptSegment> segments) {
  return transcriptSha256FromCanonical(segments.map(canonicalizeTranscriptSegment));
}

String transcriptSha256FromMaps(Iterable<Map<String, Object?>> segments) {
  return transcriptSha256FromCanonical(
    segments.map(
      (segment) => canonicalizeSegment(
        speaker: segment['speaker'] as String?,
        speakerId: segment['speaker_id'] as int?,
        isUser: segment['is_user'] as bool?,
        personId: segment['person_id'] as String?,
        text: segment['text'] as String?,
      ),
    ),
  );
}
