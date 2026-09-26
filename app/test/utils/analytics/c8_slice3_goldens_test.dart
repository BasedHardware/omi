import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../spine/c7_registry_test.dart' show RecordingAdapter, emissionPayloads;

/// Adapter payloads captured from leftover empty phone/device/speech-profile
/// public methods at `82776e2e7ab08af3c24731bd7d2d13128a1da011`, the C8 slice 2
/// tip, before those methods called [TypedEvents.emit].
const c8Slice3PreMigrationSha = '82776e2e7ab08af3c24731bd7d2d13128a1da011';

void fireC8Slice3(AnalyticsManager analytics) {
  analytics.phoneCallPageOpened();
  analytics.phoneCallVerificationStarted();
  analytics.phoneCallVerificationCompleted();
  analytics.phoneCallConnected();
  analytics.phoneCallDialpadOpened();
  analytics.phoneCallUpsellUpgradeTapped();
  analytics.phoneCallUpsellDismissed();
  analytics.deviceDisconnected();
  analytics.speechProfileCapturePageClicked();
  analytics.speechProfileSkipped();
  analytics.speechProfileUploadSucceeded();
  analytics.speechProfileEmbeddingStored();
  analytics.speechProfileContinued();
  analytics.useWithoutDeviceOnboardingWelcome();
  analytics.useWithoutDeviceOnboardingFindDevices();
}

List<List<Object>> c8Slice3Goldens(Map<String, Object> globals) => [
      [
        'Phone Call Page Opened',
        {...globals}
      ],
      [
        'Phone Call Verification Started',
        {...globals}
      ],
      [
        'Phone Call Verification Completed',
        {...globals}
      ],
      [
        'Phone Call Connected',
        {...globals}
      ],
      [
        'Phone Call Dialpad Opened',
        {...globals}
      ],
      [
        'Phone Call Upsell Upgrade Tapped',
        {...globals}
      ],
      [
        'Phone Call Upsell Dismissed',
        {...globals}
      ],
      [
        'Device Disconnected',
        {...globals}
      ],
      [
        'Speech Profile Capture Page Clicked',
        {...globals}
      ],
      [
        'Speech Profile Skipped',
        {...globals}
      ],
      [
        'Speech Profile Upload Succeeded',
        {...globals}
      ],
      [
        'Speech Profile Embedding Stored',
        {...globals}
      ],
      [
        'Onboarding Step Speech Profile Continued',
        {...globals}
      ],
      [
        'Use Without Device Onboarding Welcome',
        {...globals}
      ],
      [
        'Use Without Device Onboarding Find Devices',
        {...globals}
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

  test('C8 slice 3 public methods match goldens pinned at $c8Slice3PreMigrationSha', () async {
    final adapter = RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    fireC8Slice3(AnalyticsManager());
    await AnalyticsManager.flushPending(force: true);
    await AnalyticsManager.flushPending(force: true);
    final globals = <String, Object>{
      'app_platform': PlatformService.isIOS ? 'ios' : (PlatformService.isAndroid ? 'android' : 'unknown'),
      'app_version': '1.0.543',
      'app_build': '992',
    };
    expect(emissionPayloads(adapter.events), c8Slice3Goldens(globals));
    expect(adapter.events.every((event) => !event.$2.containsKey('correlation_id')), isTrue);
    expect(adapter.events.every((event) => event.$2.keys.toSet().difference(globals.keys.toSet()).isEmpty), isTrue);
    expect(AnalyticsManager.queuedEventCountForTesting, 0);
  });
}
