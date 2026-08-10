import 'package:flutter_test/flutter_test.dart';

import '../lib/bridge_http_host.dart';
import '../lib/gen/bridge_http_contract.g.dart';

void main() {
  test('successful exact session DELETE clears live custody before the next Settings read', () {
    final host = BridgeHttpHost(baseUrl: Uri.parse('https://settings.example.test'), token: 'live-token');

    expect(host.prepareUsingCurrentCustodyForConformance('before').request, isNotNull);
    host.observeResponseForConformance(method: 'DELETE', path: '/v1/session/current', status: 503);
    expect(host.hasCredential, isTrue, reason: 'failed DELETE keeps custody');

    for (final nearMiss in <(String, String, int)>[
      ('GET', '/v1/session/current', 204),
      ('DELETE', '/v1/session/current?all=true', 204),
      ('DELETE', '/v1/session/other', 204),
      ('DELETE', '/v1/session/current', 200),
    ]) {
      host.observeResponseForConformance(method: nearMiss.$1, path: nearMiss.$2, status: nearMiss.$3);
    }
    expect(host.hasCredential, isTrue, reason: 'another verb, path, query, or status keeps custody');

    host.observeResponseForConformance(method: 'DELETE', path: '/v1/session/current', status: 204);
    expect(host.hasCredential, isFalse);
    final next = host.prepareUsingCurrentCustodyForConformance('after');
    expect(next.request, isNull);
    expect(next.failureReason, BridgeHttpFailureReason.notAuthenticated);
    // red-proof: delete the live response-observation call or loosen its exact
    // predicate; either the final no-credential assertion or a near-miss
    // assertion fails.
    host.closeForTest();
  });
}
