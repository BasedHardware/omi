import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:uuid/uuid.dart';

enum AppSessionStartKind { coldStart, foreground }

/// Owns the mobile app-session boundary.
///
/// A cold launch starts one session. A later session is started only after the
/// app has first entered the background, so repeated `resumed` callbacks do
/// not inflate the retention denominator.
class AppSessionTelemetry {
  AppSessionTelemetry({
    AnalyticsManager? analytics,
    String Function()? createSessionId,
  })  : _analytics = analytics ?? AnalyticsManager(),
        _createSessionId = createSessionId ?? const Uuid().v4;

  final AnalyticsManager _analytics;
  final String Function() _createSessionId;
  bool _isBackgrounded = false;
  bool _coldStartRecorded = false;

  void recordColdStart() {
    if (_coldStartRecorded) return;
    _coldStartRecorded = true;
    _emit(AppSessionStartKind.coldStart);
  }

  void recordBackgrounded() {
    _isBackgrounded = true;
  }

  void recordResumed() {
    if (!_isBackgrounded) return;
    _isBackgrounded = false;
    _emit(AppSessionStartKind.foreground);
  }

  void _emit(AppSessionStartKind kind) {
    _analytics.track(
      'App Session Started',
      properties: {
        'app_session_id': _createSessionId(),
        'start_kind': kind.name,
      },
    );
  }
}
