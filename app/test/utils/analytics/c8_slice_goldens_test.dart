import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../spine/c7_registry_test.dart' show RecordingAdapter, emissionPayloads;

/// Adapter payloads captured from [AnalyticsManager] public methods at
/// `c789b4e19ebe2944cb4613425fb7643888bf4cf0`, before those methods called
/// [TypedEvents.emit]. A silent rename here breaks dashboards outside the repo.
const c8SlicePreMigrationSha = 'c789b4e19ebe2944cb4613425fb7643888bf4cf0';

void fireC8Slice(AnalyticsManager analytics) {
  analytics.onboardingCompleted();
  analytics.phoneMicRecordingStarted();
  analytics.phoneMicRecordingStopped();
  analytics.transcribeLaterToggled(enabled: false);
  analytics.transcribeLaterToggled(enabled: true);
  analytics.deviceOnboardingCompleted();
  analytics.transcribeLaterRecordingProcessed();
  analytics.calendarEnabled();
  analytics.calendarDisabled();
  analytics.calendarSelected();
  analytics.conversationDisplaySettingsOpened();
  analytics.developerModeEnabled();
  analytics.developerModeDisabled();
  analytics.settingsSaved();
  analytics.settingsSaved(hasWebhookConversationCreated: true);
  analytics.settingsSaved(hasWebhookTranscriptReceived: true);
  analytics.settingsSaved(hasWebhookConversationCreated: true, hasWebhookTranscriptReceived: true);
  analytics.voiceResponseToggled(false);
  analytics.voiceResponseToggled(true);
  analytics.showShortConversationsToggled(false);
  analytics.showShortConversationsToggled(true);
}

List<List<Object>> c8SliceGoldens(Map<String, Object> globals) => [
      ['Onboarding Completed', globals],
      ['Phone Mic Recording Started', globals],
      ['Phone Mic Recording Stopped', globals],
      [
        'Transcribe Later Toggled',
        {...globals, 'enabled': false}
      ],
      [
        'Transcribe Later Toggled',
        {...globals, 'enabled': true}
      ],
      ['Device Onboarding Completed', globals],
      ['Transcribe Later Recording Processed', globals],
      ['Calendar Enabled', globals],
      ['Calendar Disabled', globals],
      ['Calendar Selected', globals],
      ['Conversation Display Settings Opened', globals],
      ['Developer Mode Enabled', globals],
      ['Developer Mode Disabled', globals],
      [
        'Developer Settings Saved',
        {...globals, 'has_webhook_memory_created': false, 'has_webhook_transcript_received': false}
      ],
      [
        'Developer Settings Saved',
        {...globals, 'has_webhook_memory_created': true, 'has_webhook_transcript_received': false}
      ],
      [
        'Developer Settings Saved',
        {...globals, 'has_webhook_memory_created': false, 'has_webhook_transcript_received': true}
      ],
      [
        'Developer Settings Saved',
        {...globals, 'has_webhook_memory_created': true, 'has_webhook_transcript_received': true}
      ],
      [
        'Voice Response Audio Toggled',
        {...globals, 'enabled': false}
      ],
      [
        'Voice Response Audio Toggled',
        {...globals, 'enabled': true}
      ],
      [
        'Show Short Conversations Toggled',
        {...globals, 'show_short': false}
      ],
      [
        'Show Short Conversations Toggled',
        {...globals, 'show_short': true}
      ],
    ];

void fireC8TypeExtension(TypedEvents typed) {
  typed.emit(const TypeExtensionProbe(enabled: false, count: 0, mode: TypeExtensionProbeMode.off));
  typed.emit(const TypeExtensionProbe(enabled: true, count: 1, mode: TypeExtensionProbeMode.headphonesOnly));
  typed.emit(const TypeExtensionProbe(enabled: true, count: 99, mode: TypeExtensionProbeMode.always));
}

List<List<Object>> c8TypeExtensionGoldens(Map<String, Object> globals) => [
      [
        'Type Extension Probe',
        {...globals, 'enabled': false, 'count': 0, 'mode': 'off'}
      ],
      [
        'Type Extension Probe',
        {...globals, 'enabled': true, 'count': 1, 'mode': 'headphones_only'}
      ],
      [
        'Type Extension Probe',
        {...globals, 'enabled': true, 'count': 99, 'mode': 'always'}
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

  test('C8 first-slice public methods match goldens pinned at $c8SlicePreMigrationSha', () async {
    final adapter = RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    fireC8Slice(AnalyticsManager());
    await AnalyticsManager.flushPending(force: true);
    await AnalyticsManager.flushPending(force: true);
    final globals = <String, Object>{
      'app_platform': PlatformService.isIOS ? 'ios' : (PlatformService.isAndroid ? 'android' : 'unknown'),
      'app_version': '1.0.543',
      'app_build': '992',
    };
    expect(emissionPayloads(adapter.events), c8SliceGoldens(globals));
    expect(adapter.events.every((event) => !event.$2.containsKey('correlation_id')), isTrue);
    expect(AnalyticsManager.queuedEventCountForTesting, 0);
  });

  test('C8 type-extension emit matches goldens for bool, int, and closed enum', () async {
    final adapter = RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    fireC8TypeExtension(const TypedEvents());
    await AnalyticsManager.flushPending(force: true);
    await AnalyticsManager.flushPending(force: true);
    final globals = <String, Object>{
      'app_platform': PlatformService.isIOS ? 'ios' : (PlatformService.isAndroid ? 'android' : 'unknown'),
      'app_version': '1.0.543',
      'app_build': '992',
    };
    expect(emissionPayloads(adapter.events), c8TypeExtensionGoldens(globals));
    expect(adapter.events.every((event) => event.$2['count'] is int), isTrue);
    expect(adapter.events.every((event) => event.$2['mode'] is String), isTrue);
    expect(adapter.events.every((event) => !event.$2.containsKey('correlation_id')), isTrue);
    expect(AnalyticsManager.queuedEventCountForTesting, 0);
  });

  test('C8 type-extension constructors reject free values and cannot carry a mutated property bag', () {
    dynamic construct = TypeExtensionProbe.new;
    for (final value in <Object>[
      'synthetic@local.test',
      'synthetic transcript',
      {'content': 'synthetic memory'},
    ]) {
      expect(() => construct(enabled: true, count: 1, mode: value), throwsA(isA<TypeError>()));
      expect(() => construct(enabled: value, count: 1, mode: TypeExtensionProbeMode.off), throwsA(isA<TypeError>()));
      expect(() => construct(enabled: true, count: value, mode: TypeExtensionProbeMode.off), throwsA(isA<TypeError>()));
    }
    expect(() => construct(enabled: true, count: 1, mode: 17), throwsA(isA<TypeError>()));
    expect(() => construct(enabled: 17, count: 1, mode: TypeExtensionProbeMode.off), throwsA(isA<TypeError>()));
    expect(() => construct(enabled: true, count: true, mode: TypeExtensionProbeMode.off), throwsA(isA<TypeError>()));
    const event = TypeExtensionProbe(enabled: true, count: 99, mode: TypeExtensionProbeMode.headphonesOnly);
    expect(event.properties, {'enabled': true, 'count': 99, 'mode': 'headphones_only'});
    event.properties['transcript'] = 'synthetic private transcript';
    expect(event.properties, {'enabled': true, 'count': 99, 'mode': 'headphones_only'});
  });
}
