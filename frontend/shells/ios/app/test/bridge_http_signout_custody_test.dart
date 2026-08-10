import 'package:flutter_test/flutter_test.dart';

import '../lib/bridge_http_host.dart';
import '../lib/gen/bridge_http_contract.g.dart';
import '../lib/listen_socket_host.dart';

void main() {
  test('HTTP and Listen share exact-success session custody', () {
    final authority = ShellTransportAuthority(baseUrl: Uri.parse('https://settings.example.test'), token: 'live-token');
    final http = authority.makeHttpHost();
    final listen = authority.makeListenHost();

    expect(http.prepareUsingCurrentCustodyForConformance('http-before').request, isNotNull);
    expect(listen.prepareUsingCurrentCustodyForConformance('/v4/listen').request, isNotNull);

    http.observeResponseForConformance(method: 'DELETE', path: '/v1/session/current', status: 503);
    expect(http.hasCredential, isTrue, reason: 'near-miss status keeps HTTP custody');
    expect(
      listen.prepareUsingCurrentCustodyForConformance('/v4/listen').request,
      isNotNull,
      reason: 'near-miss status keeps Listen custody',
    );

    http.observeResponseForConformance(method: 'DELETE', path: '/v1/session/other', status: 204);
    expect(http.hasCredential, isTrue, reason: 'near-miss route keeps HTTP custody');
    expect(
      listen.prepareUsingCurrentCustodyForConformance('/v4/listen').request,
      isNotNull,
      reason: 'near-miss route keeps Listen custody',
    );

    expect(BridgeHttpHost.transportFailureForConformance('timeout', 'timeout'), BridgeHttpFailureReason.timeout);
    expect(http.prepareUsingCurrentCustodyForConformance('after-timeout').request, isNotNull);
    expect(listen.prepareUsingCurrentCustodyForConformance('/v4/listen').request, isNotNull);

    http.observeResponseForConformance(method: 'DELETE', path: '/v1/session/current', status: 204);
    expect(http.hasCredential, isFalse);
    final next = http.prepareUsingCurrentCustodyForConformance('after');
    expect(next.request, isNull);
    expect(next.failureReason, BridgeHttpFailureReason.notAuthenticated);
    final nextListen = listen.prepareUsingCurrentCustodyForConformance('/v4/listen?language=en');
    expect(nextListen.request, isNull, reason: 'next Listen open must share cleared HTTP custody');
    expect(nextListen.failure, 'shell holds no credential');
    // red-proof: make either host retain a token copied from custody at
    // construction, remove the live response observation, or loosen its exact
    // predicate; a named cross-transport or near-miss assertion fails.
    http.closeForTest();
  });
}
