import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';
import 'package:pool/pool.dart';

import 'package:omi/services/dev_controls/journey_faults.dart';

class HttpPoolManager {
  static final HttpPoolManager instance = HttpPoolManager._();

  late final IOClient _client;
  late final Pool _pool;

  // GET deduplication: URL -> pending future
  final Map<String, Future<http.Response>> _pendingGets = {};

  HttpPoolManager._() {
    final httpClient = HttpClient()
      ..maxConnectionsPerHost = 15
      ..idleTimeout = const Duration(seconds: 15);

    _client = IOClient(httpClient);
    _pool = Pool(10, timeout: const Duration(seconds: 60));
  }

  /// Stamps a fresh X-Request-Start-Time on any outgoing request.
  /// Shared enforcement point: every pooled request flows through send() or
  /// sendStreaming(), and the deliberately unpooled upload path
  /// (makeMultipartApiCallUnpooled in shared.dart) calls this directly, so
  /// retries, pool-queued requests, and multipart uploads all get a current
  /// timestamp. (#6274)
  static void stampRequestTime(http.BaseRequest request) {
    request.headers['X-Request-Start-Time'] = (DateTime.now().millisecondsSinceEpoch / 1000).toString();
  }

  Future<http.Response> send(
    http.Request Function() requestBuilder, {
    Duration timeout = const Duration(seconds: 30),
    int retries = 1,
  }) async {
    final sample = requestBuilder();
    final isGet = sample.method == 'GET';
    final url = sample.url.toString();

    // Deduplicate GET requests
    if (isGet && _pendingGets.containsKey(url)) {
      return _pendingGets[url]!;
    }

    final future = _pool.withResource(() async {
      return _executeWithRetry(requestBuilder, timeout, retries);
    });

    if (isGet) {
      // Share the cleanup future with callers so request failures cannot escape
      // through a second, unobserved future (even when the caller catches them).
      final tracked = future.whenComplete(() {
        _pendingGets.remove(url);
      });
      _pendingGets[url] = tracked;
      return tracked;
    }
    return future;
  }

  /// Local-dev journey fault chokepoint. Every pooled request consults the
  /// gate; with no fault armed (and always in production-family builds, where
  /// arming is impossible) this is a no-op and the request is untouched.
  void _applyJourneyFaults(http.BaseRequest request) {
    if (!kDebugMode) return;
    final gate = JourneyFaultGate.instance;
    if (gate.armed.isEmpty) return;
    final decision = gate.beforeSend(request.method, request.url, request.headers['Authorization']);
    if (decision.drop) {
      // Surfaced as a connection failure so the app's existing transient
      // error classification (and nothing else) reacts — the mutation is
      // "the request never left the app", not a new error channel.
      throw SocketException('dev-journey-fault:suppress-send (${request.url})');
    }
    final swapped = decision.swappedBearer;
    if (swapped != null && request.headers.containsKey('Authorization')) {
      request.headers['Authorization'] = 'Bearer $swapped';
    }
  }

  Future<http.Response> _executeWithRetry(http.Request Function() requestBuilder, Duration timeout, int retries) async {
    http.Response? lastResponse;
    Object? lastError;

    for (var i = 0; i <= retries; i++) {
      final attemptDeadline = Stopwatch()..start();
      final abort = Completer<void>();
      try {
        final built = requestBuilder();
        final request = http.AbortableRequest(built.method, built.url, abortTrigger: abort.future)
          ..followRedirects = built.followRedirects
          ..maxRedirects = built.maxRedirects
          ..persistentConnection = built.persistentConnection
          ..encoding = built.encoding
          ..headers.addAll(built.headers)
          ..bodyBytes = built.bodyBytes;
        stampRequestTime(request);
        _applyJourneyFaults(request);
        final streamed = await _client.send(request).timeout(
          timeout,
          onTimeout: () {
            if (!abort.isCompleted) abort.complete();
            throw TimeoutException('Request timeout');
          },
        );
        // One deadline covers headers and body: a server that sends headers
        // and then stalls the body must not extend the caller's budget to
        // timeout + timeout. Spend only what is left of this attempt.
        final bodyBudget = timeout - attemptDeadline.elapsed;
        if (bodyBudget <= Duration.zero) throw TimeoutException('Request timeout');
        lastResponse = await http.Response.fromStream(streamed).timeout(
          bodyBudget,
          onTimeout: () {
            if (!abort.isCompleted) abort.complete();
            throw TimeoutException('Request timeout');
          },
        );

        if (lastResponse.statusCode < 500) {
          return lastResponse;
        }
        lastError = Exception('Server error: ${lastResponse.statusCode}');
      } on TimeoutException {
        lastError = TimeoutException('Request timeout');
      } on SocketException catch (e) {
        lastError = e;
      } on HandshakeException catch (e) {
        lastError = e;
      } on http.ClientException catch (e) {
        lastError = e;
      } catch (e) {
        lastError = e;
        rethrow;
      }

      if (i < retries) {
        await Future.delayed(Duration(milliseconds: 200 * (i + 1)));
      }
    }

    if (lastResponse != null) return lastResponse;
    throw lastError ?? Exception('Request failed with unknown error');
  }

  Future<http.StreamedResponse> sendStreaming(
    http.BaseRequest request, {
    Duration timeout = const Duration(minutes: 5),
  }) {
    stampRequestTime(request);
    _applyJourneyFaults(request);
    return _client.send(request).timeout(timeout);
  }

  void dispose() {
    _pool.close();
    _client.close();
    _pendingGets.clear();
  }
}
