// Public share-link base URL for self-hosting (#4339).
//
// Matches backend `OMI_SHARE_BASE_URL` / desktop share helpers.
// Override at build time with `--dart-define=OMI_SHARE_BASE_URL=https://share.example.com`.

const defaultShareBaseUrl = 'https://h.omi.me';

const _shareBaseFromDefine = String.fromEnvironment('OMI_SHARE_BASE_URL');

final _hostOk = RegExp(r'^[A-Za-z0-9.-]+$');

/// Return the configured share origin (no trailing slash).
///
/// [raw] is for tests; production callers omit it so the dart-define / default apply.
String shareBaseUrl([String? raw]) {
  var value = (raw ?? _shareBaseFromDefine).trim();
  if (value.isEmpty) {
    value = defaultShareBaseUrl;
  }
  if (!value.contains('://')) {
    value = 'https://$value';
  }
  final uri = Uri.tryParse(value);
  if (uri == null ||
      uri.host.isEmpty ||
      uri.userInfo.isNotEmpty ||
      uri.hasQuery ||
      uri.hasFragment ||
      (uri.scheme != 'http' && uri.scheme != 'https') ||
      !_hostOk.hasMatch(uri.host)) {
    return defaultShareBaseUrl;
  }
  final origin = uri.hasPort ? '${uri.scheme}://${uri.host}:${uri.port}' : '${uri.scheme}://${uri.host}';
  final path = uri.path.replaceFirst(RegExp(r'/+$'), '');
  if (path.isEmpty || path == '/') {
    return origin;
  }
  return '$origin$path';
}

/// Join [shareBaseUrl] with a path (leading slash optional).
String buildShareUrl(String path, {String? raw}) {
  final normalized = path.startsWith('/') ? path : '/$path';
  return '${shareBaseUrl(raw)}$normalized';
}

String conversationShareUrl(String conversationId, {String? raw}) =>
    buildShareUrl('/conversations/$conversationId', raw: raw);

String appShareUrl(String appId, {String? raw}) => buildShareUrl('/apps/$appId', raw: raw);

String recapShareUrl(String summaryId, {String? raw}) => buildShareUrl('/recaps/$summaryId', raw: raw);
