import 'dart:async';
import 'dart:convert';
import 'package:flutter/widgets.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:uuid/uuid.dart';

/// What the user can see of a live capture, reported to `/v4/listen` as
/// `{"type": "client_state", "foreground": bool, "transcript_visible": bool}`.
///
/// The backend uses it to measure how much live time anyone actually watches in
/// real time (routers/listen/realtime_demand.py). It never changes routing here.
@immutable
class ListenClientStateSnapshot {
  const ListenClientStateSnapshot({required this.foreground, required this.transcriptVisible});

  final bool foreground;

  /// The live transcript is on screen: the capture page is open *and* the app is in front.
  final bool transcriptVisible;

  Map<String, Object> toJson() => {
        'type': 'client_state',
        'foreground': foreground,
        if (ListenClientState._reportingEnabled) 'surface_open': foreground,
        'transcript_visible': transcriptVisible,
      };

  @override
  bool operator ==(Object other) =>
      other is ListenClientStateSnapshot &&
      other.foreground == foreground &&
      other.transcriptVisible == transcriptVisible;

  @override
  int get hashCode => Object.hash(foreground, transcriptVisible);
}

class ListenClientState extends ValueNotifier<ListenClientStateSnapshot> {
  ListenClientState._() : this._create(reportingEnabled: _reportingEnabled);

  @visibleForTesting
  ListenClientState.forTest({required Future<bool> Function(Map<String, Object>) surfaceTransport})
      : this._create(reportingEnabled: true, surfaceTransport: surfaceTransport, heartbeatEnabled: false);

  ListenClientState._create({
    required bool reportingEnabled,
    Future<bool> Function(Map<String, Object>)? surfaceTransport,
    bool heartbeatEnabled = true,
  })  : _surfaceReportingEnabled = reportingEnabled,
        _surfaceTransport = surfaceTransport ?? _postSurface,
        super(ListenClientStateSnapshot(foreground: _initiallyForeground(), transcriptVisible: false)) {
    if (_surfaceReportingEnabled && heartbeatEnabled) {
      _heartbeat = Timer.periodic(const Duration(seconds: 30), (_) => _reportSurface(heartbeat: true));
      unawaited(_reportSurface());
    }
  }

  static const _reportingEnabled = bool.fromEnvironment('DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED');
  final String _surfaceSession = const Uuid().v4();
  Timer? _heartbeat;
  final bool _surfaceReportingEnabled;
  final Future<bool> Function(Map<String, Object>) _surfaceTransport;
  Future<void>? _reportTask;
  bool _reportPending = false;
  bool _lastReportedOpen = false;
  bool _disposed = false;

  Future<void> _reportSurface({bool heartbeat = false}) {
    if (!_surfaceReportingEnabled || _disposed) return Future.value();
    if (heartbeat && !value.foreground && !_reportPending && !_lastReportedOpen) return Future.value();
    _reportPending = true;
    return _reportTask ??= _drainSurfaceReports().whenComplete(() => _reportTask = null);
  }

  Future<void> _drainSurfaceReports() async {
    while (_reportPending && !_disposed) {
      _reportPending = false;
      final sent = value;
      try {
        final delivered = await _surfaceTransport({
          'session_id': _surfaceSession,
          'surface_open': sent.foreground,
          'foreground': sent.foreground,
          'transcript_visible': sent.transcriptVisible,
        });
        if (!delivered) {
          if (_reportPending) continue;
          _reportPending = true;
          break;
        }
        _lastReportedOpen = sent.foreground;
      } catch (_) {
        if (_reportPending) continue;
        // Retain failed closes for the next heartbeat, without a retry loop.
        _reportPending = true;
        break;
      }
    }
  }

  static Future<bool> _postSurface(Map<String, Object> payload) async {
    final response = await makeApiCall(
      url: '${Env.apiBaseUrl}v1/users/client-state',
      headers: {},
      method: 'POST',
      body: jsonEncode(payload),
      timeout: const Duration(seconds: 5),
      retries: 0,
      signOutOn401: false,
    );
    return response != null && response.statusCode >= 200 && response.statusCode < 300;
  }

  @visibleForTesting
  Future<void> reportSurfaceForTest({bool heartbeat = false}) => _reportSurface(heartbeat: heartbeat);

  @visibleForTesting
  Future<void> waitForSurfaceReportsForTest() => _reportTask ?? Future.value();

  @override
  void dispose() {
    _disposed = true;
    _heartbeat?.cancel();
    super.dispose();
  }

  static final ListenClientState instance = ListenClientState._();

  static void startSurfaceReporting() {
    if (_reportingEnabled) unawaited(instance._reportSurface());
  }

  bool _foreground = _initiallyForeground();
  int _capturePagesOpen = 0;

  static bool _initiallyForeground() {
    final state = WidgetsBinding.instance.lifecycleState;
    return state == null || state == AppLifecycleState.resumed || state == AppLifecycleState.inactive;
  }

  /// `inactive` (e.g. the notification shade) still counts as in front.
  void onLifecycle(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed || state == AppLifecycleState.inactive) {
      _foreground = true;
    } else {
      _foreground = false;
    }
    _publish();
  }

  void capturePageOpened() {
    _capturePagesOpen++;
    _publish();
  }

  void capturePageClosed() {
    if (_capturePagesOpen > 0) _capturePagesOpen--;
    _publish();
  }

  void _publish() {
    value = ListenClientStateSnapshot(foreground: _foreground, transcriptVisible: _foreground && _capturePagesOpen > 0);
    unawaited(_reportSurface());
  }

  @visibleForTesting
  void resetForTest({bool foreground = true}) {
    _foreground = foreground;
    _capturePagesOpen = 0;
    _publish();
  }
}
