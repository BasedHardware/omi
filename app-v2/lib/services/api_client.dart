import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'package:nooto_v2/services/auth_service.dart';

/// Typed error thrown by [ApiClient] on non-2xx responses.
///
/// Lets callers branch on `statusCode` and `detail` (parsed from the response
/// body's `detail` field if the body is JSON-shaped). Mirrors desktop-v2's
/// `ApiError` so cross-platform error handling stays parallel.
///
/// Example:
/// ```dart
/// try {
///   await client.post('v1/apps/enable?app_id=$id');
/// } on ApiError catch (e) {
///   if (e.statusCode == 400 && e.detail == 'App setup is not completed') {
///     // open OAuth flow
///   }
/// }
/// ```
class ApiError implements Exception {
  ApiError({required this.statusCode, this.detail, required this.body});

  /// HTTP status code (4xx or 5xx — 2xx never throws).
  final int statusCode;

  /// Parsed `detail` field from the JSON body, if present and the body is
  /// JSON. Null when the body isn't JSON or has no `detail` key.
  final String? detail;

  /// Raw response body (capped at the response's natural size; we don't
  /// truncate). Useful for debug logs when `detail` is null.
  final String body;

  @override
  String toString() =>
      'ApiError($statusCode${detail != null ? ': $detail' : ''})';
}

/// Lean HTTP client for the v2 backend. Injects the Firebase ID token on
/// every request, refreshes once on 401, throws [ApiError] on non-2xx, and
/// exposes a streaming entry point for SSE-style endpoints (`/v2/messages`
/// for the morning brief).
///
/// Constructor seams (`httpClient`, `getIdToken`, `signOut`, `baseUrl`) make
/// this testable without spinning up Firebase. Production callers use the
/// no-arg form.
class ApiClient {
  ApiClient({
    http.Client? httpClient,
    Future<String?> Function({bool forceRefresh})? getIdToken,
    Future<void> Function()? signOut,
    String baseUrl = _defaultBaseUrl,
  })  : _http = httpClient ?? http.Client(),
        _getIdToken = getIdToken ?? AuthService.instance.getIdToken,
        _signOut = signOut ?? AuthService.instance.signOut,
        _baseUrl = baseUrl;

  // TODO: extract to env config when v2 cuts over to prod (matches the
  // legacy `Env.apiBaseUrl` pattern). Hardcoded to staging for PR2a.
  static const String _defaultBaseUrl = 'https://nooto-dev.togodynamics.com/';
  static const Duration readTimeout = Duration(seconds: 30);
  static const Duration writeTimeout = Duration(seconds: 300);
  static const int _errorBodyCapBytes = 8192;

  final http.Client _http;
  final Future<String?> Function({bool forceRefresh}) _getIdToken;
  final Future<void> Function() _signOut;
  final String _baseUrl;

  Future<http.Response> get(String path, {Map<String, String>? headers}) async {
    final uri = _resolve(path);
    final response = await _withAuthRetry(
      headers: headers,
      timeout: readTimeout,
      run: (hdrs) => _http.get(uri, headers: hdrs).timeout(readTimeout),
    );
    _throwIfNotOk(response);
    return response;
  }

  Future<http.Response> post(
    String path, {
    Object? body,
    Map<String, String>? headers,
  }) async {
    final uri = _resolve(path);
    final encoded = _encodeBody(body);
    final response = await _withAuthRetry(
      headers: headers,
      timeout: writeTimeout,
      run: (hdrs) =>
          _http.post(uri, headers: hdrs, body: encoded).timeout(writeTimeout),
    );
    _throwIfNotOk(response);
    return response;
  }

  Future<http.Response> patch(
    String path, {
    Object? body,
    Map<String, String>? headers,
  }) async {
    final uri = _resolve(path);
    final encoded = _encodeBody(body);
    final response = await _withAuthRetry(
      headers: headers,
      timeout: writeTimeout,
      run: (hdrs) =>
          _http.patch(uri, headers: hdrs, body: encoded).timeout(writeTimeout),
    );
    _throwIfNotOk(response);
    return response;
  }

  Future<http.Response> delete(
    String path, {
    Map<String, String>? headers,
  }) async {
    final uri = _resolve(path);
    final response = await _withAuthRetry(
      headers: headers,
      timeout: writeTimeout,
      run: (hdrs) =>
          _http.delete(uri, headers: hdrs).timeout(writeTimeout),
    );
    _throwIfNotOk(response);
    return response;
  }

  /// Streams the response body byte-chunks. Caller decodes (e.g. SSE parse for
  /// the morning brief). On 401 or 5xx this throws `http.ClientException`
  /// without auto-retry — streaming consumers own retry semantics because
  /// rewinding mid-stream is rarely what they want. Streaming intentionally
  /// does NOT use [ApiError] — the body has already started flowing and
  /// surfacing a `detail` would mean buffering the whole error first.
  Future<Stream<List<int>>> stream(
    String path, {
    Object? body,
    Map<String, String>? headers,
  }) async {
    final uri = _resolve(path);
    final request = http.Request('POST', uri);
    request.headers.addAll(await _buildHeaders(extra: headers));
    final encoded = _encodeBody(body);
    if (encoded != null) request.body = encoded;
    final streamed = await _http.send(request);
    if (streamed.statusCode >= 400) {
      final preview = await _readErrorPreview(streamed.stream);
      throw http.ClientException(
        'HTTP ${streamed.statusCode}: $preview',
        uri,
      );
    }
    return streamed.stream;
  }

  Future<http.Response> _withAuthRetry({
    required Map<String, String>? headers,
    required Duration timeout,
    required Future<http.Response> Function(Map<String, String>) run,
  }) async {
    var hdrs = await _buildHeaders(extra: headers);
    var response = await run(hdrs);
    if (response.statusCode != 401) return response;

    final refreshed = await _getIdToken(forceRefresh: true);
    if (refreshed == null || refreshed.isEmpty) {
      await _signOut();
      return response;
    }
    hdrs = _headersWithToken(refreshed, extra: headers);
    response = await run(hdrs);
    if (response.statusCode == 401) await _signOut();
    return response;
  }

  /// Throws [ApiError] when `response.statusCode` is not 2xx. Parses the
  /// JSON body's `detail` field if present so callers can branch on
  /// machine-readable error reasons (e.g. "App setup is not completed").
  void _throwIfNotOk(http.Response response) {
    final code = response.statusCode;
    if (code >= 200 && code < 300) return;
    String? detail;
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map && decoded['detail'] is String) {
        detail = decoded['detail'] as String;
      }
    } catch (_) {
      // Non-JSON body (HTML error page, plain text, empty) — leave detail
      // null. Callers can still inspect statusCode and body.
    }
    throw ApiError(
      statusCode: code,
      detail: detail,
      body: response.body,
    );
  }

  Future<Map<String, String>> _buildHeaders({Map<String, String>? extra}) async {
    final token = await _getIdToken();
    return _headersWithToken(token, extra: extra);
  }

  Map<String, String> _headersWithToken(String? token,
      {Map<String, String>? extra}) {
    return {
      'Content-Type': 'application/json',
      if (token != null && token.isNotEmpty) 'Authorization': 'Bearer $token',
      ...?extra,
    };
  }

  String? _encodeBody(Object? body) {
    if (body == null) return null;
    return body is String ? body : jsonEncode(body);
  }

  Future<String> _readErrorPreview(Stream<List<int>> stream) async {
    final bytes = <int>[];
    await for (final chunk in stream) {
      bytes.addAll(chunk);
      if (bytes.length >= _errorBodyCapBytes) break;
    }
    final capped = bytes.length > _errorBodyCapBytes
        ? bytes.sublist(0, _errorBodyCapBytes)
        : bytes;
    return utf8.decode(capped, allowMalformed: true);
  }

  Uri _resolve(String path) {
    final trimmed = path.startsWith('/') ? path.substring(1) : path;
    return Uri.parse('$_baseUrl$trimmed');
  }

  void close() => _http.close();
}
