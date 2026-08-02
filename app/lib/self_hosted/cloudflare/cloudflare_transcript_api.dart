import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'cloudflare_transcript_configuration.dart';
import 'cloudflare_transcript_exception.dart';
import 'cloudflare_transcript_models.dart';

export 'cloudflare_transcript_exception.dart';

abstract interface class CloudflareTranscriptApi {
  bool get enabled;

  Future<List<CloudflareTranscriptSession>> listSessions({int limit = 50});
  Future<CloudflareTranscriptDetail> getTranscript(String sessionId);
}

class CloudflareTranscriptHttpApi implements CloudflareTranscriptApi {
  CloudflareTranscriptHttpApi({
    CloudflareTranscriptConfiguration? configuration,
    http.Client? client,
    this.timeout = const Duration(seconds: 15),
  })  : _configuration = configuration ?? CloudflareTranscriptConfiguration.fromEnvironment(),
        _client = client ?? http.Client();

  final CloudflareTranscriptConfiguration _configuration;
  final http.Client _client;
  final Duration timeout;

  @override
  bool get enabled => _configuration.isConfigured;

  @override
  Future<List<CloudflareTranscriptSession>> listSessions({int limit = 50}) async {
    if (!enabled) return const [];
    if (limit < 1 || limit > 100) throw const CloudflareTranscriptApiException('limit must be between 1 and 100.');

    final sessions = <CloudflareTranscriptSession>[];
    final seenCursors = <String>{};
    String? cursor;
    do {
      final query = <String, String>{'limit': '$limit', if (cursor != null) 'cursor': cursor};
      final body = await _getJson(_endpoint('/v1/transcript-sessions', queryParameters: query));
      final rawSessions = body['sessions'];
      if (rawSessions is! List) throw const CloudflareTranscriptApiException('Worker response is missing sessions.');
      sessions.addAll(rawSessions.map(_parseSession));
      final nextCursor = body['next_cursor'];
      cursor = nextCursor is String && nextCursor.isNotEmpty ? nextCursor : null;
      if (cursor != null && !seenCursors.add(cursor)) {
        throw const CloudflareTranscriptApiException('Worker response contains a repeated cursor.');
      }
    } while (cursor != null);
    return sessions;
  }

  @override
  Future<CloudflareTranscriptDetail> getTranscript(String sessionId) async {
    if (!enabled) throw const CloudflareTranscriptApiException('Cloudflare transcripts are not configured.');
    if (sessionId.isEmpty) throw const CloudflareTranscriptApiException('A transcript session id is required.');
    final encodedId = Uri.encodeComponent(sessionId);
    final body = await _getJson(_endpoint('/v1/upload-sessions/$encodedId/transcript'));
    _validateTranscriptDetail(body);
    return CloudflareTranscriptDetail.fromJson(body);
  }

  CloudflareTranscriptSession _parseSession(Object? rawSession) {
    if (rawSession is! Map) {
      throw const CloudflareTranscriptApiException('Worker response contains a non-object session.');
    }
    final session = Map<String, dynamic>.from(rawSession);
    final id = session['id'];
    if (id is! String || id.trim().isEmpty) {
      throw const CloudflareTranscriptApiException('Worker response contains a session without an id.');
    }
    return CloudflareTranscriptSession.fromJson(session);
  }

  void _validateTranscriptDetail(Map<String, dynamic> body) {
    _parseSession(body['session']);
    final rawChunks = body['chunks'];
    if (rawChunks is! List) {
      throw const CloudflareTranscriptApiException('Worker response is missing transcript chunks.');
    }
    for (final rawChunk in rawChunks) {
      if (rawChunk is! Map) {
        throw const CloudflareTranscriptApiException('Worker response contains a non-object transcript chunk.');
      }
      final chunk = Map<String, dynamic>.from(rawChunk);
      if (_parseSequence(chunk['sequence']) == null || chunk['text'] is! String) {
        throw const CloudflareTranscriptApiException.malformedTranscriptChunk();
      }
    }
  }

  int? _parseSequence(Object? value) => value is int ? value : null;

  Uri _endpoint(String path, {Map<String, String>? queryParameters}) {
    final base = _configuration.baseUri;
    final basePath = base.path.replaceFirst(RegExp(r'/$'), '');
    return base.replace(path: '$basePath$path', queryParameters: queryParameters);
  }

  Future<Map<String, dynamic>> _getJson(Uri uri) async {
    try {
      final request = http.Request('GET', uri)
        ..followRedirects = false
        ..maxRedirects = 0
        ..headers.addAll({'Authorization': 'Bearer ${_configuration.token.trim()}', 'Accept': 'application/json'});
      final streamed = await _client.send(request).timeout(timeout);
      final response = await http.Response.fromStream(streamed).timeout(timeout);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudflareTranscriptApiException('Worker request failed with HTTP ${response.statusCode}.');
      }
      final decoded = jsonDecode(response.body);
      if (decoded is! Map) throw const CloudflareTranscriptApiException('Worker response is not a JSON object.');
      return Map<String, dynamic>.from(decoded);
    } on CloudflareTranscriptApiException {
      rethrow;
    } on TimeoutException {
      throw const CloudflareTranscriptApiException('Worker request timed out.');
    } on FormatException {
      throw const CloudflareTranscriptApiException('Worker response is not valid JSON.');
    } catch (_) {
      throw const CloudflareTranscriptApiException.transportFailure();
    }
  }
}
