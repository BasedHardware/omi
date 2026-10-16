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
  ListenClientState._()
      : super(ListenClientStateSnapshot(foreground: _initiallyForeground(), transcriptVisible: false)) {
    if (_reportingEnabled) {
      _heartbeat = Timer.periodic(const Duration(seconds: 30), (_) => _reportSurface());
      _reportSurface();
    }
  }

  static const _reportingEnabled = bool.fromEnvironment('DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED');
  final String _surfaceSession = const Uuid().v4();
  Timer? _heartbeat;
  bool _reportInFlight = false;

  Future<void> _reportSurface() async {
    if (!_reportingEnabled || _reportInFlight) return;
    _reportInFlight = true;
    try {
      await makeApiCall(
        url: '${Env.apiBaseUrl}v1/users/client-state',
        headers: {},
        method: 'POST',
        body: jsonEncode({...value.toJson(), 'session_id': _surfaceSession}..remove('type')),
        timeout: const Duration(seconds: 5),
        retries: 0,
        signOutOn401: false,
      );
    } finally {
      _reportInFlight = false;
    }
  }

  @override
  void dispose() {
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
