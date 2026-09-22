import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/experiments/experiment_registry.dart';
import 'package:omi/utils/analytics/adapters/posthog_adapter.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('posthog_flutter');
  late List<MethodCall> calls;
  late PostHogAnalyticsAdapter adapter;
  final featureKey = '\$feature/${MobileExperiments.summaryFeedbackLayout.key}';

  setUp(() async {
    calls = [];
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call);
      if (call.method == 'getDistinctId') return 'synthetic';
      return null;
    });
    adapter = PostHogAnalyticsAdapter(apiKey: 'public-test-key');
    await adapter.init();
  });
  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null);
  });

  List<Map<String, dynamic>> captures() => calls
      .where((call) => call.method == 'capture')
      .map((call) => Map<String, dynamic>.from(call.arguments as Map))
      .toList();

  test('acknowledged outcome masks every registered experiment without explicit exposure', () async {
    await adapter.deliver(eventName: 'Product Journey Outcome', properties: {
      'outcome': 'success',
      'experiment_context_verified': true,
    });
    final properties = captures().single['properties'] as Map;
    for (final definition in MobileExperiments.all) {
      expect(properties['\$feature/${definition.key}'], false);
    }
    expect(properties['outcome'], 'success');
    expect(properties['experiment_context_verified'], true);
  });

  test('rendered exposure and retained outcome override native-cache mask', () async {
    await adapter.deliver(eventName: 'experiment_exposed', properties: {
      'experiment_key': MobileExperiments.summaryFeedbackLayout.key,
      'variant': 'compact',
      featureKey: 'compact',
    });
    await adapter.deliver(eventName: 'Product Journey Outcome', properties: {
      'outcome': 'success',
      'experiment_context_verified': true,
      featureKey: 'compact',
    });
    expect(captures().map((capture) => (capture['properties'] as Map)[featureKey]), ['compact', 'compact']);
  });

  test('legacy track is masked and snapshots caller properties before serialized capture', () async {
    final properties = <String, Object>{featureKey: 'compact', 'count': 1};
    adapter.track(eventName: 'explicit', properties: properties);
    properties[featureKey] = 'control';
    adapter.track(eventName: 'unexposed');
    // This acknowledged handoff drains the preceding track operations.
    await adapter.deliver(eventName: 'barrier', properties: {});
    final events = captures();
    expect((events[0]['properties'] as Map)[featureKey], 'compact');
    expect((events[1]['properties'] as Map)[featureKey], false);
    expect((events[2]['properties'] as Map)[featureKey], false);
    expect((events[0]['properties'] as Map)['count'], 1);
  });

  test('later unexposed capture does not inherit preceding exposed variant', () async {
    await adapter.deliver(eventName: 'Product Value', properties: {featureKey: 'compact'});
    await adapter.deliver(eventName: 'Product Value', properties: {});
    expect((captures().last['properties'] as Map)[featureKey], false);
  });
}
