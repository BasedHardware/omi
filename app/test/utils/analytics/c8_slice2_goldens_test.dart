import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../spine/c7_registry_test.dart' show RecordingAdapter, emissionPayloads;

/// Adapter payloads captured from [AnalyticsManager] public methods at
/// `75db8620c6b9628e30974c6ff21624c8f42089b5`, before those methods called
/// [TypedEvents.emit]. A silent rename here breaks dashboards outside the repo.
const c8Slice2PreMigrationSha = '75db8620c6b9628e30974c6ff21624c8f42089b5';

void fireC8Slice2(AnalyticsManager analytics) {
  analytics.deviceOnboardingAbandoned(0);
  analytics.deviceOnboardingAbandoned(3);
  analytics.deviceOnboardingDoubleTapConfigured(0);
  analytics.deviceOnboardingDoubleTapConfigured(2);
  analytics.phoneCallEnded(durationSeconds: 0);
  analytics.phoneCallEnded(durationSeconds: 42);
  analytics.shortConversationThresholdChanged(0);
  analytics.shortConversationThresholdChanged(60);
  analytics.shortConversationThresholdChanged(119);
  analytics.memorySearchCleared(0);
  analytics.memorySearchCleared(12);
  analytics.memoriesAllDeleted(0);
  analytics.memoriesAllDeleted(4);
  analytics.notificationFrequencyChanged(oldFrequency: 0, newFrequency: 1);
  analytics.notificationFrequencyChanged(oldFrequency: 24, newFrequency: 7);
  analytics.changelogDismissed(changelogCount: 0);
  analytics.changelogDismissed(changelogCount: 3);
  analytics.appsFilterRating(rating: 1);
  analytics.appsFilterRating(rating: 5);
  analytics.aiAppGeneratorPromptSubmitted(promptLength: 0);
  analytics.aiAppGeneratorPromptSubmitted(promptLength: 40);
  analytics.voiceResponseModeChanged(0);
  analytics.voiceResponseModeChanged(1);
  analytics.voiceResponseModeChanged(2);
  analytics.voiceResponseModeChanged(99);
  analytics.memoriesAllVisibilityChanged(MemoryVisibility.private, 0);
  analytics.memoriesAllVisibilityChanged(MemoryVisibility.public, 1);
  analytics.memoriesAllVisibilityChanged(MemoryVisibility.shared, 3);
}

List<List<Object>> c8Slice2Goldens(Map<String, Object> globals) => [
      [
        'Device Onboarding Abandoned',
        {...globals, 'step': 0}
      ],
      [
        'Device Onboarding Abandoned',
        {...globals, 'step': 3}
      ],
      [
        'Device Onboarding Double Tap Configured',
        {...globals, 'action': 0}
      ],
      [
        'Device Onboarding Double Tap Configured',
        {...globals, 'action': 2}
      ],
      [
        'Phone Call Ended',
        {...globals, 'duration_seconds': 0}
      ],
      [
        'Phone Call Ended',
        {...globals, 'duration_seconds': 42}
      ],
      [
        'Short Conversation Threshold Changed',
        {...globals, 'threshold_seconds': 0, 'threshold_minutes': 0}
      ],
      [
        'Short Conversation Threshold Changed',
        {...globals, 'threshold_seconds': 60, 'threshold_minutes': 1}
      ],
      [
        'Short Conversation Threshold Changed',
        {...globals, 'threshold_seconds': 119, 'threshold_minutes': 1}
      ],
      [
        'Fact Search Cleared',
        {...globals, 'total_facts_count': 0}
      ],
      [
        'Fact Search Cleared',
        {...globals, 'total_facts_count': 12}
      ],
      [
        'All Facts Deleted',
        {...globals, 'facts_count_before_deletion': 0}
      ],
      [
        'All Facts Deleted',
        {...globals, 'facts_count_before_deletion': 4}
      ],
      [
        'Notification Frequency Changed',
        {...globals, 'old_frequency': 0, 'new_frequency': 1}
      ],
      [
        'Notification Frequency Changed',
        {...globals, 'old_frequency': 24, 'new_frequency': 7}
      ],
      [
        'Changelog Dismissed',
        {...globals, 'changelog_count': 0}
      ],
      [
        'Changelog Dismissed',
        {...globals, 'changelog_count': 3}
      ],
      [
        'Apps Filter Rating',
        {...globals, 'rating': 1}
      ],
      [
        'Apps Filter Rating',
        {...globals, 'rating': 5}
      ],
      [
        'AI App Generator Prompt Submitted',
        {...globals, 'prompt_length': 0}
      ],
      [
        'AI App Generator Prompt Submitted',
        {...globals, 'prompt_length': 40}
      ],
      [
        'Voice Response Mode Changed',
        {...globals, 'mode': 'off', 'mode_int': 0}
      ],
      [
        'Voice Response Mode Changed',
        {...globals, 'mode': 'headphones_only', 'mode_int': 1}
      ],
      [
        'Voice Response Mode Changed',
        {...globals, 'mode': 'always', 'mode_int': 2}
      ],
      [
        'Voice Response Mode Changed',
        {...globals, 'mode': 'unknown', 'mode_int': 99}
      ],
      [
        'All Facts Visibility Changed',
        {...globals, 'new_visibility': 'private', 'facts_count': 0}
      ],
      [
        'All Facts Visibility Changed',
        {...globals, 'new_visibility': 'public', 'facts_count': 1}
      ],
      [
        'All Facts Visibility Changed',
        {...globals, 'new_visibility': 'shared', 'facts_count': 3}
      ],
    ];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
        appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.543', buildNumber: '992', buildSignature: '');
    await SharedPreferencesUtil.init();
  });
  tearDown(AnalyticsManager.resetForTesting);

  test('C8 slice-2 public methods match goldens pinned at $c8Slice2PreMigrationSha', () async {
    final adapter = RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    fireC8Slice2(AnalyticsManager());
    await AnalyticsManager.flushPending(force: true);
    await AnalyticsManager.flushPending(force: true);
    final globals = <String, Object>{
      'app_platform': PlatformService.isIOS ? 'ios' : (PlatformService.isAndroid ? 'android' : 'unknown'),
      'app_version': '1.0.543',
      'app_build': '992',
    };
    expect(emissionPayloads(adapter.events), c8Slice2Goldens(globals));
    expect(adapter.events.every((event) => !event.$2.containsKey('correlation_id')), isTrue);
    expect(AnalyticsManager.queuedEventCountForTesting, 0);
  });
}
