import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/clock_skew_detector.dart';
import 'package:omi/backend/http/http_pool_manager.dart';
import 'package:omi/backend/http/streaming_error.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/jwt_expiry.dart';
import 'package:omi/services/account_cutover/account_cutover_runtime.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class ApiClient {
  static const Duration requestTimeoutRead = Duration(seconds: 30);
  static const Duration requestTimeoutWrite = Duration(seconds: 300);

  static const Duration streamSetupTimeout = Duration(seconds: 60);
  static const Duration streamInactivityTimeout = Duration(seconds: 60);
  static const Duration streamTotalTimeout = Duration(seconds: 180);

  static void dispose() {
    HttpPoolManager.instance.dispose();
  }
}

class AuthTokenUnavailableException implements Exception {
  final AuthTokenResult result;
  AuthTokenUnavailableException(this.result);

  @override
  String toString() => 'AuthTokenUnavailableException(${result.runtimeType})';
}

// Normal-mode connectivity failures on mobile (no network, DNS failure,
// connection reset, TLS handshake during reconnect, request timeout, OS abort
// when the app backgrounds mid-upload). Reporting these to Crashlytics drowns
// out real signal — caller logs them locally and either returns null or
// rethrows for the upstream sync state machine.
bool isTransientNetworkError(Object e) {
  if (e is SocketException) return true;
  if (e is HandshakeException) return true;
  if (e is TimeoutException) return true;
  final text = e is http.ClientException ? e.message : e.toString();
  final lower = text.toLowerCase();
  return text.contains('SocketException') ||
      text.contains('HandshakeException') ||
      text.contains('TimeoutException') ||
      text.contains('Connection closed') ||
      text.contains('Connection reset') ||
      text.contains('Failed host lookup') ||
      text.contains('Network is unreachable') ||
      text.contains('Bad file descriptor') ||
      // Android leave/background mid-multipart (#4587): match the full abort
      // phrase only — a bare "ClientSoftware" token is not a connectivity signal.
      lower.contains('software caused connection abort');
}

Future<String> getAuthHeader({
  bool expireTerminalSession = true,
  AuthSessionSnapshot? sessionSnapshot,
  AuthService? authService,
}) async {
  final service = authService ?? AuthService.instance;
  if (sessionSnapshot != null) {
    if (!service.isSessionSnapshotCurrent(sessionSnapshot)) {
      throw AuthTokenUnavailableException(const AuthTokenMissingUser());
    }
    // Capture before awaiting refresh so a later session cannot substitute its
    // token. The post-await snapshot check below binds either result to this
    // same session.
    final storedToken = SharedPreferencesUtil().authToken;
    final refreshResult = await service.refreshIdToken();
    if (!service.isSessionSnapshotCurrent(sessionSnapshot)) {
      throw AuthTokenUnavailableException(const AuthTokenMissingUser());
    }
    switch (refreshResult) {
      case AuthTokenSuccess(:final token):
        return 'Bearer $token';
      case AuthTokenMissingToken():
        if (expireTerminalSession) {
          await service.expireSession(const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.missingToken));
        }
        throw AuthTokenUnavailableException(refreshResult);
      case AuthTokenTerminalFailure(:final code):
        if (expireTerminalSession) {
          await service.expireSession(
            AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.terminalTokenFailure, code: code),
          );
        }
        throw AuthTokenUnavailableException(refreshResult);
      case AuthTokenTransientFailure():
        final expiry = jwtExpiry(storedToken);
        if (storedToken.isNotEmpty &&
            expiry != null &&
            expiry.isAfter(DateTime.now().add(const Duration(minutes: 5)))) {
          return 'Bearer $storedToken';
        }
        throw AuthTokenUnavailableException(refreshResult);
      case _:
        throw AuthTokenUnavailableException(refreshResult);
    }
  }

  if (!service.isSignedIn()) {
    throw AuthTokenUnavailableException(const AuthTokenMissingUser());
  }

  final storedToken = SharedPreferencesUtil().authToken;
  // The token's own exp outranks the cached copy: #11694 saw clients present a
  // three-day-dead token because the cached expiry had advanced without it.
  final expiry =
      jwtExpiry(storedToken) ?? DateTime.fromMillisecondsSinceEpoch(SharedPreferencesUtil().tokenExpirationTime);
  bool hasAuthToken = storedToken.isNotEmpty;

  bool isExpirationDateValid = !(expiry.isBefore(DateTime.now()) ||
      expiry.isAtSameMomentAs(DateTime.fromMillisecondsSinceEpoch(0)) ||
      (expiry.isBefore(DateTime.now().add(const Duration(minutes: 5))) && expiry.isAfter(DateTime.now())));

  if (!hasAuthToken || !isExpirationDateValid) {
    final refreshResult = await AuthService.instance.refreshIdToken();
    switch (refreshResult) {
      case AuthTokenSuccess(:final token):
        SharedPreferencesUtil().authToken = token;
        break;
      case AuthTokenTransientFailure():
        if (expiry.isBefore(DateTime.now())) {
          // Preserve a still-valid token during transient refresh trouble, but
          // never reuse one whose expiration has already passed.
          SharedPreferencesUtil().authToken = '';
        }
        break;
      case AuthTokenMissingUser():
        throw AuthTokenUnavailableException(refreshResult);
      case AuthTokenMissingToken():
        if (expireTerminalSession) {
          await AuthService.instance.expireSession(
            const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.missingToken),
          );
        }
        throw AuthTokenUnavailableException(refreshResult);
      case AuthTokenTerminalFailure(:final code):
        if (expireTerminalSession) {
          await AuthService.instance.expireSession(
            AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.terminalTokenFailure, code: code),
          );
        }
        throw AuthTokenUnavailableException(refreshResult);
    }
    hasAuthToken = SharedPreferencesUtil().authToken.isNotEmpty;
    if (!hasAuthToken) throw AuthTokenUnavailableException(refreshResult);
  }

  if (!hasAuthToken) throw AuthTokenUnavailableException(const AuthTokenMissingToken());
  return 'Bearer ${SharedPreferencesUtil().authToken}';
}

/// Builds common headers for API and WebSocket requests
/// Centralizes header logic for easy maintenance and consistency
/// Automatically adds Authorization header if required
Future<Map<String, String>> buildHeaders({
  required bool requireAuthCheck,
  Map<String, String> fromHeaders = const {},
  bool expireTerminalSession = true,
  String? url,
  String? method,
  bool forWebSocket = false,
  AuthSessionSnapshot? sessionSnapshot,
  AuthService? authService,
}) async {
  final headers = <String, String>{
    'X-Request-Start-Time': (DateTime.now().millisecondsSinceEpoch / 1000).toString(),
    'X-App-Platform': PlatformManager.instance.platform,
    'X-Device-Id-Hash': PlatformManager.instance.deviceIdHash,
    'X-App-Version': PlatformManager.instance.appVersion,
    'X-App-Build': PlatformManager.instance.appBuild,
    ...fromHeaders,
  };

  if (shouldAttachAccountGenerationHeader(
    url: url,
    method: method,
    requireAuthCheck: requireAuthCheck,
    forWebSocket: forWebSocket,
  )) {
    final accountGeneration = AccountCutoverRuntime.instance.control.accountGeneration;
    // Generation-zero remains compatible without the header; positive generations
    // must present matching metadata on mutating Omi API requests / product WS.
    if (accountGeneration > 0) {
      headers['X-Account-Generation'] = accountGeneration.toString();
    }
  }

  if (requireAuthCheck) {
    // Authenticated requests must never degrade into anonymous traffic. A
    // typed exception stops the request before it reaches the network.
    headers['Authorization'] = await getAuthHeader(
      expireTerminalSession: expireTerminalSession,
      sessionSnapshot: sessionSnapshot,
      authService: authService,
    );
  }

  return headers;
}

@visibleForTesting
String normalizeOmiApiUrlForHostMatch(String url) {
  // HTTP helpers and product sockets share one API host; compare scheme-neutrally
  // so `wss://` listen URLs still count as Omi API traffic.
  return url
      .replaceFirst(RegExp(r'^https://', caseSensitive: false), '')
      .replaceFirst(RegExp(r'^http://', caseSensitive: false), '')
      .replaceFirst(RegExp(r'^wss://', caseSensitive: false), '')
      .replaceFirst(RegExp(r'^ws://', caseSensitive: false), '');
}

bool _isRequiredAuthCheck(String url) {
  // Agent VM endpoints always hit prod even when app uses dev
  if (url.contains('api.omi.me')) return true;
  final base = Env.apiBaseUrl;
  if (base != null && base.isNotEmpty) {
    final normalizedUrl = normalizeOmiApiUrlForHostMatch(url);
    final normalizedBase = normalizeOmiApiUrlForHostMatch(base);
    if (normalizedBase.isNotEmpty && normalizedUrl.contains(normalizedBase)) {
      return true;
    }
  }
  return false;
}

const _mutatingHttpMethods = {'POST', 'PUT', 'PATCH', 'DELETE'};

/// `X-Account-Generation` is only for authenticated Omi API mutation traffic and
/// product WebSocket admission — never arbitrary third-party hosts (e.g. zip CDN).
@visibleForTesting
bool shouldAttachAccountGenerationHeader({
  String? url,
  String? method,
  required bool requireAuthCheck,
  bool forWebSocket = false,
}) {
  if (!requireAuthCheck) return false;
  if (url != null && url.isNotEmpty && !_isRequiredAuthCheck(url)) return false;
  if (forWebSocket) return true;
  if (method == null || method.isEmpty) return false;
  return _mutatingHttpMethods.contains(method.toUpperCase());
}

Future<http.StreamedResponse> makeRawApiCall({
  required String url,
  required String method,
  Map<String, String> headers = const {},
  String body = '',
  bool signOutOn401 = true,
  Future<void>? abortTrigger,
  Duration timeout = const Duration(minutes: 5),
  AuthSessionSnapshot? sessionSnapshot,
  AuthService? authService,
  Future<http.StreamedResponse> Function(http.Request request)? sendStreaming,
}) async {
  final service = authService ?? AuthService.instance;
  final send = sendStreaming ?? (request) => HttpPoolManager.instance.sendStreaming(request, timeout: timeout);
  if (sessionSnapshot != null && !service.isSessionSnapshotCurrent(sessionSnapshot)) {
    return _authUnavailableStreamedResponse();
  }
  final requireAuthCheck = _isRequiredAuthCheck(url) || sessionSnapshot != null;
  try {
    var builtHeaders = await buildHeaders(
      requireAuthCheck: requireAuthCheck,
      fromHeaders: headers,
      expireTerminalSession: signOutOn401,
      url: url,
      method: method,
      sessionSnapshot: sessionSnapshot,
      authService: service,
    );
    if (sessionSnapshot != null && !service.isSessionSnapshotCurrent(sessionSnapshot)) {
      return _authUnavailableStreamedResponse();
    }
    var request = _buildStreamingRequest(url, builtHeaders, body, method, abortTrigger);
    var response = await send(request);
    if (requireAuthCheck && response.statusCode == 401) {
      response = await refreshAndReplayAfter401(
        firstResponse: response,
        statusCode: (value) => value.statusCode,
        disposeUnauthorizedResponse: _drainStreamedResponse,
        expireTerminalSession: signOutOn401,
        authService: service,
        sessionSnapshot: sessionSnapshot,
        replay: () async {
          if (sessionSnapshot != null && !service.isSessionSnapshotCurrent(sessionSnapshot)) {
            throw AuthTokenUnavailableException(const AuthTokenMissingUser());
          }
          builtHeaders = await buildHeaders(
            requireAuthCheck: true,
            fromHeaders: headers,
            expireTerminalSession: signOutOn401,
            url: url,
            method: method,
            sessionSnapshot: sessionSnapshot,
            authService: service,
          );
          if (sessionSnapshot != null && !service.isSessionSnapshotCurrent(sessionSnapshot)) {
            throw AuthTokenUnavailableException(const AuthTokenMissingUser());
          }
          request = _buildStreamingRequest(url, builtHeaders, body, method, abortTrigger);
          return send(request);
        },
      );
      if (response.statusCode == 401) return _authUnavailableStreamedResponse();
    }
    if (requireAuthCheck && response.statusCode == HttpStatus.forbidden) {
      // The fence is in the body; read it once and hand the caller an
      // equivalent response.
      final materialized = await _materializeErrorResponse(response);
      await _expireSessionIfAccountDeleted(materialized.statusCode, materialized.body, authService: service);
      return http.StreamedResponse(
        Stream<List<int>>.value(materialized.bodyBytes),
        materialized.statusCode,
        contentLength: materialized.bodyBytes.length,
        request: response.request,
        headers: materialized.headers,
        reasonPhrase: materialized.reasonPhrase,
      );
    }
    return response;
  } on AuthTokenUnavailableException catch (e) {
    await _handleAuthUnavailable(e, expireTerminalSession: signOutOn401);
    Logger.debug('Authenticated raw request blocked before send: ${e.result.runtimeType}');
    return _authUnavailableStreamedResponse();
  }
}

http.Request _buildStreamingRequest(
  String url,
  Map<String, String> headers,
  String body,
  String method,
  Future<void>? abortTrigger,
) {
  final request = http.AbortableRequest(method, Uri.parse(url), abortTrigger: abortTrigger);
  request.headers.addAll(headers);
  if (method != 'GET' && body.isNotEmpty) {
    request.headers['Content-Type'] = 'application/json';
    request.body = body;
  }
  return request;
}

Future<void> _drainStreamedResponse(http.StreamedResponse response) async {
  try {
    await response.stream.drain<void>();
  } catch (e) {
    Logger.debug('Failed to drain unauthorized response: ${e.runtimeType}');
  }
}

@visibleForTesting
Future<void> drainStreamedResponseForTesting(http.StreamedResponse response) => _drainStreamedResponse(response);

http.StreamedResponse _authUnavailableStreamedResponse() =>
    http.StreamedResponse(const Stream<List<int>>.empty(), 401, reasonPhrase: 'Authentication unavailable');

void _checkClockSkewResponse(http.Response response) {
  ClockSkewDetector.instance.checkResponse(response);
}

Future<http.Response> _materializeErrorResponse(http.StreamedResponse response) async {
  try {
    return await http.Response.fromStream(response);
  } catch (e) {
    // Preserve the quota/error sentinel even when the provider resets a
    // truncated response before the body can be read.
    Logger.debug('Failed to materialize streaming error response: ${e.runtimeType}');
    return http.Response('{}', response.statusCode, reasonPhrase: response.reasonPhrase, headers: response.headers);
  }
}

/// The backend's deleted-account fence (`enforce_account_deletion_http_access`):
/// every request of an account whose deletion wipe is pending or failed is
/// answered 403 with this `detail.code`; WebSockets close with
/// [accountDeletionWebSocketCloseCode]. Nothing the app can do with that
/// account succeeds, so the session is terminal and the user goes back to
/// sign-in instead of being walked into dead-end prompts (the forced
/// language sheet whose save then fails).
const String accountDeletionInProgressCode = 'account_deletion_in_progress';
const int accountDeletionWebSocketCloseCode = 4005;

/// The wipe status carried by a deleted-account 403 body, or null when
/// [body] is any other response.
String? accountDeletionStatusOf(String body) {
  if (body.isEmpty) return null;
  try {
    final decoded = jsonDecode(body);
    if (decoded is! Map) return null;
    final detail = decoded['detail'];
    if (detail is! Map || detail['code'] != accountDeletionInProgressCode) return null;
    return detail['status']?.toString() ?? '';
  } on FormatException {
    return null;
  }
}

/// Expires the session (once; [AuthService.expireSession] is idempotent) when
/// a 403 is the deleted-account fence. Any other 403 is left to the caller.
Future<void> _expireSessionIfAccountDeleted(int statusCode, String body, {AuthService? authService}) async {
  if (statusCode != HttpStatus.forbidden) return;
  final status = accountDeletionStatusOf(body);
  if (status == null) return;
  Logger.debug('Account deletion in progress (wipe status: $status): expiring the session');
  await (authService ?? AuthService.instance).expireSession(
    AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.accountDeleted, code: status),
  );
}

Future<void> _handleAuthUnavailable(
  AuthTokenUnavailableException exception, {
  required bool expireTerminalSession,
}) async {
  if (!expireTerminalSession) return;
  final event = switch (exception.result) {
    AuthTokenMissingUser() => null,
    AuthTokenMissingToken() => const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.missingToken),
    AuthTokenTerminalFailure(:final code) => AuthSessionExpiredEvent(
        reason: AuthSessionExpirationReason.terminalTokenFailure,
        code: code,
      ),
    _ => null,
  };
  if (event != null) await AuthService.instance.expireSession(event);
}

@visibleForTesting
Future<T> refreshAndReplayAfter401<T>({
  required T firstResponse,
  required int Function(T response) statusCode,
  required Future<T> Function() replay,
  required bool expireTerminalSession,
  Future<void> Function(T response)? disposeUnauthorizedResponse,
  AuthService? authService,
  void Function(AuthTokenResult refresh)? onAuthRefresh,
  AuthSessionSnapshot? sessionSnapshot,
}) async {
  final service = authService ?? AuthService.instance;
  bool sessionChanged() => sessionSnapshot != null && !service.isSessionSnapshotCurrent(sessionSnapshot);
  Future<void> expireIfCurrent(AuthSessionExpiredEvent event) async {
    if (expireTerminalSession && !sessionChanged()) await service.expireSession(event);
  }

  await disposeUnauthorizedResponse?.call(firstResponse);
  if (sessionChanged()) {
    service.recordAuthenticatedRequest401(recovered: false, outcome: 'session_changed');
    return firstResponse;
  }
  final refresh = await service.refreshIdToken();
  onAuthRefresh?.call(refresh);
  if (sessionChanged()) {
    service.recordAuthenticatedRequest401(recovered: false, outcome: 'session_changed');
    return firstResponse;
  }
  switch (refresh) {
    case AuthTokenSuccess():
      if (sessionChanged()) {
        service.recordAuthenticatedRequest401(recovered: false, outcome: 'session_changed');
        return firstResponse;
      }
      late T replayed;
      try {
        replayed = await replay();
      } catch (_) {
        service.recordAuthenticatedRequest401(recovered: false, outcome: 'replay_failed');
        rethrow;
      }
      if (sessionChanged()) {
        service.recordAuthenticatedRequest401(recovered: false, outcome: 'session_changed');
        await disposeUnauthorizedResponse?.call(replayed);
        return firstResponse;
      }
      final recovered = statusCode(replayed) != 401;
      if (!recovered) await disposeUnauthorizedResponse?.call(replayed);
      service.recordAuthenticatedRequest401(
        recovered: recovered,
        outcome: recovered ? 'refresh_succeeded' : 'backend_rejected_refreshed_token',
      );
      if (!recovered) {
        await expireIfCurrent(
          const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.backendRejectedRefreshedToken),
        );
      }
      return replayed;
    case AuthTokenTransientFailure():
      service.recordAuthenticatedRequest401(recovered: false, outcome: 'refresh_transient_failure');
      return firstResponse;
    case AuthTokenMissingUser():
      service.recordAuthenticatedRequest401(recovered: false, outcome: 'missing_user');
      await expireIfCurrent(const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.missingUser));
      return firstResponse;
    case AuthTokenMissingToken():
      service.recordAuthenticatedRequest401(recovered: false, outcome: 'missing_token');
      await expireIfCurrent(const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.missingToken));
      return firstResponse;
    case AuthTokenTerminalFailure(:final code):
      service.recordAuthenticatedRequest401(recovered: false, outcome: 'terminal_token_failure');
      await expireIfCurrent(
        AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.terminalTokenFailure, code: code),
      );
      return firstResponse;
  }
}

/// Uncaught send used by both [makeApiCall] and [executeApi]. Throws on
/// transport/auth failure so the typed path can keep the cause; the legacy
/// wrapper below is the only place those become null.
///
/// Production API, not test-only: [executeApi] (the typed ApiResult entry)
/// calls it directly, and the typed path must preserve the thrown cause.
Future<http.Response> sendUncaughtApiCall({
  required String url,
  required Map<String, String> headers,
  required String body,
  required String method,
  Duration? timeout,
  int? retries,
  bool signOutOn401 = true,
  ApiExecutionSeams? execution,
  bool Function()? canSend,
  void Function(AuthTokenResult refresh)? onAuthRefresh,
}) async {
  void ensureCurrentOwner() {
    if (canSend != null && !canSend()) throw AuthTokenUnavailableException(const AuthTokenMissingUser());
  }

  ensureCurrentOwner();
  if (execution != null) {
    var builtHeaders = await execution.headers(ApiRequest(url: url, method: method, headers: headers, body: body));
    ensureCurrentOwner();
    var response = await execution.transport(ApiRequest(url: url, method: method, headers: builtHeaders, body: body));
    if (response.statusCode == 401) {
      response = await refreshAndReplayAfter401(
        firstResponse: response,
        statusCode: (value) => value.statusCode,
        expireTerminalSession: signOutOn401,
        authService: execution.auth,
        onAuthRefresh: onAuthRefresh,
        replay: () async {
          builtHeaders = await execution.headers(ApiRequest(url: url, method: method, headers: headers, body: body));
          ensureCurrentOwner();
          return execution.transport(ApiRequest(url: url, method: method, headers: builtHeaders, body: body));
        },
      );
    }
    await _expireSessionIfAccountDeleted(response.statusCode, response.body, authService: execution.auth);
    return response;
  }

  final bool requireAuthCheck = _isRequiredAuthCheck(url);
  Map<String, String> builtHeaders = await buildHeaders(
    requireAuthCheck: requireAuthCheck,
    fromHeaders: headers,
    expireTerminalSession: signOutOn401,
    url: url,
    method: method,
  );

  final effectiveTimeout = timeout ?? (method == 'GET' ? ApiClient.requestTimeoutRead : ApiClient.requestTimeoutWrite);
  final effectiveRetries = retries ?? 1;

  http.Response response = await HttpPoolManager.instance.send(
    () {
      ensureCurrentOwner();
      return _buildRequest(url, builtHeaders, body, method);
    },
    timeout: effectiveTimeout,
    retries: effectiveRetries,
  );

  if (requireAuthCheck && response.statusCode == 401) {
    response = await refreshAndReplayAfter401(
      firstResponse: response,
      statusCode: (value) => value.statusCode,
      expireTerminalSession: signOutOn401,
      onAuthRefresh: onAuthRefresh,
      replay: () async {
        builtHeaders = await buildHeaders(
          requireAuthCheck: true,
          fromHeaders: headers,
          expireTerminalSession: signOutOn401,
          url: url,
          method: method,
        );
        return HttpPoolManager.instance.send(
          () {
            ensureCurrentOwner();
            return _buildRequest(url, builtHeaders, body, method);
          },
          timeout: effectiveTimeout,
          retries: 0,
        );
      },
    );
  }
  if (requireAuthCheck) await _expireSessionIfAccountDeleted(response.statusCode, response.body);

  _checkClockSkewResponse(response);
  return response;
}

Future<http.Response?> makeApiCall({
  required String url,
  required Map<String, String> headers,
  required String body,
  required String method,
  Duration? timeout,
  int? retries,
  bool signOutOn401 = true,
}) async {
  try {
    return await sendUncaughtApiCall(
      url: url,
      headers: headers,
      body: body,
      method: method,
      timeout: timeout,
      retries: retries,
      signOutOn401: signOutOn401,
    );
  } on AuthTokenUnavailableException catch (e) {
    await _handleAuthUnavailable(e, expireTerminalSession: signOutOn401);
    Logger.debug('Authenticated HTTP request blocked before send: ${e.result.runtimeType}');
    return null;
  } catch (e, stackTrace) {
    Logger.debug('HTTP request failed: $e, $stackTrace');
    if (!isTransientNetworkError(e)) {
      PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': method});
    }
    return null;
  }
}

http.Request _buildRequest(String url, Map<String, String> headers, String body, String method) {
  final request = http.Request(method, Uri.parse(url));
  request.headers.addAll(headers);
  if (method != 'GET' && body.isNotEmpty) {
    request.headers['Content-Type'] = 'application/json';
    request.body = body;
  }
  return request;
}

/// Reads the Omi list-truncation header from a backend response.
///
/// The header name is case-insensitive because `package:http` may preserve
/// the server's casing, and the value is the literal string `"true"`.
bool isOmiListTruncated(http.Response? response) {
  if (response == null) return false;
  for (final entry in response.headers.entries) {
    if (entry.key.toLowerCase() == 'x-omi-list-truncated' && entry.value == 'true') {
      return true;
    }
  }
  return false;
}

Future<http.StreamedResponse> _sendMultipartWithProgress(
  http.MultipartRequest request,
  UploadProgressCallback? onProgress,
) async {
  if (onProgress == null) {
    return HttpPoolManager.instance.sendStreaming(request);
  }

  final totalBytes = request.contentLength;
  int bytesSent = 0;
  final startTime = DateTime.now();

  final originalStream = request.finalize();
  final progressStream = originalStream.transform(
    StreamTransformer<List<int>, List<int>>.fromHandlers(
      handleData: (data, sink) {
        sink.add(data);
        bytesSent += data.length;
        final elapsed = DateTime.now().difference(startTime).inMilliseconds / 1000.0;
        final speed = elapsed > 0.3 ? (bytesSent / 1024.0) / elapsed : 0.0;
        onProgress(bytesSent, totalBytes, speed);
      },
    ),
  );

  final streamedRequest = http.StreamedRequest(request.method, request.url);
  streamedRequest.headers.addAll(request.headers);
  streamedRequest.contentLength = totalBytes;

  final subscription = progressStream.listen(
    streamedRequest.sink.add,
    onError: (Object e, StackTrace st) {
      streamedRequest.sink.addError(e, st);
      streamedRequest.sink.close();
    },
    onDone: streamedRequest.sink.close,
    cancelOnError: true,
  );

  try {
    return await HttpPoolManager.instance.sendStreaming(streamedRequest);
  } finally {
    // Keep cleanup on the caller's future so a handled send failure does not
    // also escape through an unobserved whenComplete future.
    await subscription.cancel();
  }
}

Future<http.MultipartRequest> _buildMultipartRequest({
  required String url,
  required List<File> files,
  required Map<String, String> headers,
  required Map<String, String> fields,
  required String fileFieldName,
  required String method,
  Future<void>? abortTrigger,
}) async {
  // Abortable when a trigger is supplied: an abandoned POST (setup deadline
  // expired) must not keep running server-side, or a user retry submits the
  // same turn twice. http 1.6 exposes this via AbortableMultipartRequest.
  var request = abortTrigger == null
      ? http.MultipartRequest(method, Uri.parse(url))
      : http.AbortableMultipartRequest(method, Uri.parse(url), abortTrigger: abortTrigger);
  request.headers.addAll(headers);
  request.fields.addAll(fields);

  for (var file in files) {
    var stream = http.ByteStream(file.openRead());
    var length = await file.length();
    var multipartFile = http.MultipartFile(fileFieldName, stream, length, filename: basename(file.path));
    request.files.add(multipartFile);
  }

  return request;
}

typedef UploadProgressCallback = void Function(int bytesSent, int totalBytes, double speedKBps);

Future<http.Response> makeMultipartApiCall({
  required String url,
  required List<File> files,
  Map<String, String> headers = const {},
  Map<String, String> fields = const {},
  String fileFieldName = 'files',
  String method = 'POST',
  UploadProgressCallback? onUploadProgress,
}) async {
  try {
    final bool requireAuthCheck = _isRequiredAuthCheck(url);
    Map<String, String> builtHeaders = await buildHeaders(
      requireAuthCheck: requireAuthCheck,
      fromHeaders: headers,
      url: url,
      method: method,
    );

    var request = await _buildMultipartRequest(
      url: url,
      files: files,
      headers: builtHeaders,
      fields: fields,
      fileFieldName: fileFieldName,
      method: method,
    );

    var streamedResponse = await _sendMultipartWithProgress(request, onUploadProgress);
    var response = await http.Response.fromStream(streamedResponse);

    if (requireAuthCheck && response.statusCode == 401) {
      response = await refreshAndReplayAfter401(
        firstResponse: response,
        statusCode: (value) => value.statusCode,
        expireTerminalSession: true,
        replay: () async {
          builtHeaders = await buildHeaders(requireAuthCheck: true, fromHeaders: headers, url: url, method: method);
          request = await _buildMultipartRequest(
            url: url,
            files: files,
            headers: builtHeaders,
            fields: fields,
            fileFieldName: fileFieldName,
            method: method,
          );
          streamedResponse = await _sendMultipartWithProgress(request, onUploadProgress);
          return http.Response.fromStream(streamedResponse);
        },
      );
    }
    if (requireAuthCheck) await _expireSessionIfAccountDeleted(response.statusCode, response.body);

    _checkClockSkewResponse(response);
    return response;
  } on AuthTokenUnavailableException catch (e) {
    await _handleAuthUnavailable(e, expireTerminalSession: true);
    Logger.debug('Authenticated multipart request blocked before send: ${e.result.runtimeType}');
    return http.Response('', 401, reasonPhrase: 'Authentication unavailable');
  } catch (e, stackTrace) {
    Logger.debug('Multipart HTTP request failed: $e, $stackTrace');
    if (!isTransientNetworkError(e)) {
      PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': method});
    }
    rethrow;
  }
}

/// Like [makeMultipartApiCall] but uses a dedicated HTTP client instead of the
/// shared connection pool. Prevents large uploads (e.g. voice recordings) from
/// blocking other app HTTP traffic. The client is created and disposed per call.
Future<http.Response> makeMultipartApiCallUnpooled({
  required String url,
  required List<File> files,
  Map<String, String> headers = const {},
  Map<String, String> fields = const {},
  String fileFieldName = 'files',
  String method = 'POST',
}) async {
  final client = http.Client();
  try {
    final bool requireAuthCheck = _isRequiredAuthCheck(url);
    Map<String, String> builtHeaders = await buildHeaders(
      requireAuthCheck: requireAuthCheck,
      fromHeaders: headers,
      url: url,
      method: method,
    );

    var request = await _buildMultipartRequest(
      url: url,
      files: files,
      headers: builtHeaders,
      fields: fields,
      fileFieldName: fileFieldName,
      method: method,
    );
    HttpPoolManager.stampRequestTime(request);

    var streamedResponse = await client.send(request).timeout(const Duration(minutes: 10));
    var response = await http.Response.fromStream(streamedResponse);

    if (requireAuthCheck && response.statusCode == 401) {
      response = await refreshAndReplayAfter401(
        firstResponse: response,
        statusCode: (value) => value.statusCode,
        expireTerminalSession: true,
        replay: () async {
          builtHeaders = await buildHeaders(requireAuthCheck: true, fromHeaders: headers, url: url, method: method);
          request = await _buildMultipartRequest(
            url: url,
            files: files,
            headers: builtHeaders,
            fields: fields,
            fileFieldName: fileFieldName,
            method: method,
          );
          HttpPoolManager.stampRequestTime(request);
          streamedResponse = await client.send(request).timeout(const Duration(minutes: 10));
          return http.Response.fromStream(streamedResponse);
        },
      );
    }
    if (requireAuthCheck) await _expireSessionIfAccountDeleted(response.statusCode, response.body);

    _checkClockSkewResponse(response);
    return response;
  } on AuthTokenUnavailableException catch (e) {
    await _handleAuthUnavailable(e, expireTerminalSession: true);
    Logger.debug('Authenticated unpooled multipart request blocked before send: ${e.result.runtimeType}');
    return http.Response('', 401, reasonPhrase: 'Authentication unavailable');
  } catch (e, stackTrace) {
    Logger.debug('Unpooled multipart HTTP request failed: $e, $stackTrace');
    if (!isTransientNetworkError(e)) {
      PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': method});
    }
    rethrow;
  } finally {
    client.close();
  }
}

class ApiStreamingSeams {
  const ApiStreamingSeams({required this.transport, this.headers, this.auth});

  final Future<http.StreamedResponse> Function(http.BaseRequest request) transport;
  final Future<Map<String, String>> Function(ApiRequest request)? headers;
  final AuthService? auth;
}

Stream<String> _sseBlocks(Stream<List<int>> byteStream) async* {
  final iterator = StreamIterator(byteStream.transform(utf8.decoder));
  final totalExpired = Completer<bool>();
  var expired = false;
  final totalTimer = Timer(ApiClient.streamTotalTimeout, () {
    expired = true;
    if (!totalExpired.isCompleted) totalExpired.complete(false);
  });
  // Stateful SSE parser: buffer partial data across TCP reads and only
  // emit complete events delimited by \n\n.  The previous 1024-byte
  // heuristic failed when TCP segments split an SSE line at arbitrary
  // byte boundaries (see issue #6284).
  var remainder = '';
  try {
    while (true) {
      if (expired) throw TimeoutException('stream exceeded total bound');
      final next = iterator.moveNext().timeout(ApiClient.streamInactivityTimeout);
      next.ignore();
      final hasNext = await Future.any<bool>([next, totalExpired.future]);
      if (expired) throw TimeoutException('stream exceeded total bound');
      if (!hasNext) break;
      remainder += iterator.current;
      var parts = remainder.split('\n\n');
      // Last element is either empty (if data ended with \n\n) or
      // an incomplete fragment — keep it in the remainder.
      remainder = parts.removeLast();
      for (var part in parts) {
        if (part.isNotEmpty) {
          yield part;
        }
      }
    }
    // Flush any trailing data that wasn't terminated by \n\n
    if (remainder.isNotEmpty) {
      yield remainder;
    }
  } catch (e) {
    throw _classifyStreamError(e);
  } finally {
    totalTimer.cancel();
    await iterator.cancel();
  }
}

ChatStreamException _classifyStreamError(Object e) {
  if (e is TimeoutException) return const ChatStreamException(ChatStreamFailureClass.timeout);
  // The setup-deadline abort fires exactly when the wait expired, so it is the
  // timeout failure, not an unknown client error.
  if (e is http.RequestAbortedException) return const ChatStreamException(ChatStreamFailureClass.timeout);
  if (isTransientNetworkError(e)) return const ChatStreamException(ChatStreamFailureClass.offline);
  return classifyChatStreamFailure(e);
}

Stream<String> _streamErrorOrThrow(http.StreamedResponse response) async* {
  try {
    // Materialize error responses so clock-skew detection sees the JSON body;
    // streamed responses previously bypassed _checkClockSkewResponse().
    final errorResponse = await _materializeErrorResponse(response).timeout(ApiClient.streamSetupTimeout);
    _checkClockSkewResponse(errorResponse);
    Logger.error('Streaming request failed: ${errorResponse.statusCode}');
    if (errorResponse.statusCode == 401) {
      throw const ChatStreamException(ChatStreamFailureClass.notSignedIn, statusCode: 401);
    }
    if (errorResponse.statusCode == 402) {
      try {
        yield 'error:402:${errorResponse.body}';
      } catch (_) {
        yield 'error:402:{}';
      }
      return;
    }
    throw ChatStreamException(ChatStreamFailureClass.server, statusCode: errorResponse.statusCode);
  } catch (e) {
    throw e is ChatStreamException ? e : _classifyStreamError(e);
  }
}

Stream<String> makeStreamingApiCall({
  required String url,
  Map<String, String> headers = const {},
  String body = '',
  String method = 'POST',
  ApiStreamingSeams? seams,
}) async* {
  // Setup-deadline abort (same rationale as the multipart variant): the POST
  // must die with the wait, or a retry can submit the chat turn twice. Armed
  // before the try so the error handlers can cancel it.
  final setupAbort = Completer<void>();
  final setupAbortTimer = Timer(ApiClient.streamSetupTimeout, () {
    if (!setupAbort.isCompleted) setupAbort.complete();
  });
  try {
    final requireAuthCheck = _isRequiredAuthCheck(url);
    final apiRequest = ApiRequest(url: url, method: method, headers: headers, body: body);
    final send = seams?.transport ??
        (request) => HttpPoolManager.instance.sendStreaming(request, timeout: ApiClient.streamSetupTimeout);
    Future<Map<String, String>> requestHeaders() => seams?.headers != null
        ? seams!.headers!(apiRequest)
        : buildHeaders(
            requireAuthCheck: requireAuthCheck,
            fromHeaders: headers,
            url: url,
            method: method,
            authService: seams?.auth,
          );

    var builtHeaders = await requestHeaders().timeout(ApiClient.streamSetupTimeout);

    http.Request buildRequest() {
      final request = http.AbortableRequest(method, Uri.parse(url), abortTrigger: setupAbort.future);
      request.headers.addAll(builtHeaders);
      if (body.isNotEmpty) {
        request.headers['Content-Type'] = 'application/json';
        request.body = body;
      }
      return request;
    }

    var streamedResponse = await send(buildRequest()).timeout(ApiClient.streamSetupTimeout);

    AuthTokenResult? observedRefresh;
    if (requireAuthCheck && streamedResponse.statusCode == 401) {
      streamedResponse = await refreshAndReplayAfter401(
        firstResponse: streamedResponse,
        statusCode: (value) => value.statusCode,
        disposeUnauthorizedResponse: _drainStreamedResponse,
        expireTerminalSession: true,
        authService: seams?.auth,
        onAuthRefresh: (refresh) => observedRefresh = refresh,
        replay: () async {
          builtHeaders = await requestHeaders().timeout(ApiClient.streamSetupTimeout);
          return send(buildRequest()).timeout(ApiClient.streamSetupTimeout);
        },
      ).timeout(ApiClient.streamSetupTimeout);
      if (streamedResponse.statusCode == 401 && observedRefresh is AuthTokenTransientFailure) {
        throw const ChatStreamException(ChatStreamFailureClass.offline, statusCode: 401);
      }
    }

    if (streamedResponse.statusCode != 200) {
      setupAbortTimer.cancel();
      yield* _streamErrorOrThrow(streamedResponse);
      return;
    }

    // Headers arrived: the setup deadline no longer applies. Cancel before the
    // body streams so the abort cannot kill a healthy long-lived SSE read
    // (inactivity/total stream timeouts govern that phase).
    setupAbortTimer.cancel();
    yield* _sseBlocks(streamedResponse.stream);
  } on AuthTokenUnavailableException catch (e) {
    setupAbortTimer.cancel();
    await _handleAuthUnavailable(e, expireTerminalSession: true);
    Logger.debug('Authenticated streaming request blocked before send: ${e.result.runtimeType}');
    throw ChatStreamException(
      e.result is AuthTokenTransientFailure ? ChatStreamFailureClass.offline : ChatStreamFailureClass.notSignedIn,
    );
  } catch (e, stackTrace) {
    setupAbortTimer.cancel();
    final failure = _classifyStreamError(e);
    Logger.error('Streaming request error: ${failure.kind} status=${failure.statusCode}');
    if (!isTransientNetworkError(e) && e is! ChatStreamException && e is! TimeoutException) {
      PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': method});
    }
    throw failure;
  }
}

Stream<String> makeMultipartStreamingApiCall({
  required String url,
  required List<File> files,
  Map<String, String> headers = const {},
  Map<String, String> fields = const {},
  String fileFieldName = 'files',
  ApiStreamingSeams? seams,
}) async* {
  // Setup-deadline abort: without this, the timeout below abandons the wait
  // but the POST keeps running and can still reach the server — a retry then
  // submits the same chat turn twice. The trigger aborts the in-flight
  // request as soon as the deadline passes. Armed before the try so the
  // error handlers can cancel it.
  final setupAbort = Completer<void>();
  final setupAbortTimer = Timer(ApiClient.streamSetupTimeout, () {
    if (!setupAbort.isCompleted) setupAbort.complete();
  });
  try {
    final bool requireAuthCheck = _isRequiredAuthCheck(url);
    final apiRequest = ApiRequest(url: url, method: 'POST', headers: headers, body: '');
    final send = seams?.transport ??
        (request) => HttpPoolManager.instance.sendStreaming(request, timeout: ApiClient.streamSetupTimeout);
    Future<Map<String, String>> requestHeaders() => seams?.headers != null
        ? seams!.headers!(apiRequest)
        : buildHeaders(
            requireAuthCheck: requireAuthCheck,
            fromHeaders: headers,
            url: url,
            method: 'POST',
            authService: seams?.auth,
          );

    Map<String, String> builtHeaders = await requestHeaders().timeout(ApiClient.streamSetupTimeout);

    Future<http.MultipartRequest> buildRequest() => _buildMultipartRequest(
          url: url,
          files: files,
          headers: builtHeaders,
          fields: fields,
          fileFieldName: fileFieldName,
          method: 'POST',
          abortTrigger: setupAbort.future,
        );

    var response = await send(await buildRequest()).timeout(ApiClient.streamSetupTimeout);

    AuthTokenResult? observedRefresh;
    if (requireAuthCheck && response.statusCode == 401) {
      response = await refreshAndReplayAfter401(
        firstResponse: response,
        statusCode: (value) => value.statusCode,
        disposeUnauthorizedResponse: _drainStreamedResponse,
        expireTerminalSession: true,
        authService: seams?.auth,
        onAuthRefresh: (refresh) => observedRefresh = refresh,
        replay: () async {
          builtHeaders = await requestHeaders().timeout(ApiClient.streamSetupTimeout);
          return send(await buildRequest()).timeout(ApiClient.streamSetupTimeout);
        },
      ).timeout(ApiClient.streamSetupTimeout);
      if (response.statusCode == 401 && observedRefresh is AuthTokenTransientFailure) {
        throw const ChatStreamException(ChatStreamFailureClass.offline, statusCode: 401);
      }
    }

    if (response.statusCode != 200) {
      setupAbortTimer.cancel();
      yield* _streamErrorOrThrow(response);
      return;
    }

    // Headers arrived: the setup deadline no longer applies (see
    // makeStreamingApiCall). The inactivity/total stream timeouts govern the
    // body phase.
    setupAbortTimer.cancel();

    // Stateful SSE parser: see makeStreamingApiCall for rationale (issue #6284).
    yield* _sseBlocks(response.stream);
  } on AuthTokenUnavailableException catch (e) {
    setupAbortTimer.cancel();
    await _handleAuthUnavailable(e, expireTerminalSession: true);
    Logger.debug('Authenticated multipart streaming request blocked before send: ${e.result.runtimeType}');
    throw ChatStreamException(
      e.result is AuthTokenTransientFailure ? ChatStreamFailureClass.offline : ChatStreamFailureClass.notSignedIn,
    );
  } catch (e, stackTrace) {
    setupAbortTimer.cancel();
    final failure = _classifyStreamError(e);
    Logger.error('Multipart streaming request error: ${failure.kind} status=${failure.statusCode}');
    if (!isTransientNetworkError(e) && e is! ChatStreamException && e is! TimeoutException) {
      PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': 'POST'});
    }
    throw failure;
  }
}

// Function to extract content from the API response.
dynamic extractContentFromResponse(
  http.Response? response, {
  bool isEmbedding = false,
  bool isFunctionCalling = false,
}) {
  if (response != null && response.statusCode == 200) {
    var data = jsonDecode(response.body);
    if (isEmbedding) {
      var embedding = data['data'][0]['embedding'];
      return embedding;
    }
    var message = data['choices'][0]['message'];
    if (isFunctionCalling && message['tool_calls'] != null) {
      Logger.debug('message $message');
      Logger.debug('message ${message['tool_calls'].runtimeType}');
      return message['tool_calls'];
    }
    return data['choices'][0]['message']['content'];
  } else {
    var errorBody = response?.body;
    Logger.debug('Error fetching data: ${response?.statusCode} Body: $errorBody');
    PlatformManager.instance.crashReporter.reportCrash(
      Exception('Error fetching data: ${response?.statusCode}'),
      StackTrace.current,
      userAttributes: {
        'response_null': (response == null).toString(),
        'response_status_code': response?.statusCode.toString() ?? '',
        'response_body': errorBody ?? '',
        'is_embedding': isEmbedding.toString(),
        'is_function_calling': isFunctionCalling.toString(),
      },
    );
    return null;
  }
}
