// Dart side of the privileged HTTP bridge — the iOS counterpart of the macOS
// BridgeHttp.swift, against core-foundation `core/contracts/src/bridge/http.ts`
// (ADR-008 §3 / ADR-009 §3).
//
// TOKEN CUSTODY: the base URL and the bearer token live HERE, in the shell, and
// are never sent to the webview. The surface sends only a method, an
// origin-relative path, and a JSON body string. Replies carry status + body text
// only — no response headers, so `set-cookie` / `www-authenticate` cannot leak
// into the page. Dev-grade custody this wave (dart-defines); keychain is owed.
//
// TRANSPORT: a Flutter JavaScriptChannel is ONE-WAY (JavaScriptMessage carries
// only a String, with no reply). So the surface's binding correlates by the
// request `id`: we post nothing back through the channel and instead invoke
// BridgeHttpContract.replyFunction in the page with (id, replyJson). That is
// exactly why `id` is part of the contract message rather than of a binding.
//
// The scheme handler (ADR-009) serves STATIC ASSETS ONLY and is deliberately
// untouched here: privileged HTTP is a separate channel, so a bundle-serving bug
// can never become a credentialed-network bug.
//
// The security-bearing constants — channel name, reply-function name, and the
// forbidden-header set — are GENERATED from the contract into
// `gen/bridge_http_contract.g.dart`; `core/scripts/gen-bridge-dart.mjs --check`
// fails the core DoD on drift. Nothing here is hand-copied.

import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:io';

import 'package:webview_flutter/webview_flutter.dart';

import 'gen/bridge_http_contract.g.dart';

class BridgeHttpPreparedRequest {
  BridgeHttpPreparedRequest({
    required this.id,
    required this.method,
    required this.url,
    required this.headers,
    required this.body,
    required this.bodyAfterHeaders,
  });

  final String id;
  final String method;
  final Uri url;
  final Map<String, String> headers;
  final String? body;
  final bool followsRedirects = false;

  /// The live path sets every header before `add`, matching dart:io's commit.
  final bool bodyAfterHeaders;

  /// Applies the exact wire ordering used by the live HttpClient path. Tests
  /// inject recorders; production passes request.headers.set/request.add.
  void apply({
    required void Function(bool followsRedirects) setFollowRedirects,
    required void Function(String name, String value) setHeader,
    required void Function(String body) addBody,
  }) {
    setFollowRedirects(followsRedirects);
    headers.forEach(setHeader);
    if (body != null) addBody(body!);
  }
}

class BridgeHttpPolicyResult {
  BridgeHttpPolicyResult.dispatch(this.request)
    : failureReason = null,
      detail = null;
  BridgeHttpPolicyResult.failure(this.failureReason, this.detail)
    : request = null;

  final BridgeHttpPreparedRequest? request;
  final BridgeHttpFailureReason? failureReason;
  final String? detail;
}

class BridgeHttpNormalizedResponse {
  BridgeHttpNormalizedResponse({
    required this.id,
    required this.status,
    required this.body,
    required this.retryAfterMs,
  });

  final String id;
  final int status;
  final String? body;
  final int? retryAfterMs;
  // Deliberately no response-header field: headers never cross into the page.
  bool get exposesResponseHeaders => false;
}

/// Correlation gate for the one-way channel: an id can produce at most one
/// page reply. Unknown/duplicate late replies are dropped at this boundary.
class BridgeHttpReplyGate {
  BridgeHttpReplyGate({this.maxEntries = 256}) : assert(maxEntries > 0);

  final int maxEntries;
  final Set<String> _settled = <String>{};
  final Queue<String> _order = Queue<String>();

  bool accept(String id) {
    if (!_settled.add(id)) return false;
    _order.addLast(id);
    while (_order.length > maxEntries) {
      _settled.remove(_order.removeFirst());
    }
    return true;
  }
}

/// Pure request/response policy used by the live handler and the generated
/// host-conformance test. The runner therefore exercises the same path as
/// `_handle` without a socket or a WebView.
class BridgeHttpHostPolicy {
  static BridgeHttpPolicyResult prepare({
    required String id,
    required String method,
    required String path,
    required Map<String, String> headers,
    required String? body,
    required Uri baseUrl,
    required String? token,
  }) {
    if (!const {'GET', 'POST', 'PATCH', 'DELETE'}.contains(method)) {
      return BridgeHttpPolicyResult.failure(
        BridgeHttpFailureReason.shellError,
        'missing or unsupported method/path',
      );
    }
    if (!path.startsWith('/') ||
        path.startsWith('//') ||
        path.contains('://')) {
      return BridgeHttpPolicyResult.failure(
        BridgeHttpFailureReason.shellError,
        'path is not origin-relative',
      );
    }
    final resolved = baseUrl.resolve(path);
    if (resolved.scheme != baseUrl.scheme ||
        resolved.host != baseUrl.host ||
        resolved.port != baseUrl.port) {
      return BridgeHttpPolicyResult.failure(
        BridgeHttpFailureReason.shellError,
        'path is not origin-relative',
      );
    }
    if (token == null || token.isEmpty) {
      return BridgeHttpPolicyResult.failure(
        BridgeHttpFailureReason.notAuthenticated,
        'shell holds no credential',
      );
    }
    final outbound = <String, String>{};
    for (final entry in headers.entries) {
      if (BridgeHttpContract.forbiddenHeaders.contains(entry.key.toLowerCase()))
        continue;
      outbound[entry.key] = entry.value;
    }
    if (body != null)
      outbound[HttpHeaders.contentTypeHeader] = 'application/json';
    outbound[HttpHeaders.authorizationHeader] = 'Bearer $token';
    return BridgeHttpPolicyResult.dispatch(
      BridgeHttpPreparedRequest(
        id: id,
        method: method,
        url: resolved,
        headers: outbound,
        body: body,
        bodyAfterHeaders: body != null,
      ),
    );
  }

  static BridgeHttpFailureReason transportFailure(String name) {
    return switch (name) {
      'offline' => BridgeHttpFailureReason.offline,
      'timeout' => BridgeHttpFailureReason.timeout,
      'cancelled' => BridgeHttpFailureReason.cancelled,
      _ => BridgeHttpFailureReason.shellError,
    };
  }

  static BridgeHttpNormalizedResponse normalizeResponse({
    required String id,
    required int status,
    required String? body,
    required int? retryAfterSeconds,
  }) {
    return BridgeHttpNormalizedResponse(
      id: id,
      status: status,
      body: body,
      retryAfterMs: retryAfterSeconds == null ? null : retryAfterSeconds * 1000,
    );
  }

  /// Live reply factory: only id/status/body/retry hint cross into the page;
  /// response headers are deliberately absent. The generated runner invokes
  /// this exact factory for its redaction assertion.
  static Map<String, dynamic> responsePayload(
    BridgeHttpNormalizedResponse normalized,
  ) {
    final out = <String, dynamic>{
      'id': normalized.id,
      'status': normalized.status,
      'body': normalized.body,
    };
    if (normalized.retryAfterMs != null) {
      out['retryAfterMs'] = normalized.retryAfterMs;
    }
    return out;
  }
}

class BridgeHttpHost {
  BridgeHttpHost({required this.baseUrl, required String? token})
    : _token = (token == null || token.isEmpty) ? null : token,
      _client = HttpClient()
        ..connectionTimeout = const Duration(seconds: 10)
        // The shell owns cookies: never persist or send them for API calls.
        ..userAgent = null;

  /// Shell-held origin. Never sent to the webview.
  final Uri baseUrl;
  final String? _token;
  final HttpClient _client;
  final BridgeHttpReplyGate _replyGate = BridgeHttpReplyGate();

  /// Requests actually dispatched, for verification output. No URLs, no tokens.
  int servedCount = 0;

  /// Whether a usable credential exists. Logged at boot without revealing it.
  bool get hasCredential => _token != null;

  /// Public only for the generated fixture runner; the live message handler
  /// calls this exact policy before opening a socket.
  static BridgeHttpPolicyResult prepareForConformance({
    required String id,
    required String method,
    required String path,
    required Map<String, String> headers,
    required String? body,
    required Uri baseUrl,
    required String? token,
  }) => BridgeHttpHostPolicy.prepare(
    id: id,
    method: method,
    path: path,
    headers: headers,
    body: body,
    baseUrl: baseUrl,
    token: token,
  );

  static BridgeHttpFailureReason transportFailureForConformance(
    String id,
    String name,
  ) => BridgeHttpHostPolicy.transportFailure(name);

  static BridgeHttpNormalizedResponse normalizeResponseForConformance({
    required String id,
    required int status,
    required String? body,
    required int? retryAfterSeconds,
  }) => BridgeHttpHostPolicy.normalizeResponse(
    id: id,
    status: status,
    body: body,
    retryAfterSeconds: retryAfterSeconds,
  );

  /// Register the one-way channel. Must run BEFORE the surface loads, so the
  /// page's feature detection sees `window.<channel>` and picks bridge mode.
  Future<void> register(WebViewController controller) {
    return controller.addJavaScriptChannel(
      BridgeHttpContract.channel,
      onMessageReceived: (JavaScriptMessage message) {
        // Fire-and-forget: the reply is delivered by invoking the page's reply
        // function, not by returning from this callback.
        unawaited(_handle(controller, message.message));
      },
    );
  }

  Future<void> _handle(WebViewController controller, String raw) async {
    String id = '?';
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) {
        return _fail(
          controller,
          id,
          BridgeHttpFailureReason.shellError,
          'malformed bridge http request',
        );
      }
      final rawId = decoded['id'];
      if (rawId is! String) {
        // No correlation id: there is nothing the page could match a reply to.
        return;
      }
      id = rawId;

      final method = decoded['method'];
      final path = decoded['path'];
      if (method is! String || path is! String) {
        return _fail(
          controller,
          id,
          BridgeHttpFailureReason.shellError,
          'missing or unsupported method/path',
        );
      }

      final rawHeaders = decoded['headers'];
      final headers = rawHeaders is Map
          ? Map<String, String>.fromEntries(
              rawHeaders.entries
                  .where(
                    (entry) => entry.key is String && entry.value is String,
                  )
                  .map(
                    (entry) =>
                        MapEntry(entry.key as String, entry.value as String),
                  ),
            )
          : <String, String>{};
      final body = decoded['body'] is String ? decoded['body'] as String : null;
      final decision = BridgeHttpHostPolicy.prepare(
        id: id,
        method: method,
        path: path,
        headers: headers,
        body: body,
        baseUrl: baseUrl,
        token: _token,
      );
      if (decision.request == null) {
        return _fail(controller, id, decision.failureReason!, decision.detail!);
      }
      servedCount += 1;
      final prepared = decision.request!;
      final request = await _client.openUrl(prepared.method, prepared.url);

      // ALL headers must be set before the first body write: dart:io commits the
      // header block as soon as the request becomes a stream sink, and mutating
      // headers afterwards throws HttpException. Ordering within that: caller
      // headers first (minus anything privileged), then OUR auth last so a
      // caller can never override it, then the body.
      prepared.apply(
        setFollowRedirects: (value) => request.followRedirects = value,
        setHeader: request.headers.set,
        addBody: (value) => request.add(utf8.encode(value)),
      );

      final response = await request.close().timeout(
        const Duration(seconds: 12),
      );
      final text = await response
          .transform(utf8.decoder)
          .join()
          .timeout(const Duration(seconds: 12));

      final retryAfter = response.headers.value(HttpHeaders.retryAfterHeader);
      final secs = retryAfter == null ? null : num.tryParse(retryAfter);
      final normalized = BridgeHttpHostPolicy.normalizeResponse(
        id: id,
        status: response.statusCode,
        body: text.isEmpty ? null : text,
        retryAfterSeconds: secs?.toInt(),
      );
      final out = BridgeHttpHostPolicy.responsePayload(normalized);

      await _reply(controller, id, <String, dynamic>{
        'ok': true,
        'response': out,
      });
    } on TimeoutException {
      await _fail(
        controller,
        id,
        BridgeHttpFailureReason.timeout,
        'request timed out',
      );
    } on SocketException catch (e) {
      // Detail carries the OS error code only — never the URL or the token.
      await _fail(
        controller,
        id,
        BridgeHttpFailureReason.offline,
        'socket error ${e.osError?.errorCode ?? -1}',
      );
    } on HttpException {
      await _fail(
        controller,
        id,
        BridgeHttpFailureReason.offline,
        'http exception',
      );
    } catch (_) {
      await _fail(
        controller,
        id,
        BridgeHttpFailureReason.shellError,
        'unexpected shell error',
      );
    }
  }

  Future<void> _fail(
    WebViewController controller,
    String id,
    BridgeHttpFailureReason reason,
    String detail,
  ) {
    return _reply(controller, id, <String, dynamic>{
      'ok': false,
      'failure': <String, dynamic>{
        'id': id,
        'reason': reason.wire,
        'detail': detail,
      },
    });
  }

  /// Deliver exactly one reply per id by invoking the page's reply function.
  /// Both arguments are JSON-encoded, so nothing in a path or body can break out
  /// of the expression.
  Future<void> _reply(
    WebViewController controller,
    String id,
    Map<String, dynamic> reply,
  ) async {
    if (!_replyGate.accept(id)) return;
    final js =
        '${BridgeHttpContract.replyFunction}('
        '${jsonEncode(id)},'
        '${jsonEncode(jsonEncode(reply))}'
        ');';
    try {
      await controller.runJavaScript(js);
    } catch (_) {
      // The page went away; the surface's own timeout will classify it.
    }
  }
}
