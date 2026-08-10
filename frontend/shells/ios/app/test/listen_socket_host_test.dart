import 'package:flutter_test/flutter_test.dart';
import 'package:omi_webview_proto/listen_socket_host.dart';

void main() {
  test('iOS production socket composition targets the API authority with the shell bearer', () {
    final authority = ShellTransportAuthority(
      baseUrl: Uri.parse('https://staging.example.test/api'),
      token: 'shell-token',
    );
    final http = authority.makeHttpHost();
    final result = authority.prepareListen('/v4/listen?language=en');
    expect(http.baseUrl, authority.baseUrl);
    expect(http.hasCredential, isTrue);
    expect(result.failure, isNull);
    expect(result.request?.url.toString(), 'wss://staging.example.test/v4/listen?language=en');
    expect(result.request?.url.toString(), isNot(contains('omi-ui://local')));
    expect(result.request?.headers['authorization'], 'Bearer shell-token');
    http.closeForTest();
  });
}
