import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';
import 'package:pool/pool.dart';

import 'package:omi/services/dev_controls/journey_faults.dart';
import 'package:omi/backend/http/api_edge_throttle_telemetry.dart';

class _ObservedStreamedResponse extends http.StreamedResponse implements http.BaseResponseWithUrl {
  @override
  final Uri url;

  _ObservedStreamedResponse(http.StreamedResponse response, Stream<List<int>> stream, this.url)
      : super(
          stream,
          response.statusCode,
          contentLength: response.contentLength,
          request: response.request,
          headers: response.headers,
          isRedirect: response.isRedirect,
          persistentConnection: response.persistentConnection,
          reasonPhrase: response.reasonPhrase,
        );
}

class HttpPoolManager {
  static final HttpPoolManager instance = HttpPoolManager._();

  late IOClient _client;
  late final Pool _pool;

  /// Where the pool was first built. Replacement clients and their retirement
  /// timers live here too, so an HttpOverrides zone that supplied the first
  /// client supplies the rest.
  final Zone _zone;

  /// Pools replaced by [resetConnections] whose requests may still be running.
  final List<({IOClient client, Timer deadline})> _retired = [];
  final Duration _retiredGrace;
  final int _maxRetired;
  final Duration _connectionTimeout;
  bool _disposed = false;

  // GET deduplication: URL -> pending future
  final Map<String, Future<http.Response>> _pendingGets = {};

  /// A retired pool is force-closed after this. It outlasts every bounded
  /// request through the pool (an upload waits up to 5 min for headers and
  /// 2 min for its body), so only work that has stalled is cut off.
  static const retiredClientGrace = Duration(minutes: 15);

  /// A reset storm force-closes the oldest retired pool beyond this many.
  static const maxRetiredClients = 4;

  /// Bounds TCP connect plus TLS handshake. Closing a pool cannot stop a
  /// handshake whose peer went silent; only this timeout ends that request.
  static const connectionTimeout = Duration(seconds: 30);

  HttpPoolManager._({
    Duration retiredGrace = retiredClientGrace,
    int maxRetired = maxRetiredClients,
    Duration connectTimeout = connectionTimeout,
  })  : _zone = Zone.current,
        _retiredGrace = retiredGrace,
        _maxRetired = maxRetired,
        _connectionTimeout = connectTimeout {
    _client = _newClient();
    _pool = Pool(10, timeout: const Duration(seconds: 60));
  }

  @visibleForTesting
  HttpPoolManager.forTesting({
    Duration retiredGrace = retiredClientGrace,
    int maxRetired = maxRetiredClients,
    Duration connectTimeout = connectionTimeout,
  }) : this._(retiredGrace: retiredGrace, maxRetired: maxRetired, connectTimeout: connectTimeout);

  IOClient _newClient() => IOClient(
        _zone.run(
          () => HttpClient()
            ..maxConnectionsPerHost = 15
            ..idleTimeout = const Duration(seconds: 15)
            ..connectionTimeout = _connectionTimeout,
        ),
      );

  /// Sends every later request over new sockets.
  ///
  /// Keep-alive sockets live as long as requests keep arriving within the idle
  /// timeout, so they outlive a Wi-Fi/cellular switch; iOS then fails the
  /// reused socket with EADDRNOTAVAIL ("Can't assign requested address").
  /// The old pool is retired, not closed: closing cancels connects in flight.
  /// Its requests and response streams finish, its idle sockets expire, and
  /// whatever is still open at its deadline was stalled and is closed.
  void resetConnections() {
    if (_disposed) return;
    final retired = _client;
    _client = _newClient();
    _retired.add((client: retired, deadline: _zone.run(() => Timer(_retiredGrace, () => _closeRetired(retired)))));
    while (_retired.length > _maxRetired) {
      _closeRetired(_retired.first.client);
    }
  }

  void _closeRetired(IOClient client) {
    final index = _retired.indexWhere((retired) => identical(retired.client, client));
    if (index < 0) return;
    final retired = _retired.removeAt(index);
    retired.deadline.cancel();
    retired.client.close();
  }

  @visibleForTesting
  int get retiredClientCount => _retired.length;

  /// A transport failure can mean the network under the pool is gone, and the
  /// failed socket's idle siblings were opened on the same network. Only the
  /// pool that failed is replaced, so a burst of its failures resets once.
  void _resetAfterTransportFailure(Object error, IOClient failedClient) {
    if (error is http.RequestAbortedException) return;
    if (error is! SocketException && error is! http.ClientException) return;
    if (identical(failedClient, _client)) resetConnections();
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

  /// Exercises the fault chokepoint without sending. Production sends go
  /// through [send] and [sendStreaming].
  @visibleForTesting
  void applyJourneyFaultsForTesting(http.BaseRequest request) => _applyJourneyFaults(request);

  Future<http.Response> _executeWithRetry(http.Request Function() requestBuilder, Duration timeout, int retries) async {
    http.Response? lastResponse;
    Object? lastError;

    for (var i = 0; i <= retries; i++) {
      final attemptDeadline = Stopwatch()..start();
      final abort = Completer<void>();
      final client = _client;
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
        final streamed = await client.send(request).timeout(
          timeout,
          onTimeout: () {
            if (!abort.isCompleted) abort.complete();
            throw TimeoutException('Request timeout');
          },
        );
        ApiEdgeThrottleTelemetry.instance.observe(request, streamed);
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
        _resetAfterTransportFailure(e, client);
      } on HandshakeException catch (e) {
        lastError = e;
      } on http.ClientException catch (e) {
        lastError = e;
        _resetAfterTransportFailure(e, client);
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
    final client = _client;
    return client.send(request).timeout(timeout).then(
      (response) {
        ApiEdgeThrottleTelemetry.instance.observe(request, response);
        return _ObservedStreamedResponse(
          response,
          response.stream.handleError((Object error, StackTrace stackTrace) {
            _resetAfterTransportFailure(error, client);
            Error.throwWithStackTrace(error, stackTrace);
          }),
          response is http.BaseResponseWithUrl ? (response as http.BaseResponseWithUrl).url : request.url,
        );
      },
      onError: (Object error, StackTrace stackTrace) {
        _resetAfterTransportFailure(error, client);
        Error.throwWithStackTrace(error, stackTrace);
      },
    );
  }

  void dispose() {
    _disposed = true;
    _pool.close();
    _client.close();
    while (_retired.isNotEmpty) {
      _closeRetired(_retired.first.client);
    }
    _pendingGets.clear();
  }
}
