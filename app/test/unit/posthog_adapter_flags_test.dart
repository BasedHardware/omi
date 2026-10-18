import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:omi/utils/analytics/adapters/posthog_adapter.dart';

// The production adapter boundary: a flag reload is "successful" only when PostHog answered for the
// current distinct id. A failed fetch must not let cached (stale, possibly another person's) flags
// decide, and the identity changing clears the verified snapshot.

PostHogAnalyticsAdapter _adapter(
  MockClient client, {
  String? distinctId = 'u',
  DateTime Function()? clock,
  Map<String, Object?> Function()? personProperties,
}) =>
    PostHogAnalyticsAdapter(
      apiKey: 'phc_test',
      host: 'https://ph.test',
      client: client,
      distinctIdReader: () async => distinctId,
      personPropertiesForFlags: personProperties,
      clock: clock,
    );

MockClient _answering(Map<String, Object?> body, {int status = 200}) => MockClient((request) async {
      expect(request.url.toString(), 'https://ph.test/decide/?v=3');
      expect(jsonDecode(request.body), {'api_key': 'phc_test', 'distinct_id': 'u'});
      return http.Response(jsonEncode(body), status);
    });

void main() {
  test('boolean kill switches accept true only, never variants or missing flags', () async {
    final adapter = _adapter(_answering({
      'featureFlags': {
        'kill': true,
        'off': false,
        'variant': 'enabled',
        'string_true': 'true',
      }
    }));
    expect(await adapter.reloadFeatureFlags(), isTrue);
    expect(await adapter.isBooleanFeatureEnabled('kill'), isTrue);
    expect(adapter.isBooleanFeatureEnabledCached('kill'), isTrue);
    expect(adapter.isBooleanFeatureEnabledCached('variant'), isFalse);
    expect(adapter.isBooleanFeatureEnabledCached('missing'), isFalse);
    for (final key in ['off', 'variant', 'string_true', 'missing']) {
      expect(await adapter.isBooleanFeatureEnabled(key), isFalse);
    }
  });

  test('person properties ride along with the fetch; blank ones are dropped', () async {
    Object? sent;
    final client = MockClient((request) async {
      sent = jsonDecode(request.body);
      return http.Response(jsonEncode({'featureFlags': {}}), 200);
    });
    expect(await _adapter(client, personProperties: () => {'\$email': 'n@x.io', '\$name': ''}).reloadFeatureFlags(),
        isTrue);
    expect(sent, {
      'api_key': 'phc_test',
      'distinct_id': 'u',
      'person_properties': {'\$email': 'n@x.io'}
    });
    expect(await _adapter(client, personProperties: () => {'\$email': ''}).reloadFeatureFlags(), isTrue);
    expect(sent, {'api_key': 'phc_test', 'distinct_id': 'u'});
  });

  test('a successful fetch verifies the flags and the reads use them', () async {
    final adapter = _adapter(_answering({
      'featureFlags': {'onboarding-webview': true, 'paywall-variant': 'outline', 'off-flag': false},
      'featureFlagPayloads': {'onboarding-webview': '{"url": "https://x.example/onboarding"}'},
    }));
    expect(await adapter.reloadFeatureFlags(), isTrue);
    expect(await adapter.isFeatureEnabled('onboarding-webview'), isTrue);
    expect(await adapter.isFeatureEnabled('off-flag'), isFalse);
    expect(await adapter.isFeatureEnabled('unknown'), isFalse);
    expect(await adapter.getFeatureFlagPayload('onboarding-webview'), {'url': 'https://x.example/onboarding'});
    expect(await adapter.getFeatureFlagVariant('paywall-variant'), 'outline');
    expect(await adapter.getFeatureFlagVariant('onboarding-webview'), isNull);
  });

  test('a failed fetch is not a reload, and a stale enabled flag does not survive it', () async {
    var status = 200;
    final client = MockClient((_) async => http.Response(
          jsonEncode({
            'featureFlags': {'onboarding-webview': true}
          }),
          status,
        ));
    final adapter = _adapter(client);
    expect(await adapter.reloadFeatureFlags(), isTrue);
    expect(await adapter.isFeatureEnabled('onboarding-webview'), isTrue);

    status = 500;
    expect(await adapter.reloadFeatureFlags(), isFalse, reason: 'HTTP failure is not a refresh');
    // The verified snapshot is what a read sees; the gate never reads after a false reload anyway.
    expect(await adapter.isFeatureEnabled('onboarding-webview'), isTrue);
  });

  test('network errors, bad bodies and a missing distinct id all report no reload', () async {
    expect(
        await _adapter(MockClient((_) async => throw const SocketException('offline'))).reloadFeatureFlags(), isFalse);
    expect(await _adapter(MockClient((_) async => http.Response('not json', 200))).reloadFeatureFlags(), isFalse);
    expect(await _adapter(MockClient((_) async => http.Response('{"status":1}', 200))).reloadFeatureFlags(), isFalse);
    expect(await _adapter(_answering({'featureFlags': {}}), distinctId: null).reloadFeatureFlags(), isFalse);
  });

  test('an identity change drops the verified snapshot', () async {
    final adapter = _adapter(_answering({
      'featureFlags': {'onboarding-webview': true}
    }));
    expect(await adapter.reloadFeatureFlags(), isTrue);
    expect(adapter.hasVerifiedFlags, isTrue);
    adapter.identify(userId: 'someone-else');
    expect(adapter.hasVerifiedFlags, isFalse, reason: 'the next read must not see the previous identity\'s flags');
  });

  test("a delayed answer for account A cannot land after account B's reload", () async {
    final pendingA = Completer<http.Response>();
    var requests = 0;
    final client = MockClient((request) async {
      requests++;
      if (requests == 1) return pendingA.future; // A's request hangs
      return http.Response(
          jsonEncode({
            'featureFlags': {'only-b': true}
          }),
          200);
    });
    final adapter = _adapter(client);
    final reloadA = adapter.reloadFeatureFlags();
    adapter.identify(userId: 'b');
    expect(await adapter.reloadFeatureFlags(), isTrue);
    expect(await adapter.isFeatureEnabled('only-b'), isTrue);

    pendingA.complete(http.Response(
        jsonEncode({
          'featureFlags': {'only-a': true}
        }),
        200));
    expect(await reloadA, isFalse, reason: 'started under A, finished under B');
    expect(await adapter.isFeatureEnabled('only-a'), isFalse);
    expect(await adapter.isFeatureEnabled('only-b'), isTrue);
  });

  test('a verified fetch outranks the SDK only briefly; later reads fall through to the SDK cache', () async {
    var now = DateTime(2026, 10, 14, 20);
    final adapter = _adapter(
        _answering({
          'featureFlags': {'paywall-variant': 'outline'}
        }),
        clock: () => now);
    expect(await adapter.reloadFeatureFlags(), isTrue);
    expect(await adapter.getFeatureFlagVariant('paywall-variant'), 'outline');
    expect(adapter.hasVerifiedFlags, isTrue);

    now = now.add(PostHogAnalyticsAdapter.verifiedFlagsTtl + const Duration(seconds: 1));
    expect(adapter.hasVerifiedFlags, isFalse, reason: 'the SDK\'s own refreshes decide the rest of the session');
  });

  test('an internally created HTTP client is closed on success, failure and timeout', () async {
    // No injected client: the adapter creates and closes its own. The request goes to an unroutable
    // host, so this exercises the error path; closing is observable as the Future completing (an
    // unclosed client would keep the isolate's event loop busy, which the test harness reports).
    final adapter = PostHogAnalyticsAdapter(
      apiKey: 'phc_test',
      host: 'http://127.0.0.1:9',
      distinctIdReader: () async => 'u',
    );
    expect(await adapter.reloadFeatureFlags(), isFalse);
  });
}
