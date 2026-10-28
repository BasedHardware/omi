import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api_result.dart';

/// Optional refusal metadata, separate from the authoritative HTTP failure.
class SyncUploadRefusalBody {
  const SyncUploadRefusalBody({this.code, this.detail});
  final String? code;
  final String? detail;

  bool get invalidCaptureTime =>
      code == 'invalid_capture_time' || detail == 'Invalid sync file format: invalid timestamp';

  /// Only closed tokens can reach the WAL ledger or analytics.
  String get reasonCode {
    const tokens = {
      'invalid_capture_time',
      'invalid_file',
      'malformed_multipart',
      'too_many_parts',
      'too_large',
      'empty_clip',
      'server_refused'
    };
    if (tokens.contains(code)) return code!;
    if (invalidCaptureTime) return 'invalid_capture_time';
    if (detail == 'Uploaded file is missing a filename' || detail == 'Invalid sync file format') return 'invalid_file';
    if (detail == 'Missing boundary in multipart.' ||
        detail == 'Malformed multipart body' ||
        detail == 'The Content-Disposition header field "name" must be provided.') {
      return 'malformed_multipart';
    }
    if (detail?.startsWith('Part exceeded maximum size of ') ?? false) return 'too_large';
    if ((detail?.startsWith('Too many files. Maximum number of files is ') ?? false) ||
        (detail?.startsWith('Too many fields. Maximum number of fields is ') ?? false)) {
      return 'too_many_parts';
    }
    return 'server_refused';
  }
}

String? _optionalText(Object? value) {
  final text = value is String ? value.trim() : null;
  return text == null || text.isEmpty ? null : text.substring(0, text.length > 200 ? 200 : text.length);
}

/// Decode once. A malformed body is an explicit decode failure; the upload
/// caller still retains the HTTP refusal and its audio, with an unknown token.
ApiResult<SyncUploadRefusalBody> decodeSyncUploadRefusal(http.Response response) {
  try {
    // omi-perf-allow: history-json-on-ui -- a small error body, never a conversation list
    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic>) {
      return ApiFailure(ApiProblem(ApiProblemKind.decode, statusCode: response.statusCode));
    }
    final detail = decoded['detail'];
    final code = decoded['code'] ?? (detail is Map ? detail['code'] : null);
    String? reason;
    for (final key in ['detail', 'message', 'error']) {
      reason = _optionalText(decoded[key]);
      if (reason != null) break;
    }
    return ApiSuccess(SyncUploadRefusalBody(code: _optionalText(code), detail: reason));
  } on FormatException {
    return ApiFailure(ApiProblem(ApiProblemKind.decode, statusCode: response.statusCode));
  }
}
