import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart' show AnalyticsManager;
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/spine/contract.dart';
import 'c7_registry_test.dart' show RecordingAdapter, emissionPayloads;

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

  for (final queued in [false, true]) {
    contractTest('C7 registered emission payload excludes user content (pre-init queue: $queued)', () async {
      final adapter = RecordingAdapter();
      AnalyticsManager.configure(adapter);
      if (!queued) await AnalyticsManager.init();
      final events = <RegisteredEvent>[
        const OnboardingCompleted(),
        const PhoneMicRecordingStarted(),
        const PhoneMicRecordingStopped(),
        const TranscribeLaterToggled(enabled: false),
        const TranscribeLaterToggled(enabled: true),
      ];
      for (final event in events) {
        // A caller retaining/mutating a property map must not affect a later emission.
        event.properties.addAll({
          'transcript': 'synthetic private transcript',
          'memory': 'synthetic private memory',
          'email': 'synthetic@local.test',
          'device_address': '00:11:22:33:44:55',
        });
        const TypedEvents().emit(event);
      }
      if (queued) {
        expect(adapter.events, isEmpty);
        expect(AnalyticsManager.queuedEventCountForTesting, events.length);
        await AnalyticsManager.init();
      }
      await AnalyticsManager.flushPending(force: true);
      await AnalyticsManager.flushPending(force: true);
      final globals = <String, Object>{
        'app_platform': PlatformService.isIOS ? 'ios' : (PlatformService.isAndroid ? 'android' : 'unknown'),
        'app_version': '1.0.543',
        'app_build': '992',
      };
      // Literal allowlist at the real adapter boundary, independent of legacy emission
      // and generated properties; dropping all events or leaking extra fields fails.
      expect(emissionPayloads(adapter.events), [
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
      ]);
      expect(AnalyticsManager.queuedEventCountForTesting, 0);
    });
  }
}
