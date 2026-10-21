import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/apps.dart';

void main() {
  test('a plain setup url gets uid as its query', () {
    expect(appSetupUrlWithUid('https://example.com/setup', 'u1'), 'https://example.com/setup?uid=u1');
  });

  test('a setup url with a query keeps it and gets uid as its own param', () {
    final url = appSetupUrlWithUid('https://example.com/setup?source=omi', 'u1');

    expect(url, 'https://example.com/setup?source=omi&uid=u1');
    expect(Uri.parse(url).queryParameters, {'source': 'omi', 'uid': 'u1'});
  });

  test('existing query bytes are kept as they are and a stale uid is replaced', () {
    expect(
      appSetupUrlWithUid('https://example.com/setup?uid=old&sig=a%2Fb%3D&x=1+2', 'u1'),
      'https://example.com/setup?sig=a%2Fb%3D&x=1+2&uid=u1',
    );
  });

  test('the fragment stays after the query', () {
    expect(appSetupUrlWithUid('https://example.com/setup#step2', 'u1'), 'https://example.com/setup?uid=u1#step2');
    expect(
        appSetupUrlWithUid('https://example.com/setup?a=b#step2', 'u1'), 'https://example.com/setup?a=b&uid=u1#step2');
  });

  test('a uid with reserved characters reaches the server unchanged', () {
    final params = Uri.parse(appSetupUrlWithUid('https://example.com/setup?a=b', 'u&x=1#f')).queryParameters;

    expect(params, {'a': 'b', 'uid': 'u&x=1#f'});
  });
}
