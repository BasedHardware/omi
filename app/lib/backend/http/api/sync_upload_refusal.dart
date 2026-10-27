import 'dart:convert';
import 'package:http/http.dart' as http;

/// Bounded `code` the sync upload route puts on a 400 refusal, or null when
/// the body carries none. Never parses human-readable text into behavior.
String? syncUploadErrorCode(http.Response response) {
  try {
    // omi-perf-allow: history-json-on-ui -- a small error body, never a conversation list
    final decoded = jsonDecode(response.body);
    if (decoded is Map<String, dynamic>) {
      final detail = decoded['detail'];
      final code = decoded['code'] ?? (detail is Map ? detail['code'] : null);
      if (code is String && code.trim().isNotEmpty) return code.trim();
    }
  } catch (_) {}
  return null;
}

/// Map known server wire reasons to a closed token; arbitrary prose is never persisted.
String syncUploadRefusalCode(http.Response response) {
  const tokens = {
    'invalid_capture_time',
    'invalid_file',
    'malformed_multipart',
    'too_many_parts',
    'too_large',
    'empty_clip',
    'server_refused'
  };
  final code = syncUploadErrorCode(response);
  if (tokens.contains(code)) return code!;
  final detail = syncUploadErrorReason(response);
  if (detail == 'Uploaded file is missing a filename' || detail == 'Invalid sync file format') return 'invalid_file';
  if (detail == 'Missing boundary in multipart.' ||
      detail == 'Malformed multipart body' ||
      detail == 'The Content-Disposition header field "name" must be provided.') return 'malformed_multipart';
  if (detail?.startsWith('Part exceeded maximum size of ') ?? false) return 'too_large';
  if ((detail?.startsWith('Too many files. Maximum number of files is ') ?? false) ||
      (detail?.startsWith('Too many fields. Maximum number of fields is ') ?? false)) return 'too_many_parts';
  return 'server_refused';
}

/// The server's own one-line reason from a 400 body, for logs and terminal
/// rows: kept verbatim but bounded, so display surfaces never echo an
/// unbounded error string.
String? syncUploadErrorReason(http.Response response) {
  try {
    // omi-perf-allow: history-json-on-ui -- a small error body, never a conversation list
    final decoded = jsonDecode(response.body);
    if (decoded is Map<String, dynamic>) {
      for (final key in ['detail', 'message', 'error']) {
        final value = decoded[key];
        if (value is String && value.trim().isNotEmpty) {
          final reason = value.trim();
          return reason.length > 200 ? reason.substring(0, 200) : reason;
        }
      }
    }
  } catch (_) {}
  return null;
}

/// The exact detail the deployed upload route puts on a 400 whose filename
/// timestamp it refuses (`utils/sync/pipeline.py`, before the bounded `code`
/// field existed). Matched verbatim — never a substring of other refusals.
const String _kInvalidCaptureTimeDetail = 'Invalid sync file format: invalid timestamp';

/// Whether a sync-upload 400 refuses the recording's claimed capture time.
/// The server names this refusal two ways: the bounded `code`
/// `invalid_capture_time` (server PR #23746) or, on the currently deployed
/// route, the exact detail line above with no code at all.
bool isInvalidCaptureTimeResponse(http.Response response) {
  if (syncUploadErrorCode(response) == 'invalid_capture_time') return true;
  return syncUploadErrorReason(response) == _kInvalidCaptureTimeDetail;
}
