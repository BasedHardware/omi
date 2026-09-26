import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/app_review_service.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

import '../../spine/c7_registry_test.dart' show RecordingAdapter;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final now = DateTime(2026, 9, 22, 12);
  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({
      'app_review_policy_v1': jsonEncode({
        'schema': 1,
        'migrationComplete': true,
        'migratedAtMs': null,
        'firstSeenAtMs': now.subtract(const Duration(days: 8)).millisecondsSinceEpoch,
        'readingDays': ['2026-09-15', '2026-09-16', '2026-09-22'],
        'attempts': <Object>[],
      }),
    });
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0',
      buildNumber: '1',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
  });
  tearDown(AnalyticsManager.resetForTesting);

  for (final platform in ['ios', 'android']) {
    test('$platform native request emits accurate typed counters through the analytics queue', () async {
      final adapter = RecordingAdapter();
      AnalyticsManager.configure(adapter);
      // Deliberately exercise the real production telemetry callback before init.
      final service = AppReviewService.forTesting(
        storage: await SharedPreferences.getInstance(),
        clock: () => now,
        platform: platform,
        appVersion: '1.0+1',
        isAvailable: () async => true,
        requestNativeReview: () async {},
      );
      await service.requestReview(moment: AppReviewMoment.dailySummaryRead, isStillAppropriate: () => true);
      expect(adapter.events, isEmpty);
      await AnalyticsManager.init();
      await AnalyticsManager.flushPending(force: true);
      expect(adapter.events.map((e) => e.$1), [
        'App Review Opportunity',
        'App Review Request Attempted',
        'App Review Request Finished',
      ]);
      expect(adapter.events.map((e) => e.$2['moment']), everyElement('daily_summary_read'));
      expect(adapter.events.first.$2['decision'], 'eligible');
      expect(adapter.events.last.$2['result'], 'returned');
      expect(adapter.events.any((e) => e.$2.containsKey('rated') || e.$2.containsKey('shown')), isFalse);
      await AnalyticsManager.flushPending(force: true);
      expect(adapter.events, hasLength(3));
    });
  }
}
