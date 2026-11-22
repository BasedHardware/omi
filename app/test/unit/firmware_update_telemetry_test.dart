import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/firmware_update_telemetry.dart';

void main() {
  FirmwareUpdateTelemetry start(_Analytics analytics, {String protocol = 'mcumgr'}) => FirmwareUpdateTelemetry.start(
        device: BtDevice(
            id: 'private-id',
            name: 'private-name',
            type: DeviceType.omi,
            rssi: -45,
            serialNumber: 'private-serial',
            firmwareRevision: '3.1.0'),
        protocol: protocol,
        analytics: analytics,
      );

  test('all stages share one attempt, close once, and carry only closed properties', () {
    final analytics = _Analytics();
    final attempt = start(analytics);
    attempt.uploadFinished();
    attempt.uploadFinished();
    attempt.installRequested();
    attempt.installRequested();
    attempt.completed(observedVersion: ' 3.1.1 ');
    attempt.completed(observedVersion: '3.2.0');
    attempt.failed(failureClass: 'no_reconnect');
    attempt.uploadFinished();
    expect(analytics.events.map((event) => event.name), [
      'Firmware Update Started',
      'Firmware Update Upload Finished',
      'Firmware Update Install Requested',
      'Firmware Update Completed',
    ]);
    expect(analytics.events.map((event) => event.props['firmware_update_attempt_id']).toSet(), hasLength(1));
    for (final event in analytics.events) {
      expect(
          event.props.keys.toSet().difference({
            'firmware_update_attempt_id',
            'protocol',
            'from_version',
            'to_version',
            'verified',
            'failure_class',
          }),
          isEmpty);
      expect(event.props['protocol'], 'mcumgr');
      expect(event.props['from_version'], '3.1.0');
      expect(event.props.values, isNot(contains('private-id')));
      expect(event.props.values, isNot(contains('private-name')));
      expect(event.props.values, isNot(contains('private-serial')));
    }
    expect(analytics.events.last.props['to_version'], '3.1.1');
    expect(analytics.events.last.props['verified'], isTrue);
    expect(analytics.events.first.props, isNot(contains('verified')));
  });

  test('an unreadable observed revision cannot claim verified completion', () {
    final analytics = _Analytics();
    start(analytics).completed(observedVersion: 'Unknown');
    expect(analytics.events.last.name, 'Firmware Update Failed');
    expect(analytics.events.last.props['failure_class'], 'no_reconnect');
  });

  for (final failure in [
    'disconnected',
    'app_backgrounded',
    'low_battery',
    'upload_error',
    'mark_error',
    'not_installed',
    'no_reconnect',
    'firmware_file_missing',
    'native_dfu_error',
    'unknown',
    'raw exception text'
  ]) {
    test('failure $failure uses allowlist and closes once', () {
      final analytics = _Analytics();
      final attempt = start(analytics, protocol: 'nordic_dfu');
      attempt.failed(failureClass: failure);
      attempt.installRequested();
      attempt.completed(observedVersion: '3.2.0');
      expect(analytics.events, hasLength(2));
      expect(analytics.events.last.name, 'Firmware Update Failed');
      expect(analytics.events.last.props['failure_class'], failure == 'raw exception text' ? 'unknown' : failure);
      expect(analytics.events.last.props, isNot(contains('to_version')));
      expect(analytics.events.last.props, isNot(contains('verified')));
    });
  }
}

class _Analytics implements AnalyticsManager {
  final events = <({String name, Map<String, dynamic> props})>[];
  @override
  void track(String eventName, {Map<String, dynamic>? properties}) => events.add((name: eventName, props: properties!));
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
