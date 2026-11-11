import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:omi/backend/http/api_edge_throttle_telemetry.dart';

void main() {
  late int now;
  late List<Map<String, dynamic>> events;
  late ApiEdgeThrottleTelemetry telemetry;
  setUp(() {
    now = 0;
    events = [];
    telemetry = ApiEdgeThrottleTelemetry(
      elapsedMilliseconds: () => now,
      emit: (name, properties) => events.add({'name': name, ...properties}),
    );
  });
  void observe(String path, {String method = 'GET', int status = 429, Map<String, String> headers = const {}}) {
    telemetry.observe(
        http.Request(method, Uri.parse('https://api.omi.me$path')), http.Response('', status, headers: headers));
  }

  test('IDs, query, fragment and all-letter IDs never leave the template allowlist', () {
    for (final id in ['123', 'abcd-efgh-1234', 'alice', 'alice%40example.com', 'a%2Fb']) {
      expect(
          ApiEdgeThrottleTelemetry.endpointTemplate(
              Uri.parse('https://api.omi.me/v2/sync-local-files/$id?uid=secret#private')),
          '/v2/sync-local-files/{id}');
    }
    for (final path in ['/v1/unknown/alice', '/alice/private']) {
      expect(ApiEdgeThrottleTelemetry.endpointTemplate(Uri.parse('https://api.omi.me$path')), '/other');
    }
    observe('/v2/sync-local-files/alice?uid=secret', headers: {'Retry-After': '120'});
    expect(events.single, {
      'name': 'api_edge_throttled',
      'endpoint_template': '/v2/sync-local-files/{id}',
      'method': 'GET',
      'path_family': 'sync',
      'trigger': 'system',
      'retry_after': '120',
    });
  });
  test('one per template per five minutes, across IDs and methods', () {
    observe('/v2/sync-local-files/one');
    for (var i = 0; i < 1000; i++) {
      observe('/v2/sync-local-files/$i', method: 'POST');
    }
    now = 299999;
    observe('/v2/sync-local-files/two');
    expect(events, hasLength(1));
    observe('/v1/conversations/another');
    expect(events, hasLength(2));
    now = 300000;
    observe('/v2/sync-local-files/three');
    expect(events, hasLength(3));
  });
  test('untrusted hosts and other status codes do not consume the budget', () {
    for (final host in ['api.omi.me.attacker.test', 'one.one.one.one', '127.0.0.1']) {
      telemetry.observe(
          http.Request('GET', Uri.parse('https://$host/v2/sync-local-files/one')), http.Response('', 429));
    }
    observe('/v2/sync-local-files/one', status: 200);
    observe('/v2/sync-local-files/one', status: 409);
    expect(events, isEmpty);
    observe('/v2/sync-local-files/one');
    expect(events, hasLength(1));
  });
  test('Retry-After date survives; arbitrary header content is discarded', () {
    observe('/v1/conversations', headers: {'retry-after': 'Wed, 21 Oct 2026 07:28:00 GMT'});
    expect(events.last['retry_after'], 'Wed, 21 Oct 2026 07:28:00 GMT');
    observe('/v1/action-items', headers: {'retry-after': 'alice@example.com'});
    expect(events.last.containsKey('retry_after'), isFalse);
    observe('/v3/memories');
    expect(events.last.containsKey('retry_after'), isFalse);
  });
  test('analytics failure cannot change the transport result or retry the event', () {
    var attempts = 0;
    telemetry = ApiEdgeThrottleTelemetry(
        elapsedMilliseconds: () => now,
        emit: (_, __) {
          attempts++;
          throw StateError('sink unavailable');
        });
    observe('/v1/conversations');
    observe('/v1/conversations');
    expect(attempts, 1);
  });
}
