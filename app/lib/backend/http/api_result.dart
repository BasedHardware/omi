import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:omi/backend/http/shared.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

import 'api_fallback.dart';

enum ApiProblemKind {
  transport,
  authTerminal,
  authTransient,
  notFound,
  forbidden,
  paymentRequired,
  unprocessable,
  rateLimited,
  server,
  decode,
  rejected,
}

class ApiProblem {
  const ApiProblem(this.kind, {this.statusCode, this.retryAfter});
  final ApiProblemKind kind;
  final int? statusCode;
  final Duration? retryAfter;
  bool get retryable => switch (kind) {
        ApiProblemKind.transport ||
        ApiProblemKind.authTransient ||
        ApiProblemKind.rateLimited ||
        ApiProblemKind.server =>
          true,
        _ => false,
      };

  @override
  String toString() => 'ApiProblem($kind, statusCode: $statusCode)';
}

sealed class ApiResult<T> {
  const ApiResult();
}

final class ApiSuccess<T> extends ApiResult<T> {
  const ApiSuccess(this.data, {this.rejectedRows = 0});
  final T data;
  final int rejectedRows;
}

final class ApiFailure<T> extends ApiResult<T> {
  const ApiFailure(this.problem);
  final ApiProblem problem;
}

class ApiRequest {
  const ApiRequest({required this.url, required this.method, this.headers = const {}, this.body = ''});
  final String url;
  final String method;
  final Map<String, String> headers;
  final String body;
}

typedef ApiSend = Future<http.Response> Function(ApiRequest request);

/// I/O seams into the shared production execution path, including 401 replay.
/// Explicit execution never resolves auth/header/transport globals.
class ApiExecutionSeams {
  const ApiExecutionSeams({required this.transport, required this.headers, required this.auth});
  final ApiSend transport;
  final Future<Map<String, String>> Function(ApiRequest) headers;
  final AuthService auth;
}

ApiProblemKind _kindForStatus(int statusCode) => switch (statusCode) {
      401 => ApiProblemKind.authTerminal,
      403 => ApiProblemKind.forbidden,
      404 => ApiProblemKind.notFound,
      402 => ApiProblemKind.paymentRequired,
      422 => ApiProblemKind.unprocessable,
      429 => ApiProblemKind.rateLimited,
      >= 500 && <= 599 => ApiProblemKind.server,
      _ => ApiProblemKind.rejected,
    };

ApiFailure<T> _authFailure<T>(AuthTokenResult result) {
  final transient = result is AuthTokenTransientFailure;
  return ApiFailure(ApiProblem(transient ? ApiProblemKind.authTransient : ApiProblemKind.authTerminal));
}

Duration? _retryAfter(http.Response response, DateTime Function() now) {
  final raw = response.headers['retry-after'];
  if (raw == null) return null;
  final seconds = int.tryParse(raw.trim());
  if (seconds != null) {
    return seconds < 0 ? null : Duration(seconds: seconds);
  }
  try {
    final date = HttpDate.parse(raw);
    final delta = date.toUtc().difference(now().toUtc());
    if (delta.isNegative) return null;
    return delta;
  } catch (_) {
    return null;
  }
}

ApiResult<T> _decodeSuccess<T>(String body, T Function(String) decode) {
  try {
    return ApiSuccess(decode(body));
  } on FormatException {
    return const ApiFailure(ApiProblem(ApiProblemKind.decode));
  }
}

ApiResult<T> _classifyResponse<T>(http.Response response, T Function(String) decode, DateTime Function() now) {
  if (response.statusCode >= 200 && response.statusCode < 300) {
    return _decodeSuccess(response.body, decode);
  }
  final kind = _kindForStatus(response.statusCode);
  return ApiFailure(
    ApiProblem(
      kind,
      statusCode: response.statusCode,
      retryAfter: kind == ApiProblemKind.rateLimited ? _retryAfter(response, now) : null,
    ),
  );
}

/// Existing shared.dart header/auth/pool/replay path supplies the default send.
/// The typed path must never call nullable makeApiCall and guess why it failed.
Future<ApiResult<T>> executeApi<T>({
  required ApiRequest request,
  required T Function(String) decode,
  ApiSend? send,
  ApiExecutionSeams? execution,
  DateTime Function()? now,
}) async {
  final clock = now ?? DateTime.now;
  try {
    if (send != null) {
      return _classifyResponse(await send(request), decode, clock);
    }
    AuthTokenResult? observedRefresh;
    final response = await sendUncaughtApiCall(
      url: request.url,
      headers: request.headers,
      body: request.body,
      method: request.method,
      execution: execution,
      onAuthRefresh: (result) => observedRefresh = result,
    );
    if (response.statusCode == 401 && observedRefresh is AuthTokenTransientFailure) {
      return const ApiFailure(ApiProblem(ApiProblemKind.authTransient, statusCode: 401));
    }
    return _classifyResponse(response, decode, clock);
  } on AuthTokenUnavailableException catch (e) {
    return _authFailure(e.result);
  } on SocketException {
    return const ApiFailure(ApiProblem(ApiProblemKind.transport));
  } on HandshakeException {
    return const ApiFailure(ApiProblem(ApiProblemKind.transport));
  } on TimeoutException {
    return const ApiFailure(ApiProblem(ApiProblemKind.transport));
  } on http.ClientException {
    return const ApiFailure(ApiProblem(ApiProblemKind.transport));
  }
}

/// Decode the envelope once and rows independently. A wholly invalid nonempty
/// list is decode failure; a valid [] alone is empty success.
ApiResult<List<T>> decodeApiRows<T>(
  String body,
  T Function(Map<String, dynamic>) row, {
  void Function(ApiFallbackEvent)? fallback,
}) {
  late final Object? decoded;
  try {
    decoded = jsonDecode(body);
  } on FormatException {
    return const ApiFailure(ApiProblem(ApiProblemKind.decode));
  }
  if (decoded is! List) {
    return const ApiFailure(ApiProblem(ApiProblemKind.decode));
  }
  if (decoded.isEmpty) {
    return ApiSuccess<List<T>>(<T>[]);
  }
  final kept = <T>[];
  var rejected = 0;
  for (final item in decoded) {
    if (item is! Map) {
      rejected++;
      continue;
    }
    try {
      kept.add(row(Map<String, dynamic>.from(item)));
    } catch (_) {
      rejected++;
    }
  }
  if (kept.isEmpty) {
    return const ApiFailure(ApiProblem(ApiProblemKind.decode));
  }
  if (rejected > 0) {
    fallback?.call(
      const ApiFallbackEvent(reason: ApiFallbackReason.partialDecode, outcome: ApiFallbackOutcome.degraded),
    );
  }
  return ApiSuccess(kept, rejectedRows: rejected);
}
