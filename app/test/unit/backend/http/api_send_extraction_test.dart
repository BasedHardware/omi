import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';

class _ExtractionEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'https://auth-not-required.invalid/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  setUpAll(() {
    Env.init(_ExtractionEnv());
  });

  test('sendUncaughtApiCall is the uncaught path makeApiCall wraps as null', () async {
    Object? uncaught;
    try {
      await sendUncaughtApiCall(
        url: 'http://127.0.0.1:1/v1/conversations',
        headers: {},
        body: '',
        method: 'GET',
      );
    } catch (e) {
      uncaught = e;
    }
    expect(uncaught, isNotNull);
    final wrapped = await makeApiCall(
      url: 'http://127.0.0.1:1/v1/conversations',
      headers: {},
      body: '',
      method: 'GET',
    );
    expect(wrapped, isNull);
  });

  test('402 and 422 are terminal: one send, no decode, never retryable', () async {
    for (final status in [402, 422]) {
      var sends = 0;
      final result = await executeApi<String>(
        request: const ApiRequest(url: 'http://127.0.0.1:1/v1/sync', method: 'POST'),
        send: (_) async {
          sends++;
          return http.Response('{}', status);
        },
        decode: (_) => throw StateError('must not decode or mark uploaded'),
      );
      final problem = (result as ApiFailure<String>).problem;
      expect(sends, 1);
      expect(problem.retryable, isFalse);
      expect(problem.kind, status == 402 ? ApiProblemKind.paymentRequired : ApiProblemKind.unprocessable);
    }
  });
}
