import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart';

import 'package:omi/backend/http/clock_skew_detector.dart';
import 'package:omi/backend/http/http_pool_manager.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';

class ApiClient {
  static const Duration requestTimeoutRead = Duration(seconds: 30);
  static const Duration requestTimeoutWrite = Duration(seconds: 300);

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
// connection reset, TLS handshake during reconnect, request timeout). Reporting
// these to Crashlytics drowns out real signal — caller logs them locally and
// either returns null or rethrows for the upstream sync state machine.
bool _isTransientNetworkError(Object e) {
  if (e is SocketException) return true;
  if (e is HandshakeException) return true;
  if (e is TimeoutException) return true;
  if (e is http.ClientException) {
    final m = e.message;
    return m.contains('SocketException') ||
        m.contains('HandshakeException') ||
        m.contains('TimeoutException') ||
        m.contains('Connection closed') ||
        m.contains('Connection reset') ||
        m.contains('Failed host lookup') ||
        m.contains('Network is unreachable') ||
        m.contains('Bad file descriptor');
  }
  return false;
}

Future<String> getAuthHeader({bool expireTerminalSession = true}) async {
  if (!AuthService.instance.isSignedIn()) {
    throw AuthTokenUnavailableException(const AuthTokenMissingUser());
  }

  final expiry = DateTime.fromMillisecondsSinceEpoch(SharedPreferencesUtil().tokenExpirationTime);
  bool hasAuthToken = SharedPreferencesUtil().authToken.isNotEmpty;

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
}) async {
  final headers = <String, String>{
    'X-Request-Start-Time': (DateTime.now().millisecondsSinceEpoch / 1000).toString(),
    'X-App-Platform': PlatformManager.instance.platform,
    'X-Device-Id-Hash': PlatformManager.instance.deviceIdHash,
    'X-App-Version': PlatformManager.instance.appVersion,
    ...fromHeaders,
  };

  if (requireAuthCheck) {
    // Authenticated requests must never degrade into anonymous traffic. A
    // typed exception stops the request before it reaches the network.
    headers['Authorization'] = await getAuthHeader(expireTerminalSession: expireTerminalSession);
  }

  return headers;
}

bool _isRequiredAuthCheck(String url) {
  // Agent VM endpoints always hit prod even when app uses dev
  if (url.contains('api.omi.me')) return true;
  if (url.contains(Env.apiBaseUrl!)) {
    return true;
  }
  return false;
}

Future<http.StreamedResponse> makeRawApiCall({
  required String url,
  required String method,
  Map<String, String> headers = const {},
}) async {
  final requireAuthCheck = _isRequiredAuthCheck(url);
  try {
    var builtHeaders = await buildHeaders(requireAuthCheck: requireAuthCheck, fromHeaders: headers);
    var request = http.Request(method, Uri.parse(url));
    request.headers.addAll(builtHeaders);
    var response = await HttpPoolManager.instance.sendStreaming(request);
    if (requireAuthCheck && response.statusCode == 401) {
      response = await refreshAndReplayAfter401(
        firstResponse: response,
        statusCode: (value) => value.statusCode,
        disposeUnauthorizedResponse: _drainStreamedResponse,
        expireTerminalSession: true,
        replay: () async {
          builtHeaders = await buildHeaders(requireAuthCheck: true, fromHeaders: headers);
          request = http.Request(method, Uri.parse(url));
          request.headers.addAll(builtHeaders);
          return HttpPoolManager.instance.sendStreaming(request);
        },
      );
      if (response.statusCode == 401) return _authUnavailableStreamedResponse();
    }
    return response;
  } on AuthTokenUnavailableException catch (e) {
    await _handleAuthUnavailable(e, expireTerminalSession: true);
    Logger.debug('Authenticated raw request blocked before send: ${e.result.runtimeType}');
    return _authUnavailableStreamedResponse();
  }
}

Future<void> _drainStreamedResponse(http.StreamedResponse response) async {
  try {
    await response.stream.drain<void>();
  } catch (e) {
    Logger.debug('Failed to drain unauthorized response: ${e.runtimeType}');
  }
}

http.StreamedResponse _authUnavailableStreamedResponse() =>
    http.StreamedResponse(const Stream<List<int>>.empty(), 401, reasonPhrase: 'Authentication unavailable');

void _checkClockSkewResponse(http.Response response) {
  ClockSkewDetector.instance.checkResponse(response);
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
}) async {
  final service = authService ?? AuthService.instance;
  await disposeUnauthorizedResponse?.call(firstResponse);
  final refresh = await service.refreshIdToken();
  switch (refresh) {
    case AuthTokenSuccess():
      late T replayed;
      try {
        replayed = await replay();
      } catch (_) {
        service.recordAuthenticatedRequest401(recovered: false, outcome: 'replay_failed');
        rethrow;
      }
      final recovered = statusCode(replayed) != 401;
      if (!recovered) await disposeUnauthorizedResponse?.call(replayed);
      service.recordAuthenticatedRequest401(
        recovered: recovered,
        outcome: recovered ? 'refresh_succeeded' : 'backend_rejected_refreshed_token',
      );
      if (!recovered && expireTerminalSession) {
        await service.expireSession(
          const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.backendRejectedRefreshedToken),
        );
      }
      return replayed;
    case AuthTokenTransientFailure():
      service.recordAuthenticatedRequest401(recovered: false, outcome: 'refresh_transient_failure');
      return firstResponse;
    case AuthTokenMissingUser():
      service.recordAuthenticatedRequest401(recovered: false, outcome: 'missing_user');
      if (expireTerminalSession) {
        await service.expireSession(const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.missingUser));
      }
      return firstResponse;
    case AuthTokenMissingToken():
      service.recordAuthenticatedRequest401(recovered: false, outcome: 'missing_token');
      if (expireTerminalSession) {
        await service.expireSession(const AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.missingToken));
      }
      return firstResponse;
    case AuthTokenTerminalFailure(:final code):
      service.recordAuthenticatedRequest401(recovered: false, outcome: 'terminal_token_failure');
      if (expireTerminalSession) {
        await service.expireSession(
          AuthSessionExpiredEvent(reason: AuthSessionExpirationReason.terminalTokenFailure, code: code),
        );
      }
      return firstResponse;
  }
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
    final bool requireAuthCheck = _isRequiredAuthCheck(url);
    Map<String, String> builtHeaders = await buildHeaders(
      requireAuthCheck: requireAuthCheck,
      fromHeaders: headers,
      expireTerminalSession: signOutOn401,
    );

    final effectiveTimeout =
        timeout ?? (method == 'GET' ? ApiClient.requestTimeoutRead : ApiClient.requestTimeoutWrite);
    final effectiveRetries = retries ?? 1;

    http.Response response = await HttpPoolManager.instance.send(
      () => _buildRequest(url, builtHeaders, body, method),
      timeout: effectiveTimeout,
      retries: effectiveRetries,
    );

    if (requireAuthCheck && response.statusCode == 401) {
      response = await refreshAndReplayAfter401(
        firstResponse: response,
        statusCode: (value) => value.statusCode,
        expireTerminalSession: signOutOn401,
        replay: () async {
          builtHeaders = await buildHeaders(
            requireAuthCheck: true,
            fromHeaders: headers,
            expireTerminalSession: signOutOn401,
          );
          return HttpPoolManager.instance.send(
            () => _buildRequest(url, builtHeaders, body, method),
            timeout: effectiveTimeout,
            retries: 0,
          );
        },
      );
    }

    _checkClockSkewResponse(response);
    return response;
  } on AuthTokenUnavailableException catch (e) {
    await _handleAuthUnavailable(e, expireTerminalSession: signOutOn401);
    Logger.debug('Authenticated HTTP request blocked before send: ${e.result.runtimeType}');
    return null;
  } catch (e, stackTrace) {
    Logger.debug('HTTP request failed: $e, $stackTrace');
    if (!_isTransientNetworkError(e)) {
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

  final future = HttpPoolManager.instance.sendStreaming(streamedRequest);
  future.whenComplete(subscription.cancel);
  return future;
}

Future<http.MultipartRequest> _buildMultipartRequest({
  required String url,
  required List<File> files,
  required Map<String, String> headers,
  required Map<String, String> fields,
  required String fileFieldName,
  required String method,
}) async {
  var request = http.MultipartRequest(method, Uri.parse(url));
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
    Map<String, String> builtHeaders = await buildHeaders(requireAuthCheck: requireAuthCheck, fromHeaders: headers);

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
          builtHeaders = await buildHeaders(requireAuthCheck: true, fromHeaders: headers);
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

    _checkClockSkewResponse(response);
    return response;
  } on AuthTokenUnavailableException catch (e) {
    await _handleAuthUnavailable(e, expireTerminalSession: true);
    Logger.debug('Authenticated multipart request blocked before send: ${e.result.runtimeType}');
    return http.Response('', 401, reasonPhrase: 'Authentication unavailable');
  } catch (e, stackTrace) {
    Logger.debug('Multipart HTTP request failed: $e, $stackTrace');
    if (!_isTransientNetworkError(e)) {
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
    Map<String, String> builtHeaders = await buildHeaders(requireAuthCheck: requireAuthCheck, fromHeaders: headers);

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
          builtHeaders = await buildHeaders(requireAuthCheck: true, fromHeaders: headers);
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

    _checkClockSkewResponse(response);
    return response;
  } on AuthTokenUnavailableException catch (e) {
    await _handleAuthUnavailable(e, expireTerminalSession: true);
    Logger.debug('Authenticated unpooled multipart request blocked before send: ${e.result.runtimeType}');
    return http.Response('', 401, reasonPhrase: 'Authentication unavailable');
  } catch (e, stackTrace) {
    Logger.debug('Unpooled multipart HTTP request failed: $e, $stackTrace');
    if (!_isTransientNetworkError(e)) {
      PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': method});
    }
    rethrow;
  } finally {
    client.close();
  }
}

Stream<String> makeStreamingApiCall({
  required String url,
  Map<String, String> headers = const {},
  String body = '',
  String method = 'POST',
}) async* {
  try {
    final requireAuthCheck = _isRequiredAuthCheck(url);
    var builtHeaders = await buildHeaders(requireAuthCheck: requireAuthCheck, fromHeaders: headers);

    var request = http.Request(method, Uri.parse(url));
    request.headers.addAll(builtHeaders);

    if (body.isNotEmpty) {
      request.headers['Content-Type'] = 'application/json';
      request.body = body;
    }

    var streamedResponse = await HttpPoolManager.instance.sendStreaming(request);

    if (requireAuthCheck && streamedResponse.statusCode == 401) {
      streamedResponse = await refreshAndReplayAfter401(
        firstResponse: streamedResponse,
        statusCode: (value) => value.statusCode,
        disposeUnauthorizedResponse: _drainStreamedResponse,
        expireTerminalSession: true,
        replay: () async {
          builtHeaders = await buildHeaders(requireAuthCheck: true, fromHeaders: headers);
          request = http.Request(method, Uri.parse(url));
          request.headers.addAll(builtHeaders);
          if (body.isNotEmpty) {
            request.headers['Content-Type'] = 'application/json';
            request.body = body;
          }
          return HttpPoolManager.instance.sendStreaming(request);
        },
      );
      if (streamedResponse.statusCode == 401) return;
    }

    if (streamedResponse.statusCode != 200) {
      Logger.error('Streaming request failed: ${streamedResponse.statusCode}');
      if (streamedResponse.statusCode == 402) {
        try {
          var body = await streamedResponse.stream.bytesToString();
          yield 'error:402:$body';
        } catch (_) {
          yield 'error:402:{}';
        }
      }
      return;
    }

    // Stateful SSE parser: buffer partial data across TCP reads and only
    // emit complete events delimited by \n\n.  The previous 1024-byte
    // heuristic failed when TCP segments split an SSE line at arbitrary
    // byte boundaries (see issue #6284).
    var remainder = '';
    await for (var data in streamedResponse.stream.transform(utf8.decoder)) {
      remainder += data;
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
  } on AuthTokenUnavailableException catch (e) {
    await _handleAuthUnavailable(e, expireTerminalSession: true);
    Logger.debug('Authenticated streaming request blocked before send: ${e.result.runtimeType}');
  } catch (e, stackTrace) {
    Logger.error('Streaming request error: $e');
    if (!_isTransientNetworkError(e)) {
      PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': method});
    }
  }
}

Stream<String> makeMultipartStreamingApiCall({
  required String url,
  required List<File> files,
  Map<String, String> headers = const {},
  Map<String, String> fields = const {},
  String fileFieldName = 'files',
}) async* {
  try {
    final bool requireAuthCheck = _isRequiredAuthCheck(url);
    Map<String, String> builtHeaders = await buildHeaders(requireAuthCheck: requireAuthCheck, fromHeaders: headers);

    var request = await _buildMultipartRequest(
      url: url,
      files: files,
      headers: builtHeaders,
      fields: fields,
      fileFieldName: fileFieldName,
      method: 'POST',
    );

    var response = await HttpPoolManager.instance.sendStreaming(request);

    if (requireAuthCheck && response.statusCode == 401) {
      response = await refreshAndReplayAfter401(
        firstResponse: response,
        statusCode: (value) => value.statusCode,
        disposeUnauthorizedResponse: _drainStreamedResponse,
        expireTerminalSession: true,
        replay: () async {
          builtHeaders = await buildHeaders(requireAuthCheck: true, fromHeaders: headers);
          request = await _buildMultipartRequest(
            url: url,
            files: files,
            headers: builtHeaders,
            fields: fields,
            fileFieldName: fileFieldName,
            method: 'POST',
          );
          return HttpPoolManager.instance.sendStreaming(request);
        },
      );
      if (response.statusCode == 401) return;
    }

    if (response.statusCode != 200) {
      Logger.error('Multipart streaming request failed: ${response.statusCode}');
      if (response.statusCode == 402) {
        try {
          var body = await response.stream.bytesToString();
          yield 'error:402:$body';
        } catch (_) {
          yield 'error:402:{}';
        }
      }
      return;
    }

    // Stateful SSE parser: see makeStreamingApiCall for rationale (issue #6284).
    var remainder = '';
    await for (var data in response.stream.transform(utf8.decoder)) {
      remainder += data;
      var parts = remainder.split('\n\n');
      remainder = parts.removeLast();
      for (var part in parts) {
        if (part.isNotEmpty) {
          yield part;
        }
      }
    }

    if (remainder.isNotEmpty) {
      yield remainder;
    }
  } on AuthTokenUnavailableException catch (e) {
    await _handleAuthUnavailable(e, expireTerminalSession: true);
    Logger.debug('Authenticated multipart streaming request blocked before send: ${e.result.runtimeType}');
  } catch (e, stackTrace) {
    Logger.error('Multipart streaming request error: $e');
    if (!_isTransientNetworkError(e)) {
      PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': 'POST'});
    }
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
    Logger.debug('Error fetching data: ${response?.statusCode}');
    // TODO: handle error, better specially for script migration
    PlatformManager.instance.crashReporter.reportCrash(
      Exception('Error fetching data: ${response?.statusCode}'),
      StackTrace.current,
      userAttributes: {
        'response_null': (response == null).toString(),
        'response_status_code': response?.statusCode.toString() ?? '',
        'is_embedding': isEmbedding.toString(),
        'is_function_calling': isFunctionCalling.toString(),
      },
    );
    return null;
  }
}
