import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/empty_recording_notice.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '1.0.0',
      buildNumber: '1',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
  });

  tearDown(AnalyticsManager.resetForTesting);

  test('funnel events emit the closed property sets', () async {
    final adapter = _RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    final analytics = AnalyticsManager();

    analytics.onboardingWelcomeShown();
    analytics.onboardingGetStartedTapped();
    analytics.signInStarted('google');
    analytics.signInStarted('local_dev');
    analytics.signInFailed('apple', cancelled: true);
    analytics.signInFailed('email', error: StateError('ignored'));
    analytics.onboardingPermissionResult(
      permission: OnboardingPermissionResultPermission.backgroundActivity,
      granted: false,
      permanentlyDenied: false,
      servicesDisabled: false,
    );
    analytics.devicePairingBlocked(
      reason: DevicePairingBlockedReason.locationPermissionMissing,
      androidSdk: 30,
      iosVersion: 0,
    );
    analytics.devicePairingBlocked(
      reason: DevicePairingBlockedReason.bluetoothOff,
      androidSdk: -1,
      iosVersion: -2,
    );
    analytics.deviceScanEmpty(afterSeconds: 10);
    analytics.deviceConnectFailed(DeviceConnectFailedErrorClass.initializationFailed);
    analytics.recordingProducedNoConversation(
      source: RecordingSurface.phone,
      durationSeconds: 12,
      transcriptObserved: false,
      reason: EmptyRecordingReason.emptyDeleted,
    );
    analytics.recordingProducedNoConversation(
      source: RecordingSurface.watch,
      durationSeconds: -4,
      transcriptObserved: true,
      reason: EmptyRecordingReason.discarded,
    );
    analytics.recordingProducedNoConversation(
      source: RecordingSurface.omi,
      durationSeconds: 40,
      transcriptObserved: false,
      reason: EmptyRecordingReason.nullResult,
    );
    analytics.onboardingPermissionResult(
      permission: OnboardingPermissionResultPermission.location,
      granted: false,
      permanentlyDenied: false,
      servicesDisabled: true,
    );
    analytics.devicePairingBlocked(
      reason: DevicePairingBlockedReason.noAdapter,
      androidSdk: 34,
      iosVersion: 0,
    );
    analytics.devicePairingBlocked(
      reason: DevicePairingBlockedReason.scannerUnavailable,
      androidSdk: 34,
      iosVersion: 0,
    );
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.names, [
      'Onboarding Welcome Shown',
      'Onboarding Get Started Tapped',
      'Sign In Started',
      'Sign In Failed',
      'Onboarding Permission Result',
      'Device Pairing Blocked',
      'Device Pairing Blocked',
      'Device Scan Empty',
      'Device Connect Failed',
      'Recording Produced No Conversation',
      'Recording Produced No Conversation',
      'Recording Produced No Conversation',
      'Onboarding Permission Result',
      'Device Pairing Blocked',
      'Device Pairing Blocked',
    ]);
    expect(adapter.propertiesAt(2), containsPair('provider', 'google'));
    expect(adapter.propertiesAt(3), containsPair('provider', 'apple'));
    expect(adapter.propertiesAt(3), containsPair('error_class', 'cancelled'));
    expect(adapter.propertiesAt(4), containsPair('permission', 'background_activity'));
    expect(adapter.propertiesAt(4), containsPair('granted', false));
    expect(adapter.propertiesAt(4), containsPair('permanently_denied', false));
    expect(adapter.propertiesAt(4), containsPair('services_disabled', false));
    expect(adapter.propertiesAt(5), containsPair('reason', 'location_permission_missing'));
    expect(adapter.propertiesAt(5), containsPair('android_sdk', 30));
    expect(adapter.propertiesAt(5), containsPair('ios_version', 0));
    expect(adapter.propertiesAt(6)['android_sdk'], 0);
    expect(adapter.propertiesAt(6)['ios_version'], 0);
    expect(adapter.propertiesAt(7), containsPair('after_seconds', 10));
    expect(adapter.propertiesAt(8), containsPair('error_class', 'initialization_failed'));
    expect(adapter.propertiesAt(9), containsPair('source', 'phone'));
    expect(adapter.propertiesAt(9), containsPair('duration_s', 12));
    expect(adapter.propertiesAt(9), containsPair('transcript_observed', false));
    expect(adapter.propertiesAt(9), containsPair('reason', 'empty_deleted'));
    expect(adapter.propertiesAt(10)['source'], 'watch');
    expect(adapter.propertiesAt(10)['duration_s'], 0);
    expect(adapter.propertiesAt(10)['reason'], 'discarded');
    expect(adapter.propertiesAt(11)['source'], 'omi');
    expect(adapter.propertiesAt(11)['reason'], 'null_result');
    expect(adapter.propertiesAt(12), containsPair('services_disabled', true));
    expect(adapter.propertiesAt(12), containsPair('permanently_denied', false));
    expect(adapter.propertiesAt(13), containsPair('reason', 'no_adapter'));
    expect(adapter.propertiesAt(14), containsPair('reason', 'scanner_unavailable'));
  });
}

class _RecordingAdapter implements AnalyticsAdapter {
  final events = <(String, Map<String, Object>)>[];
  bool initialized = false;

  List<String> get names => events.map((event) => event.$1).toList();

  Map<String, Object> propertiesAt(int index) => events[index].$2;

  @override
  bool get isInitialized => initialized;

  @override
  Future<void> init() async => initialized = true;

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    events.add((eventName, Map<String, Object>.of(properties ?? const {})));
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}
