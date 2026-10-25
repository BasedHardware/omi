import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api/apps.dart';

void main() {
  test('plugin completion uses the signed query without Omi bearer headers', () async {
    final result = await isAppSetupCompleted(
      'https://plugin.test/status?omi_token=synthetic.signed&uid=old',
      uid: 'fixture-user',
      send: (request) async {
        expect(Uri.parse(request.url).queryParameters, {'omi_token': 'synthetic.signed', 'uid': 'fixture-user'});
        expect(request.headers, isEmpty);
        return http.Response('{"is_setup_completed":true}', 200);
      },
    );
    expect(result, isTrue);
  });

  test('a vendor rejection or malformed verdict never completes setup', () async {
    for (final (status, body) in [
      (401, '{"is_setup_completed":true}'),
      (503, '{"is_setup_completed":true}'),
      (200, '{"is_setup_completed":"true"}'),
      (200, '{}'),
      (200, 'not json'),
    ]) {
      expect(
          await isAppSetupCompleted('https://plugin.test/status',
              uid: 'fixture-user', send: (_) async => http.Response(body, status)),
          isFalse);
    }
  });

  test('legacy apps without a completion endpoint retain optional setup', () async {
    var sends = 0;
    expect(
        await isAppSetupCompleted(null, uid: 'fixture-user', send: (_) async {
          sends++;
          return http.Response('{}', 200);
        }),
        isTrue);
    expect(sends, 0);
  });
}
