import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:uuid/uuid.dart';

class FirmwareUpdateTelemetry {
  FirmwareUpdateTelemetry.start({required BtDevice device, required String protocol, AnalyticsManager? analytics})
      : protocol = protocol == 'mcumgr' || protocol == 'nordic_dfu' ? protocol : 'unknown',
        _analytics = analytics ?? AnalyticsManager(),
        _attemptId = const Uuid().v4(),
        _fromVersion = device.firmwareRevision {
    _analytics.track('Firmware Update Started', properties: _properties());
  }

  final AnalyticsManager _analytics;
  final String _attemptId;
  final String _fromVersion;
  final String protocol;
  bool _terminal = false;
  final Set<String> _stages = {};

  String get fromVersion => _fromVersion;

  void uploadFinished() => _stage('Firmware Update Upload Finished');
  void installRequested() => _stage('Firmware Update Install Requested');

  void _stage(String event) {
    if (_terminal || !_stages.add(event)) return;
    _analytics.track(event, properties: _properties());
  }

  void completed({required String observedVersion}) {
    final observed = _normalizeFirmwareVersion(observedVersion);
    if (observed == 'unknown') {
      failed(failureClass: 'no_reconnect');
      return;
    }
    _finish('Firmware Update Completed', toVersion: observed);
  }

  void failed({required String failureClass}) => _finish('Firmware Update Failed', failureClass: failureClass);

  void _finish(String event, {String? toVersion, String? failureClass}) {
    if (_terminal) return;
    _terminal = true;
    _analytics.track(
      event,
      properties: _properties(toVersion: toVersion, failureClass: failureClass),
    );
  }

  Map<String, Object> _properties({String? toVersion, String? failureClass}) => {
        'firmware_update_attempt_id': _attemptId,
        'protocol': protocol,
        'from_version': _normalizeFirmwareVersion(_fromVersion),
        if (toVersion != null) ...{'to_version': toVersion, 'verified': true},
        if (failureClass != null) 'failure_class': _normalizeFailureClass(failureClass),
      };

  static String _normalizeFailureClass(String failureClass) => switch (failureClass) {
        'disconnected' ||
        'app_backgrounded' ||
        'low_battery' ||
        'upload_error' ||
        'mark_error' ||
        'not_installed' ||
        'no_reconnect' ||
        'firmware_file_missing' ||
        'native_dfu_error' ||
        'unknown' =>
          failureClass,
        _ => 'unknown',
      };

  static String _normalizeFirmwareVersion(String version) {
    final normalized = version.trim();
    return normalized.isEmpty || normalized.toLowerCase() == 'unknown' ? 'unknown' : normalized;
  }
}
