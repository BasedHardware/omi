import 'dart:convert';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

/// Exact v5 length framing used by backend/utils/conversations/transcript_hash.py.
String onDeviceTranscriptHash(List<TranscriptSegment> segments) {
  final bytes = BytesBuilder();
  for (final segment in segments) {
    for (final value in [
      segment.speaker?.trim().isNotEmpty == true ? segment.speaker!.trim() : 'SPEAKER_00',
      '${segment.speakerId}',
      segment.isUser ? 'Y' : 'N',
      segment.personId?.trim() ?? '',
      segment.text.trim()
    ]) {
      final encoded = utf8.encode(value);
      bytes.add(utf8.encode('${encoded.length}\n'));
      bytes.add(encoded);
    }
  }
  return sha256.convert(bytes.takeBytes()).toString();
}

/// Only a hash-bound server projection may replace display fields. It never
/// changes the transcript, identity, backend intelligence or flag-off output.
ServerConversation applyOnDeviceProjection(ServerConversation conversation, {required bool enabled}) {
  final projection = conversation.clientProcessing;
  final provenance = projection?['provenance'];
  if (!enabled ||
      projection == null ||
      (provenance is! Map || provenance['runtime'] != 'local') ||
      projection['structure'] is! Map ||
      projection['transcript_sha256'] != onDeviceTranscriptHash(conversation.transcriptSegments)) {
    return conversation;
  }
  final json = conversation.toJson();
  json['structured'] = Map<String, dynamic>.from(projection['structure']);
  try {
    return ServerConversation.fromJson(json);
  } on FormatException {
    return conversation;
  } on TypeError {
    return conversation;
  }
}
