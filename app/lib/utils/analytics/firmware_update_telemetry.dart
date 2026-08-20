import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:uuid/uuid.dart';

class FirmwareUpdateTelemetry {
  FirmwareUpdateTelemetry.start({required BtDevice device, required this.protocol, AnalyticsManager? analytics})
      : _analytics = analytics ?? AnalyticsManager(),
        _attemptId = const Uuid().v4(),
        _fromVersion = device.firmwareRevision {
    _analytics.track('Firmware Update Started', properties: _properties());
  }

  final AnalyticsManager _analytics;
  final String _attemptId;
  final String _fromVersion;
  final String protocol;
  bool _terminal = false;

  void completed({String? toVersion}) => _finish('Firmware Update Completed', toVersion: toVersion);
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
        if (toVersion != null) 'to_version': toVersion,
        if (failureClass != null) 'failure_class': _normalizeFailureClass(failureClass),
      };

  static String _normalizeFailureClass(String failureClass) => switch (failureClass) {
        'firmware_file_missing' || 'native_dfu_error' || 'unknown' => failureClass,
        _ => 'unknown',
      };

  static String _normalizeFirmwareVersion(String version) {
    final normalized = version.trim();
    return normalized.isEmpty || normalized.toLowerCase() == 'unknown' ? 'unknown' : normalized;
  }
}
