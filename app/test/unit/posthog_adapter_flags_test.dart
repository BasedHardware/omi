import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/utils/analytics/adapters/posthog_adapter.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('first native setup attribution matches the resolved Flutter SDK', () {
    final lock = File('pubspec.lock').readAsStringSync();
    final block = RegExp(r'^  posthog_flutter:\n((?: {4}.*\n)+)', multiLine: true).firstMatch(lock)?.group(1);
    expect(block, isNotNull);
    final version = RegExp(r'^    version: "([^"]+)"$', multiLine: true).firstMatch(block!)?.group(1);
    expect(PostHogAnalyticsAdapter.flutterSdkVersion, version);
  });

  test('setup disables preloads; reload and every read use only Omi; capture still delivers', () async {
    SharedPreferences.setMockInitialValues({});
    final calls = <MethodCall>[];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('posthog_flutter'),
      (call) async {
        calls.add(call);
        // A stale SDK flag must never be consulted, even when the store omits it.
        if (call.method == 'getFeatureFlagResult' || call.method == 'isFeatureEnabled') return true;
        return null;
      },
    );
    var refreshes = 0;
    final adapter = PostHogAnalyticsAdapter(
        apiKey: 'test',
        omiFlags: () async {
          refreshes++;
          return {
            'on': (enabled: true, variant: null, payloadJson: '{"n":1}'),
            'off': (enabled: false, variant: null, payloadJson: null),
            'variant': (enabled: true, variant: 'telegram', payloadJson: null),
          };
        });
    await adapter.init();
    expect(await adapter.reloadFeatureFlags(), isTrue);
    expect(refreshes, 1);
    expect(adapter.isBooleanFeatureEnabledCached('on'), isTrue);
    expect(await adapter.isBooleanFeatureEnabled('variant'), isFalse);
    expect(await adapter.isFeatureEnabled('on'), isTrue);
    expect(await adapter.resolvedFeatureEnabled('off'), isFalse);
    expect(await adapter.getFeatureFlagVariant('variant'), 'telegram');
    expect(await adapter.getFeatureFlagPayload('on'), {'n': 1});
    expect(await adapter.resolvedFeatureEnabled('sdk-only'), isNull);
    expect(await adapter.isFeatureEnabled('sdk-only'), isFalse);
    expect(await adapter.isBooleanFeatureEnabled('sdk-only'), isFalse);
    expect(await adapter.getFeatureFlagVariant('sdk-only'), isNull);
    expect(await adapter.getFeatureFlagPayload('sdk-only'), isNull);
    adapter.identify(userId: 'b');
    expect(await adapter.resolvedFeatureEnabled('on'), isNull);
    await adapter.deliver(eventName: 'Chat Message Sent', properties: {'length': 1});
    final setup = calls.singleWhere((c) => c.method == 'setup').arguments as Map;
    expect(setup['preloadFeatureFlags'], isFalse);
    expect(setup['surveys'], isFalse);
    expect(setup['sendFeatureFlagEvents'], isFalse);
    expect(calls.where((c) => c.method == 'capture').single.arguments['eventName'], 'Chat Message Sent');
    expect(calls.map((c) => c.method), isNot(contains('reloadFeatureFlags')));
    expect(calls.map((c) => c.method), isNot(contains('getFeatureFlagResult')));
    expect(calls.map((c) => c.method), isNot(contains('isFeatureEnabled')));
  });

  test('failed refresh keeps same-account answers; successful empty refresh removes them', () async {
    Map<String, OmiFlag>? flags = {'k': (enabled: true, variant: null, payloadJson: null)};
    final adapter = PostHogAnalyticsAdapter(apiKey: 'test', omiFlags: () async => flags);
    expect(await adapter.reloadFeatureFlags(), isTrue);
    flags = null;
    expect(await adapter.reloadFeatureFlags(), isFalse);
    expect(await adapter.isFeatureEnabled('k'), isTrue);
    flags = {};
    expect(await adapter.reloadFeatureFlags(), isTrue);
    expect(await adapter.resolvedFeatureEnabled('k'), isNull);
  });

  test('late account A answer cannot replace account B', () async {
    final pendingA = Completer<Map<String, OmiFlag>?>();
    var calls = 0;
    final adapter = PostHogAnalyticsAdapter(
        apiKey: 'test',
        omiFlags: () {
          if (++calls == 1) return pendingA.future;
          return Future.value({'b': (enabled: true, variant: null, payloadJson: null)});
        });
    final reloadA = adapter.reloadFeatureFlags();
    adapter.identify(userId: 'b');
    expect(await adapter.reloadFeatureFlags(), isTrue);
    pendingA.complete({'a': (enabled: true, variant: null, payloadJson: null)});
    expect(await reloadA, isFalse);
    expect(await adapter.isFeatureEnabled('b'), isTrue);
    expect(await adapter.resolvedFeatureEnabled('a'), isNull);
    adapter.reset();
    expect(await adapter.resolvedFeatureEnabled('b'), isNull);
  });

  test('same-account profile updates preserve flags and an in-flight refresh', () async {
    final pending = Completer<Map<String, OmiFlag>?>();
    var delayed = false;
    final adapter = PostHogAnalyticsAdapter(
        apiKey: 'test',
        omiFlags: () async {
          if (delayed) return pending.future;
          return {'k': (enabled: true, variant: null, payloadJson: null)};
        });
    adapter.identify(userId: 'u');
    await adapter.reloadFeatureFlags();
    adapter.identify(userId: 'u', userProperties: {'name': 'updated'});
    expect(await adapter.isFeatureEnabled('k'), isTrue);
    delayed = true;
    final reload = adapter.reloadFeatureFlags();
    adapter.identify(userId: 'u', userProperties: {'device': 'paired'});
    pending.complete({'k': (enabled: false, variant: null, payloadJson: null)});
    expect(await reload, isTrue);
    expect(await adapter.resolvedFeatureEnabled('k'), isFalse);
  });

  test('unavailable store never falls through to SDK', () async {
    for (final fetch in <Future<Map<String, OmiFlag>?> Function()?>[null, () async => throw StateError('offline')]) {
      final adapter = PostHogAnalyticsAdapter(apiKey: 'test', omiFlags: fetch);
      expect(await adapter.reloadFeatureFlags(), isFalse);
      expect(await adapter.resolvedFeatureEnabled('missing'), isNull);
    }
  });
}
