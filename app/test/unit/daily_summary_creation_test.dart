import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/daily_summary_creation.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';

String _body() => jsonEncode({'id': 'recap-1', 'date': '2026-10-04', 'headline': 'Recovered day'});

void main() {
  test('uses the idempotent creation endpoint and decodes the persisted recap', () async {
    final api = DailySummaryCreationApi(
      baseUrl: 'https://recap.test.invalid/',
      send: (request) async {
        expect(request.method, 'POST');
        expect(Uri.parse(request.url).path, '/v1/users/daily-summaries');
        expect(jsonDecode(request.body), {'date': '2026-10-04'});
        return http.Response(_body(), 200);
      },
    );
    final result = await api.create('2026-10-04');
    expect((result as ApiSuccess<DailySummary>).data.id, 'recap-1');
    expect(result.data.date, '2026-10-04');
  });

  for (final status in [400, 402, 409, 422, 429, 500]) {
    test('retains status $status instead of claiming an empty or successful recap', () async {
      final api = DailySummaryCreationApi(
        baseUrl: 'https://recap.test.invalid/',
        send: (_) async => http.Response('{}', status, headers: {'retry-after': '30'}),
      );
      final result = await api.create('2026-10-04') as ApiFailure<DailySummary>;
      expect(result.problem.statusCode, status);
      if (status == 429) expect(result.problem.retryAfter, const Duration(seconds: 30));
    });
  }

  for (final body in [
    '{}',
    '{"summary_id":"old-test-envelope"}',
    '[]',
    '{"id":3,"date":"2026-10-04"}',
    '{"id":"wrong-date","date":"2026-10-05"}'
  ]) {
    test('rejects malformed or legacy test response $body', () async {
      final api =
          DailySummaryCreationApi(baseUrl: 'https://recap.test.invalid/', send: (_) async => http.Response(body, 200));
      final result = await api.create('2026-10-04') as ApiFailure<DailySummary>;
      expect(result.problem.kind, ApiProblemKind.decode);
    });
  }

  test('a connection failure is retained as a transport error', () async {
    final api = DailySummaryCreationApi(
      baseUrl: 'https://recap.test.invalid/',
      send: (_) async => throw const SocketException('offline'),
    );
    expect((await api.create('2026-10-04') as ApiFailure<DailySummary>).problem.kind, ApiProblemKind.transport);
  });

  test('does not publish a recap after an account A-to-B-to-A change', () async {
    final gateway = _Gateway();
    final auth = AuthService.forTesting(tokenGateway: gateway, refreshDelay: (_) async {});
    final api = DailySummaryCreationApi(
      auth: auth,
      baseUrl: 'https://recap.test.invalid/',
      send: (_) async {
        gateway.user = const AuthUserSnapshot(uid: 'b');
        auth.handleAuthUserChanged('b');
        gateway.user = const AuthUserSnapshot(uid: 'a');
        auth.handleAuthUserChanged('a');
        return http.Response(_body(), 200);
      },
    );
    final result = await api.create('2026-10-04') as ApiFailure<DailySummary>;
    expect(result.problem.kind, ApiProblemKind.authTerminal);
  });
}

class _Gateway implements AuthTokenGateway {
  AuthUserSnapshot? user = const AuthUserSnapshot(uid: 'a');
  @override
  AuthUserSnapshot? get currentUser => user;
  @override
  Future<RefreshedAuthToken?> forceRefresh() async => null;
  @override
  Future<void> signOut() async => user = null;
}
