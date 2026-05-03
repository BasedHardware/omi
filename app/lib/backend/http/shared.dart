import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:path/path.dart';

import 'package:omi/backend/http/clock_skew_detector.dart';
import 'package:omi/backend/http/http_pool_manager.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
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
  final String message;
  AuthTokenUnavailableException([this.message = 'No auth token found']);

  @override
  String toString() => 'AuthTokenUnavailableException: $message';
}

Future<String> getAuthHeader() async {
  DateTime? expiry = DateTime.fromMillisecondsSinceEpoch(SharedPreferencesUtil().tokenExpirationTime);
  bool hasAuthToken = SharedPreferencesUtil().authToken.isNotEmpty;

  bool isExpirationDateValid = !(expiry.isBefore(DateTime.now()) ||
      expiry.isAtSameMomentAs(DateTime.fromMillisecondsSinceEpoch(0)) ||
      (expiry.isBefore(DateTime.now().add(const Duration(minutes: 5))) && expiry.isAfter(DateTime.now())));

  if (!hasAuthToken || !isExpirationDateValid) {
    final refreshedToken = await AuthService.instance.getIdToken();
    if (refreshedToken != null) {
      SharedPreferencesUtil().authToken = refreshedToken;
    }
    hasAuthToken = SharedPreferencesUtil().authToken.isNotEmpty;
  }

  if (!hasAuthToken) {
    if (AuthService.instance.isSignedIn()) {
      // should only throw if the user is signed in but the token is not found
      // if the user is not signed in, the token will always be empty
      throw AuthTokenUnavailableException('No auth token found');
    }
  }
  return 'Bearer ${SharedPreferencesUtil().authToken}';
}

/// Builds common headers for API and WebSocket requests
/// Centralizes header logic for easy maintenance and consistency
/// Automatically adds Authorization header if required
Future<Map<String, String>> buildHeaders({
  required bool requireAuthCheck,
  Map<String, String> fromHeaders = const {},
}) async {
  final headers = <String, String>{
    'X-Request-Start-Time': (DateTime.now().millisecondsSinceEpoch / 1000).toString(),
    'X-App-Platform': PlatformManager.instance.platform,
    'X-Device-Id-Hash': PlatformManager.instance.deviceIdHash,
    'X-App-Version': PlatformManager.instance.appVersion,
    ...fromHeaders,
  };

  if (requireAuthCheck) {
    try {
      headers['Authorization'] = await getAuthHeader();
    } on AuthTokenUnavailableException {
      // Signed-in user has no usable token (refresh returned null for a
      // transient or degraded reason). Proceed without Authorization; the
      // downstream HTTP 401 path in makeApiCall already calls
      // AuthService.signOut(), so recovery runs where it was already wired.
      // We avoid forcing sign-out here because getIdToken() treats generic
      // failures as transient (e.g. offline / platform hiccups) and leaves
      // currentUser intact.
      Logger.debug('No auth token available for request, proceeding without Authorization header');
    }
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
  final builtHeaders = await buildHeaders(requireAuthCheck: _isRequiredAuthCheck(url), fromHeaders: headers);
  var request = http.Request(method, Uri.parse(url));
  request.headers.addAll(builtHeaders);
  return HttpPoolManager.instance.sendStreaming(request);
}

void _checkClockSkewResponse(http.Response response) {
  ClockSkewDetector.instance.checkResponse(response);
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
    Map<String, String> builtHeaders = await buildHeaders(requireAuthCheck: requireAuthCheck, fromHeaders: headers);

    final effectiveTimeout =
        timeout ?? (method == 'GET' ? ApiClient.requestTimeoutRead : ApiClient.requestTimeoutWrite);
    final effectiveRetries = retries ?? 1;

    http.Response response = await HttpPoolManager.instance.send(
      () => _buildRequest(url, builtHeaders, body, method),
      timeout: effectiveTimeout,
      retries: effectiveRetries,
    );

    if (requireAuthCheck && response.statusCode == 401) {
      Logger.log('Token expired on 1st attempt');
      SharedPreferencesUtil().authToken = await AuthService.instance.getIdToken() ?? '';
      if (SharedPreferencesUtil().authToken.isNotEmpty) {
        builtHeaders = await buildHeaders(requireAuthCheck: requireAuthCheck, fromHeaders: headers);
        response = await HttpPoolManager.instance.send(
          () => _buildRequest(url, builtHeaders, body, method),
          timeout: effectiveTimeout,
          retries: 0,
        );
        Logger.log('Token refreshed and request retried');
        if (response.statusCode == 401 && signOutOn401) {
          await AuthService.instance.signOut();
          Logger.handle(
            Exception('Authentication failed. Please sign in again.'),
            StackTrace.current,
            message: 'Authentication failed. Please sign in again.',
          );
        }
      } else if (signOutOn401) {
        await AuthService.instance.signOut();
        Logger.handle(
          Exception('Authentication failed. Please sign in again.'),
          StackTrace.current,
          message: 'Authentication failed. Please sign in again.',
        );
      }
    }

    _checkClockSkewResponse(response);
    return response;
  } catch (e, stackTrace) {
    Logger.debug('HTTP request failed: $e, $stackTrace');
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': method});
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

  progressStream.listen(
    streamedRequest.sink.add,
    onError: streamedRequest.sink.addError,
    onDone: streamedRequest.sink.close,
  );

  return HttpPoolManager.instance.sendStreaming(streamedRequest);
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
      Logger.log('Token expired on 1st multipart attempt');
      SharedPreferencesUtil().authToken = await AuthService.instance.getIdToken() ?? '';
      if (SharedPreferencesUtil().authToken.isNotEmpty) {
        builtHeaders = await buildHeaders(requireAuthCheck: requireAuthCheck, fromHeaders: headers);
        request = await _buildMultipartRequest(
          url: url,
          files: files,
          headers: builtHeaders,
          fields: fields,
          fileFieldName: fileFieldName,
          method: method,
        );
        streamedResponse = await _sendMultipartWithProgress(request, onUploadProgress);
        response = await http.Response.fromStream(streamedResponse);
        Logger.log('Token refreshed and multipart request retried');
        if (response.statusCode == 401) {
          await AuthService.instance.signOut();
          Logger.handle(
            Exception('Authentication failed. Please sign in again.'),
            StackTrace.current,
            message: 'Authentication failed. Please sign in again.',
          );
        }
      } else {
        await AuthService.instance.signOut();
        Logger.handle(
          Exception('Authentication failed. Please sign in again.'),
          StackTrace.current,
          message: 'Authentication failed. Please sign in again.',
        );
      }
    }

    _checkClockSkewResponse(response);
    return response;
  } catch (e, stackTrace) {
    Logger.debug('Multipart HTTP request failed: $e, $stackTrace');
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': method});
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
      Logger.log('Token expired on 1st unpooled multipart attempt');
      SharedPreferencesUtil().authToken = await AuthService.instance.getIdToken() ?? '';
      if (SharedPreferencesUtil().authToken.isNotEmpty) {
        builtHeaders = await buildHeaders(requireAuthCheck: requireAuthCheck, fromHeaders: headers);
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
        response = await http.Response.fromStream(streamedResponse);
        Logger.log('Token refreshed and unpooled multipart request retried');
        if (response.statusCode == 401) {
          await AuthService.instance.signOut();
          Logger.handle(
            Exception('Authentication failed. Please sign in again.'),
            StackTrace.current,
            message: 'Authentication failed. Please sign in again.',
          );
        }
      } else {
        await AuthService.instance.signOut();
        Logger.handle(
          Exception('Authentication failed. Please sign in again.'),
          StackTrace.current,
          message: 'Authentication failed. Please sign in again.',
        );
      }
    }

    _checkClockSkewResponse(response);
    return response;
  } catch (e, stackTrace) {
    Logger.debug('Unpooled multipart HTTP request failed: $e, $stackTrace');
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': method});
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
    final builtHeaders = await buildHeaders(requireAuthCheck: _isRequiredAuthCheck(url), fromHeaders: headers);

    var request = http.Request(method, Uri.parse(url));
    request.headers.addAll(builtHeaders);

    if (body.isNotEmpty) {
      request.headers['Content-Type'] = 'application/json';
      request.body = body;
    }

    var streamedResponse = await HttpPoolManager.instance.sendStreaming(request);

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
  } catch (e, stackTrace) {
    Logger.error('Streaming request error: $e');
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': method});
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
      Logger.log('Token expired on 1st multipart streaming attempt');
      SharedPreferencesUtil().authToken = await AuthService.instance.getIdToken() ?? '';
      if (SharedPreferencesUtil().authToken.isNotEmpty) {
        builtHeaders = await buildHeaders(requireAuthCheck: requireAuthCheck, fromHeaders: headers);
        request = await _buildMultipartRequest(
          url: url,
          files: files,
          headers: builtHeaders,
          fields: fields,
          fileFieldName: fileFieldName,
          method: 'POST',
        );
        response = await HttpPoolManager.instance.sendStreaming(request);
        Logger.log('Token refreshed and multipart streaming request retried');
        if (response.statusCode == 401) {
          await AuthService.instance.signOut();
          Logger.handle(
            Exception('Authentication failed. Please sign in again.'),
            StackTrace.current,
            message: 'Authentication failed. Please sign in again.',
          );
          return;
        }
      } else {
        await AuthService.instance.signOut();
        Logger.handle(
          Exception('Authentication failed. Please sign in again.'),
          StackTrace.current,
          message: 'Authentication failed. Please sign in again.',
        );
        return;
      }
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
  } catch (e, stackTrace) {
    Logger.error('Multipart streaming request error: $e');
    PlatformManager.instance.crashReporter.reportCrash(e, stackTrace, userAttributes: {'url': url, 'method': 'POST'});
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
