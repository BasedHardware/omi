import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/apps.dart';
import 'package:omi/backend/http/api_result.dart';

void main() {
  test('the setup probe requires a successful boolean verdict', () async {
    Future<ApiResult<AppSetupStatus>> read(int status, String body) =>
        getAppSetupStatus('https://vendor.test/setup', uid: 'synthetic', send: (request) async {
          expect(request.url, 'https://vendor.test/setup?uid=synthetic');
          expect(request.headers, isEmpty);
          return http.Response(body, status);
        });
    expect(
        (await read(200, '{"is_setup_completed":true}') as ApiSuccess<AppSetupStatus>).data, AppSetupStatus.completed);
    expect(
        (await read(200, '{"is_setup_completed":false}') as ApiSuccess<AppSetupStatus>).data, AppSetupStatus.pending);
    for (final body in ['{}', '[]', '{"is_setup_completed":"true"}', 'not json']) {
      expect(await read(200, body), isA<ApiFailure<AppSetupStatus>>());
    }
    expect(await read(503, '{"is_setup_completed":true}'), isA<ApiFailure<AppSetupStatus>>());
  });

  test('a legacy app without a completion endpoint is optional, never a verified connection', () async {
    var sends = 0;
    final result = await getAppSetupStatus(null, uid: 'synthetic', send: (_) async {
      sends++;
      return http.Response('{}', 200);
    });
    expect((result as ApiSuccess<AppSetupStatus>).data, AppSetupStatus.notRequired);
    expect(sends, 0);
  });
}
