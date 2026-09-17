import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:omi/services/dev_controls/journey_faults.dart';

/// Deterministic loopback fixture backend for the hermetic journey lane
/// (SCA-488 / C2).
///
/// This is **external I/O faked at the declared boundary**: the app's real
/// HTTP client (`makeApiCall` / `makeStreamingApiCall` → `HttpPoolManager`)
/// performs real loopback HTTP against this server. Nothing inside the app is
/// stubbed; the deterministic assistant reply arrives through the same SSE
/// parsing the production backend's stream goes through.
///
/// The server owns the backend-side journey faults ([JourneyFault.suppressAssistantReply],
/// [JourneyFault.dropMemorySave]) and validates session ownership: any request
/// bearing the wrong-owner bearer inserted by the client-side fault gate is
/// rejected with 403, exactly as a real backend must reject cross-account
/// access.
class JourneyFixtureBackend {
  JourneyFixtureBackend._(this._server);

  static const String fixtureUid = 'omi-fixture-v1-user-1';
  static const String fixtureEmail = 'omi-fixture-v1-user-1@local.test';
  static const String fixtureBearer = 'synthetic-journey-bearer';
  static const String wrongOwnerBearer = 'synthetic-wrong-owner-session-token';

  final HttpServer _server;
  final Set<JourneyFault> _faults = {};

  /// Seeded, owned records served by the fixture.
  final List<Map<String, dynamic>> conversations = [];
  final List<Map<String, dynamic>> memories = [];

  /// Request journal: method + path -> count. Journeys assert on it (e.g.
  /// "the send request actually reached the server") — the structural
  /// evidence that a fault did or did not let a request leave the app.
  final Map<String, int> requestCounts = {};
  final List<Map<String, Object?>> requestLog = [];

  /// Text chunks served for the deterministic assistant reply. Distinct from
  /// any user prompt by construction.
  String assistantReplyText = 'fixture-acknowledged: your seeded local assistant reply';

  static Future<JourneyFixtureBackend> start() async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final backend = JourneyFixtureBackend._(server);
    server.listen(
      backend._handle,
      onError: (Object e) => print('FIXTURE SERVER ERROR: $e'),
    );
    return backend;
  }

  String get baseUrl => 'http://127.0.0.1:${_server.port}/';

  void arm(JourneyFault fault) => _faults.add(fault);

  void clear(JourneyFault fault) => _faults.remove(fault);

  void clearFaults() => _faults.clear();

  int countOf(String method, String path) => requestCounts['$method $path'] ?? 0;

  Future<void> stop() => _server.close(force: true);

  void _record(String method, HttpRequest req) {
    final path = req.uri.path;
    requestCounts['$method $path'] = (requestCounts['$method $path'] ?? 0) + 1;
    requestLog.add({
      'method': method,
      'path': path,
      'bearer': _bearerOf(req),
      'at': DateTime.now().toUtc().toIso8601String(),
    });
  }

  String? _bearerOf(HttpRequest req) {
    final auth = req.headers.value(HttpHeaders.authorizationHeader);
    if (auth == null || !auth.startsWith('Bearer ')) return null;
    return auth.substring(7);
  }

  /// Ownership guard: every seeded record belongs to [fixtureUid]. A request
  /// presenting the wrong-owner bearer is refused before any data is served.
  bool _ownershipRejected(HttpRequest req) {
    final bearer = _bearerOf(req);
    return bearer == wrongOwnerBearer;
  }

  Future<void> _handle(HttpRequest req) async {
    final method = req.method.toUpperCase();
    final path = req.uri.path;
    _record(method, req);

    if (_ownershipRejected(req)) {
      req.response.statusCode = HttpStatus.forbidden;
      req.response.headers.contentType = ContentType.json;
      req.response.write(jsonEncode({
        'error': 'ownership',
        'detail': 'bearer does not own the requested records',
      }));
      await req.response.close();
      return;
    }
    // Dynamic id routes before the exact-match switch.
    if (method == 'PATCH' && path.startsWith('/v3/memories/') && !path.contains('/baseline')) {
      await _handleMemoryEdit(req);
      return;
    }
    if (method == 'GET' && path.startsWith('/v1/conversations/')) {
      final id = path.substring('/v1/conversations/'.length).split('/').first;
      final match = conversations.where((c) => c['id'] == id).toList();
      if (match.isEmpty) {
        req.response.statusCode = 404;
        req.response.write(jsonEncode({'error': 'unknown conversation', 'id': id}));
      } else {
        req.response.statusCode = 200;
        req.response.headers.contentType = ContentType.json;
        req.response.write(jsonEncode(match.first));
      }
      await req.response.close();
      return;
    }

    switch ('$method $path') {
      case 'POST /v1/auth/local-dev/custom-token':
        final body = await _readBody(req);
        final uid = body['uid'] as String? ?? fixtureUid;
        req.response.statusCode = 200;
        req.response.write(jsonEncode({'custom_token': 'synthetic-custom-token-for-$uid'}));
        await req.response.close();
        return;

      case 'POST /v2/messages':
        await _handleChatSend(req);
        return;

      case 'GET /v2/messages':
        // Chat history: seeded empty; the journey's own send populates the
        // transcript in-memory through the real provider.
        req.response.statusCode = 200;
        req.response.headers.contentType = ContentType.json;
        req.response.write(jsonEncode([]));
        await req.response.close();
        return;

      case 'GET /v1/conversations':
        req.response.statusCode = 200;
        req.response.headers.contentType = ContentType.json;
        req.response.write(jsonEncode(conversations));
        await req.response.close();
        return;

      case 'GET /v2/apps/search':
        // ChatPage fetches installed chat apps; the fixture serves none.
        req.response.statusCode = 200;
        req.response.headers.contentType = ContentType.json;
        req.response.write(jsonEncode({
          'data': [],
          'pagination': {'total': 0, 'count': 0, 'offset': 0, 'limit': 50},
          'filters': {
            'sort': 'popular',
            'categories': [],
            'capabilities': [],
            'languages': [],
            'deployed_on': [],
          },
        }));
        await req.response.close();
        return;

      case 'POST /v3/memories':
        await _handleMemoryCreate(req);
        return;

      case 'GET /v3/memories':
        req.response.statusCode = 200;
        req.response.headers.contentType = ContentType.json;
        req.response.write(jsonEncode(memories));
        await req.response.close();
        return;

      default:
        req.response.statusCode = 404;
        req.response.write(jsonEncode({'error': 'no fixture route', 'route': '$method $path'}));
        await req.response.close();
    }
  }

  Future<void> _handleMemoryEdit(HttpRequest req) async {
    final id = req.uri.path.split('/').last;
    final body = await _readBody(req);
    final idx = memories.indexWhere((m) => m['id'] == id);
    if (idx == -1) {
      req.response.statusCode = 404;
      await req.response.close();
      return;
    }
    final edited = <String, dynamic>{
      ...memories[idx],
      'content': body['value'],
      'edited': true,
      'updated_at': DateTime.now().toUtc().toIso8601String(),
    };
    memories[idx] = edited;
    req.response.statusCode = 200;
    req.response.headers.contentType = ContentType.json;
    req.response.write(jsonEncode({'memory': edited}));
    await req.response.close();
  }

  Future<Map<String, dynamic>> _readBody(HttpRequest req) async {
    final text = await utf8.decoder.bind(req).join();
    if (text.isEmpty) return {};
    if (text.startsWith('{') || text.startsWith('[')) {
      return jsonDecode(text) as Map<String, dynamic>;
    }
    // x-www-form-urlencoded (the custom-token endpoint)
    return {for (final kv in text.split('&')) kv.split('=')[0]: Uri.decodeComponent(kv.split('=').last)};
  }

  Future<void> _handleChatSend(HttpRequest req) async {
    // Distinctness is structural: the reply references the prompt through a
    // fixed prefix and a server minted id, never by echoing it.
    final replyId = 'srv-reply-${DateTime.now().microsecondsSinceEpoch}';

    req.response.statusCode = 200;
    req.response.headers.contentType = ContentType.text;
    req.response.headers.set(HttpHeaders.transferEncodingHeader, 'chunked');
    req.response.bufferOutput = false;

    if (_faults.contains(JourneyFault.suppressAssistantReply)) {
      // Close the stream without any chunk — "the assistant reply never
      // arrived". The journey oracle must fail on the missing reply.
      await req.response.close();
      return;
    }

    final donePayload = base64Encode(utf8.encode(jsonEncode({
      'id': replyId,
      'text': '$assistantReplyText [$replyId]',
      'sender': 'ai',
      'created_at': DateTime.now().toUtc().toIso8601String(),
      'type': 'text',
    })));

    final chunks = [
      'data: $assistantReplyText\n\n',
      'done: $donePayload\n\n',
    ];
    for (final chunk in chunks) {
      req.response.add(utf8.encode(chunk));
      await req.response.flush();
    }
    await req.response.close();
  }

  Future<void> _handleMemoryCreate(HttpRequest req) async {
    if (_faults.contains(JourneyFault.dropMemorySave)) {
      req.response.statusCode = 503;
      req.response.write(jsonEncode({'error': 'persistence unavailable'}));
      await req.response.close();
      return;
    }
    final body = await _readBody(req);
    final now = DateTime.now().toUtc().toIso8601String();
    final stored = <String, dynamic>{
      // Full non-nullable wire set for GeneratedMemoryDB: the production
      // decoder must accept what the fixture serves.
      'id': 'srv-mem-${DateTime.now().microsecondsSinceEpoch}',
      'uid': fixtureUid,
      'content': body['content'],
      'visibility': body['visibility'] ?? 'public',
      'category': body['category'] ?? 'manual',
      'created_at': now,
      'updated_at': now,
      'discarded': false,
      'deleted': false,
      'edited': false,
      'reviewed': false,
      'user_review': null,
      'manually_added': true,
      'is_locked': false,
      'is_baseline': false,
      'is_dismissed': false,
      'is_read': false,
      'kg_extracted': false,
      'intent_backed': false,
      'curation_weight': 0,
      'subject_attribution': 'user',
      'embedding': [],
      'capture_device_ids': [],
      'conversation_id': null,
    };
    memories.add(stored);
    req.response.statusCode = 200;
    req.response.headers.contentType = ContentType.json;
    req.response.write(jsonEncode(stored));
    await req.response.close();
  }
}
