import 'package:flutter_test/flutter_test.dart';
import 'package:omi_webview_proto/listen_socket_host.dart';

void main() {
  test('iOS production socket composition targets the API authority with the shell bearer', () {
    final authority = ShellTransportAuthority(
      baseUrl: Uri.parse('https://staging.example.test/api'),
      token: 'shell-token',
      runId: 'run-listen-proof',
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

  test('authority validates raw run identity and suffixes ios exactly once', () {
    final valid = ShellTransportAuthority(
      baseUrl: Uri.parse('https://api.example'),
      token: 'shell-token',
      runId: 'run-evidence_01',
    );
    expect(valid.clientIdentity, 'run-evidence_01::ios');
    valid.makeHttpHost().closeForTest();

    for (final raw in <String>['', 'unsafe value', 'already::ios', 'anonymous', 'overflow', '__reserved']) {
      expect(
        () => ShellTransportAuthority(baseUrl: Uri.parse('https://api.example'), token: 'shell-token', runId: raw),
        throwsArgumentError,
        reason: raw,
      );
    }
  });
}
