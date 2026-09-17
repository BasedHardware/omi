import 'package:http/http.dart' as http;
import 'api_fallback.dart';
import 'package:omi/services/auth_service.dart';

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
  bool get retryable => throw UnimplementedError('C3 retry policy');
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

/// Existing shared.dart header/auth/pool/replay path supplies the default send.
/// The typed path must never call nullable makeApiCall and guess why it failed.
Future<ApiResult<T>> executeApi<T>(
        {required ApiRequest request,
        required T Function(String) decode,
        ApiSend? send,
        ApiExecutionSeams? execution,
        DateTime Function()? now}) =>
    throw UnimplementedError('C3 lossless request boundary');

/// Decode the envelope once and rows independently. A wholly invalid nonempty
/// list is decode failure; a valid [] alone is empty success.
ApiResult<List<T>> decodeApiRows<T>(String body, T Function(Map<String, dynamic>) row,
        {void Function(ApiFallbackEvent)? fallback}) =>
    throw UnimplementedError('C3 isolated row decoding');
