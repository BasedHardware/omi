import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import '../support/spine/contract.dart';

const request = ApiRequest(url: 'http://127.0.0.1:1/v1/conversations', method: 'GET');

void main() {
  const statuses = {
    401: ApiProblemKind.authTerminal,
    403: ApiProblemKind.forbidden,
    404: ApiProblemKind.notFound,
    402: ApiProblemKind.paymentRequired,
    422: ApiProblemKind.unprocessable,
    429: ApiProblemKind.rateLimited,
    503: ApiProblemKind.server,
    500: ApiProblemKind.server,
    400: ApiProblemKind.rejected,
    409: ApiProblemKind.rejected,
    302: ApiProblemKind.rejected
  };
  for (final entry in statuses.entries) {
    contractTest('C3 HTTP ${entry.key} retains its distinct cause and never decodes/retries', () async {
      pendingContract('C3');
      var sends = 0;
      var decodes = 0;
      final result = await executeApi(
          request: request,
          send: (_) async {
            sends++;
            return http.Response('sensitive-server-body', entry.key);
          },
          decode: (_) {
            decodes++;
            return ['must-not-render'];
          });
      expect(result, isA<ApiFailure<List<String>>>());
      final error = (result as ApiFailure<List<String>>).problem;
      expect(error.kind, entry.value);
      expect(error.statusCode, entry.key);
      expect(error.retryable, [429, 500, 503].contains(entry.key));
      expect(sends, 1);
      expect(decodes, 0);
      expect(error.toString(), isNot(contains('sensitive-server-body')));
    });
  }
  for (final error in [
    const SocketException('synthetic'),
    const HandshakeException('synthetic'),
    TimeoutException('synthetic'),
    http.ClientException('synthetic')
  ]) {
    contractTest('C3 ${error.runtimeType} is transport, never null/success', () async {
      pendingContract('C3');
      final result = await executeApi<String>(request: request, send: (_) async => throw error, decode: (s) => s);
      expect(result, isA<ApiFailure<String>>());
      final problem = (result as ApiFailure<String>).problem;
      expect(problem.kind, ApiProblemKind.transport);
      expect(problem.retryable, isTrue);
      expect(problem.statusCode, isNull);
    });
  }
  for (final auth in [
    const AuthTokenMissingUser(),
    const AuthTokenMissingToken(),
    const AuthTokenTerminalFailure(code: 'user-disabled'),
    const AuthTokenTransientFailure(failureClass: 'network')
  ]) {
    contractTest('C3 preserves ${auth.runtimeType} without a second auth interpretation', () async {
      pendingContract('C3');
      final result = await executeApi<String>(
          request: request, send: (_) async => throw AuthTokenUnavailableException(auth), decode: (s) => s);
      final p = (result as ApiFailure<String>).problem;
      expect(p.kind, auth is AuthTokenTransientFailure ? ApiProblemKind.authTransient : ApiProblemKind.authTerminal);
      expect(p.retryable, auth is AuthTokenTransientFailure);
    });
  }
  contractTest('C3 success decodes once and programmer failures do not become transport', () async {
    pendingContract('C3');
    var decodes = 0;
    final ok = await executeApi(
        request: request,
        send: (_) async => http.Response('[]', 200),
        decode: (s) {
          decodes++;
          expect(s, '[]');
          return <String>[];
        });
    expect((ok as ApiSuccess<List<String>>).data, isEmpty);
    expect(decodes, 1);
    await expectLater(
        executeApi<String>(request: request, send: (_) async => throw StateError('bug'), decode: (s) => s),
        throwsStateError);
    await expectLater(
        executeApi<String>(
            request: request,
            send: (_) async => http.Response('valid response', 200),
            decode: (_) => throw StateError('programmer bug')),
        throwsStateError);
    final bad = await executeApi<String>(
        request: request,
        send: (_) async => http.Response('bad', 200),
        decode: (_) => throw const FormatException('invalid response'));
    expect((bad as ApiFailure<String>).problem.kind, ApiProblemKind.decode);
  });
  for (final header in ['30', 'Thu, 17 Sep 2026 00:00:45 GMT', 'invalid', '-1']) {
    contractTest('C3 Retry-After $header is bounded metadata, not a timer', () async {
      pendingContract('C3');
      final r = await executeApi<String>(
          request: request,
          decode: (s) => s,
          now: () => DateTime.utc(2026, 9, 17),
          send: (_) async => http.Response('{}', 429, headers: {'retry-after': header}));
      final expected = header == '30'
          ? const Duration(seconds: 30)
          : header.contains('GMT')
              ? const Duration(seconds: 45)
              : null;
      expect((r as ApiFailure<String>).problem.retryAfter, expected);
    });
  }
}
