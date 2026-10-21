import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/recording_analytics.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PackageInfo.setMockInitialValues(
        appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.543', buildNumber: '992', buildSignature: '');
  });

  group('Device Disconnected Detailed registry shape', () {
    test('emits the registered wire name with snake_case property keys', () async {
      const event = DeviceDisconnectedDetailed(
        reason: DeviceDisconnectedDetailedReason.connectionTimeout,
        reasonCode: 8,
        appState: DeviceDisconnectedDetailedAppState.background,
      );
      expect(event.wireName, 'Device Disconnected Detailed');
      expect(event.properties, {
        'reason': 'connection_timeout',
        'reason_code': 8,
        'app_state': 'background',
      });
    });

    test('enum values carry the native reason vocabulary', () {
      const reason = DeviceDisconnectedDetailedReason.values;
      expect(reason.map((r) => r.wireName), [
        'clean_disconnect',
        'connection_timeout',
        'remote_device_terminated',
        'connection_failed_instant_passed',
        'paired_to_another_phone',
        'link_key_mismatch',
        'pairing_lost',
        'app_closed',
        'manual',
        'gatt_error',
        'unknown',
      ]);
      expect(DeviceDisconnectedDetailedAppState.values.map((s) => s.wireName),
          ['foreground', 'background', 'inactive', 'unknown']);
      expect(DiagnosticsSendFailedFailureStage.values.map((s) => s.wireName),
          ['build_bundle', 'dialog_cancelled', 'upload', 'ticket_parse']);
    });

    test('TypedEvents routes the event through the manager queue', () async {
      final analytics = RecordingAnalytics();
      AnalyticsManager.resetForTesting();
      AnalyticsManager.configure(analytics.adapter);
      await AnalyticsManager.init();
      const TypedEvents().emit(
        const DeviceDisconnectedDetailed(
          reason: DeviceDisconnectedDetailedReason.gattError,
          reasonCode: 25,
          appState: DeviceDisconnectedDetailedAppState.foreground,
        ),
      );
      await AnalyticsManager.flushPending(force: true);

      analytics.expectSingle('Device Disconnected Detailed', {
        'reason': 'gatt_error',
        'reason_code': 25,
        'app_state': 'foreground',
      });
      expect(analytics.names, isNot(contains('Device Disconnected')));
    });
  });

  group('native reason mapping', () {
    test('known native reasons map onto the closed enum', () {
      final mapped = {
        'clean_disconnect': DeviceDisconnectedDetailedReason.cleanDisconnect,
        'connection_timeout': DeviceDisconnectedDetailedReason.connectionTimeout,
        'remote_device_terminated': DeviceDisconnectedDetailedReason.remoteDeviceTerminated,
        'connection_failed_instant_passed': DeviceDisconnectedDetailedReason.connectionFailedInstantPassed,
        'paired_to_another_phone': DeviceDisconnectedDetailedReason.pairedToAnotherPhone,
        'link_key_mismatch': DeviceDisconnectedDetailedReason.linkKeyMismatch,
        'pairing_lost': DeviceDisconnectedDetailedReason.pairingLost,
        'app_closed': DeviceDisconnectedDetailedReason.appClosed,
        'manual': DeviceDisconnectedDetailedReason.manual,
      };
      mapped.forEach((native, expected) {
        expect(AnalyticsManager.disconnectReasonFromNative(native), expected, reason: native);
      });
    });

    test('gatt_error codes collapse and unmapped values degrade to unknown', () {
      expect(AnalyticsManager.disconnectReasonFromNative('gatt_error_25'), DeviceDisconnectedDetailedReason.gattError);
      expect(AnalyticsManager.disconnectReasonFromNative('gatt_status_133'), DeviceDisconnectedDetailedReason.unknown);
      expect(AnalyticsManager.disconnectReasonFromNative(''), DeviceDisconnectedDetailedReason.unknown);
      expect(AnalyticsManager.disconnectReasonFromNative(null), DeviceDisconnectedDetailedReason.unknown);
    });

    test('app state maps with unknown fallback', () {
      expect(
          AnalyticsManager.disconnectAppStateFromNative('foreground'), DeviceDisconnectedDetailedAppState.foreground);
      expect(
          AnalyticsManager.disconnectAppStateFromNative('background'), DeviceDisconnectedDetailedAppState.background);
      expect(AnalyticsManager.disconnectAppStateFromNative('inactive'), DeviceDisconnectedDetailedAppState.inactive);
      expect(AnalyticsManager.disconnectAppStateFromNative(''), DeviceDisconnectedDetailedAppState.unknown);
      expect(AnalyticsManager.disconnectAppStateFromNative(null), DeviceDisconnectedDetailedAppState.unknown);
    });
  });

  group('diagnostics support-send events', () {
    test('Diagnostics Sent carries sizes and counts only', () {
      const event = DiagnosticsSent(bundleBytes: 2048, disconnectCount: 7, schemaVersion: 2);
      expect(event.wireName, 'Diagnostics Sent');
      expect(event.properties, {'bundle_bytes': 2048, 'disconnect_count': 7, 'schema_version': 2});
    });

    test('Diagnostics Send Failed carries the stage and HTTP status when present', () {
      const event = DiagnosticsSendFailed(
        bundleBytes: 2048,
        disconnectCount: 7,
        schemaVersion: 2,
        failureStage: DiagnosticsSendFailedFailureStage.upload,
        statusCode: 503,
      );
      expect(event.wireName, 'Diagnostics Send Failed');
      expect(event.properties, {
        'bundle_bytes': 2048,
        'disconnect_count': 7,
        'schema_version': 2,
        'failure_stage': 'upload',
        'status_code': 503,
      });

      const early = DiagnosticsSendFailed(
        bundleBytes: 0,
        disconnectCount: 0,
        schemaVersion: 0,
        failureStage: DiagnosticsSendFailedFailureStage.buildBundle,
        statusCode: 0,
      );
      expect(early.properties, {
        'bundle_bytes': 0,
        'disconnect_count': 0,
        'schema_version': 0,
        'failure_stage': 'build_bundle',
        'status_code': 0,
      });
    });

    test('manager helpers forward to the typed events', () async {
      final analytics = RecordingAnalytics();
      AnalyticsManager.resetForTesting();
      AnalyticsManager.configure(analytics.adapter);
      await AnalyticsManager.init();
      final manager = AnalyticsManager();
      manager.diagnosticsSent(bundleBytes: 512, disconnectCount: 3, schemaVersion: 2);
      manager.diagnosticsSendFailed(
        failureStage: DiagnosticsSendFailedFailureStage.dialogCancelled,
        bundleBytes: 512,
        disconnectCount: 3,
        schemaVersion: 2,
      );
      await AnalyticsManager.flushPending(force: true);

      analytics.expectSingle('Diagnostics Sent', {'bundle_bytes': 512, 'disconnect_count': 3, 'schema_version': 2});
      analytics.expectSingle('Diagnostics Send Failed', {'failure_stage': 'dialog_cancelled', 'status_code': 0});
    });
  });
}
