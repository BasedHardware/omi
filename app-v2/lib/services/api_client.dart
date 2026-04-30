import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'package:nooto_v2/services/auth_service.dart';

/// Lean HTTP client for the v2 backend. Injects the Firebase ID token on
/// every request, refreshes once on 401, and exposes a streaming entry point
/// for SSE-style endpoints (`/v2/messages` for the morning brief).
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
    return _withAuthRetry(
      headers: headers,
      timeout: readTimeout,
      run: (hdrs) => _http.get(uri, headers: hdrs).timeout(readTimeout),
    );
  }

  Future<http.Response> post(
    String path, {
    Object? body,
    Map<String, String>? headers,
  }) async {
    final uri = _resolve(path);
    final encoded = _encodeBody(body);
    return _withAuthRetry(
      headers: headers,
      timeout: writeTimeout,
      run: (hdrs) =>
          _http.post(uri, headers: hdrs, body: encoded).timeout(writeTimeout),
    );
  }

  Future<http.Response> patch(
    String path, {
    Object? body,
    Map<String, String>? headers,
  }) async {
    final uri = _resolve(path);
    final encoded = _encodeBody(body);
    return _withAuthRetry(
      headers: headers,
      timeout: writeTimeout,
      run: (hdrs) =>
          _http.patch(uri, headers: hdrs, body: encoded).timeout(writeTimeout),
    );
  }

  /// Streams the response body byte-chunks. Caller decodes (e.g. SSE parse for
  /// the morning brief). On 401 or 5xx this throws `http.ClientException`
  /// without auto-retry — streaming consumers own retry semantics because
  /// rewinding mid-stream is rarely what they want.
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
