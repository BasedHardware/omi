// In-app loopback HTTP server (candidate A of the ship-origin fork).
// Serves the probe surface from flutter assets on 127.0.0.1 and exposes the
// endpoints the probe suite exercises: echo, chunked stream, websocket.
// Everything interesting it observes goes to debugPrint with a [loop] prefix.
import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

class LoopServer {
  HttpServer? _server;
  final String assetPrefix; // e.g. 'assets/surface-loop'
  LoopServer(this.assetPrefix);

  int get port => _server!.port;

  static const _mime = {
    'html': 'text/html; charset=utf-8',
    'js': 'text/javascript',
    'json': 'application/json',
  };

  /// port 0 = ephemeral (OS-assigned) — used to demonstrate that the web
  /// origin, and therefore all storage, is keyed on the port.
  Future<void> start({int port = 0}) async {
    _server = await HttpServer.bind(InternetAddress.loopbackIPv4, port);
    debugPrint('[loop] listening on 127.0.0.1:${_server!.port}');
    _server!.listen(_handle, onError: (Object e) => debugPrint('[loop] server error $e'));
  }

  Future<void> stop() async => _server?.close(force: true);

  Future<void> _handle(HttpRequest req) async {
    final path = req.uri.path;
    final cookie = req.headers.value('cookie');
    debugPrint('[loop] ${req.method} $path cookie=${cookie ?? '(none)'}');
    try {
      switch (path) {
        case '/probe/echo':
          req.response.headers.contentType = ContentType.json;
          req.response.write(
              '{"echo":true,"xProbe":"${req.headers.value('x-probe')}","sawCookie":"${cookie ?? ''}"}');
          await req.response.close();
        case '/probe/stream':
          await _stream(req);
        case '/probe/ws':
          final ws = await WebSocketTransformer.upgrade(req);
          ws.listen((dynamic m) => ws.add('echo:$m'));
          for (var i = 1; i <= 3; i++) {
            await Future<void>.delayed(const Duration(milliseconds: 150));
            ws.add('push-$i@${DateTime.now().millisecondsSinceEpoch}');
          }
        default:
          await _asset(req, path);
      }
    } catch (e) {
      debugPrint('[loop] handler error on $path: $e');
      try {
        req.response.statusCode = 500;
        await req.response.close();
      } catch (_) {}
    }
  }

  Future<void> _stream(HttpRequest req) async {
    final res = req.response;
    res.bufferOutput = false;
    res.headers.contentType = ContentType('text', 'plain');
    var aborted = false;
    final t0 = DateTime.now();
    unawaited(res.done.then(
      (_) => debugPrint('[loop] stream res.done after ${DateTime.now().difference(t0).inMilliseconds}ms'),
      onError: (Object e) {
        aborted = true;
        debugPrint('[loop] stream client ABORT observed after ${DateTime.now().difference(t0).inMilliseconds}ms: $e');
      },
    ));
    for (var i = 1; i <= 10 && !aborted; i++) {
      res.write('chunk-$i@${DateTime.now().millisecondsSinceEpoch}\n');
      // flush() can hang forever on a dead peer — race it against a timeout so
      // we can report whether client aborts are actually observable server-side.
      final flushed = await res.flush().then((_) => true).catchError((Object e) {
        debugPrint('[loop] stream flush error at chunk $i: $e');
        return false;
      }).timeout(const Duration(seconds: 3), onTimeout: () {
        debugPrint('[loop] stream flush TIMED OUT at chunk $i (peer gone, no error surfaced)');
        return false;
      });
      if (!flushed) return;
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
    if (!aborted) {
      debugPrint('[loop] stream completed all 10 chunks (no abort seen)');
      await res.close();
    }
  }

  Future<void> _asset(HttpRequest req, String path) async {
    final name = path == '/' ? 'index.html' : path.substring(1);
    final res = req.response;
    try {
      final data = await rootBundle.load('$assetPrefix/$name');
      final ext = name.split('.').last;
      res.headers.set('content-type', _mime[ext] ?? 'application/octet-stream');
      res.headers.set('cache-control', 'no-store');
      if (name == 'index.html') {
        // Cookie probes: does an http loopback page store a plain cookie, and
        // does WebKit accept a Secure-attribute cookie from http://127.0.0.1?
        res.headers.add('set-cookie', 'plain=1; Path=/');
        res.headers.add('set-cookie', 'secflag=1; Path=/; Secure');
      }
      res.add(data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes));
    } catch (_) {
      res.statusCode = 404;
      res.write('not found: $name');
    }
    await res.close();
  }
}
