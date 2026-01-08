import 'dart:async';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';
import 'package:pool/pool.dart';

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
      _pendingGets[url] = future;
      future.whenComplete(() => _pendingGets.remove(url));
    }

    return future;
  }

  Future<http.Response> _executeWithRetry(
    http.Request Function() requestBuilder,
    Duration timeout,
    int retries,
  ) async {
    http.Response? lastResponse;
    Object? lastError;

    for (var i = 0; i <= retries; i++) {
      try {
        final request = requestBuilder();
        final streamed = await _client.send(request).timeout(timeout);
        lastResponse = await http.Response.fromStream(streamed);

        if (lastResponse.statusCode < 500) {
          return lastResponse;
        }
        lastError = Exception('Server error: ${lastResponse.statusCode}');
      } on TimeoutException {
        lastError = TimeoutException('Request timeout');
      } on SocketException catch (e) {
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

  Future<http.StreamedResponse> sendStreaming(http.BaseRequest request) {
    return _client.send(request);
  }

  void dispose() {
    _pool.close();
    _client.close();
    _pendingGets.clear();
  }
}
