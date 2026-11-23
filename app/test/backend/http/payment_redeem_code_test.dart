// Exercises the real redemption request and strict applied-response decoder.
// All transport is injected; no code or account ever reaches a live service.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/payment.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/env/env.dart';

void main() {
  setUp(() => Env.overrideApiBaseUrl('http://127.0.0.1/'));
  tearDown(Env.clearApiBaseUrlOverrideForTesting);
  test('redeem posts only the trimmed code, never a plan or checkout input', () async {
    var calls = 0;
    final result = await redeemSubscriptionCode('  SYNTHETIC  ', send: (request) async {
      calls++;
      expect(request.method, 'POST');
      expect(Uri.parse(request.url).path, endsWith('/v1/payments/redeem-code'));
      expect(jsonDecode(request.body), {'code': 'SYNTHETIC'});
      return http.Response('{"status":"applied","percent_off":100,"applies_at":2000000000}', 200);
    });
    expect(calls, 1);
    expect(result, isA<ApiSuccess<bool>>());
    expect((result as ApiSuccess<bool>).data, isTrue);
  });

  for (final body in ['{}', '{"status":"pending"}', 'null', '[]', 'not json']) {
    test('does not accept an unconfirmed 2xx envelope: $body', () async {
      final result = await redeemSubscriptionCode('SYNTHETIC', send: (_) async => http.Response(body, 200));
      expect((result as ApiFailure<bool>).problem.kind, ApiProblemKind.decode);
    });
  }

  for (final status in [400, 401, 403, 409, 422, 429, 502]) {
    test('refusal $status never becomes applied or returns raw detail', () async {
      final result = await redeemSubscriptionCode('SYNTHETIC',
          send: (_) async =>
              http.Response('{"detail":"private free-form response"}', status, headers: {'retry-after': '3600'}));
      final problem = (result as ApiFailure<bool>).problem;
      expect(problem.statusCode, status);
      expect(problem.detail, isNull);
      if (status == 429) expect(problem.retryAfter, const Duration(hours: 1));
    });
  }

  test('transport failures remain failures', () async {
    for (final error in [const SocketException('offline'), TimeoutException('offline')]) {
      final result = await redeemSubscriptionCode('SYNTHETIC', send: (_) async => throw error);
      expect((result as ApiFailure<bool>).problem.kind, ApiProblemKind.transport);
    }
  });

  test('empty/oversize input and expired session do not send', () async {
    var calls = 0;
    Future<http.Response> send(ApiRequest _) async {
      calls++;
      return http.Response('{}', 200);
    }

    for (final code in ['', '   ', 'x' * 65]) {
      expect(await redeemSubscriptionCode(code, send: send), isA<ApiFailure<bool>>());
    }
    expect(await redeemSubscriptionCode('SYNTHETIC', send: send, canSend: () => false), isA<ApiFailure<bool>>());
    expect(calls, 0);
  });
}
