// Wire types for the recordings-and-conversations (v3) reads: the live read, audio manifest pieces and
// the summary stream's events, with their decoders. The HTTP calls live in backend/http/api/conversations_v3.dart.
import 'dart:convert';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/utils/logger.dart';

/// `GET /v1/conversations/live`. [v3] is the per-user switch; [conversation] is the conversation in
/// progress, or null.
class ConversationsLiveRead {
  const ConversationsLiveRead({required this.v3, this.conversation});
  final bool v3;
  final ServerConversation? conversation;

  static ConversationsLiveRead fromJson(Map<String, dynamic> json) {
    final v3 = json['v3'] == true;
    final conversation = json['conversation'];
    ServerConversation? live;
    if (v3 && conversation is Map<String, dynamic>) {
      // The switch must resolve even when the live row cannot be read: an unreadable row is no live row,
      // never an unanswered switch (which would hold back both Homes).
      try {
        live = ServerConversation.fromJson(conversation);
      } catch (e) {
        Logger.debug('conversations/live: unreadable live row: $e');
      }
    }
    return ConversationsLiveRead(v3: v3, conversation: live);
  }
}

/// One playable piece of a conversation's audio: a span of one recording's file, with a signed URL.
class AudioManifestPiece {
  const AudioManifestPiece({
    required this.recordingId,
    required this.audioFileId,
    required this.url,
    required this.start,
    required this.end,
    this.expiresAt,
  });

  final String recordingId;
  final String audioFileId;
  final String url;

  /// Seconds on that file's clock.
  final double start;
  final double end;
  final DateTime? expiresAt;

  Duration get length => Duration(milliseconds: ((end - start) * 1000).round());

  static AudioManifestPiece? fromJson(Object? json) {
    if (json is! Map) return null;
    final url = json['url'];
    final start = json['start'];
    final end = json['end'];
    if (url is! String || url.isEmpty || start is! num || end is! num || end <= start) return null;
    final expires = json['expires_at'];
    return AudioManifestPiece(
      recordingId: json['recording_id'] is String ? json['recording_id'] as String : '',
      audioFileId: json['audio_file_id'] is String ? json['audio_file_id'] as String : '',
      url: url,
      start: start.toDouble(),
      end: end.toDouble(),
      expiresAt: expires is String ? DateTime.tryParse(expires) : null,
    );
  }
}

/// One event of the summary stream.
sealed class SummaryStreamEvent {
  const SummaryStreamEvent();
}

/// One summary section, as markdown.
final class SummarySection extends SummaryStreamEvent {
  const SummarySection(this.markdown);
  final String markdown;
}

/// The stored summary. A summary that was already fresh arrives as this event alone.
final class SummaryDone extends SummaryStreamEvent {
  const SummaryDone(this.structured, this.coversThrough);
  final Structured structured;
  final DateTime? coversThrough;
}

/// Another writer holds the summary: poll the conversation instead.
final class SummaryInProgress extends SummaryStreamEvent {
  const SummaryInProgress();
}

final class SummaryFailed extends SummaryStreamEvent {
  const SummaryFailed([this.detail]);
  final String? detail;
}

/// Parses one frame of the summary stream. Null for keep-alive and comment frames.
SummaryStreamEvent? parseSummaryFrame(String frame) {
  final line = frame.trim();
  if (line.isEmpty || line.startsWith(':')) return null;
  if (line.startsWith('data: ')) return SummarySection(line.substring(6).replaceAll('__CRLF__', '\n'));
  if (line.startsWith('done: ')) {
    try {
      final json = jsonDecode(utf8.decode(base64.decode(line.substring(6).trim())));
      if (json is! Map<String, dynamic> || json['structured'] is! Map<String, dynamic>) {
        return const SummaryFailed('bad_done_frame');
      }
      final covers = json['summary_covers_through'];
      return SummaryDone(
        Structured.fromJson(json['structured'] as Map<String, dynamic>),
        covers is String ? DateTime.tryParse(covers) : null,
      );
    } on FormatException {
      return const SummaryFailed('bad_done_frame');
    }
  }
  if (line.startsWith('error: ') || line.startsWith('error:')) {
    final payload = line.substring(line.indexOf(':') + 1).trim();
    try {
      final json = jsonDecode(payload);
      if (json is Map && json['detail'] is String) {
        return json['detail'] == 'summary_in_progress'
            ? const SummaryInProgress()
            : SummaryFailed(json['detail'] as String);
      }
    } on FormatException {
      // Fall through to an unspecific failure.
    }
    return const SummaryFailed();
  }
  return null;
}
