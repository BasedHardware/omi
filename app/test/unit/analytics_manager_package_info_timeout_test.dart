import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const packageInfoChannel = MethodChannel('dev.fluttercommunity.plus/package_info');

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      packageInfoChannel,
      null,
    );
    AnalyticsManager.resetForTesting();
  });

  test('init fails open when package metadata lookup hangs', () async {
    final neverCompletes = Completer<Object?>();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      packageInfoChannel,
      (_) => neverCompletes.future,
    );
    final adapter = _TestAnalyticsAdapter();
    AnalyticsManager.configure(adapter);

    final elapsed = Stopwatch()..start();
    await AnalyticsManager.init(timeout: const Duration(milliseconds: 10));
    elapsed.stop();
    AnalyticsManager().track('Event After Metadata Timeout');
    await AnalyticsManager.flushPending(force: true);

    expect(elapsed.elapsed, lessThan(const Duration(milliseconds: 250)));
    expect(adapter.events.single, 'Event After Metadata Timeout');
  });
}

class _TestAnalyticsAdapter implements AnalyticsAdapter {
  final List<String> events = [];

  @override
  bool get isInitialized => true;

  @override
  Future<void> init() async {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) => events.add(eventName);

  @override
  void alias({required String newUserId}) {}

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}
