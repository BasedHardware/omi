import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'heavy_fixture.dart';

/// In-process loopback fixture API for the profile-mode perf harness. Runs
/// inside the app process (dart:io works in profile), so the simulator app
/// talks to itself over loopback with the real HTTP client.
///
/// Profile builds never arm the debug fixture-authority registry, so requests
/// carry no Omi credentials — this fixture is deliberately credential-free.
///
/// Shape decisions (each mirrors a heavy-account offline-ish cold start):
///  - `/v1/conversations*` → 200 with an empty page: the provider then
///    restores Home from the seeded conversations cache (the real heavy
///    decode path) and does not enter a failure retry loop.
///  - upload paths → 429: WAL sync stays rate-limited with WALs pending,
///    David's 6.5k-backlog shape, without an unbounded upload storm.
///  - everything else → fast empty 200/404 so callers settle quickly and
///    deterministically; every request is counted for the receipt.
class HeavyFixtureServer {
  HttpServer? _server;
  final _counts = <String, int>{};
  int get requestCount => _counts.values.fold(0, (a, b) => a + b);
  Map<String, int> get countsByKind => Map.unmodifiable(_counts);
  int activeUploads = 0;

  String? get baseUrl => _server == null ? null : 'http://127.0.0.1:${_server!.port}/';

  static const _uploadPrefixes = ['/v2/sync-local-files'];

  Future<void> start() async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen(_handle);
    _server = server;
  }

  Future<void> stop() async {
    await _server?.close(force: true);
    _server = null;
  }

  void _handle(HttpRequest request) async {
    try {
      final path = request.uri.path;
      _counts[path] = (_counts[path] ?? 0) + 1;
      if (kDebugMode) debugPrint('perf-fixture ${request.method} $path');

      // Drain request bodies so clients never stall on a full socket window.
      unawaited(request.drain<void>().catchError((Object _) {}));

      if (path.startsWith('/v1/conversations/perf-heavy-conv-')) {
        final index = int.tryParse(path.split('perf-heavy-conv-').last);
        if (index != null && index >= 0 && index < heavyConversationCount) {
          await _json(request, 200, heavyConversation(index).toJson());
          return;
        }
      }

      if (_uploadPrefixes.any(path.startsWith)) {
        // Stay in-flight across the scripted lifecycle transitions; no real
        // backend or audio decoder consumes these synthetic framed bytes.
        activeUploads++;
        try {
          await Future<void>.delayed(const Duration(seconds: 30));
          request.response.headers.set('retry-after', '60');
          await _json(request, 429, {'code': 'rate_limited', 'detail': 'perf fixture keeps sync backed off'});
        } finally {
          activeUploads--;
        }
        return;
      }
      switch (path) {
        case '/v1/conversations':
          await _json(request, 200, []);
          return;
        case '/v1/apps/search':
          await _json(request, 200, {
            'data': [],
            'pagination': {'total': 0, 'count': 0, 'offset': 0, 'limit': 50, 'hasNext': false, 'hasPrevious': false},
            'filters': {'sort': 'popular', 'categories': [], 'capabilities': [], 'languages': [], 'deployed_on': []},
          });
          return;
        case '/v1/episodes/live':
          await _json(request, 200, {'enabled': true, 'episode': null});
          return;
        case '/v2/messages':
          await _json(request, 200, []);
          return;
        case '/v3/memories':
          await _json(request, 200, []);
          return;
        default:
          await _json(request, 404, {'detail': 'perf fixture: no such endpoint'});
          return;
      }
    } catch (error) {
      try {
        await _json(request, 500, {'detail': 'perf fixture error: $error'});
      } catch (_) {}
    }
  }

  Future<void> _json(HttpRequest request, int status, Object body) async {
    request.response.statusCode = status;
    request.response.headers.contentType = ContentType.json;
    request.response.write(jsonEncode(body));
    await request.response.close();
  }
}
